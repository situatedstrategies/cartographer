"""Shared session model every adapter produces.

An adapter turns one coding agent's on-disk history into a `Session`: an
ordered list of `Event`s in a common vocabulary. Everything downstream
(digest, brief, recap) works only on this model, which is what makes the
mapping agent-agnostic.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# Event kinds. Keep this list small: the map vocabulary is built on top of it.
PROMPT = "prompt"    # a message from the human that steers the agent
REPLY = "reply"      # a natural-language message from the agent
TOOL = "tool"        # the agent ran a tool (shell, edit, search, ...)
ERROR = "error"      # a tool failed, a command exited non-zero, a build broke
BRANCH = "branch"    # the git branch changed mid-session
NOTE = "note"        # anything else worth a line (model switch, compaction, ...)

FENCE_RE = re.compile(r"```([A-Za-z0-9_+#.-]*)[^\n]*\n(.*?)```", re.S)
PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})(?![\w/])")


@dataclass
class Event:
    ts: Optional[datetime]
    kind: str
    text: str = ""
    tool: str = ""
    files: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRef:
    """A session the adapter can load, listed without parsing it fully."""
    agent: str
    id: str
    path: str
    mtime: float
    cwd: Optional[str] = None
    title: Optional[str] = None
    size: int = 0


@dataclass
class Session:
    agent: str
    id: str
    path: str
    cwd: Optional[str] = None
    title: Optional[str] = None
    model: Optional[str] = None
    branch: Optional[str] = None
    events: List[Event] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def started(self) -> Optional[datetime]:
        for e in self.events:
            if e.ts:
                return e.ts
        return None

    @property
    def ended(self) -> Optional[datetime]:
        for e in reversed(self.events):
            if e.ts:
                return e.ts
        return None


class Adapter:
    """Interface every agent adapter implements."""

    name = "base"          # machine name used in config and CLI flags
    label = "Base"         # human name
    headless: List[str] = []  # command that runs the agent non-interactively with a prompt

    def available(self) -> bool:
        return False

    def list_sessions(self, cwd: Optional[str] = None, limit: Optional[int] = None) -> List[SessionRef]:
        return []

    def find(self, session_id: str) -> Optional[SessionRef]:
        sid = session_id.lower()
        for ref in self.list_sessions():
            if ref.id.lower() == sid or ref.id.lower().startswith(sid):
                return ref
        return None

    def load(self, ref: SessionRef) -> Session:
        raise NotImplementedError

    def load_path(self, path: str) -> Session:
        return self.load(SessionRef(self.name, os.path.splitext(os.path.basename(path))[0], path, os.path.getmtime(path)))


# ---------------------------------------------------------------- helpers

def parse_ts(value: Any) -> Optional[datetime]:
    """Accept ISO strings, epoch seconds or epoch milliseconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        if value > 1e12:
            value = value / 1000.0
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return parse_ts(int(s))
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def code_blocks(text: str) -> List[Dict[str, Any]]:
    """Fenced code blocks in a message: language tag + line count."""
    out = []
    for lang, body in FENCE_RE.findall(text or ""):
        out.append({"lang": (lang or "").lower(), "lines": body.count("\n") + 1})
    return out


def paths_in(text: str) -> List[str]:
    seen, out = set(), []
    for p in PATH_RE.findall(text or ""):
        if p not in seen and not p.startswith(("http", "www.")):
            seen.add(p)
            out.append(p)
    return out


def strip_tags(text: str, tags: Iterable[str]) -> str:
    for tag in tags:
        text = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), "", text, flags=re.S)
    return text


def sort_events(events: List[Event]) -> List[Event]:
    """Stable sort by timestamp; events without one keep their position."""
    indexed = list(enumerate(events))
    last = None
    keys = []
    for i, e in indexed:
        if e.ts:
            last = e.ts
        keys.append((last or datetime.min.replace(tzinfo=timezone.utc), i))
    return [e for _, e in sorted(zip(keys, events), key=lambda x: x[0])]
