"""Installation into each agent, and the hooks that make auto-wrap work.

* Claude Code: skills copied to ~/.claude/skills, and (auto mode) a
  `SessionEnd` hook in ~/.claude/settings.json.
* Codex CLI: a block appended to ~/.codex/AGENTS.md (global instructions) so
  "wrap up" is understood, and (auto mode) `notify` in ~/.codex/config.toml.
  Codex has no session-end event, so notify only records activity and
  `cartographer sweep` wraps sessions once they have been idle.
* Cursor: a project rule (.cursor/rules/cartographer.mdc) and (auto mode) a
  `stop` hook in ~/.cursor/hooks.json.

Hook payloads are read from stdin and only ever used to find the session;
nothing in them is executed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from . import config, store

APP_DIR = os.path.join(config.HOME, "app")
MARK_START, MARK_END = "<!-- cartographer:start -->", "<!-- cartographer:end -->"


def package_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bin_path() -> str:
    installed = os.path.join(APP_DIR, "bin", "cartographer")
    if os.path.exists(installed):
        return installed
    return os.path.join(package_root(), "bin", "cartographer")


def self_install() -> str:
    """Copy this checkout to ~/.cartographer/app and link ~/.local/bin/cartographer."""
    src = package_root()
    if os.path.abspath(src) != os.path.abspath(APP_DIR):
        if os.path.isdir(APP_DIR):
            shutil.rmtree(APP_DIR)
        shutil.copytree(src, APP_DIR, ignore=shutil.ignore_patterns("__pycache__", ".git", "tests", "demo", "*.pyc"))
    target = os.path.join(APP_DIR, "bin", "cartographer")
    os.chmod(target, 0o755)
    local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
    os.makedirs(local_bin, exist_ok=True)
    link = os.path.join(local_bin, "cartographer")
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(target, link)
    except OSError:
        pass
    return target


# ------------------------------------------------------------ installers

def install(agent: str, auto: bool, project: Optional[str], bin_cmd: str) -> List[str]:
    if agent == "claude-code":
        return install_claude_code(auto, bin_cmd)
    if agent == "codex":
        return install_codex(auto, bin_cmd, project)
    if agent == "cursor":
        return install_cursor(auto, bin_cmd, project)
    raise KeyError(agent)


def install_claude_code(auto: bool, bin_cmd: str) -> List[str]:
    msgs = []
    src = os.path.join(package_root(), "skills")
    dst = os.path.join(os.path.expanduser("~"), ".claude", "skills")
    os.makedirs(dst, exist_ok=True)
    for name in ("wrap", "replay", "cartographer-setup"):
        _copytree(os.path.join(src, name), os.path.join(dst, name))
    _copytree(os.path.join(src, "references"), os.path.join(dst, "wrap", "references"))
    msgs.append("Claude Code: installed /wrap, /replay and /cartographer-setup into %s" % dst)
    settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    settings = _read_json(settings_path, {})
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault("SessionEnd", [])
    entries[:] = [e for e in entries if "cartographer hook" not in json.dumps(e)]
    if auto:
        entries.append({"matcher": "", "hooks": [{"type": "command", "command": '"%s" hook claude-code' % bin_cmd, "timeout": 20}]})
        msgs.append("Claude Code: SessionEnd hook added to %s (auto-wrap on)" % settings_path)
    elif not entries:
        hooks.pop("SessionEnd", None)
    _write_json(settings_path, settings)
    if not auto:
        msgs.append("Claude Code: manual mode; type /wrap at the end of a session")
    return msgs


def install_codex(auto: bool, bin_cmd: str, project: Optional[str]) -> List[str]:
    msgs = []
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    os.makedirs(home, exist_ok=True)
    snippet = _agents_snippet(bin_cmd, "Codex")
    targets = [os.path.join(home, "AGENTS.md")]
    if project:
        targets.append(os.path.join(project, "AGENTS.md"))
    for path in targets:
        _upsert_block(path, snippet)
        msgs.append("Codex: wrap instructions written to %s" % path)
    cfg_path = os.path.join(home, "config.toml")
    if auto:
        text = _read_text(cfg_path)
        line = 'notify = ["%s", "hook", "codex"]' % bin_cmd
        if re.search(r"^\s*notify\s*=", text, flags=re.M):
            if "cartographer" not in text:
                msgs.append("Codex: config.toml already has a `notify` entry. Add this yourself and chain the two if needed: %s" % line)
        else:
            _write_text(cfg_path, (text.rstrip("\n") + "\n\n" if text.strip() else "") + "# Cartographer records activity so `cartographer sweep` can auto-wrap idle sessions\n" + line + "\n")
            msgs.append("Codex: notify hook added to %s" % cfg_path)
        msgs.append("Codex has no session-end event: run `%s sweep` (add it to your shell login, or `%s install --launchd`) to wrap sessions idle for %d min" %
                    (bin_cmd, bin_cmd, config.load()["wrap"]["idle_minutes"]))
    else:
        msgs.append("Codex: manual mode; say 'wrap up this session with cartographer' or run `%s wrap --agent codex`" % bin_cmd)
    return msgs


def install_cursor(auto: bool, bin_cmd: str, project: Optional[str]) -> List[str]:
    msgs = []
    rule = _cursor_rule(bin_cmd)
    if project:
        path = os.path.join(project, ".cursor", "rules", "cartographer.mdc")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_text(path, rule)
        msgs.append("Cursor: project rule written to %s" % path)
    else:
        msgs.append("Cursor: no --project given. Paste this into Cursor Settings → Rules → User Rules, or rerun with --project <repo>:\n\n%s" % rule)
    if auto:
        hooks_path = os.path.join(os.path.expanduser("~"), ".cursor", "hooks.json")
        data = _read_json(hooks_path, {"version": 1, "hooks": {}})
        data.setdefault("version", 1)
        stops = data.setdefault("hooks", {}).setdefault("stop", [])
        stops[:] = [h for h in stops if "cartographer" not in json.dumps(h)]
        stops.append({"command": '"%s" hook cursor' % bin_cmd})
        _write_json(hooks_path, data)
        msgs.append("Cursor: stop hook added to %s (auto-wrap on)" % hooks_path)
    else:
        msgs.append("Cursor: manual mode; tell the agent 'wrap up this session with cartographer'")
    return msgs


def install_launchd(bin_cmd: str, every_min: int = 20) -> str:
    """macOS: run `cartographer sweep` periodically so Codex/Cursor sessions get wrapped."""
    label = "com.cartographer.sweep"
    path = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", label + ".plist")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>%s</string>
  <key>ProgramArguments</key><array><string>%s</string><string>sweep</string></array>
  <key>StartInterval</key><integer>%d</integer>
  <key>StandardOutPath</key><string>%s</string>
  <key>StandardErrorPath</key><string>%s</string>
</dict></plist>
""" % (label, bin_cmd, every_min * 60, os.path.join(config.HOME, "sweep.log"), os.path.join(config.HOME, "sweep.log"))
    _write_text(path, plist)
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    subprocess.run(["launchctl", "load", path], capture_output=True)
    return path


