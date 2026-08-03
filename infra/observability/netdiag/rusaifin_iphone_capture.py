#!/usr/bin/env python3
"""Capture a bounded TCP-header sample for rusaifin iPhone navigations.

The nginx line for a completed HTML navigation is written before the browser
starts most Nuxt asset requests. That lets us start a client-IP-scoped capture
without recording the other tenants served by the same nginx/IP.
"""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile


LOG_PATH = Path("/var/log/rusaifin-netdiag/access.jsonl")
CAPTURE_DIR = Path("/var/log/rusaifin-netdiag/pcap")
STATE_PATH = Path("/var/lib/rusaifin-netdiag-capture/state.json")
MAX_CAPTURES = 50
CAPTURE_SECONDS = 90
COOLDOWN_SECONDS = 300


def eligible_navigation(record: dict) -> bool:
    if record.get("server_name") != "fintech.rusaifin.ru":
        return False
    if record.get("method") != "GET" or int(record.get("status", 0)) != 200:
        return False
    if "text/html" not in str(record.get("content_type", "")):
        return False
    user_agent = str(record.get("user_agent", ""))
    if "AppleWebKit" not in user_agent or not any(device in user_agent for device in ("iPhone", "iPad")):
        return False
    try:
        ipaddress.ip_address(str(record["remote_addr"]))
    except (KeyError, ValueError):
        return False
    return True


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("captures_started", 0)
    state.setdefault("last_capture_by_ip", {})
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=STATE_PATH.parent, prefix=".state.", delete=False) as handle:
        json.dump(state, handle, separators=(",", ":"))
        temp_name = handle.name
    os.chmod(temp_name, 0o600)
    os.replace(temp_name, STATE_PATH)


def start_capture(client_ip: str, request_id: str) -> subprocess.Popen:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_ip = client_ip.replace(":", "_")
    safe_request_id = "".join(c for c in request_id if c.isalnum())[:32] or "unknown"
    output = CAPTURE_DIR / f"{stamp}-{safe_ip}-{safe_request_id}.pcap"
    command = [
        "/usr/bin/timeout",
        "--signal=INT",
        "--kill-after=5s",
        f"{CAPTURE_SECONDS}s",
        "/usr/bin/tcpdump",
        "-i",
        "ens3",
        "-nn",
        "-s",
        "96",
        "-B",
        "4096",
        "-U",
        "-Z",
        "tcpdump",
        "-w",
        str(output),
        "host",
        client_ip,
        "and",
        "tcp",
        "port",
        "443",
    ]
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def follow_log() -> int:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    active: list[subprocess.Popen] = []
    handle = None
    inode = None

    while state["captures_started"] < MAX_CAPTURES:
        active = [process for process in active if process.poll() is None]
        try:
            stat = LOG_PATH.stat()
        except FileNotFoundError:
            time.sleep(0.2)
            continue

        if handle is None or inode != stat.st_ino:
            if handle is not None:
                handle.close()
            handle = LOG_PATH.open()
            handle.seek(0, os.SEEK_END)
            inode = stat.st_ino

        line = handle.readline()
        if not line:
            time.sleep(0.05)
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not eligible_navigation(record):
            continue

        client_ip = str(record["remote_addr"])
        now = time.time()
        last_capture = float(state["last_capture_by_ip"].get(client_ip, 0))
        if now - last_capture < COOLDOWN_SECONDS or len(active) >= 4:
            continue

        active.append(start_capture(client_ip, str(record.get("request_id", ""))))
        state["captures_started"] += 1
        state["last_capture_by_ip"][client_ip] = now
        save_state(state)

    return 0


if __name__ == "__main__":
    raise SystemExit(follow_log())
