"""Generic transcript adapter.

For agents without a dedicated adapter (Gemini CLI, Copilot, Aider, a chat
export). Accepts:

* JSON: `{"messages": [{"role", "content", "timestamp"?}, ...]}` or a bare list
* JSONL: one such message per line
* Markdown / text: turns introduced by a role label at line start, e.g.
  `**User:**`, `## Assistant`, `User:`, `Human:`, `> user`, `### Agent`

Tool calls are recognized when a message has `tool_calls` / `tool` fields or
the role is `tool`.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from .base import ERROR, PROMPT, REPLY, TOOL, Adapter, Event, Session, SessionRef, code_blocks, parse_ts, paths_in

ROLE_RE = re.compile(r"^\s*(?:[#>*_\-]+\s*)*(user|human|you|me|assistant|agent|ai|model|claude|gpt|gemini|codex|cursor|tool)\s*[:：]?\s*(?:[*_]+)?\s*$",
                     re.I | re.M)
USER_ROLES = {"user", "human", "you", "me"}


class GenericAdapter(Adapter):
    name = "generic"
    label = "Generic transcript"

    def available(self) -> bool:
        return True

    def load(self, ref: SessionRef) -> Session:
        s = Session(agent=self.name, id=ref.id, path=ref.path, cwd=ref.cwd)
        with open(ref.path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        messages = self._parse_json(raw) or self._parse_jsonl(raw) or self._parse_text(raw)
        for m in messages:
            role = str(m.get("role") or "").lower()
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
            text = str(content or "").strip()
            ts = parse_ts(m.get("timestamp") or m.get("ts") or m.get("created_at"))
            if role in USER_ROLES and text:
                s.events.append(Event(ts, PROMPT, text, meta={"code_blocks": code_blocks(text), "paths": paths_in(text)}))
            elif role == "tool":
                s.events.append(Event(ts, ERROR if m.get("is_error") else TOOL, text[:300], tool=str(m.get("name") or "tool")))
            elif role:
                for call in m.get("tool_calls") or []:
                    fn = (call.get("function") or call) if isinstance(call, dict) else {}
                    s.events.append(Event(ts, TOOL, str(fn.get("arguments") or "")[:300], tool=str(fn.get("name") or "tool")))
                if text:
                    s.events.append(Event(ts, REPLY, text))
        return s

    @staticmethod
    def _parse_json(raw: str) -> Optional[List[dict]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            data = data.get("messages") or data.get("conversation") or data.get("history")
        return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else None

    @staticmethod
    def _parse_jsonl(raw: str) -> Optional[List[dict]]:
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                return None
            if isinstance(m, dict):
                out.append(m)
        return out or None

    @staticmethod
    def _parse_text(raw: str) -> List[dict]:
        out, pos, role = [], None, None
        for m in ROLE_RE.finditer(raw):
            if role is not None:
                out.append({"role": role, "content": raw[pos:m.start()].strip()})
            role, pos = m.group(1).lower(), m.end()
        if role is not None:
            out.append({"role": role, "content": raw[pos:].strip()})
        for m in out:
            if m["role"] not in USER_ROLES and m["role"] != "tool":
                m["role"] = "assistant"
        return out
