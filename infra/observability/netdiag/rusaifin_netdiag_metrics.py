#!/usr/bin/env python3
"""Export a short-window summary of the rusaifin nginx transport log.

The exporter intentionally emits aggregate metrics only. Client IPs, user agents
and request IDs remain in the root-readable diagnostic log and never become
Prometheus labels.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile


KNOWN_SERVERS = {
    "fintech.rusaifin.ru",
    "server.rusaifin.ru",
    "sso.rusaifin.ru",
}

BOOTSTRAP_EVENT_PREFIX = "/__netdiag/bootstrap/"
KNOWN_BOOTSTRAP_EVENTS = {"resource-error", "timeout"}


def resource_class(uri: str, content_type: str) -> str:
    if uri.startswith(BOOTSTRAP_EVENT_PREFIX):
        return "bootstrap_event"
    if uri.startswith("/_nuxt/") and uri.endswith((".js", ".mjs")):
        return "nuxt_js"
    if uri.startswith("/_nuxt/"):
        return "nuxt_other"
    if uri.startswith("/api/"):
        return "api"
    if "text/html" in content_type or "." not in uri.rsplit("/", 1)[-1]:
        return "navigation"
    return "other"


def prometheus_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def render_metrics(records: list[dict], now: float, window_seconds: int, parse_errors: int) -> str:
    request_counts: Counter[tuple[str, str, str]] = Counter()
    incomplete_counts: Counter[tuple[str, str, str]] = Counter()
    client_abort_counts: Counter[tuple[str, str, str]] = Counter()
    # Emit stable zero-valued series as well. An empty Prometheus result used to
    # be ambiguous: it could mean either "no client failures" or "the beacon is
    # not deployed". Deployment presence is checked separately by blackbox.
    bootstrap_event_counts: Counter[tuple[str, str]] = Counter(
        {
            ("fintech.rusaifin.ru", event): 0
            for event in KNOWN_BOOTSTRAP_EVENTS
        }
    )
    last_incomplete: dict[tuple[str, str, str], float] = {}

    for record in records:
        try:
            timestamp = float(record["msec"])
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp < now - window_seconds or timestamp > now + 30:
            continue

        server = str(record.get("server_name", "unknown"))
        if server not in KNOWN_SERVERS:
            continue
        protocol = str(record.get("protocol", "unknown"))
        completion = "ok" if record.get("request_completion") == "OK" else "incomplete"
        request_counts[(server, protocol, completion)] += 1

        try:
            status = int(record.get("status", 0))
        except (TypeError, ValueError):
            status = 0
        if status == 200 and completion == "incomplete":
            kind = resource_class(str(record.get("uri", "")), str(record.get("content_type", "")))
            key = (server, protocol, kind)
            incomplete_counts[key] += 1
            last_incomplete[key] = max(last_incomplete.get(key, 0), timestamp)
        if status == 499:
            kind = resource_class(str(record.get("uri", "")), str(record.get("content_type", "")))
            client_abort_counts[(server, protocol, kind)] += 1
        uri = str(record.get("uri", ""))
        event = uri.removeprefix(BOOTSTRAP_EVENT_PREFIX)
        user_agent = str(record.get("user_agent", ""))
        is_ios_webkit = "AppleWebKit" in user_agent and any(
            device in user_agent for device in ("iPhone", "iPad", "iPod")
        )
        if (
            uri.startswith(BOOTSTRAP_EVENT_PREFIX)
            and event in KNOWN_BOOTSTRAP_EVENTS
            and str(record.get("method", "")) == "POST"
            and status == 204
            and is_ios_webkit
        ):
            bootstrap_event_counts[(server, event)] += 1

    lines = [
        "# HELP rusaifin_netdiag_requests_window Requests observed in the rolling diagnostic window.",
        "# TYPE rusaifin_netdiag_requests_window gauge",
    ]
    for (server, protocol, completion), value in sorted(request_counts.items()):
        labels = (
            f'server="{prometheus_escape(server)}",'
            f'protocol="{prometheus_escape(protocol)}",'
            f'completion="{completion}"'
        )
        lines.append(f"rusaifin_netdiag_requests_window{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP rusaifin_netdiag_incomplete_responses_window Incomplete HTTP 200 responses in the rolling diagnostic window.",
            "# TYPE rusaifin_netdiag_incomplete_responses_window gauge",
        ]
    )
    for (server, protocol, kind), value in sorted(incomplete_counts.items()):
        labels = (
            f'server="{prometheus_escape(server)}",'
            f'protocol="{prometheus_escape(protocol)}",'
            f'resource_class="{kind}"'
        )
        lines.append(f"rusaifin_netdiag_incomplete_responses_window{{{labels}}} {value}")
        lines.append(
            "rusaifin_netdiag_last_incomplete_timestamp_seconds"
            f"{{{labels}}} {last_incomplete[(server, protocol, kind)]:.3f}"
        )

    lines.extend(
        [
            "# HELP rusaifin_netdiag_client_aborts_window Requests logged as nginx 499 in the rolling diagnostic window.",
            "# TYPE rusaifin_netdiag_client_aborts_window gauge",
        ]
    )
    for (server, protocol, kind), value in sorted(client_abort_counts.items()):
        labels = (
            f'server="{prometheus_escape(server)}",'
            f'protocol="{prometheus_escape(protocol)}",'
            f'resource_class="{kind}"'
        )
        lines.append(f"rusaifin_netdiag_client_aborts_window{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP rusaifin_netdiag_bootstrap_events_window Pre-Nuxt iOS bootstrap failure signals in the rolling diagnostic window.",
            "# TYPE rusaifin_netdiag_bootstrap_events_window gauge",
        ]
    )
    for (server, event), value in sorted(bootstrap_event_counts.items()):
        labels = (
            f'server="{prometheus_escape(server)}",'
            f'event="{event}"'
        )
        lines.append(f"rusaifin_netdiag_bootstrap_events_window{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP rusaifin_netdiag_window_seconds Size of the rolling diagnostic window.",
            "# TYPE rusaifin_netdiag_window_seconds gauge",
            f"rusaifin_netdiag_window_seconds {window_seconds}",
            "# HELP rusaifin_netdiag_parse_errors_window Malformed JSON lines found in the inspected log tail.",
            "# TYPE rusaifin_netdiag_parse_errors_window gauge",
            f"rusaifin_netdiag_parse_errors_window {parse_errors}",
            "# HELP rusaifin_netdiag_exporter_last_run_timestamp_seconds Last successful exporter run.",
            "# TYPE rusaifin_netdiag_exporter_last_run_timestamp_seconds gauge",
            f"rusaifin_netdiag_exporter_last_run_timestamp_seconds {now:.3f}",
        ]
    )
    return "\n".join(lines) + "\n"


def read_tail(path: Path, max_bytes: int) -> tuple[list[dict], int]:
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        raw_lines = handle.readlines()

    records: list[dict] = []
    parse_errors = 0
    for raw_line in raw_lines:
        try:
            records.append(json.loads(raw_line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            parse_errors += 1
    return records, parse_errors


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(content)
        temp_name = handle.name
    os.chmod(temp_name, 0o644)
    os.replace(temp_name, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=Path("/var/log/rusaifin-netdiag/access.jsonl"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/var/lib/node_exporter/textfile/rusaifin_netdiag.prom"),
    )
    parser.add_argument("--window-seconds", type=int, default=300)
    parser.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--now", type=float, default=None)
    args = parser.parse_args()

    now = args.now if args.now is not None else time.time()
    records, parse_errors = read_tail(args.log, args.max_bytes)
    atomic_write(args.output, render_metrics(records, now, args.window_seconds, parse_errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
