"""Claude Code adapter.

Claude Code writes one JSONL file per session under
~/.claude/projects/<encoded cwd>/<session id>.jsonl. Each line is a record;
the ones that matter here are `user` and `assistant` messages whose
`message.content` is a list of blocks (text, tool_use, tool_result).
Records also carry `cwd`, `gitBranch`, `isSidechain` (subagent traffic) and
timestamps. Format verified against Claude Code 2.1.x.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import List, Optional

from .base import (BRANCH, ERROR, NOTE, PROMPT, REPLY, TOOL, Adapter, Event, Session,
                   SessionRef, code_blocks, parse_ts, paths_in, strip_tags)

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
NOISE_TAGS = ("system-reminder", "command-name", "command-message", "command-args",
              "local-command-stdout", "local-command-caveat", "ide_opened_file", "ide_selection")
PASTED_RE = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
COMMAND_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
# A message the user sends while the agent is still working is not a user turn in the transcript: Claude Code
# hands it to the agent inside a system reminder, kept on the record under `rendered`.
MID_TURN_RE = re.compile(r"The user sent a new message while you were working:\n(.*?)\n\nThis is how Claude Code surfaces", re.S)
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read"}


def encode_cwd(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"
    label = "Claude Code"
    headless = ["claude", "-p", "--permission-mode", "acceptEdits"]

    def __init__(self, projects_dir: Optional[str] = None):
        self.projects_dir = projects_dir or PROJECTS

    def available(self) -> bool:
        return os.path.isdir(self.projects_dir)

    def list_sessions(self, cwd: Optional[str] = None, limit: Optional[int] = None) -> List[SessionRef]:
        if cwd:
            pattern = os.path.join(self.projects_dir, encode_cwd(os.path.abspath(cwd)), "*.jsonl")
        else:
            pattern = os.path.join(self.projects_dir, "*", "*.jsonl")
        refs = []
        for path in glob.glob(pattern):
            if "/subagents/" in path:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            refs.append(SessionRef(self.name, os.path.splitext(os.path.basename(path))[0], path, st.st_mtime, size=st.st_size))
        refs.sort(key=lambda r: -r.mtime)
        if limit:
            refs = refs[:limit]
        for ref in refs:
            ref.cwd, ref.title = self._peek(ref.path)
        return refs

    def find(self, session_id: str) -> Optional[SessionRef]:
        hits = [h for h in glob.glob(os.path.join(self.projects_dir, "*", "%s*.jsonl" % session_id)) if "/subagents/" not in h]
        if hits:
            path = hits[0]
            ref = SessionRef(self.name, os.path.splitext(os.path.basename(path))[0], path, os.path.getmtime(path))
            ref.cwd, ref.title = self._peek(path)
            return ref
        return None

    def _peek(self, path: str):
        cwd = title = None
        try:
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i > 400 and cwd:
                        break
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = cwd or r.get("cwd")
                    if r.get("type") == "custom-title":
                        title = r.get("customTitle") or title
        except OSError:
            pass
        return cwd, title

    def load(self, ref: SessionRef) -> Session:
        s = Session(agent=self.name, id=ref.id, path=ref.path)
        tool_names = {}
        last_branch = None
        with open(ref.path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = r.get("type")
                if kind == "custom-title":
                    s.title = r.get("customTitle") or s.title
                    continue
                if kind == "summary":  # Claude Code's auto summary; a user-set title wins
                    s.title = s.title or r.get("summary")
                    continue
                if kind == "system" and r.get("subtype") == "compact_boundary":
                    s.events.append(Event(parse_ts(r.get("timestamp")), NOTE, "context compacted"))
                    continue
                if r.get("isSidechain"):
                    s.meta["subagent_events"] = s.meta.get("subagent_events", 0) + 1
                    continue
                ts = parse_ts(r.get("timestamp"))
                for item in r.get("rendered") or []:  # any record type can carry one (seen on "attachment" records)
                    for m in MID_TURN_RE.finditer(str(item.get("content") or "") if isinstance(item, dict) else ""):
                        ev = self._prompt(ts, m.group(1))
                        if ev:
                            ev.meta["mid_turn"] = True
                            s.events.append(ev)
                if kind not in ("user", "assistant"):
                    continue
                s.cwd = s.cwd or r.get("cwd")
                branch = r.get("gitBranch")
                if branch == "HEAD":  # Claude Code writes HEAD when the folder isn't a repo
                    branch = None
                if branch and branch != last_branch:
                    if last_branch is not None:
                        s.events.append(Event(ts, BRANCH, branch, meta={"from": last_branch}))
                    last_branch = branch
                    s.branch = s.branch or branch
                msg = r.get("message") or {}
                if kind == "assistant" and msg.get("model"):
                    s.model = s.model or msg["model"]
                content = msg.get("content")
                blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if kind == "user" and bt == "text":
                        if r.get("isMeta") or (r.get("origin") or {}).get("kind") not in (None, "human"):
                            continue
                        ev = self._prompt(ts, b.get("text", ""))
                        if ev:
                            s.events.append(ev)
                    elif kind == "user" and bt == "tool_result":
                        if b.get("is_error"):
                            body = b.get("content")
                            if isinstance(body, list):
                                body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                            s.events.append(Event(ts, ERROR, str(body or "")[:600], tool=tool_names.get(b.get("tool_use_id"), "tool")))
                    elif kind == "assistant" and bt == "text" and (b.get("text") or "").strip():
                        s.events.append(Event(ts, REPLY, b["text"]))
                    elif kind == "assistant" and bt == "tool_use":
                        name = b.get("name", "?")
                        tool_names[b.get("id")] = name
                        s.events.append(self._tool(ts, name, b.get("input") or {}))
        s.meta["last_branch"] = last_branch
        return s

    def _prompt(self, ts, text: str) -> Optional[Event]:
        pasted = PASTED_RE.findall(text)
        command = COMMAND_RE.search(text)
        text = strip_tags(text, NOISE_TAGS)
        text = PASTED_RE.sub(lambda m: m.group(1), text).strip()
        if not text:  # a bare slash command is worth a line on the timeline, not a prompt
            return Event(ts, NOTE, "ran " + command.group(1).strip()) if command and command.group(1).strip() else None
        meta = {"code_blocks": code_blocks(text), "paths": paths_in(text)}
        if pasted:
            meta["pasted"] = True
        return Event(ts, PROMPT, text, meta=meta)

    def _tool(self, ts, name: str, inp: dict) -> Event:
        files = []
        if name in FILE_TOOLS and inp.get("file_path"):
            files = [inp["file_path"]]
        text = ""
        for key in ("description", "file_path", "path", "command", "pattern", "url", "query", "prompt", "skill", "notebook_path"):
            if inp.get(key):
                text = str(inp[key])
                break
        meta = {}
        if name in READ_TOOLS and inp.get("file_path"):
            meta["read"] = inp["file_path"]
        if name == "Bash" and inp.get("command"):
            meta["command"] = str(inp["command"])[:300]
        if name in ("Agent", "Task"):
            meta["subagent"] = True
        return Event(ts, TOOL, text[:300], tool=name, files=files, meta=meta)
