"""Adapter registry."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from .base import Adapter, Session, SessionRef
from .claude_code import ClaudeCodeAdapter
from .codex_cli import CodexAdapter
from .cursor import CursorAdapter
from .generic import GenericAdapter

ALIASES = {
    "claude": "claude-code", "claude_code": "claude-code", "claudecode": "claude-code",
    "codex-cli": "codex", "codex_cli": "codex", "openai": "codex",
    "cursor-agent": "cursor", "composer": "cursor",
    "file": "generic", "export": "generic", "md": "generic",
}


def registry() -> Dict[str, Adapter]:
    ads = [ClaudeCodeAdapter(), CodexAdapter(), CursorAdapter(), GenericAdapter()]
    return {a.name: a for a in ads}


def get(name: str) -> Adapter:
    key = ALIASES.get(name.lower(), name.lower())
    reg = registry()
    if key not in reg:
        raise KeyError("unknown agent %r; known: %s" % (name, ", ".join(reg)))
    return reg[key]


def installed() -> List[Adapter]:
    return [a for a in registry().values() if a.name != "generic" and a.available()]


def list_all(cwd: Optional[str] = None, agent: Optional[str] = None, limit: Optional[int] = None) -> List[SessionRef]:
    ads = [get(agent)] if agent else installed()
    refs: List[SessionRef] = []
    for a in ads:
        refs.extend(a.list_sessions(cwd=cwd))
    refs.sort(key=lambda r: -r.mtime)
    return refs[:limit] if limit else refs


def resolve(session_id: Optional[str] = None, transcript: Optional[str] = None,
            agent: Optional[str] = None, cwd: Optional[str] = None) -> Tuple[Adapter, SessionRef]:
    """Find the session to work on, in this order: explicit transcript path,
    explicit session id, newest session for cwd, newest session anywhere."""
    if transcript:
        a = get(agent) if agent else _sniff(transcript)
        ref = SessionRef(a.name, os.path.splitext(os.path.basename(transcript))[0], transcript,
                         os.path.getmtime(transcript), cwd=cwd)
        return a, ref
    if session_id and not session_id.startswith("$"):
        for a in ([get(agent)] if agent else installed()):
            ref = a.find(session_id)
            if ref:
                return a, ref
        raise LookupError("no session matching %r" % session_id)
    refs = list_all(cwd=cwd or os.getcwd(), agent=agent, limit=1) or list_all(agent=agent, limit=1)
    if not refs:
        raise LookupError("no sessions found for any installed agent")
    return get(refs[0].agent), refs[0]


def _sniff(path: str) -> Adapter:
    """Guess the adapter for a transcript file from its location and shape."""
    p = os.path.abspath(path)
    if "/.claude/projects/" in p:
        return get("claude-code")
    if "/.codex/" in p:
        return get("codex")
    if p.endswith(".vscdb"):
        return get("cursor")
    try:
        with open(p, encoding="utf-8") as fh:
            head = fh.read(4000)
    except OSError:
        return get("generic")
    if '"session_meta"' in head or '"response_item"' in head:
        return get("codex")
    if '"isSidechain"' in head or '"parentUuid"' in head:
        return get("claude-code")
    return get("generic")


def load(session_id: Optional[str] = None, transcript: Optional[str] = None,
         agent: Optional[str] = None, cwd: Optional[str] = None) -> Session:
    a, ref = resolve(session_id, transcript, agent, cwd)
    return a.load(ref)
