"""OpenAI Codex CLI adapter.

Codex CLI stores "rollouts" as JSONL under ~/.codex/sessions/YYYY/MM/DD/
(and ~/.codex/archived_sessions/). Two layouts exist:

* current (0.4x+): every line is `{"timestamp", "type", "payload"}` where
  type is session_meta | response_item | event_msg | turn_context | compacted.
* legacy: the first line is session metadata, later lines are raw response
  items (`{"type": "message", ...}`, `{"type": "function_call", ...}`).

Both are handled. The format is not a public contract; anything unknown is
skipped rather than failing.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional

from .base import (BRANCH, ERROR, NOTE, PROMPT, REPLY, TOOL, Adapter, Event, Session,
                   SessionRef, code_blocks, parse_ts, paths_in, strip_tags)

CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
WRAPPER_TAGS = ("environment_context", "user_instructions", "permissions_instructions", "turn_aborted", "collab_context")
SHELL_TOOLS = {"shell", "shell_command", "local_shell", "container.exec", "exec_command", "bash"}
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)
EXIT_RE = re.compile(r"exit(?:ed with)? code[:\s]+(\d+)", re.I)


class CodexAdapter(Adapter):
    name = "codex"
    label = "Codex CLI"
    headless = ["codex", "exec", "--full-auto"]

    def __init__(self, home: Optional[str] = None):
        self.home = home or CODEX_HOME

    def _dirs(self):
        return [os.path.join(self.home, "sessions"), os.path.join(self.home, "archived_sessions")]

    def available(self) -> bool:
        return any(os.path.isdir(d) for d in self._dirs())

    def list_sessions(self, cwd: Optional[str] = None, limit: Optional[int] = None) -> List[SessionRef]:
        refs = []
        for d in self._dirs():
            for path in glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True):
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                meta = self._peek(path)
                if cwd and os.path.abspath(cwd) != os.path.abspath(meta.get("cwd") or ""):
                    continue
                sid = meta.get("id") or self._id_from_name(path)
                refs.append(SessionRef(self.name, sid, path, st.st_mtime, cwd=meta.get("cwd"), size=st.st_size))
        refs.sort(key=lambda r: -r.mtime)
        return refs[:limit] if limit else refs

    @staticmethod
    def _id_from_name(path: str) -> str:
        base = os.path.splitext(os.path.basename(path))[0]
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", base)
        return m.group(1) if m else base

    def _peek(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i > 5:
                        break
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get("type") == "session_meta":
                        return r.get("payload") or {}
                    if "id" in r and ("instructions" in r or "git" in r or "cwd" in r):
                        return r
        except OSError:
            pass
        return {}

    def load(self, ref: SessionRef) -> Session:
        s = Session(agent=self.name, id=ref.id, path=ref.path)
        calls: Dict[str, str] = {}  # call_id -> tool name
        last_branch = None
        with open(ref.path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = parse_ts(r.get("timestamp"))
                kind = r.get("type")
                payload = r.get("payload") if isinstance(r.get("payload"), dict) else None

                if kind == "session_meta" or (payload is None and "id" in r and ("instructions" in r or "git" in r)):
                    meta = payload or r
                    s.cwd = s.cwd or meta.get("cwd")
                    git = meta.get("git") or {}
                    if git.get("branch"):
                        s.branch = s.branch or git["branch"]
                        last_branch = git["branch"]
                    if git.get("repository_url"):
                        s.meta["remote"] = git["repository_url"]
                    s.meta["cli_version"] = meta.get("cli_version")
                    continue
                if kind == "turn_context" and payload:
                    s.cwd = s.cwd or payload.get("cwd")
                    s.model = s.model or payload.get("model")
                    continue
                if kind == "compacted":
                    s.events.append(Event(ts, NOTE, "context compacted"))
                    continue
                if kind == "event_msg" and payload:
                    pt = payload.get("type")
                    if pt == "exec_command_end" and payload.get("exit_code") not in (None, 0):
                        err = (payload.get("stderr") or payload.get("aggregated_output") or "")[:600]
                        s.events.append(Event(ts, ERROR, err, tool="shell"))
                    elif pt == "git_branch_changed" and payload.get("branch"):
                        s.events.append(Event(ts, BRANCH, payload["branch"], meta={"from": last_branch}))
                        last_branch = payload["branch"]
                    continue

                item = payload if kind == "response_item" else (r if payload is None else None)
                if not item or not isinstance(item, dict):
                    continue
                it = item.get("type")
                if it == "message":
                    role = item.get("role")
                    text = self._text(item.get("content"))
                    if role == "user":
                        ev = self._prompt(ts, text)
                        if ev:
                            s.events.append(ev)
                    elif role == "assistant" and text.strip():
                        s.events.append(Event(ts, REPLY, text))
                elif it in ("function_call", "custom_tool_call", "local_shell_call"):
                    ev = self._tool(ts, item)
                    calls[item.get("call_id") or ""] = ev.tool
                    s.events.append(ev)
                elif it in ("function_call_output", "custom_tool_call_output"):
                    err = self._error_from_output(item.get("output"))
                    if err is not None:
                        s.events.append(Event(ts, ERROR, err, tool=calls.get(item.get("call_id") or "", "tool")))
        s.meta["last_branch"] = last_branch
        return s

    @staticmethod
    def _text(content) -> str:
        if isinstance(content, str):
            return content
        parts = []
        for c in content or []:
            if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text"):
                parts.append(c.get("text", ""))
        return "\n".join(parts)

    def _prompt(self, ts, text: str) -> Optional[Event]:
        text = strip_tags(text, WRAPPER_TAGS).strip()
        if not text or text.startswith("# AGENTS.md") or text.startswith("<") and text.endswith(">"):
            return None
        return Event(ts, PROMPT, text, meta={"code_blocks": code_blocks(text), "paths": paths_in(text)})

    def _tool(self, ts, item: dict) -> Event:
        name = item.get("name") or ("shell" if item.get("type") == "local_shell_call" else "tool")
        args = item.get("arguments") or item.get("input") or ""
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except json.JSONDecodeError:
                parsed = {"input": args}
        else:
            parsed = args or {}
        if item.get("type") == "local_shell_call":
            parsed = (item.get("action") or {})
        files: List[str] = []
        text = ""
        if name in SHELL_TOOLS or "command" in parsed:
            cmd = parsed.get("command") or parsed.get("cmd") or ""
            text = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            name = "shell"
        elif name == "apply_patch" or "*** Begin Patch" in str(parsed.get("input", "")):
            patch = parsed.get("input") or parsed.get("patch") or ""
            files = PATCH_FILE_RE.findall(patch)
            text = ", ".join(files)[:300]
            name = "apply_patch"
        else:
            for key in ("path", "file_path", "query", "pattern", "url", "prompt"):
                if parsed.get(key):
                    text = str(parsed[key])
                    if key in ("path", "file_path"):
                        files = [parsed[key]]
                    break
        meta = {"command": text[:300]} if name == "shell" else {}
        return Event(ts, TOOL, text[:300], tool=name, files=files, meta=meta)

    @staticmethod
    def _error_from_output(output) -> Optional[str]:
        if output is None:
            return None
        if isinstance(output, dict):
            meta = output.get("metadata") or {}
            if meta.get("exit_code") not in (None, 0):
                return str(output.get("output", ""))[-600:]
            return None
        text = str(output)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                meta = parsed.get("metadata") or {}
                if meta.get("exit_code") not in (None, 0):
                    return str(parsed.get("output", ""))[-600:]
                return None
        except (json.JSONDecodeError, TypeError):
            pass
        m = EXIT_RE.search(text[:200])
        if m and m.group(1) != "0":
            return text[-600:]
        if text.lstrip().lower().startswith(("error:", "traceback", "fatal:")):
            return text[-600:]
        return None
