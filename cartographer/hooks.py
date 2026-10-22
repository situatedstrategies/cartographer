"""Installation into each agent, and the hooks that make auto-wrap work.

* Claude Code: skills copied to ~/.claude/skills; auto mode adds a
  `SessionEnd` hook to ~/.claude/settings.json.
* Codex CLI: a block in ~/.codex/AGENTS.md so "wrap up" is understood. Codex
  has no session-end event, so auto mode means running `cartographer sweep`
  periodically (a cron line is printed).
* Cursor: /wrap, /replay, /complete as .cursor/commands, plus a project rule
  (.cursor/rules/cartographer.mdc) for the same thing said in words; auto mode adds a
  `stop` hook to ~/.cursor/hooks.json.

Hook payloads are only ever used to find the session; nothing in them is run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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


def launcher() -> List[str]:
    """How a hook runs the CLI: the script itself on POSIX, the interpreter plus the script on Windows."""
    return [bin_path()] if os.name != "nt" else [sys.executable, bin_path()]


def command_prefix() -> str:
    """The launcher as a quoted shell fragment, for hook commands, rules and hints."""
    return " ".join('"%s"' % p.replace("\\", "/") for p in launcher())


def self_install() -> str:
    """Copy this checkout to ~/.cartographer/app and put a `cartographer` command in ~/.local/bin."""
    src = package_root()
    if os.path.abspath(src) != os.path.abspath(APP_DIR):
        if os.path.isdir(APP_DIR):
            shutil.rmtree(APP_DIR)
        shutil.copytree(src, APP_DIR, ignore=shutil.ignore_patterns("__pycache__", ".git", "tests", "demo", "site", "*.pyc"))
    target = os.path.join(APP_DIR, "bin", "cartographer")
    os.chmod(target, 0o755)
    link_dir = os.path.join(HOME, ".local", "bin")
    try:
        os.makedirs(link_dir, exist_ok=True)
        if os.name == "nt":
            write_shims(link_dir, target)
        else:
            link = os.path.join(link_dir, "cartographer")
            if os.path.islink(link) or os.path.exists(link):
                os.remove(link)
            os.symlink(target, link)
    except OSError:
        pass
    return target


def write_shims(link_dir: str, target: str, python: Optional[str] = None) -> List[str]:
    """Windows has no symlinks for ordinary users: a .cmd for PowerShell and cmd, and an extensionless
    sh script for Git Bash, which is what Claude Code uses on Windows."""
    python = python or sys.executable
    cmd = os.path.join(link_dir, "cartographer.cmd")
    with open(cmd, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write('@echo off\n"%s" "%s" %%*\n' % (python, target))
    sh = os.path.join(link_dir, "cartographer")
    with open(sh, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (python.replace("\\", "/"), target.replace("\\", "/")))
    return [cmd, sh]


def sweep_hint(bin_cmd: str) -> str:
    idle = config.load()["wrap"]["idle_minutes"]
    if os.name == "nt":
        return ("Codex has no session-end event: run `%s sweep` every 20 min to wrap sessions idle for %d min, e.g. "
                "schtasks /create /sc minute /mo 20 /tn Cartographer /tr '%s sweep'" % (bin_cmd, idle, bin_cmd))
    return ("Codex has no session-end event: run `%s sweep` every 20 min to wrap sessions idle for %d min, e.g. crontab -e → "
            "*/20 * * * * %s sweep >> \"%s\" 2>&1" % (bin_cmd, idle, bin_cmd, os.path.join(config.HOME, "sweep.log")))


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
    for name in ("wrap", "replay", "complete", "cartographer-setup"):
        shutil.copytree(os.path.join(src, name), os.path.join(dst, name), dirs_exist_ok=True)
    msgs = ["Claude Code: installed /wrap, /replay, /complete and /cartographer-setup into %s" % dst]
    settings_path = os.path.join(HOME, ".claude", "settings.json")
    settings = store.read_json(settings_path, {})
    hooks = settings.setdefault("hooks", {})
    entries = [e for e in (hooks.get("SessionEnd") or []) if not _ours(e)]
    if auto:
        entries.append({"hooks": [{"type": "command", "command": '%s hook claude-code' % bin_cmd, "timeout": 20}]})
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
    prompts = os.path.join(home, "prompts")
    for name in COMMANDS:
        _write_text(os.path.join(prompts, name + ".md"), command_text(name, "codex", bin_cmd))
    msgs.append("Codex: /wrap, /replay and /complete installed into %s" % prompts)
    msgs.append(sweep_hint(bin_cmd) if auto else "Codex: manual mode; type /wrap at the end of a session")
    return msgs


def install_cursor(auto: bool, bin_cmd: str, project: Optional[str] = None) -> List[str]:
    rule = _cursor_rule(bin_cmd)
    cmd_dirs = [os.path.join(HOME, ".cursor", "commands")] + ([os.path.join(project, ".cursor", "commands")] if project else [])
    for d in cmd_dirs:
        for name in COMMANDS:
            _write_text(os.path.join(d, name + ".md"), command_text(name, "cursor", bin_cmd))
    msgs = ["Cursor: /wrap, /replay and /complete installed into %s" % " and ".join(cmd_dirs)]
    if project:
        path = os.path.join(project, ".cursor", "rules", "cartographer.mdc")
        _write_text(path, rule)
        msgs.append("Cursor: project rule written to %s (so 'wrap up' in plain words works too)" % path)
    else:
        msgs.append("Cursor: rerun with --project <repo> to add a rule that also answers 'wrap up' said in plain words")
    if auto:
        hooks_path = os.path.join(HOME, ".cursor", "hooks.json")
        data = store.read_json(hooks_path, {})
        data.setdefault("version", 1)
        stops = [h for h in (data.setdefault("hooks", {}).get("stop") or []) if not _ours(h)]
        stops.append({"command": '%s hook cursor' % bin_cmd})
        data["hooks"]["stop"] = stops
        store.write_json(hooks_path, data, indent=2)
        msgs.append("Cursor: stop hook added to %s (auto-wrap on)" % hooks_path)
    else:
        msgs.append("Cursor: manual mode; type /wrap at the end of a session")
    return msgs


# ---------------------------------------------------------------- hooks

def handle(agent: str, payload: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Called by `cartographer hook <agent>` with the agent's JSON payload."""
    sid = next((str(payload[k]) for k in ("session_id", "conversation_id", "thread_id", "thread-id", "id") if payload.get(k)), None)
    item = {"agent": agent, "session_id": sid, "cwd": payload.get("cwd") or (payload.get("workspace_roots") or [None])[0],
            "transcript": payload.get("transcript_path"), "event": payload.get("hook_event_name") or payload.get("type")}
    # Only Claude Code and Cursor say a session actually ended; everything else is picked up by `sweep`.
    if cfg["wrap"]["mode"] == "auto" and agent in ("claude-code", "cursor") and sid:
        cmd = launcher() + ["wrap", "--run", "--agent", agent, "--session", sid]
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

