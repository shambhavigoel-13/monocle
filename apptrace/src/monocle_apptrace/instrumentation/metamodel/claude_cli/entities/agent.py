from monocle_apptrace.instrumentation.common.constants import SPAN_SUBTYPES, SPAN_TYPES
from monocle_apptrace.instrumentation.common.utils import get_error_message, get_span_id
from monocle_apptrace.instrumentation.metamodel.claude_cli import _helper
from monocle_apptrace.instrumentation.common.utils import get_error_message

REQUEST = {
      "type": SPAN_TYPES.AGENTIC_REQUEST,
      "subtype": SPAN_SUBTYPES.TURN,
      "attributes": [
        [
              {
                "_comment": "agent type",
                "attribute": "type",
                "accessor": lambda arguments:'agent.claude_cli'
              }
        ],
      ],
      "events": [
        {
          "name":"data.input",
          "attributes": [
            {
                "_comment": "this is Agent turn input",
                "attribute": "input",
                "accessor": lambda arguments: _helper.extract_agent_request_input(arguments)
            }
          ]
        },
        {
          "name":"data.output",
          "attributes": [
            {
                "_comment": "this is response from LLM",
                "attribute": "response",
                "accessor": lambda arguments: _helper.extract_agent_response(arguments['result'])
            }
          ]
        }
      ]
}

