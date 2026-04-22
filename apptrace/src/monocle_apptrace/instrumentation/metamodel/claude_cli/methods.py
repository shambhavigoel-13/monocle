from monocle_apptrace.instrumentation.common.wrapper import task_wrapper, atask_wrapper
from monocle_apptrace.instrumentation.metamodel.claude_cli.entities.agent import REQUEST
from monocle_apptrace.instrumentation.metamodel.claude_cli.entities.tool import TOOL
from monocle_apptrace.instrumentation.metamodel.agents.agents_processor import (
    constructor_wrapper,
    handoff_constructor_wrapper,
)

CLAUDE_CLI_PROXY_METHODS = [
    # Main agent runner methods
    {
        "package": "monocle_apptrace.instrumentation.metamodel.claude_cli.replay_handlers",
        "object": "ReplayHandler",
        "method": "handle_turn",
        "wrapper_method": task_wrapper,
        "output_processor": REQUEST,
        "span_handler": "claude_handler"
    },
    {
        "package": "monocle_apptrace.instrumentation.metamodel.claude_cli.replay_handlers",
        "object": "ReplayHandler",
        "method": "handle_tool_call",
        "wrapper_method": task_wrapper,
        "output_processor": TOOL,
        "span_handler": "claude_handler"
    },
]
