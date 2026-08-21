import os
import sqlite3
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: snapshot_sqlite.py SOURCE DESTINATION")

source_path, destination_path = sys.argv[1:]
os.makedirs(os.path.dirname(destination_path), exist_ok=True)

source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
destination = sqlite3.connect(destination_path)
with destination:
    source.backup(destination)

integrity = destination.execute("pragma integrity_check").fetchone()[0]
if integrity != "ok":
    raise SystemExit(f"snapshot integrity failed: {integrity}")

os.chmod(destination_path, 0o600)
print(f"snapshot_ok bytes={os.path.getsize(destination_path)}")
