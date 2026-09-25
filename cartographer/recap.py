"""Recap schema: the map of one session.

A recap is what the mapping model writes and what everything downstream
(storage, replay, profile) consumes. `validate` returns human-readable
problems; `normalize` fills what can be derived from the digest so the model
only has to supply judgment.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

SCHEMA = "cartographer.session/v2"
KINDS = ("prompt", "question", "decision", "dead_end", "fix", "artifact", "pivot", "insight")
RELS = ("led_to", "blocked_by", "reverted", "reused", "answered")
FOCUS = ("prompt", "code", "workflow")

EXAMPLE: Dict[str, Any] = {
    "schema": SCHEMA,
    "agent": "claude-code", "session_id": "…", "title": "Short session title",
    "project": {"id": "github.com/me/app", "name": "app", "root": "/path/to/repo", "remote": "git@github.com:me/app.git"},
    "branch": "feature/auth", "branches": ["main", "feature/auth"],
    "date": "YYYY-MM-DD", "started_at": "…", "ended_at": "…", "duration_min": 0,
    "goal": "what the user set out to do, in their own terms",
    "outcome": "where it actually landed",
    "voice": "technical",
    "stats": {}, "languages": ["typescript"], "frameworks": ["Next.js"], "files": ["src/auth.ts"],
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


def validate(recap: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if not isinstance(recap, dict):
        return ["recap must be a JSON object"]
    for key in ("title", "goal", "outcome", "phases", "steps"):
        if not recap.get(key):
            errs.append("missing %s" % key)
    phases = recap.get("phases") or []
    names = set()
    for i, p in enumerate(phases):
        if not isinstance(p, dict) or not p.get("name"):
            errs.append("phases[%d] needs a name" % i)
        else:
            names.add(p["name"])
    if len(phases) > 8:
        errs.append("too many phases (%d); merge to 8 or fewer" % len(phases))
    steps = recap.get("steps") or []
    ids = set()
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            errs.append("steps[%d] must be an object" % i)
            continue
        sid = s.get("id")
        if not sid:
            errs.append("steps[%d] needs an id" % i)
        elif sid in ids:
            errs.append("duplicate step id %s" % sid)
        ids.add(sid)
        if s.get("kind") not in KINDS:
            errs.append("step %s: kind must be one of %s" % (sid, ", ".join(KINDS)))
        if not s.get("title"):
            errs.append("step %s: missing title" % sid)
        if s.get("phase") and names and s["phase"] not in names:
            errs.append("step %s: phase %r is not in phases" % (sid, s["phase"]))
        for l in s.get("links") or []:
            if not isinstance(l, dict) or l.get("rel") not in RELS:
                errs.append("step %s: link rel must be one of %s" % (sid, ", ".join(RELS)))
    for s in steps:
        if isinstance(s, dict):
            for l in s.get("links") or []:
                if isinstance(l, dict) and l.get("to") and l["to"] not in ids and ":" not in str(l["to"]):
                    errs.append("step %s links to unknown step %s" % (s.get("id"), l["to"]))
    if len(steps) < 3:
        errs.append("fewer than 3 steps; a map needs at least the goal, one turning point and the outcome")
    if len(steps) > 40:
        errs.append("more than 40 steps; keep the moments that changed direction")
    for i, c in enumerate(recap.get("coaching") or []):
        if not isinstance(c, dict) or c.get("focus") not in FOCUS:
            errs.append("coaching[%d]: focus must be one of %s" % (i, ", ".join(FOCUS)))
        elif not (c.get("observation") and c.get("suggestion")):
            errs.append("coaching[%d]: needs observation and suggestion" % i)
    return errs


def normalize(recap: Dict[str, Any], digest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill derivable fields from the digest. The model's values win when present."""
    r = copy.deepcopy(recap)
    r["schema"] = SCHEMA
    d = digest or {}
    for key in ("agent", "session_id", "started_at", "ended_at", "duration_min", "branch", "branches", "stats", "frameworks"):
        if r.get(key) in (None, "", [], {}) and d.get(key) not in (None, ""):
            r[key] = d[key]
    if not r.get("project") and d.get("project"):
        r["project"] = {k: d["project"].get(k) for k in ("id", "name", "root", "remote")}
    if not r.get("date"):
        r["date"] = (r.get("started_at") or "")[:10] or None
    if not r.get("languages") and d.get("languages"):
        r["languages"] = [l["lang"] for l in d["languages"][:6]]
    if isinstance(r.get("frameworks"), list) and r["frameworks"] and isinstance(r["frameworks"][0], dict):
        r["frameworks"] = [f.get("name") for f in r["frameworks"]]
    if not r.get("files") and d.get("files"):
        r["files"] = d["files"][:20]
    if d.get("prompting"):
        r["prompting"] = d["prompting"]
    r.setdefault("tags", [])
    r.setdefault("reusable_prompts", [])
    r.setdefault("patterns", [])
    r.setdefault("time_sinks", [])
    r.setdefault("coaching", [])
    r.setdefault("next_steps", [])
    for s in r.get("steps") or []:
        s.setdefault("links", [])
        if s.get("t") is None:
            s["t"] = 0
    return r
