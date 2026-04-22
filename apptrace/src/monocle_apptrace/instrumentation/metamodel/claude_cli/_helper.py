
def extract_agent_request_input(arguments) -> dict:
    # For UserPromptSubmit, the input is in the "prompt" field; for PreToolUse, it's in "tool_input"
    return arguments['kwargs']['prompt']

def extract_agent_response(result) -> dict:
    # For handle_prompt_response, the response is in "response"; for handle_tool_call, it's in "tool_output"
    return result

def get_tool_type(arguments) -> str:
    # For PreToolUse, the tool type is in "tool_name"; for handle_tool_call, it's in "args"
    return 'tool.claude_cli' ## TBD handle MCP tools

def get_tool_name(arguments) -> str:
    # For PreToolUse, the tool name is in "tool_name"; for handle_tool_call, it's in "instance"
    return arguments['kwargs']['tool_name']

def get_tool_description(arguments) -> str:
    return arguments['kwargs']['tool_input']['description']

def extract_tool_input(arguments) -> dict:
    return arguments['kwargs']['tool_input']['command']

def extract_tool_response(result) -> dict:
    return result['stdout']

def get_agent_type(arguments) -> str:
    return 'agent.claude_cli'

def get_agent_name(arguments) -> str:
    return 'Claude CLI'