# ---------------------------------------------------------------- hooks

def handle(agent: str, payload: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Called by `cartographer hook <agent>` with the agent's JSON on stdin."""
    sid = None
    for key in ("session_id", "session-id", "conversation_id", "conversation-id", "thread_id", "thread-id", "id"):
        if payload.get(key):
            sid = str(payload[key])
            break
    cwd = payload.get("cwd") or (payload.get("workspace_roots") or [None])[0]
    item = {"agent": agent, "session_id": sid, "cwd": cwd, "transcript": payload.get("transcript_path"),
            "event": payload.get("hook_event_name") or payload.get("type"), "reason": payload.get("reason") or payload.get("status")}
    store.enqueue(item)
    # Codex's notify fires after every turn; only Claude Code and Cursor tell us a session actually ended.
    if cfg["wrap"]["mode"] == "auto" and agent in ("claude-code", "cursor") and sid:
        _spawn([bin_path(), "autowrap", "--agent", agent, "--session", sid] + (["--transcript", item["transcript"]] if item.get("transcript") else []))
        item["spawned"] = True
    return item


def _spawn(cmd: List[str]) -> None:
    log = open(os.path.join(config.HOME, "autowrap.log"), "a")
    kwargs = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


# ------------------------------------------------------------- snippets

def _agents_snippet(bin_cmd: str, agent_label: str) -> str:
    return """%s
## Cartographer (session mapping)

When the user says "wrap", "wrap up", "map this session", or "cartographer", run:

    "%s" wrap --agent %s

It prints a BRIEF path. Read that file and follow it exactly: write the recap JSON to the RECAP_OUT path it names, then run the save command it gives. Report the result in the voice the brief specifies. Do not wrap unless asked.
%s""" % (MARK_START, bin_cmd, agent_label.lower(), MARK_END)


def _cursor_rule(bin_cmd: str) -> str:
    return """---
description: Wrap up / map this session with Cartographer
alwaysApply: false
---
When the user says "wrap", "wrap up", "map this session" or "cartographer", run `"%s" wrap --agent cursor` in the terminal. It prints a BRIEF path. Read that file and follow it exactly: write the recap JSON to the RECAP_OUT path it names, then run the save command it gives, then summarize for the user in the voice the brief specifies.
""" % bin_cmd


# ---------------------------------------------------------------- utils

def _copytree(src: str, dst: str) -> None:
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for f in files:
            if not f.endswith(".pyc"):
                shutil.copy2(os.path.join(root, f), os.path.join(target, f))


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _upsert_block(path: str, block: str) -> None:
    text = _read_text(path)
    if MARK_START in text and MARK_END in text:
        text = text[: text.index(MARK_START)] + block + text[text.index(MARK_END) + len(MARK_END):]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
    _write_text(path, text)
