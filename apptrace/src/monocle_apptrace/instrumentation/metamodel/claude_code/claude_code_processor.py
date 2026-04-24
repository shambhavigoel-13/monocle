"""
Claude Code transcript processor.

Parses Claude Code JSONL transcript files and emits OpenTelemetry spans
using Monocle's SpanHandler API — the same pattern used by all other metamodels.

Because this module replays a transcript rather than intercepting live calls,
spans must carry explicit start/end timestamps from the JSONL file. This is
handled by passing start_time/end_time to start_as_monocle_span, which forwards
them to the underlying OTel tracer. Everything else (attribute hydration, event
population, scope management, default Monocle attributes) goes through the
standard SpanHandler and utility APIs.
"""

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


from monocle_apptrace.instrumentation.common.span_handler import SpanHandler
from monocle_apptrace.instrumentation.common.utils import (
    set_scope,
    remove_scope,
)
from monocle_apptrace.instrumentation.common.wrapper import start_as_monocle_span
from monocle_apptrace.instrumentation.common.constants import (
    AGENT_SESSION,
    AGENT_REQUEST_SPAN_NAME,
    AGENT_INVOCATION_SPAN_NAME,
)
from monocle_apptrace.instrumentation.metamodel.claude_code._helper import (
    SessionState,
    SubagentInfo,
    Turn,
    build_turns,
    extract_text,
    get_content,
    get_message_id,
    get_model,
    get_stop_reason,
    get_timestamp,
    get_usage,
    iter_tool_uses,
    parse_command_skill,
    read_new_jsonl,
    read_subagent_jsonl,
)
from monocle_apptrace.instrumentation.metamodel.claude_code.entities.agent import (
    AGENT_REQUEST,
    INVOCATION,
    SKILL,
    get_tool_output_processor,
)
from monocle_apptrace.instrumentation.metamodel.claude_code.entities.inference import INFERENCE

logger = logging.getLogger(__name__)

SERVICE_NAME = "claude-cli"

_handler = SpanHandler()


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _parse_timestamp_ns(ts: Optional[str]) -> Optional[int]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core span context manager
# ---------------------------------------------------------------------------

@contextmanager
def _timed_span(
    tracer,
    name: str,
    start_ns: Optional[int],
    end_ns: Optional[int],
    is_root: bool = False,
) -> Generator:
    with start_as_monocle_span(tracer, name, auto_close_span=True,
                                start_time=start_ns, end_time=end_ns) as span:
        SpanHandler.set_default_monocle_attributes(span)
        if is_root:
            SpanHandler.set_workflow_properties(span, to_wrap={"package": "claude_code"})
        yield span


# ---------------------------------------------------------------------------
# Helpers shared across emitters
# ---------------------------------------------------------------------------

def _build_full_response(turn: Turn) -> str:
    parts = []
    for assistant_msg in turn.assistant_msgs:
        text = extract_text(get_content(assistant_msg))
        if text:
            parts.append(text)
    for tool_output in turn.tool_results_by_id.values():
        if tool_output:
            parts.append(tool_output if isinstance(tool_output, str) else json.dumps(tool_output))
    return "\n".join(parts)


def _build_inference_metadata(assistant_msg: Dict[str, Any], stop_reason: str) -> Dict[str, Any]:
    """
    prompt_tokens = input_tokens + cache_read + cache_creation.
    Reporting input_tokens alone is misleading because Claude Code uses
    aggressive prompt caching, making raw input_tokens as small as 3.
    """
    usage = get_usage(assistant_msg)
    finish_type = "tool_call" if stop_reason == "tool_use" else "success"
    meta: Dict[str, Any] = {"finish_reason": stop_reason, "finish_type": finish_type}

    input_t = usage.get("input_tokens") or 0
    cache_read_t = usage.get("cache_read_tokens") or 0
    cache_creation_t = usage.get("cache_creation_tokens") or 0
    output_t = usage.get("output_tokens") or 0
    prompt_t = input_t + cache_read_t + cache_creation_t

    if prompt_t:
        meta["prompt_tokens"] = prompt_t
    if output_t:
        meta["completion_tokens"] = output_t
    if prompt_t or output_t:
        meta["total_tokens"] = prompt_t + output_t
    if cache_read_t:
        meta["cache_read_tokens"] = cache_read_t
    if cache_creation_t:
        meta["cache_creation_tokens"] = cache_creation_t
    return meta