When the user says "wrap", "wrap up", "map this session", or "cartographer" without using the /wrap prompt, run:

    %s wrap --agent codex

It prints a BRIEF path. Read that file and follow it exactly: write the recap JSON to the RECAP_OUT path it names, then run the save command it gives. Report the result in the voice the brief specifies. Do not wrap unless asked. The /wrap, /replay and /complete prompts in ~/.codex/prompts carry the full steps.
%s""" % (MARK_START, bin_cmd, MARK_END)


COMMANDS = ("wrap", "replay", "complete")
# The same three commands in every agent. Claude Code gets them as skills (skills/*/SKILL.md); Cursor reads
# Markdown commands from .cursor/commands/<name>.md (global under ~/.cursor, or per project); Codex reads
# custom prompts from $CODEX_HOME/prompts/<name>.md. The text below is the skill, condensed, with the agent
# name filled in so `wrap` finds that agent's session.


def command_text(name: str, agent: str, bin_cmd: str) -> str:
    c = bin_cmd
    if name == "wrap":
        return """# /wrap: map this session with Cartographer

You are Cartographer. The map is of how the user built, not what changed. Anything the user typed after /wrap is the project name; `--session <id>` picks another session (`%(c)s sessions` lists them); `--force` redoes an already wrapped or very short session.

