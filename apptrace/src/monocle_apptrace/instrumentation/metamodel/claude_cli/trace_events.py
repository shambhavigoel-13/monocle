"""
Monocle Claude Trace

Writes every hook event to a single append-only trace file at the project root:
  .monocle_claude_trace.jsonl

All sessions share the same file, so the full history of events across
sessions is available in one place.

Public API
----------
record_trace_event(entry)  – append an already-enriched event dict as a JSON line
delete_trace_file()        – remove the trace file if it exists
"""

import json
import os
import sys
from pathlib import Path

# Project root is one level above the hooks/ directory
TRACE_FILE = Path(__file__).parent.parent / ".monocle_claude_trace.jsonl"
# set current directory to the location of this script, so we can write session logs here
SESSIONS_DIR = Path(os.getcwd()) / ".monocle" / ".claude_sessions"

def _session_log(session_id: str) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f".monocle_claude_{session_id}.jsonl"

def record_trace_event(entry: dict) -> None:
    """Append an enriched event dict as a single JSON line to the trace file."""
    with TRACE_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def delete_trace_file() -> None:
    """Delete the trace file if it exists."""
    if TRACE_FILE.exists():
        TRACE_FILE.unlink()
        _log(f"Deleted trace file: {TRACE_FILE}")
    else:
        _log(f"Trace file not found, nothing to delete: {TRACE_FILE}")


def _log(msg: str) -> None:
    print(f"[trace] {msg}", file=sys.stderr)
