"""Installation into each agent, and the hooks that make auto-wrap work.

* Claude Code: skills copied to ~/.claude/skills; auto mode adds a
  `SessionEnd` hook to ~/.claude/settings.json.
* Codex CLI: a block in ~/.codex/AGENTS.md so "wrap up" is understood. Codex
  has no session-end event, so auto mode means running `cartographer sweep`
  periodically (a cron line is printed).
* Cursor: a project rule (.cursor/rules/cartographer.mdc); auto mode adds a
  `stop` hook to ~/.cursor/hooks.json.

Hook payloads are only ever used to find the session; nothing in them is run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from . import config, store

APP_DIR = os.path.join(config.HOME, "app")
MARK_START, MARK_END = "<!-- cartographer:start -->", "<!-- cartographer:end -->"
HOME = os.path.expanduser("~")


def package_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bin_path() -> str:
    installed = os.path.join(APP_DIR, "bin", "cartographer")
    return installed if os.path.exists(installed) else os.path.join(package_root(), "bin", "cartographer")


def self_install() -> str:
    """Copy this checkout to ~/.cartographer/app and link ~/.local/bin/cartographer."""
    src = package_root()
    if os.path.abspath(src) != os.path.abspath(APP_DIR):
        if os.path.isdir(APP_DIR):
            shutil.rmtree(APP_DIR)
        shutil.copytree(src, APP_DIR, ignore=shutil.ignore_patterns("__pycache__", ".git", "tests", "demo", "*.pyc"))
    target = os.path.join(APP_DIR, "bin", "cartographer")
    os.chmod(target, 0o755)
    link = os.path.join(HOME, ".local", "bin", "cartographer")
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(target, link)
    except OSError:
        pass
    return target


def sweep_hint(bin_cmd: str) -> str:
    return ("Codex has no session-end event: run `%s sweep` every 20 min to wrap sessions idle for %d min, e.g. crontab -e → "
            "*/20 * * * * \"%s\" sweep >> \"%s\" 2>&1" % (bin_cmd, config.load()["wrap"]["idle_minutes"], bin_cmd, os.path.join(config.HOME, "sweep.log")))


# ------------------------------------------------------------ installers

def install(agent: str, auto: bool, project: Optional[str], bin_cmd: str) -> List[str]:
    fn = {"claude-code": install_claude_code, "codex": install_codex, "cursor": install_cursor}.get(agent)
    if not fn:
        raise KeyError(agent)
    return fn(auto, bin_cmd, project)


def _ours(entry: Any) -> bool:
    s = json.dumps(entry)
    return "cartographer" in s and " hook " in s


def install_claude_code(auto: bool, bin_cmd: str, project: Optional[str] = None) -> List[str]:
    src = os.path.join(package_root(), "skills")
    if not os.path.isdir(src):
        raise LookupError("skills folder not found at %s; run install from the git checkout" % src)
    dst = os.path.join(HOME, ".claude", "skills")
    for name in ("wrap", "replay", "cartographer-setup"):
        shutil.copytree(os.path.join(src, name), os.path.join(dst, name), dirs_exist_ok=True)
    msgs = ["Claude Code: installed /wrap, /replay and /cartographer-setup into %s" % dst]
    settings_path = os.path.join(HOME, ".claude", "settings.json")
    settings = store.read_json(settings_path, {})
    hooks = settings.setdefault("hooks", {})
    entries = [e for e in (hooks.get("SessionEnd") or []) if not _ours(e)]
    if auto:
        entries.append({"hooks": [{"type": "command", "command": '"%s" hook claude-code' % bin_cmd, "timeout": 20}]})
        msgs.append("Claude Code: SessionEnd hook added to %s (auto-wrap on)" % settings_path)
    else:
        msgs.append("Claude Code: manual mode; type /wrap at the end of a session")
    if entries:
        hooks["SessionEnd"] = entries
    else:
        hooks.pop("SessionEnd", None)
    store.write_json(settings_path, settings, indent=2)
    return msgs


def install_codex(auto: bool, bin_cmd: str, project: Optional[str] = None) -> List[str]:
    home = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
    msgs = []
    for path in [os.path.join(home, "AGENTS.md")] + ([os.path.join(project, "AGENTS.md")] if project else []):
        _upsert_block(path, _agents_snippet(bin_cmd))
        msgs.append("Codex: wrap instructions written to %s" % path)
    msgs.append(sweep_hint(bin_cmd) if auto else "Codex: manual mode; say 'wrap up this session with cartographer'")
    return msgs


def install_cursor(auto: bool, bin_cmd: str, project: Optional[str] = None) -> List[str]:
    rule = _cursor_rule(bin_cmd)
    if project:
        path = os.path.join(project, ".cursor", "rules", "cartographer.mdc")
        _write_text(path, rule)
        msgs = ["Cursor: project rule written to %s" % path]
    else:
        msgs = ["Cursor: no --project given. Paste this into Cursor Settings → Rules → User Rules, or rerun with --project <repo>:\n\n%s" % rule]
    if auto:
        hooks_path = os.path.join(HOME, ".cursor", "hooks.json")
        data = store.read_json(hooks_path, {})
        data.setdefault("version", 1)
        stops = [h for h in (data.setdefault("hooks", {}).get("stop") or []) if not _ours(h)]
        stops.append({"command": '"%s" hook cursor' % bin_cmd})
        data["hooks"]["stop"] = stops
        store.write_json(hooks_path, data, indent=2)
        msgs.append("Cursor: stop hook added to %s (auto-wrap on)" % hooks_path)
    else:
        msgs.append("Cursor: manual mode; tell the agent 'wrap up this session with cartographer'")
    return msgs


# ---------------------------------------------------------------- hooks

def handle(agent: str, payload: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Called by `cartographer hook <agent>` with the agent's JSON payload."""
    sid = next((str(payload[k]) for k in ("session_id", "conversation_id", "thread_id", "thread-id", "id") if payload.get(k)), None)
    item = {"agent": agent, "session_id": sid, "cwd": payload.get("cwd") or (payload.get("workspace_roots") or [None])[0],
            "transcript": payload.get("transcript_path"), "event": payload.get("hook_event_name") or payload.get("type")}
    # Only Claude Code and Cursor say a session actually ended; everything else is picked up by `sweep`.
    if cfg["wrap"]["mode"] == "auto" and agent in ("claude-code", "cursor") and sid:
        cmd = [bin_path(), "wrap", "--run", "--agent", agent, "--session", sid]
        if item["transcript"]:
            cmd += ["--transcript", item["transcript"]]
        _spawn(cmd)
        item["spawned"] = True
    return item


def _spawn(cmd: List[str]) -> None:
    log = open(os.path.join(config.HOME, "autowrap.log"), "a")
    kwargs: Dict[str, Any] = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


# ------------------------------------------------------------- snippets

def _agents_snippet(bin_cmd: str) -> str:
    return """%s
## Cartographer (session mapping)

When the user says "wrap", "wrap up", "map this session", or "cartographer", run:

    "%s" wrap --agent codex

It prints a BRIEF path. Read that file and follow it exactly: write the recap JSON to the RECAP_OUT path it names, then run the save command it gives. Report the result in the voice the brief specifies. Do not wrap unless asked.
%s""" % (MARK_START, bin_cmd, MARK_END)


def _cursor_rule(bin_cmd: str) -> str:
    return """---
description: Wrap up / map this session with Cartographer
alwaysApply: false
---
When the user says "wrap", "wrap up", "map this session" or "cartographer", run `"%s" wrap --agent cursor` in the terminal. It prints a BRIEF path. Read that file and follow it exactly: write the recap JSON to the RECAP_OUT path it names, then run the save command it gives, then summarize for the user in the voice the brief specifies.
""" % bin_cmd


# ---------------------------------------------------------------- utils

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
