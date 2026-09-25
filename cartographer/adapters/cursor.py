"""Cursor adapter.

Cursor keeps its chat history in SQLite, not in files:

* Global: <UserData>/User/globalStorage/state.vscdb, table `cursorDiskKV`.
  - `composerData:<composerId>` -> one Composer/Agent conversation
    (name, createdAt, and either `conversation` inline or
    `fullConversationHeadersOnly: [{bubbleId, type}]`).
  - `bubbleId:<composerId>:<bubbleId>` -> one message. `type` 1 = user,
    2 = assistant. Tool calls live in `toolFormerData`.
* Per workspace: <UserData>/User/workspaceStorage/<hash>/workspace.json
  (`folder`) and state.vscdb `ItemTable` key `composer.composerData`
  (`allComposers`) which ties composers to a folder.

<UserData> is ~/Library/Application Support/Cursor on macOS,
~/.config/Cursor on Linux, %APPDATA%/Cursor on Windows. Cursor's schema is
internal and shifts between releases; this adapter reads defensively and
returns whatever it recognizes.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from .base import (ERROR, PROMPT, REPLY, TOOL, Adapter, Event, Session, SessionRef,
                   code_blocks, parse_ts, paths_in)

FILE_KEYS = ("target_file", "relative_workspace_path", "file_path", "path", "targetFile", "file")
EDIT_TOOLS = {"edit_file", "search_replace", "write", "MultiEdit", "delete_file", "create_file", "edit"}


def default_user_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor/User")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA", ""), "Cursor", "User")
    return os.path.expanduser("~/.config/Cursor/User")


def _open(path: str) -> sqlite3.Connection:
    # Read-only + immutable so a running Cursor holding the DB doesn't block us.
    return sqlite3.connect("file:%s?mode=ro&immutable=1" % path, uri=True)


def _loads(value) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


class CursorAdapter(Adapter):
    name = "cursor"
    label = "Cursor"
    headless = ["cursor-agent", "-p", "--force"]

    def __init__(self, user_dir: Optional[str] = None):
        self.user_dir = user_dir or default_user_dir()
        self.global_db = os.path.join(self.user_dir, "globalStorage", "state.vscdb")
        self._folders: Optional[Dict[str, str]] = None

    def available(self) -> bool:
        return os.path.isfile(self.global_db)

    # composerId -> workspace folder, from every workspaceStorage/<hash>
    def folders(self) -> Dict[str, str]:
        if self._folders is not None:
            return self._folders
        out: Dict[str, str] = {}
        for ws in glob.glob(os.path.join(self.user_dir, "workspaceStorage", "*")):
            folder = None
            try:
                with open(os.path.join(ws, "workspace.json"), encoding="utf-8") as fh:
                    uri = (json.load(fh).get("folder") or "")
                if uri.startswith("file:"):
                    folder = unquote(urlparse(uri).path)
            except (OSError, json.JSONDecodeError, ValueError):
                pass
            db = os.path.join(ws, "state.vscdb")
            if not folder or not os.path.isfile(db):
                continue
            try:
                con = _open(db)
                row = con.execute("SELECT value FROM ItemTable WHERE key='composer.composerData'").fetchone()
                con.close()
            except sqlite3.Error:
                continue
            data = _loads(row[0]) if row else None
            for c in (data or {}).get("allComposers") or []:
                if c.get("composerId"):
                    out[c["composerId"]] = folder
        self._folders = out
        return out

    def list_sessions(self, cwd: Optional[str] = None, limit: Optional[int] = None) -> List[SessionRef]:
        refs: List[SessionRef] = []
        if not self.available():
            return refs
        folders = self.folders()
        try:
            con = _open(self.global_db)
            rows = con.execute("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
            con.close()
        except sqlite3.Error:
            return refs
        for key, value in rows:
            data = _loads(value) or {}
            cid = key.split(":", 1)[1]
            folder = folders.get(cid)
            if cwd and (not folder or os.path.abspath(folder) != os.path.abspath(cwd)):
                continue
            ts = parse_ts(data.get("lastUpdatedAt") or data.get("createdAt"))
            refs.append(SessionRef(self.name, cid, self.global_db, ts.timestamp() if ts else 0.0,
                                   cwd=folder, title=data.get("name") or data.get("title"), size=len(value or b"")))
        refs.sort(key=lambda r: -r.mtime)
        return refs[:limit] if limit else refs

    def load(self, ref: SessionRef) -> Session:
        s = Session(agent=self.name, id=ref.id, path=ref.path, cwd=ref.cwd, title=ref.title)
        con = _open(ref.path)
        try:
            row = con.execute("SELECT value FROM cursorDiskKV WHERE key=?", ("composerData:%s" % ref.id,)).fetchone()
            data = _loads(row[0]) if row else {}
            bubbles: List[dict] = []
            if data.get("conversation"):
                bubbles = [b for b in data["conversation"] if isinstance(b, dict)]
            else:
                headers = data.get("fullConversationHeadersOnly") or []
                for h in headers:
                    bid = h.get("bubbleId")
                    if not bid:
                        continue
                    brow = con.execute("SELECT value FROM cursorDiskKV WHERE key=?", ("bubbleId:%s:%s" % (ref.id, bid),)).fetchone()
                    b = _loads(brow[0]) if brow else None
                    if isinstance(b, dict):
                        bubbles.append(b)
        finally:
            con.close()
        s.model = data.get("modelConfig", {}).get("modelName") if isinstance(data.get("modelConfig"), dict) else None
        created = parse_ts(data.get("createdAt"))
        for b in bubbles:
            ts = parse_ts(b.get("createdAt") or b.get("timestamp")) or created
            btype = b.get("type")
            text = (b.get("text") or "").strip()
            tool = b.get("toolFormerData")
            if btype == 1 and text:
                files = [f.get("uri", {}).get("path") or f.get("path") for f in (b.get("context") or {}).get("fileSelections") or []]
                s.events.append(Event(ts, PROMPT, text, meta={"code_blocks": code_blocks(text), "paths": paths_in(text),
                                                              "attached": [f for f in files if f]}))
            elif btype == 2 and isinstance(tool, dict) and tool.get("name"):
                s.events.append(self._tool(ts, tool))
            elif btype == 2 and text:
                s.events.append(Event(ts, REPLY, text))
        return s

    def _tool(self, ts, tool: dict) -> Event:
        name = tool.get("name") or "tool"
        params = _loads(tool.get("params")) if isinstance(tool.get("params"), str) else (tool.get("params") or {})
        params = params if isinstance(params, dict) else {}
        files = []
        text = ""
        for k in FILE_KEYS:
            if params.get(k):
                text = str(params[k])
                if name in EDIT_TOOLS:
                    files = [text]
                break
        if not text:
            text = str(params.get("command") or params.get("query") or params.get("explanation") or "")[:300]
        ev = Event(ts, TOOL, text[:300], tool=name, files=files,
                   meta={"command": text[:300]} if name in ("run_terminal_cmd", "run_terminal_command") else {})
        status = str(tool.get("status") or "").lower()
        result = tool.get("result")
        failed = status in ("error", "rejected", "cancelled") or (isinstance(result, str) and result.lstrip().startswith('{"error"'))
        if failed:
            return Event(ts, ERROR, (result or status)[:600] if isinstance(result, str) else status, tool=name)
        return ev
