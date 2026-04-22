import functools
from datetime import datetime
from opentelemetry.context import attach, detach, set_value
from monocle_apptrace.instrumentation.common.constants import SPAN_START_TIME, SPAN_END_TIME
from .trace_events import _log


# ── Dummy handlers ────────────────────────────────────────────────────────────
# Replace the bodies of these functions with real logic as needed.

class ReplayHandler:

    def handle_session_start(self, session_id: str, source: str, model: str, **kwargs) -> None:
        """Called once when a session begins or resumes."""
        _log(f"SessionStart      | session={session_id}  source={source}  model={model}")

    def handle_tool_call(self, tool_name: str, tool_input: dict, tool_output: dict, **kwargs) -> dict:
        """
        Combined tool handler — fired when the PostToolUse for a tool arrives.

        Receives the tool name and input (captured at PreToolUse) and the actual
        tool output recorded from the PostToolUse event.
        Returns the tool output; replace with real tool invocation logic.
        """
        _log(f"ToolCall          | tool={tool_name}  input_fields={list(tool_input.keys())}")
        _log(f"  -> output: {tool_output}")
        return tool_output

    def handle_turn(self, prompt: str, response: str, **kwargs) -> str:
        """
        Combined prompt/response handler — fired when the Stop event arrives.

        Receives the user prompt (captured at UserPromptSubmit), the actual
        assistant response recorded from the transcript at Stop time, and an
        ordered list of tool calls via kwargs["tool_calls"].  Each entry
        in tool_calls has keys: tool_name, tool_input, tool_output,
        SPAN_START_TIME, and SPAN_END_TIME.

        Dispatches every tool call to handle_tool_call before returning.
        Returns the response; replace with real LLM call logic.
        """
        tool_calls: list[dict] = kwargs.get("tool_calls") or []
        preview = prompt[:120].replace("\n", " ")
        suffix = "…" if len(prompt) > 120 else ""
        _log(f"PromptResponse    | prompt={preview}{suffix}")
        for tc in tool_calls:
            self.handle_tool_call(
                tool_name=tc["tool_name"],
                tool_input=tc["tool_input"],
                tool_output=tc["tool_output"],
                **{SPAN_START_TIME: tc.get(SPAN_START_TIME), SPAN_END_TIME: tc.get(SPAN_END_TIME)},
            )
        _log(f"  -> response: {response[:200]}{'…' if len(response) > 200 else ''}")
        return response

    def handle_session_end(self, session_id: str, **kwargs) -> None:
        """Called once when a session terminates."""
        _log(f"SessionEnd        | session={session_id}")


def _log(msg: str) -> None:
#    print(f"[hook] {msg}", file=sys.stderr)
    pass
