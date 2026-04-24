"""
monocle-install-claude  —  install Monocle hooks into ~/.claude/settings.json

Usage:
  monocle-install-claude [--api-key KEY] [--endpoint URL] [--exporter LIST] [--workflow-name NAME]
"""

import json
import sys
from pathlib import Path

_HOOK_EVENTS = [
    "SessionStart", "UserPromptSubmit",
    "PreToolUse", "PostToolUse",
    "SubagentStart", "SubagentStop",
    "Stop", "StopFailure",
    "PreCompact", "PostCompact",
    "SessionEnd",
]

_CONFIG_PATH = Path("~/.monocle/config.json")


def _is_monocle_hook(cmd: str) -> bool:
    return "monocle_apptrace" in cmd or "monocle_hook" in cmd


def install_hooks(api_key=None, endpoint=None, exporter=None, workflow_name=None):
    config_updates = {}
    if api_key:
        config_updates["okahu_api_key"] = api_key
    if endpoint:
        config_updates["okahu_endpoint"] = endpoint
    if exporter:
        config_updates["monocle_exporter"] = exporter
    if workflow_name:
        config_updates["workflow_name"] = workflow_name

    if config_updates:
        config_path = _CONFIG_PATH.expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
            except Exception:
                pass
        config.update(config_updates)
        config_path.write_text(json.dumps(config, indent=2))
        print(f"Monocle config saved → {config_path}")

    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except Exception:
            pass

    command = f"{sys.executable} -m monocle_apptrace.instrumentation.metamodel.claude_cli"
    monocle_entry = {"type": "command", "command": command, "statusMessage": "Monocle telemetry"}
    hooks = settings.setdefault("hooks", {})

    for event in _HOOK_EVENTS:
        cleaned = [
            bucket for bucket in hooks.get(event, [])
            if not any(_is_monocle_hook(h.get("command", "")) for h in bucket.get("hooks", []))
        ]
        cleaned.append({"hooks": [monocle_entry]})
        hooks[event] = cleaned

    settings_path.write_text(json.dumps(settings, indent=2))
    print(f"Monocle hooks installed → {settings_path}")
    print(f"Hook command: {command}")
    print("Start Claude Code — traces will be emitted automatically.")


def main():
    args = sys.argv[1:]
    api_key = endpoint = exporter = workflow_name = None
    i = 0
    while i < len(args):
        if args[i] == "--api-key" and i + 1 < len(args):
            api_key = args[i + 1]; i += 2
        elif args[i] == "--endpoint" and i + 1 < len(args):
            endpoint = args[i + 1]; i += 2
        elif args[i] == "--exporter" and i + 1 < len(args):
            exporter = args[i + 1]; i += 2
        elif args[i] == "--workflow-name" and i + 1 < len(args):
            workflow_name = args[i + 1]; i += 2
        else:
            i += 1
    install_hooks(api_key=api_key, endpoint=endpoint, exporter=exporter, workflow_name=workflow_name)