def _round_inference_start_ns(turn: Turn, round_index: int, turn_start_ns: Optional[int]) -> Optional[int]:
    if round_index == 0:
        return turn_start_ns
    prev_tool_ids = [
        tu.get("id")
        for tu in iter_tool_uses(get_content(turn.assistant_msgs[round_index - 1]))
    ]
    prev_end_times = [
        _parse_timestamp_ns(turn.tool_result_times_by_id.get(tid))
        for tid in prev_tool_ids if tid
    ]
    prev_end_times = [t for t in prev_end_times if t]
    if prev_end_times:
        return max(prev_end_times)
    return _parse_timestamp_ns(get_timestamp(turn.assistant_msgs[round_index - 1]))


def _hydrate(output_processor: dict, args_item: Any, ctx: Dict[str, Any],
             span, parent_span) -> None:
    """Call hydrate_span twice — once for input events/pre-exec attributes,
    once for output events/status. Mirrors monocle_wrapper_span_processor."""
    to_wrap = {"output_processor": output_processor}
    _handler.hydrate_span(to_wrap, None, None, [args_item], ctx, None,
                          span, parent_span, None, is_post_exec=False)
    _handler.hydrate_span(to_wrap, None, None, [args_item], ctx, args_item,
                          span, parent_span, None, is_post_exec=True)


# ---------------------------------------------------------------------------
# Span emitters — each uses _timed_span + _hydrate, no direct OTel calls
# ---------------------------------------------------------------------------

def _emit_skill_span(
    tracer,
    cmd_skill: Dict[str, str],
    turn_start_ns: Optional[int],
    turn_end_ns: Optional[int],
    ctx: Dict[str, Any],
    parent_span,
) -> None:
    skill_name = cmd_skill["skill_name"]
    skill_input: Dict[str, Any] = {"skill": skill_name}
    if cmd_skill["args"]:
        skill_input["args"] = cmd_skill["args"]
    if cmd_skill["plugin_name"]:
        skill_input["plugin"] = cmd_skill["plugin_name"]

    skill_ctx = {
        **ctx,
        "skill_name": skill_name,
        "skill_input_str": json.dumps(skill_input),
        "skill_output": f"/{cmd_skill['command_name']}",
    }
    with _timed_span(tracer, f"Skill: {skill_name}", turn_start_ns, turn_end_ns) as span:
        _hydrate(SKILL, cmd_skill, skill_ctx, span, parent_span)


def _emit_inference_span(
    tracer,
    assistant_msg: Dict[str, Any],
    round_index: int,
    num_rounds: int,
    turn: Turn,
    user_text: str,
    ctx: Dict[str, Any],
    turn_start_ns: Optional[int],
    parent_span,
) -> None:
    stop_reason = get_stop_reason(assistant_msg) or "end_turn"
    msg_id = get_message_id(assistant_msg) or ""
    start_ns = _round_inference_start_ns(turn, round_index, turn_start_ns)
    end_ns = _parse_timestamp_ns(get_timestamp(assistant_msg))
    metadata = _build_inference_metadata(assistant_msg, stop_reason)
    name = "Claude Inference" if num_rounds == 1 else f"Claude Inference ({round_index + 1}/{num_rounds})"

    inf_ctx = {**ctx, "user_text": user_text, "metadata": metadata}

    with _timed_span(tracer, name, start_ns, end_ns) as span:
        # gen_ai.* are transcript-specific span attributes with no entity.N.* mapping
        model = get_model(assistant_msg) or ""
        if model:
            span.set_attribute("gen_ai.request.model", model)
        if msg_id:
            span.set_attribute("gen_ai.response.id", msg_id)
        span.set_attribute("gen_ai.system", "anthropic")

        _hydrate(INFERENCE, assistant_msg, inf_ctx, span, parent_span)


