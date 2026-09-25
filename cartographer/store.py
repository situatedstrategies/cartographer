"""Local storage under ~/.cartographer (or $CARTOGRAPHER_HOME).

    config.json                                  user settings
    projects.json                                project id -> name, slug, roots, remote
    sessions/<slug>/<date>_<agent>_<sid8>.json   one recap per wrapped session
    replays/<slug>.html                          rendered replays
    briefs/, digests/                            working files

Which sessions are wrapped is read from the recap file names, so there is no
second index to keep in sync. Secrets are redacted before anything is written;
raw transcripts are never copied here.
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
SESSIONS, REPLAYS, BRIEFS, DIGESTS = (os.path.join(HOME, d) for d in ("sessions", "replays", "briefs", "digests"))
PROJECTS = os.path.join(HOME, "projects.json")

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
    for d in (HOME, SESSIONS, REPLAYS, BRIEFS, DIGESTS):
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


def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: str, data: Any, indent: int = 1) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------- projects

def projects() -> Dict[str, Dict[str, Any]]:
    return read_json(PROJECTS, {})


def register_project(pid: str, name: str, root: Optional[str], remote: Optional[str]) -> Dict[str, Any]:
    reg = projects()
    entry = reg.get(pid) or {"id": pid, "name": name, "slug": _unique_slug(reg, project_slug(name), pid),
                             "created_at": datetime.now(timezone.utc).isoformat()}
    entry["name"] = entry.get("name") or name
    if root and root not in entry.setdefault("roots", []):
        entry["roots"].append(root)
    if remote:
        entry["remote"] = remote
    reg[pid] = entry
    write_json(PROJECTS, reg)
    return entry


def _unique_slug(reg: Dict[str, Any], slug: str, pid: str) -> str:
    taken = {v["slug"] for k, v in reg.items() if k != pid}
    out, n = slug, 2
    while out in taken:
        out, n = "%s-%d" % (slug, n), n + 1
    return out


def find_project(query: str) -> Optional[Dict[str, Any]]:
    q = query.lower()
    reg = projects()
    for exact in (True, False):
        for pid, p in reg.items():
            keys = (pid.lower(), p["slug"], (p.get("name") or "").lower())
            if (q in keys) if exact else any(q in k for k in keys):
                return p
    return None


# ------------------------------------------------------------ versions
# A version is the unit of truth: the user declares what done means, builds,
# then marks it complete with what actually happened. Session maps are
# provisional until then; the appraisal judges them against this.

RESULTS = ("shipped", "partial", "abandoned")


def open_version(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The version still being built: the last one not marked complete."""
    for v in reversed(entry.get("versions") or []):
        if not v.get("completed_at"):
            return v
    return None


def _version(entry: Dict[str, Any], name: Optional[str], create: bool = True) -> Optional[Dict[str, Any]]:
    vs = entry.setdefault("versions", [])
    v = next((x for x in vs if x.get("name") == name), None) if name else open_version(entry)
    if v is None and create:
        v = {"name": name or "v%d" % (len(vs) + 1), "desired": None, "set_at": None, "completed_at": None, "result": None, "actual": None, "appraisal": None}
        vs.append(v)
    return v


def set_goal(project: str, desired: str, version: Optional[str] = None) -> Dict[str, Any]:
    reg = projects()
    entry = find_project(project)
    if not entry:
        raise LookupError("no project matching %r; wrap a session first, or run `cartographer goal` inside the repo" % project)
    v = _version(reg[entry["id"]], version)
    v["desired"], v["set_at"] = desired.strip(), datetime.now(timezone.utc).isoformat()
    write_json(PROJECTS, reg)
    return v


def complete(project: str, result: str, actual: str = "", version: Optional[str] = None) -> Dict[str, Any]:
    if result not in RESULTS:
        raise ValueError("result must be one of: %s" % ", ".join(RESULTS))
    reg = projects()
    entry = find_project(project)
    if not entry:
        raise LookupError("no project matching %r" % project)
    v = _version(reg[entry["id"]], version)
    v.update(completed_at=datetime.now(timezone.utc).isoformat(), result=result, actual=(actual or "").strip() or None)
    write_json(PROJECTS, reg)
    return v


def get_version(project: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """A named version, or the open one, without creating anything."""
    entry = find_project(project)
    return _version(entry, name, create=False) if entry else None


def desired_for(pid: str) -> Optional[str]:
    entry = projects().get(pid or "")
    v = open_version(entry) if entry else None
    return (v or {}).get("desired")


def appraisal_path(slug: str, version: str) -> str:
    return os.path.join(SESSIONS, slug, "appraisal_%s.json" % project_slug(version))


def save_appraisal(appraisal: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or config.load()
    proj = appraisal.get("project") or {}
    entry = find_project(proj.get("id") or proj.get("slug") or proj.get("name") or "")
    if not entry:
        raise LookupError("appraisal names a project that is not wrapped: %r" % proj)
    appraisal["project"] = {"id": entry["id"], "name": entry["name"], "slug": entry["slug"]}
    appraisal["saved_at"] = datetime.now(timezone.utc).isoformat()
    if cfg["privacy"].get("redact_secrets", True):
        appraisal = redact(appraisal)
    path = write_json(appraisal_path(entry["slug"], appraisal.get("version") or "v1"), appraisal)
    reg = projects()
    v = _version(reg[entry["id"]], appraisal.get("version") or "v1")
    v["appraisal"] = path
    write_json(PROJECTS, reg)
    return path


def load_appraisals(slug: str) -> List[Dict[str, Any]]:
    out = [read_json(p, None) for p in sorted(glob.glob(os.path.join(SESSIONS, slug, "appraisal_*.json")))]
    return [a for a in out if isinstance(a, dict)]


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
    return write_json(recap_path(recap, entry["slug"]), recap)


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
        if os.path.basename(path).startswith("appraisal_"):
            continue
        data = read_json(path, None)
        if isinstance(data, dict):
            data["_path"] = path
            out.append(data)
    out.sort(key=lambda r: (r.get("started_at") or r.get("date") or ""))
    return out


def wrapped() -> Dict[str, str]:
    """{'<agent>:<first 8 chars of session id>': recap path}, from the file names."""
    out = {}
    for path in glob.glob(os.path.join(SESSIONS, "*", "*.json")):
        parts = os.path.splitext(os.path.basename(path))[0].split("_", 2)  # date_agent_sid8
        if len(parts) == 3:
            out["%s:%s" % (parts[1], parts[2])] = path
    return out


def wrapped_path(agent: str, session_id: str) -> Optional[str]:
    return wrapped().get("%s:%s" % (agent, (session_id or "")[:8]))


def is_wrapped(agent: str, session_id: str) -> bool:
    return wrapped_path(agent, session_id) is not None
