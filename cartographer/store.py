"""Local storage under ~/.cartographer.

    config.json                 user settings
    projects.json               registry: project id -> name, root, remote, slug, sessions
    sessions/<slug>/<file>.json one recap per wrapped session
    replays/<slug>.html         rendered replays
    briefs/, digests/, queue/   working files
    wrapped.json                which session ids have been wrapped (for sweeps)

Secrets are redacted before anything is written. Raw transcripts are never
copied here.
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config
from .gitinfo import project_slug

HOME = config.HOME
SESSIONS = os.path.join(HOME, "sessions")
REPLAYS = os.path.join(HOME, "replays")
BRIEFS = os.path.join(HOME, "briefs")
DIGESTS = os.path.join(HOME, "digests")
QUEUE = os.path.join(HOME, "queue")
PROJECTS = os.path.join(HOME, "projects.json")
WRAPPED = os.path.join(HOME, "wrapped.json")

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"), re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(r"(?i)(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s'\"]*:[^\s'\"@]+@"),
]


def ensure_dirs() -> None:
    for d in (HOME, SESSIONS, REPLAYS, BRIEFS, DIGESTS, QUEUE):
        os.makedirs(d, exist_ok=True)


def redact_text(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group(0)[:6] + "…[redacted]", text)
    return text


def redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    return obj


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data: Any) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------- projects

def projects() -> Dict[str, Dict[str, Any]]:
    return _read_json(PROJECTS, {})


def register_project(pid: str, name: str, root: Optional[str], remote: Optional[str]) -> Dict[str, Any]:
    reg = projects()
    entry = reg.get(pid) or {"id": pid, "name": name, "slug": _unique_slug(reg, project_slug(name), pid),
                             "created_at": datetime.now(timezone.utc).isoformat()}
    entry["name"] = entry.get("name") or name
    if root:
        roots = entry.setdefault("roots", [])
        if root not in roots:
            roots.append(root)
    if remote:
        entry["remote"] = remote
    reg[pid] = entry
    _write_json(PROJECTS, reg)
    return entry


def _unique_slug(reg: Dict[str, Any], slug: str, pid: str) -> str:
    taken = {v["slug"] for k, v in reg.items() if k != pid}
    out, n = slug, 2
    while out in taken:
        out = "%s-%d" % (slug, n)
        n += 1
    return out


def find_project(name_or_slug_or_id: str) -> Optional[Dict[str, Any]]:
    q = name_or_slug_or_id.lower()
    for pid, p in projects().items():
        if q in (pid.lower(), p["slug"], (p.get("name") or "").lower()):
            return p
    for pid, p in projects().items():
        if q in pid.lower() or q in p["slug"] or q in (p.get("name") or "").lower():
            return p
    return None


# -------------------------------------------------------------- recaps

def recap_path(recap: Dict[str, Any], slug: str) -> str:
    date = (recap.get("date") or "undated")[:10]
    sid = (recap.get("session_id") or "session")[:8]
    return os.path.join(SESSIONS, slug, "%s_%s_%s.json" % (date, recap.get("agent", "agent"), sid))


def save_recap(recap: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or config.load()
    ensure_dirs()
    proj = recap.get("project") or {}
    entry = register_project(proj.get("id") or "local:unknown", proj.get("name") or "Untitled", proj.get("root"), proj.get("remote"))
    proj["slug"] = entry["slug"]
    recap["project"] = proj
    recap["saved_at"] = datetime.now(timezone.utc).isoformat()
    if cfg["privacy"].get("redact_secrets", True):
        recap = redact(recap)
    path = _write_json(recap_path(recap, entry["slug"]), recap)
    mark_wrapped(recap.get("agent", ""), recap.get("session_id", ""), path)
    return path


def load_recaps(project: Optional[str] = None) -> List[Dict[str, Any]]:
    if project:
        entry = find_project(project)
        if not entry:
            return []
        pattern = os.path.join(SESSIONS, entry["slug"], "*.json")
    else:
        pattern = os.path.join(SESSIONS, "*", "*.json")
    out = []
    for path in glob.glob(pattern):
        data = _read_json(path, None)
        if isinstance(data, dict):
            data["_path"] = path
            out.append(data)
    out.sort(key=lambda r: (r.get("started_at") or r.get("date") or ""))
    return out


def wrapped() -> Dict[str, str]:
    return _read_json(WRAPPED, {})


def mark_wrapped(agent: str, session_id: str, path: str) -> None:
    w = wrapped()
    w["%s:%s" % (agent, session_id)] = path
    _write_json(WRAPPED, w)


def is_wrapped(agent: str, session_id: str) -> bool:
    return ("%s:%s" % (agent, session_id)) in wrapped()


# --------------------------------------------------------------- queue

def enqueue(item: Dict[str, Any]) -> str:
    ensure_dirs()
    item = dict(item, queued_at=datetime.now(timezone.utc).isoformat())
    path = os.path.join(QUEUE, "pending.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(item) + "\n")
    return path


def drain_queue() -> List[Dict[str, Any]]:
    path = os.path.join(QUEUE, "pending.jsonl")
    items: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        os.remove(path)
    except OSError:
        pass
    return items
