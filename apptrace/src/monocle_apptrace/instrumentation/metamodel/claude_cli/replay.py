"""
Session Replay

Loads a recorded session log and replays the interaction through paired
dummy handlers:

  PreToolUse + PostToolUse  →  handle_tool_call(tool_name, tool_input) -> dict
  UserPromptSubmit + Stop   →  handle_turn(prompt, response) -> str

SessionStart and SessionEnd are dispatched immediately as standalone calls.
"""

# Enable Monocle Tracing
from monocle_apptrace.instrumentation.common.instrumentor import setup_monocle_telemetry
setup_monocle_telemetry(workflow_name = 'claude-cli', monocle_exporters_list = 'file')

import json
import sys
from pathlib import Path
from  monocle_apptrace.instrumentation.metamodel.claude_cli.replay_handlers import ReplayHandler
from monocle_apptrace.instrumentation.metamodel.claude_cli.trace_events import record_trace_event, _session_log, _log
from monocle_apptrace.instrumentation.common.constants import AGENT_SESSION, SPAN_START_TIME, SPAN_END_TIME

# ── Storage (read side) ───────────────────────────────────────────────────────

def load_events(session_id: str) -> list[dict]:
    """Return all recorded events for a session, in order."""
    log = _session_log(session_id)
    if not log.exists():
        return []
    events = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events



# ── Replay ────────────────────────────────────────────────────────────────────


def replay_session(session_id: str) -> None:
    """
    Replay all recorded events for a session.

    Pairing rules:
      - PreToolUse is buffered (keyed by tool_use_id); when the matching
        PostToolUse arrives, handle_tool_call is fired with the buffered input.
      - UserPromptSubmit is buffered; when Stop arrives,
        handle_prompt_response is fired with the buffered prompt.
      - SessionStart and SessionEnd are dispatched immediately.
    """
    events = load_events(session_id)
    _log(f"--- Replay start: {len(events)} events for session {session_id} ---")

    pending_prompt_event: dict | None = None  # UserPromptSubmit event (pre)
    pending_tools: dict[str, dict] = {}        # tool_use_id -> PreToolUse event
    pending_tool_calls: list[dict] = []        # ordered tool calls for the current turn
    replay_handler: ReplayHandler = ReplayHandler()
    for event in events:
        name = event.get("hook_event_name", "")

        if name == "SessionStart":
            replay_handler.handle_session_start(
                session_id,
                event.get("source", ""),
                event.get("model", ""),
            )

        elif name == "UserPromptSubmit":
            pending_prompt_event = event
            pending_tool_calls = []

        elif name == "PreToolUse":
            pending_tools[event.get("tool_use_id", "")] = event

        elif name == "PostToolUse":
            tool_use_id = event.get("tool_use_id", "")
            pre = pending_tools.pop(tool_use_id, event)
            pending_tool_calls.append({
                "tool_name": pre.get("tool_name", event.get("tool_name", "")),
                "tool_input": pre.get("tool_input", {}),
                "tool_output": event.get("tool_response", {}),
                SPAN_START_TIME: pre.get("timestamp"),
                SPAN_END_TIME: event.get("timestamp"),
            })

        elif name == "Stop":
            if pending_prompt_event is not None:
                replay_handler.handle_turn(
                    prompt=pending_prompt_event.get("prompt", ""),
                    response=event.get("assistant_response", ""),
                    tool_calls=pending_tool_calls,
                    **{SPAN_START_TIME: pending_prompt_event.get("timestamp"), SPAN_END_TIME: event.get("timestamp"), AGENT_SESSION: session_id},
                )
                pending_prompt_event = None
                pending_tool_calls = []

        elif name == "SessionEnd":
            replay_handler.handle_session_end(
                session_id,
                **{SPAN_END_TIME: event.get("timestamp")},
            )

    _log("--- Replay end ---")


# ── Utilities ─────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        _log("Usage: replay.py <session_id>")
        sys.exit(1)
    session_id = sys.argv[1]
    replay_session(session_id)

if __name__ == "__main__":
    main()