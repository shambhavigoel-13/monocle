#!/usr/bin/env python3
"""
Claude CLI Event Handler

Hook entry point for all Claude CLI events. Responsibilities:
  - Read the event JSON from stdin
  - Append every event with a UTC timestamp to a per-session JSONL log file
  - On Stop, delegate to replay.replay_session to reproduce the interaction

Events handled:
  SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, SessionEnd
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from monocle_apptrace.instrumentation.metamodel.claude_cli.trace_events import delete_trace_file, record_trace_event, _session_log, _log
from monocle_apptrace.instrumentation.metamodel.claude_cli.replay import replay_session

# ── Storage (write side) ──────────────────────────────────────────────────────



def _read_last_assistant_message(transcript_path: str) -> str:
    """
    Extract the last assistant message text from the transcript JSONL file.
    The transcript uses the Anthropic Messages API format — each line is a
    message dict with 'role' and 'content' fields.
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return ""
        last_text = ""
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                # Handle both flat {"role": "assistant", "content": ...}
                # and wrapped {"type": "assistant", "message": {...}} formats
                if msg.get("type") == "assistant":
                    msg = msg.get("message", msg)
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    texts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    last_text = "\n".join(t for t in texts if t)
            except json.JSONDecodeError:
                pass
        return last_text
    except Exception:
        return ""


def record_event(event_data: dict) -> None:
    """
    Append the event dict plus a UTC timestamp to the session log.
    For Stop events, also extracts and stores the last assistant response
    from the transcript so the replay has access to the actual output.
    """
    session_id = event_data.get("session_id", "unknown")
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **event_data}

    if event_data.get("hook_event_name") == "Stop":
        transcript_path = event_data.get("transcript_path", "")
        entry["assistant_response"] = _read_last_assistant_message(transcript_path)

    with _session_log(session_id).open("a") as fh:
        fh.write(json.dumps(entry) + "\n")

    record_trace_event(entry)
    delete_trace_file()

# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
### UNCOMMENT    raw = sys.stdin.read()
    raw = [line.rstrip("\n") for line in sys.stdin.readlines()]

    try:
        event_data = json.loads("".join(raw))
    except json.JSONDecodeError as exc:
        _log(f"ERROR: could not parse stdin as JSON – {exc}")
        sys.exit(1)

    session_id = event_data.get("session_id", "unknown")
    event_name = event_data.get("hook_event_name", "unknown")

    record_event(event_data)
    _log(f"Recorded {event_name} for session {session_id}")
    replay_session(session_id)


if __name__ == "__main__":
    main()