1. Run in the terminal: `%(c)s wrap --agent %(agent)s --project "<project name, or omit>"`. It prints BRIEF, RECAP_OUT and the session facts. If it starts with `SKIPPED:`, tell the user why and offer `--force`. If it prints a `NOTE:` line, repeat it to the user.
2. Read the BRIEF file and follow it exactly: the reader profile, the voice, the language notes, the prompt readings, the rules, the schema and the timeline are all in it. Write the recap JSON to RECAP_OUT with every placeholder replaced. Every move cites the timeline items it rests on; no praise words.
3. Run `%(c)s save "<RECAP_OUT>"`. If it lists problems, fix the JSON and run it again. It prints SAVED and REPLAY paths.
4. Tell the user, in the voice the brief specifies, as a short story in second person: one line on what happened, three to five beats, one observation about how they build, coaching if the brief asked for it, and the REPLAY path.
""" % {"c": c, "agent": agent}
    if name == "replay":
        return """# /replay: watch the build

Anything the user typed after /replay is the project name.

1. If no project was given, run `%(c)s projects`, show the list and ask which one (or take the only one).
2. Run `%(c)s render --project "<project>"`.
3. Read the recaps under ~/.cartographer/sessions/<slug>/ and tell the story of the build in five to eight lines, in second person, in the voice the user configured (`%(c)s config show`, the `effective.voice` line): how it started, the moves that turned it, the biggest setback and how they responded, and what repeats across sessions.
4. Offer to open the replay: `%(c)s open "<project>"`. Inside it, Replay the build tells the story one move at a time; Story/Map and Plain/Native are the switches in the toolbar.
""" % {"c": c}
    if name == "complete":
        return """# /complete: mark a version done, then appraise it honestly

Anything the user typed after /complete is the project name, optionally with `--version <name>`. With no project, the folder you are in is the project.

1. Run `%(c)s projects`. If the version being closed has no desired outcome declared, ask the user one question: what did "done" mean for this version, in their words? Then `%(c)s goal "<their words>" --project "<project>"`.
2. Ask two things: the result (shipped, partial or abandoned) and, in one sentence, what actually happened. Then run `%(c)s complete --project "<project>" --result <result> --actual "<their sentence>"`. It prints BRIEF and RECAP_OUT.
3. Read the BRIEF: the yardstick, the reader profile, the rules, and every session's moves with their evidence. Write the appraisal JSON to RECAP_OUT. Every item cites session and move ids; technical implications, not adjectives; minutes where the record has them; "unclear from the record" where it does not. The user asked for an appraisal, not a celebration.
4. Run `%(c)s save "<RECAP_OUT>"`; fix and rerun if it lists problems.
5. Tell the user, in the configured voice: the verdict; what got them there; what cost them, with minutes; what was carried into the result and what it will cost later; how they prompted and what it did; then the REPLAY path.
""" % {"c": c}
    raise ValueError(name)


def _cursor_rule(bin_cmd: str) -> str:
    return """---
description: Wrap up / map this session with Cartographer
alwaysApply: false
---
When the user says "wrap", "wrap up", "map this session" or "cartographer" without using the /wrap command, do exactly what the /wrap command in .cursor/commands/wrap.md says: run `%s wrap --agent cursor` in the terminal, read the BRIEF file it names and follow it exactly, write the recap JSON to RECAP_OUT, run the save command, then summarize for the user in the voice the brief specifies.
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
