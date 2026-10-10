"""Cursor adapter.

Cursor keeps its chat history in SQLite, not in files:

* Global: <UserData>/User/globalStorage/state.vscdb, table `cursorDiskKV`.
  - `composerData:<composerId>` -> one Composer/Agent conversation
    (name, createdAt, and either `conversation` inline or
    `fullConversationHeadersOnly: [{bubbleId, type}]`).
  - `bubbleId:<composerId>:<bubbleId>` -> one message. `type` 1 = user,
    2 = assistant. Tool calls live in `toolFormerData`.
* Per workspace: <UserData>/User/workspaceStorage/<hash>/workspace.json
  (`folder`). Older Cursor ties composers to a workspace through that
  folder's state.vscdb (`ItemTable` key `composer.composerData`,
  `allComposers`). Newer Cursor (2.x) puts `workspaceIdentifier: {id}` on
  each composer, where id is the workspaceStorage hash, keeps titles in a
  global `composerHeaders` table, and stamps `workspaceUris` on bubbles.
  A chat in an empty window has no folder at all.

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
from collections import Counter
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


def _maybe_json(value) -> Any:
    """Parse a column that holds JSON; leave plain scalars alone."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str) and value[:1] in "{[":
        parsed = _loads(value)
        return parsed if parsed is not None else value
    return value


def _folder_of(uri: str) -> str:
    return unquote(urlparse(uri).path)


def _title_of(text: Any) -> Optional[str]:
    """A listing title from the first prompt: its first line, trimmed."""
    if not isinstance(text, str) or not text.strip():
        return None
    line = text.strip().splitlines()[0].strip()
    return line if len(line) <= 70 else line[:67].rstrip() + "…"


class CursorAdapter(Adapter):
    name = "cursor"
    label = "Cursor"
    headless = ["cursor-agent", "-p", "--force"]

    def __init__(self, user_dir: Optional[str] = None):
        self.user_dir = user_dir or default_user_dir()
        self.global_db = os.path.join(self.user_dir, "globalStorage", "state.vscdb")
        self._folders: Optional[Dict[str, str]] = None
        self._ws: Optional[Dict[str, str]] = None
        self._headers: Optional[Dict[str, Dict[str, Any]]] = None

    def available(self) -> bool:
        return os.path.isfile(self.global_db)

    # workspaceStorage hash -> folder
    def workspaces(self) -> Dict[str, str]:
        if self._ws is not None:
            return self._ws
        out: Dict[str, str] = {}
        for ws in glob.glob(os.path.join(self.user_dir, "workspaceStorage", "*")):
            try:
                with open(os.path.join(ws, "workspace.json"), encoding="utf-8") as fh:
                    uri = (json.load(fh).get("folder") or "")
                if uri.startswith("file:"):
                    out[os.path.basename(ws)] = _folder_of(uri)
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        self._ws = out
        return out

    # composerId -> {name, folder} from the global composerHeaders table (newer Cursor). Column names are not
    # documented, so every column is read and JSON columns are flattened; anything named like a title or a
    # workspace is used.
    def headers(self) -> Dict[str, Dict[str, Any]]:
        if self._headers is not None:
            return self._headers
        out: Dict[str, Dict[str, Any]] = {}
        try:
            con = _open(self.global_db)
            if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='composerHeaders'").fetchone():
                cur = con.execute("SELECT * FROM composerHeaders")
                cols = [c[0] for c in cur.description]
                for row in cur.fetchall():
                    flat: Dict[str, Any] = {}
                    for k, v in zip(cols, row):
                        parsed = _maybe_json(v)
                        if isinstance(parsed, dict):
                            flat.update(parsed)
                        else:
                            flat[k] = v
                    cid = flat.get("composerId") or flat.get("composer_id") or flat.get("id") or flat.get("key")
                    if not cid:
                        continue
                    cid = str(cid).split(":")[-1]
                    rec: Dict[str, Any] = {}
                    name = flat.get("name") or flat.get("title") or flat.get("subtitle")
                    if isinstance(name, str) and name.strip():
                        rec["name"] = name.strip()
                    folder = self._folder_hint(flat)
                    if folder:
                        rec["folder"] = folder
                    if rec:
                        out[cid] = rec
            con.close()
        except sqlite3.Error:
            pass
        self._headers = out
        return out

    def _folder_hint(self, data: Dict[str, Any]) -> Optional[str]:
        """A folder from any workspace-ish field: a {id} pointing at workspaceStorage, a file: URI, or a bare path."""
        ws = self.workspaces()
        for k, v in data.items():
            if not any(w in k.lower() for w in ("workspace", "folder", "root", "cwd")):
                continue
            if isinstance(v, dict):
                v = v.get("id") or v.get("uri") or v.get("path") or v.get("fsPath")
            if isinstance(v, list):
                v = v[0] if v else None
                if isinstance(v, dict):
                    v = v.get("uri") or v.get("path") or v.get("fsPath") or v.get("id")
            if not isinstance(v, str) or not v:
                continue
            if v in ws:
                return ws[v]
            if v.startswith("file:"):
                return _folder_of(v)
            if v.startswith("/") or (len(v) > 2 and v[1] == ":"):
                return v
        return None

    # composerId -> workspace folder, from every workspaceStorage/<hash> (older Cursor)
    def folders(self) -> Dict[str, str]:
        if self._folders is not None:
            return self._folders
        out: Dict[str, str] = {}
        for ws in glob.glob(os.path.join(self.user_dir, "workspaceStorage", "*")):
            folder = self.workspaces().get(os.path.basename(ws))
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
        heads = self.headers()
        try:
            con = _open(self.global_db)
            for key, value in rows:
                data = _loads(value) or {}
                cid = key.split(":", 1)[1]
                if cid.startswith("empty-state"):        # Cursor's placeholder for a chat that was never started
                    continue
                hdr = heads.get(cid, {})
                folder = folders.get(cid) or hdr.get("folder") or self._folder_hint(data)
                title = data.get("name") or data.get("title") or hdr.get("name")
                if not folder or not title:
                    first = self._first_user_bubble(con, cid, data)
                    if first:
                        folder = folder or self._folder_hint(first)
                        title = title or _title_of(first.get("text"))
                if cwd and (not folder or os.path.abspath(folder) != os.path.abspath(cwd)):
                    continue
                ts = parse_ts(data.get("lastUpdatedAt") or data.get("createdAt"))
                refs.append(SessionRef(self.name, cid, self.global_db, ts.timestamp() if ts else 0.0,
                                       cwd=folder, title=title, size=len(value or b"")))
            con.close()
        except sqlite3.Error:
            return refs
        refs.sort(key=lambda r: -r.mtime)
        return refs[:limit] if limit else refs

    def _first_user_bubble(self, con: sqlite3.Connection, cid: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for b in data.get("conversation") or []:
            if isinstance(b, dict) and b.get("type") == 1:
                return b
        cmap = data.get("conversationMap") if isinstance(data.get("conversationMap"), dict) else {}
        for h in data.get("fullConversationHeadersOnly") or []:
            if not isinstance(h, dict) or h.get("type") != 1 or not h.get("bubbleId"):
                continue
            b = cmap.get(h["bubbleId"])
            if not isinstance(b, dict):
                row = con.execute("SELECT value FROM cursorDiskKV WHERE key=?", ("bubbleId:%s:%s" % (cid, h["bubbleId"]),)).fetchone()
                b = _loads(row[0]) if row else None
            if isinstance(b, dict):
                return b
        return None

    def dump(self) -> str:
        """The shape of Cursor's storage on this machine: paths, tables, keys, counts and short scalar values.
        No message text. This is what to paste when the adapter finds sessions but no folders or titles."""
        HINT = ("name", "title", "workspace", "folder", "root", "cwd", "path", "uri", "mode", "created", "updated", "status")
        out = ["cursor user_dir: %s (exists=%s)" % (self.user_dir, os.path.isdir(self.user_dir)),
               "global_db: %s (exists=%s)" % (self.global_db, os.path.isfile(self.global_db))]
        for ws in sorted(glob.glob(os.path.join(self.user_dir, "workspaceStorage", "*")))[:12]:
            folder, db = None, os.path.join(ws, "state.vscdb")
            try:
                with open(os.path.join(ws, "workspace.json"), encoding="utf-8") as fh:
                    folder = json.load(fh).get("folder")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                folder = "(no workspace.json: %s)" % exc.__class__.__name__
            out.append("workspace %s folder=%s db=%s" % (os.path.basename(ws), folder, os.path.isfile(db)))
            if not os.path.isfile(db):
                continue
            try:
                con = _open(db)
                tables = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                out.append("  tables: %s" % ", ".join(tables))
                if "ItemTable" in tables:
                    keys = [k for (k,) in con.execute("SELECT key FROM ItemTable") if any(w in k.lower() for w in ("composer", "aichat", "agent", "chat"))]
                    out.append("  ItemTable keys: %s" % ", ".join(sorted(keys)[:25]))
                    row = con.execute("SELECT value FROM ItemTable WHERE key='composer.composerData'").fetchone()
                    data = _loads(row[0]) if row else None
                    if isinstance(data, dict):
                        comps = data.get("allComposers") or []
                        out.append("  composer.composerData keys=%s allComposers=%d" % (sorted(data)[:15], len(comps)))
                        for c in comps[:3]:
                            out.append("    composer %s keys=%s" % (str(c.get("composerId"))[:13], sorted(c)[:25]))
                con.close()
            except sqlite3.Error as exc:
                out.append("  sqlite error: %s" % exc)
        if not os.path.isfile(self.global_db):
            return "\n".join(out)
        try:
            con = _open(self.global_db)
            tables = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            out.append("global tables: %s" % ", ".join(tables))
            for t in tables:
                if t == "cursorDiskKV":
                    continue
                cols = [c[1] for c in con.execute("PRAGMA table_info(%s)" % t.replace('"', ""))]
                n = con.execute('SELECT count(*) FROM "%s"' % t.replace('"', "")).fetchone()[0]
                out.append("table %s: %d rows, columns %s" % (t, n, cols))
                if t == "composerHeaders" and n:
                    cur = con.execute('SELECT * FROM "composerHeaders" LIMIT 2')
                    names = [c[0] for c in cur.description]
                    for row in cur.fetchall():
                        for k, v in zip(names, row):
                            p = _maybe_json(v)
                            if isinstance(p, dict):
                                out.append("  %s = {%s}" % (k, ", ".join("%s: %s" % (kk, str(vv)[:60]) for kk, vv in sorted(p.items())
                                                                     if any(w in kk.lower() for w in HINT))[:400]))
                            else:
                                out.append("  %s = %s" % (k, str(p)[:80]))
            if "cursorDiskKV" in tables:
                prefixes = Counter(k.split(":")[0] for (k,) in con.execute("SELECT key FROM cursorDiskKV"))
                out.append("cursorDiskKV key prefixes: %s" % ", ".join("%s=%d" % kv for kv in prefixes.most_common(15)))
                rows = con.execute("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%' ORDER BY rowid DESC LIMIT 3").fetchall()
                for key, value in rows:
                    data = _loads(value) or {}
                    cid = key.split(":", 1)[1]
                    out.append("composer %s keys=%s" % (cid[:13], sorted(data)[:45]))
                    for k, v in sorted(data.items()):
                        if any(w in k.lower() for w in HINT):
                            if isinstance(v, (str, int, float, bool)) or v is None:
                                out.append("   %s = %s" % (k, str(v)[:100]))
                            elif isinstance(v, dict):
                                out.append("   %s = {%s}" % (k, ", ".join("%s: %s" % (kk, str(vv)[:60]) for kk, vv in sorted(v.items())[:12])))
                            elif isinstance(v, list):
                                out.append("   %s = [%d items]" % (k, len(v)))
                    heads, conv = data.get("fullConversationHeadersOnly") or [], data.get("conversation") or []
                    out.append("   headers=%d conversation=%d" % (len(heads), len(conv)))
                    first = (heads[0].get("bubbleId") if heads and isinstance(heads[0], dict) else None)
                    row = con.execute("SELECT value FROM cursorDiskKV WHERE key=?", ("bubbleId:%s:%s" % (cid, first),)).fetchone() if first else None
                    bd = _loads(row[0]) if row else None
                    if isinstance(bd, dict):
                        out.append("   bubble keys=%s" % sorted(bd)[:70])
                        for k, v in sorted(bd.items()):
                            if any(w in k.lower() for w in ("workspace", "folder", "root", "cwd")):
                                out.append("     %s = %s" % (k, (str(v)[:120] if not isinstance(v, (dict, list)) else "%s with %d" % (type(v).__name__, len(v)))))
            if "ItemTable" in tables:
                keys = [k for (k,) in con.execute("SELECT key FROM ItemTable") if any(w in k.lower() for w in ("composer", "aichat", "agent"))]
                out.append("global ItemTable keys: %s" % ", ".join(sorted(keys)[:25]))
            con.close()
        except sqlite3.Error as exc:
            out.append("global sqlite error: %s" % exc)
        return "\n".join(out)

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
