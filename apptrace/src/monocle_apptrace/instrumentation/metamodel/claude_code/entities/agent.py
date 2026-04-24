from monocle_apptrace.instrumentation.common.constants import SPAN_TYPES
from monocle_apptrace.instrumentation.metamodel.claude_code import _helper

# ---------------------------------------------------------------------------
# Agent request (one user turn — outer container)
# ---------------------------------------------------------------------------

AGENT_REQUEST = {
    "type": SPAN_TYPES.AGENTIC_REQUEST,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_AGENT_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: "Claude",
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_text(
                        _helper.get_content(arguments["args"][0].user_msg)
                    ),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("full_response", ""),
                }
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Agent invocation (Claude reasoning + tool-use loop inside a turn)
# ---------------------------------------------------------------------------

INVOCATION = {
    "type": SPAN_TYPES.AGENTIC_INVOCATION,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_AGENT_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: "Claude",
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_text(
                        _helper.get_content(arguments["args"][0].user_msg)
                    ),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("full_response", ""),
                }
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Tool invocations (regular, MCP, subagent delegation)
# ---------------------------------------------------------------------------

TOOL = {
    "type": SPAN_TYPES.AGENTIC_TOOL_INVOCATION,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_TOOL_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: arguments["args"][0].get("name", "unknown"),
            },
            {
                "attribute": "description",
                "accessor": lambda arguments: _helper.get_tool_description(
                    arguments["args"][0].get("name", ""),
                    arguments["args"][0].get("input", {}),
                ),
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: arguments["kwargs"].get("input_str", ""),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("output_str", ""),
                }
            ],
        },
    ],
}

MCP_TOOL = {
    "type": SPAN_TYPES.AGENTIC_MCP_INVOCATION,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_MCP_TOOL_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: arguments["args"][0].get("name", "unknown"),
            },
            {
                "attribute": "description",
                "accessor": lambda arguments: _helper.get_tool_description(
                    arguments["args"][0].get("name", ""),
                    arguments["args"][0].get("input", {}),
                ),
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: arguments["kwargs"].get("input_str", ""),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("output_str", ""),
                }
            ],
        },
    ],
}

AGENT_TOOL = {
    "type": SPAN_TYPES.AGENTIC_INVOCATION,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_AGENT_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: (
                    arguments["args"][0].get("input", {}).get("subagent_type") or "sub-agent"
                ),
            },
            {
                "attribute": "description",
                "accessor": lambda arguments: (
                    arguments["args"][0].get("input", {}).get("description", "")
                ),
            },
            {
                "attribute": "from_agent",
                "accessor": lambda arguments: "Claude",
            },
            {
                "attribute": "from_agent_span_id",
                "accessor": lambda arguments: arguments["kwargs"].get("parent_invocation_span_id", ""),
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: arguments["kwargs"].get("input_str", ""),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("output_str", ""),
                }
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Skill invocation (Claude Code harness slash-command, no Skill tool call)
# ---------------------------------------------------------------------------

SKILL = {
    "type": "agentic.skill.invocation",
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: _helper.CLAUDE_CODE_SKILL_TYPE_KEY,
            },
            {
                "attribute": "name",
                "accessor": lambda arguments: arguments["kwargs"].get("skill_name", "unknown"),
            },
            {
                "attribute": "invocation",
                "accessor": lambda arguments: "harness",
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: arguments["kwargs"].get("skill_input_str", ""),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: arguments["kwargs"].get("skill_output", ""),
                }
            ],
        },
    ],
}


def get_tool_output_processor(tool_name: str) -> dict:
    """Select the right output_processor dict based on tool name."""
    if tool_name == "Agent":
        return AGENT_TOOL
    if tool_name.startswith("mcp__"):
        return MCP_TOOL
    return TOOL
