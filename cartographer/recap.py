"""Recap schema: the map of one session.

A recap is what the mapping model writes and what everything downstream
(storage, replay, profile) consumes. `normalize` fills what can be derived
from the digest so the model only has to supply judgment, and treats
placeholders copied from the example as unset. `validate` returns
human-readable problems.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

SCHEMA = "cartographer.session/v2"
KINDS = ("prompt", "question", "decision", "dead_end", "fix", "artifact", "pivot", "insight")
RELS = ("led_to", "blocked_by", "reverted", "reused", "answered")
FOCUS = ("prompt", "code", "workflow")
PLACEHOLDER = re.compile(r"^(?:…|\.\.\.|YYYY-MM-DD|TBD|)$")

EXAMPLE: Dict[str, Any] = {
    "schema": SCHEMA,
    "agent": "claude-code", "session_id": "…", "title": "Short session title",
    "project": {"id": "github.com/me/app", "name": "app", "root": "/path/to/repo", "remote": "git@github.com:me/app.git"},
    "branch": "feature/auth", "branches": ["main", "feature/auth"],
    "date": "YYYY-MM-DD", "started_at": "…", "ended_at": "…", "duration_min": 0,
    "goal": "what the user set out to do, in their own terms",
    "outcome": "where it actually landed",
    "voice": "technical",
    "languages": ["typescript"], "frameworks": ["Next.js"], "files": ["src/auth.ts"],
    "tags": ["nextjs", "auth", "webapp"],
    "phases": [{"name": "Explore", "summary": "one line", "branch": "main"}],
    "steps": [{
        "id": "s1", "t": 0.0, "phase": "Explore", "branch": "main", "kind": "prompt",
        "title": "≤ 7 words, verb first", "detail": "1–2 sentences: what happened and why it mattered.",
        "plain": {"title": "same step in everyday words", "detail": "only when voice is 'both'"},
        "prompt": "the user's exact wording when the phrasing is the lesson",
        "files": ["src/auth.ts"],
        "links": [{"to": "s4", "rel": "led_to"}],
    }],
    "reusable_prompts": [{"prompt": "template with <placeholders>", "why": "what it reliably gets", "language": "typescript"}],
    "patterns": ["neutral observation about how this person builds"],
    "time_sinks": [{"what": "…", "minutes": 0}],
    "coaching": [{"focus": "prompt", "observation": "what happened", "suggestion": "what to do next time",
                  "rewrite": "an improved version of a real prompt from this session", "step": "s3"}],
    "next_steps": ["unfinished work, phrased so the next session can pick it up"],
}
DERIVED = ("agent", "session_id", "title", "started_at", "ended_at", "duration_min", "branch", "branches", "frameworks", "files", "project")


def _unset(key: str, value: Any) -> bool:
    """Missing, empty, a placeholder, or copied verbatim from the example."""
    if value is None or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, str) and PLACEHOLDER.match(value.strip()):
        return True
    return value == EXAMPLE.get(key)


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate(recap: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if not isinstance(recap, dict):
        return ["recap must be a JSON object"]
    for key in ("title", "goal", "outcome", "phases", "steps"):
        if _unset(key, recap.get(key)):
            errs.append("missing %s" % key)
    phases = recap.get("phases") or []
    names = {p["name"] for p in phases if isinstance(p, dict) and p.get("name")}
    errs += ["phases[%d] needs a name" % i for i, p in enumerate(phases) if not (isinstance(p, dict) and p.get("name"))]
    if len(phases) > 8:
        errs.append("too many phases (%d); merge to 8 or fewer" % len(phases))
    steps = [s for s in (recap.get("steps") or []) if isinstance(s, dict)]
    ids = [s.get("id") for s in steps]
    for i, s in enumerate(steps):
        sid = s.get("id")
        if not sid:
            errs.append("steps[%d] needs an id" % i)
        elif ids.index(sid) != i:
            errs.append("duplicate step id %s" % sid)
        if s.get("kind") not in KINDS:
            errs.append("step %s: kind must be one of %s" % (sid, ", ".join(KINDS)))
        if not s.get("title"):
            errs.append("step %s: missing title" % sid)
        if s.get("t") is not None and not _num(s["t"]):
            errs.append("step %s: t must be a number (minutes from start)" % sid)
        if s.get("phase") and names and s["phase"] not in names:
            errs.append("step %s: phase %r is not in phases" % (sid, s["phase"]))
        for l in s.get("links") or []:
            if not isinstance(l, dict) or l.get("rel") not in RELS:
                errs.append("step %s: link rel must be one of %s" % (sid, ", ".join(RELS)))
            elif l.get("to") and l["to"] not in ids and ":" not in str(l["to"]):
                errs.append("step %s links to unknown step %s" % (sid, l["to"]))
    if len(steps) < 3:
        errs.append("fewer than 3 steps; a map needs at least the goal, one turning point and the outcome")
    if len(steps) > 40:
        errs.append("more than 40 steps; keep the moments that changed direction")
    for i, c in enumerate(recap.get("coaching") or []):
        if not isinstance(c, dict) or c.get("focus") not in FOCUS:
            errs.append("coaching[%d]: focus must be one of %s" % (i, ", ".join(FOCUS)))
        elif not (c.get("observation") and c.get("suggestion")):
            errs.append("coaching[%d]: needs observation and suggestion" % i)
        elif c.get("step") and c["step"] not in ids:
            errs.append("coaching[%d]: step %r is not a step id" % (i, c["step"]))
    for i, t in enumerate(recap.get("time_sinks") or []):
        if not isinstance(t, dict) or not t.get("what") or (t.get("minutes") is not None and not _num(t["minutes"])):
            errs.append("time_sinks[%d]: needs `what` and a numeric `minutes`" % i)
    return errs


def normalize(recap: Dict[str, Any], digest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill derivable fields from the digest. The model's real values win; placeholders don't."""
    r = copy.deepcopy(recap)
    r["schema"] = SCHEMA
    d = digest or {}
    for key in DERIVED:
        if _unset(key, r.get(key)) and not _unset(key, d.get(key)):
            r[key] = {k: d[key].get(k) for k in ("id", "name", "root", "remote")} if key == "project" else d[key]
    if _unset("date", r.get("date")):
        r["date"] = (r.get("started_at") or "")[:10] or None
    if _unset("languages", r.get("languages")) and d.get("languages"):
        r["languages"] = [l["lang"] for l in d["languages"][:6]]
    if r.get("frameworks") and isinstance(r["frameworks"][0], dict):
        r["frameworks"] = [f.get("name") for f in r["frameworks"]]
    if r.get("files"):
        r["files"] = r["files"][:20]
    if d.get("stats"):
        r["stats"] = d["stats"]
    if d.get("prompting"):
        r["prompting"] = d["prompting"]
    for key in ("tags", "reusable_prompts", "patterns", "time_sinks", "coaching", "next_steps"):
        r.setdefault(key, [])
    for s in r.get("steps") or []:
        if isinstance(s, dict):
            s.setdefault("links", [])
            if s.get("t") is None:
                s["t"] = 0
    return r
