from monocle_apptrace.instrumentation.common.constants import SPAN_TYPES
from monocle_apptrace.instrumentation.metamodel.claude_code import _helper

INFERENCE = {
    "type": SPAN_TYPES.INFERENCE,
    "attributes": [
        [
            {
                "attribute": "type",
                "accessor": lambda arguments: "inference.anthropic",
            },
            {
                "attribute": "provider_name",
                "accessor": lambda arguments: "api.anthropic.com",
            },
        ],
        [
            {
                "attribute": "name",
                "accessor": lambda arguments: _helper.get_model(arguments["args"][0]) or "claude",
            },
            {
                "attribute": "type",
                "accessor": lambda arguments: "model.llm." + (
                    _helper.get_model(arguments["args"][0]) or "claude"
                ),
            },
        ],
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "attribute": "input",
                    "accessor": lambda arguments: arguments["kwargs"].get("user_text", ""),
                }
            ],
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.round_output_text(arguments["args"][0]),
                }
            ],
        },
        {
            "name": "metadata",
            "attributes": [
                {
                    # No attribute key — dict is merged directly into event attributes
                    "accessor": lambda arguments: arguments["kwargs"].get("metadata", {}),
                }
            ],
        },
    ],
}