def _emit_tool_span(
    tracer,
    tool_use: Dict[str, Any],
    turn: Turn,
    ctx: Dict[str, Any],
    start_ns: Optional[int],
    turn_end_ns: Optional[int],
    parent_span,
    parent_invocation_span_id: str,
) -> None:
    tool_id = tool_use.get("id", "")
    tool_name = tool_use.get("name", "unknown")
    tool_input = tool_use.get("input", {})
    tool_output = turn.tool_results_by_id.get(tool_id, "")
    end_ns = _parse_timestamp_ns(turn.tool_result_times_by_id.get(tool_id)) or turn_end_ns

    input_str = json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)
    output_str = (
        tool_output if isinstance(tool_output, str)
        else (json.dumps(tool_output) if tool_output else "")
    )

    tool_ctx = {
        **ctx,
        "input_str": input_str,
        "output_str": output_str,
        "parent_invocation_span_id": parent_invocation_span_id,
    }

    if tool_name == "Agent" and isinstance(tool_input, dict):
        subagent_type = tool_input.get("subagent_type") or "sub-agent"
        span_name = f"Sub-Agent: {subagent_type}"
        # Fresh invocation scope so the narrative graph treats this as a separate invocation
        invoc_scope_token = set_scope(AGENT_INVOCATION_SPAN_NAME)
    elif tool_name == "Skill" and isinstance(tool_input, dict):
        span_name = f"Skill: {tool_input.get('skill', 'unknown')}"
        invoc_scope_token = None
    else:
        span_name = f"Tool: {tool_name}"
        invoc_scope_token = None

    output_processor = get_tool_output_processor(tool_name)
    with _timed_span(tracer, span_name, start_ns, end_ns) as span:
        _hydrate(output_processor, tool_use, tool_ctx, span, parent_span)

    if invoc_scope_token is not None:
        remove_scope(invoc_scope_token)


# ---------------------------------------------------------------------------
# Turn emitter
# ---------------------------------------------------------------------------

def _emit_turn(
    tracer,
    turn: Turn,
    session_id: str,
    sdk_version: str,
    service_name: str,
    user_name: Optional[str] = None,
    span_name_prefix: str = "Claude Code",
) -> bool:
    if not turn.assistant_msgs:
        return False

    user_text = extract_text(get_content(turn.user_msg))
    full_response = _build_full_response(turn)
    model = get_model(turn.assistant_msgs[0])
    turn_start_ns = _parse_timestamp_ns(turn.start_time)
    turn_end_ns = _parse_timestamp_ns(turn.end_time)
    turn_id = str(uuid.uuid4())
    invocation_id = str(uuid.uuid4())

    ctx: Dict[str, Any] = {
        "session_id": session_id,
        "turn_id": turn_id,
        "invocation_id": invocation_id,
        "service_name": service_name,
        "sdk_version": sdk_version,
        "user_name": user_name,
        "full_response": full_response,
        "model": model,
    }

    turn_scope_token = set_scope(AGENT_REQUEST_SPAN_NAME, turn_id)
    try:
        with _timed_span(tracer, span_name_prefix, turn_start_ns, turn_end_ns) as turn_span:
            _hydrate(AGENT_REQUEST, turn, ctx, turn_span, None)

            invoc_scope_token = set_scope(AGENT_INVOCATION_SPAN_NAME, invocation_id)
            try:
                with _timed_span(tracer, "Claude Invocation", turn_start_ns, turn_end_ns) as invoc_span:
                    _hydrate(INVOCATION, turn, ctx, invoc_span, turn_span)

                    cmd_skill = parse_command_skill(user_text)
                    has_explicit_skill = any(
                        tu.get("name") == "Skill"
                        for am in turn.assistant_msgs
                        for tu in iter_tool_uses(get_content(am))
                    )
                    if cmd_skill and not has_explicit_skill:
                        _emit_skill_span(tracer, cmd_skill, turn_start_ns, turn_end_ns, ctx, invoc_span)

                    parent_span_id = format(invoc_span.get_span_context().span_id, "016x")
                    num_rounds = len(turn.assistant_msgs)
                    total_tool_spans = 0

                    for i, assistant_msg in enumerate(turn.assistant_msgs):
                        _emit_inference_span(
                            tracer, assistant_msg, i, num_rounds, turn,
                            user_text, ctx, turn_start_ns, invoc_span,
                        )
                        tool_start_ns = _parse_timestamp_ns(get_timestamp(assistant_msg))
                        for tool_use in iter_tool_uses(get_content(assistant_msg)):
                            _emit_tool_span(
                                tracer, tool_use, turn, ctx,
                                tool_start_ns, turn_end_ns,
                                invoc_span, parent_invocation_span_id=parent_span_id,
                            )
                            total_tool_spans += 1

            finally:
                remove_scope(invoc_scope_token)

            logger.debug("%s: %d LLM rounds, %d tool spans", span_name_prefix, num_rounds, total_tool_spans)
    finally:
        remove_scope(turn_scope_token)

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_transcript(
    session_id: str,
    turns: List[Turn],
    tracer,
    sdk_version: str,
    service_name: str = SERVICE_NAME,
    user_name: Optional[str] = None,
    subagents: Optional[List[SubagentInfo]] = None,
) -> int:
    """Emit Monocle-compatible spans for a list of turns under a workflow root span.

    Returns the number of turns emitted (excludes subagent turns).
    """
    if not turns and not subagents:
        return 0

    workflow_start_ns = _parse_timestamp_ns(turns[0].start_time) if turns else None
    workflow_end_ns = _parse_timestamp_ns(turns[-1].end_time) if turns else None

    session_scope_token = set_scope(AGENT_SESSION, session_id)
    try:
        with _timed_span(
            tracer, "workflow", workflow_start_ns, workflow_end_ns, is_root=True
        ) as workflow_span:
            emitted = sum(
                1 for turn in turns
                if _emit_turn(tracer, turn, session_id, sdk_version, service_name, user_name)
            )
            if subagents:
                process_subagents(subagents, tracer, session_id, sdk_version, service_name, user_name)
    finally:
        remove_scope(session_scope_token)

    return emitted


def process_subagents(
    subagents: List[SubagentInfo],
    tracer,
    parent_session_id: str,
    sdk_version: str,
    service_name: str = SERVICE_NAME,
    user_name: Optional[str] = None,
) -> int:
    """Emit spans for subagent JSONL files under the current OTel context."""
    total_emitted = 0
    for sa in subagents:
        msgs = read_subagent_jsonl(sa.jsonl_path)
        if not msgs:
            logger.debug("subagent %s: no messages", sa.agent_id)
            continue
        turns = build_turns(msgs)
        if not turns:
            logger.debug("subagent %s: no complete turns", sa.agent_id)
            continue
        prefix = f"Sub-Agent: {sa.agent_type}" if sa.agent_type != "sub-agent" else "Sub-Agent"
        for turn in turns:
            if _emit_turn(tracer, turn, sa.agent_id, sdk_version, service_name, user_name, span_name_prefix=prefix):
                total_emitted += 1
    return total_emitted


def process_transcript_file(
    session_id: str,
    transcript_path: Path,
    tracer,
    sdk_version: str,
    service_name: str = SERVICE_NAME,
    session_state: Optional[SessionState] = None,
    user_name: Optional[str] = None,
) -> tuple:
    """Read new JSONL from a transcript file, build turns, emit spans.

    Returns (emitted_count, updated_session_state).
    """
    if session_state is None:
        session_state = SessionState()
    msgs, session_state = read_new_jsonl(transcript_path, session_state)
    if not msgs:
        return 0, session_state
    turns = build_turns(msgs)
    if not turns:
        return 0, session_state
    emitted = process_transcript(
        session_id=session_id, turns=turns, tracer=tracer,
        sdk_version=sdk_version, service_name=service_name, user_name=user_name,
    )
    return emitted, session_state
