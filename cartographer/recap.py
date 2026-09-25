"""Recap schema: the story of one session.

The unit is a *move*: what you did, what happened, what it meant, how you
responded. The mapping model writes moves in second person; the replay
narrates them. `normalize` fills what can be derived from the digest, treats
placeholders copied from the example as unset, and converts the older
typed-step shape (v2) into moves so old maps still play. `validate` returns
human-readable problems.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

SCHEMA = "cartographer.session/v3"
OUTCOMES = ("worked", "partly", "broke", "wrong_way", "opened")      # what happened, in one word
MARKS = ("decision", "question", "dead_end", "fix", "artifact", "pivot", "insight")  # optional turning-point tag
FOCUS = ("prompt", "code", "workflow")
PLACEHOLDER = re.compile(r"^(?:…|\.\.\.|YYYY-MM-DD|TBD|)$")

EXAMPLE: Dict[str, Any] = {
    "schema": SCHEMA,
    "agent": "claude-code", "session_id": "…", "title": "Short session title",
    "project": {"id": "github.com/me/app", "name": "app", "root": "/path/to/repo", "remote": "git@github.com:me/app.git"},
    "branch": "feature/auth", "branches": ["main", "feature/auth"],
    "date": "YYYY-MM-DD", "started_at": "…", "ended_at": "…", "duration_min": 0,
    "desired": "the desired outcome declared for this version (copied from the project; null when none was declared)",
    "goal": "what you set out to do this session, in your own terms",
    "outcome": "where the session actually landed, judged against `desired` when there is one",
    "voice": "native",
    "languages": ["typescript"], "frameworks": ["Next.js"], "files": ["src/auth.ts"],
    "tags": ["nextjs", "auth", "webapp"],
    "phases": [{"name": "Explore", "summary": "one line", "branch": "main"}],
    "moves": [{
        "id": "m1", "t": 0.0, "phase": "Explore", "branch": "main",
        "you": "What you did, second person, one sentence: 'You asked for…'",
        "prompt": "your exact wording, when the phrasing is the lesson",
        "happened": "What the agent did and what resulted. One or two concrete sentences.",
        "consequence": "What that meant for the build.",
        "outcome": "worked",
        "response": "How you responded: accepted it, repaired it, went back, changed direction.",
        "mark": "decision",
        "evidence": ["prompt #3", "error at 12.4m", "repair at 20.1m"],
        "files": ["src/auth.ts"],
        "plain": {"you": "same move in everyday words", "happened": "…", "consequence": "…", "response": "only when voice is 'both'"},
    }],
    "reusable_prompts": [{"prompt": "template with <placeholders>", "why": "what it reliably gets", "language": "typescript"}],
    "patterns": ["neutral observation about how you build"],
    "time_sinks": [{"what": "…", "minutes": 0}],
    "coaching": [{"focus": "prompt", "observation": "what happened", "suggestion": "what to do next time",
                  "rewrite": "an improved version of a real prompt from this session", "move": "m3"}],
    "next_steps": ["unfinished work, phrased so the next session can pick it up"],
}
DERIVED = ("agent", "session_id", "title", "started_at", "ended_at", "duration_min", "branch", "branches", "frameworks", "files", "project", "desired")
PRAISE = re.compile(r"\b(?:great|excellent|brilliant|smart|impressive|nicely|beautifully|perfect(?:ly)?|well done|good job|wonderful|amazing|fantastic)\b", re.I)
RESULTS = ("shipped", "partial", "abandoned")
APPRAISAL_SCHEMA = "cartographer.appraisal/v1"
APPRAISAL_EXAMPLE: Dict[str, Any] = {
    "schema": APPRAISAL_SCHEMA,
    "project": {"id": "github.com/me/app", "name": "app"}, "version": "v1",
    "desired": "what done meant, as declared", "result": "shipped", "actual": "what actually shipped, as declared",
    "verdict": "Two or three sentences: did the build reach the desired outcome, and what the record shows about why. Say 'unclear from the record' where it is.",
    "got_you_there": [{"what": "a move or habit that produced the result", "why": "the mechanism, technically", "evidence": ["session a1b2c3d4 m4"]}],
    "cost_you": [{"what": "a detour, a loop, a wrong turn", "minutes": 0, "evidence": ["session a1b2c3d4 m7", "pause 56m"]}],
    "carried_forward": [{"what": "a technical implication now living in the result: a shortcut, a dependency, a missing test, a data shape", "since": "session a1b2c3d4 m9", "risk": "what it will cost later", "evidence": ["session a1b2c3d4 m9"]}],
    "prompting": [{"pattern": "how you prompted, neutrally", "effect": "how it showed up in the outcome", "evidence": ["session a1b2c3d4 prompt #2"]}],
    "next_time": ["one concrete change per line, tied to an item above"],
}
LEGACY_OUTCOME = {"dead_end": "wrong_way", "fix": "worked", "artifact": "worked", "decision": "worked", "pivot": "opened", "question": "opened", "insight": "opened"}


LITERAL_OK = {"agent", "voice", "branch", "branches", "languages", "frameworks", "files", "tags", "schema", "result"}  # real values can equal the example's


def _unset(key: str, value: Any) -> bool:
    """Missing, empty, a placeholder, or copied verbatim from the example."""
    if value is None or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, str) and PLACEHOLDER.match(value.strip()):
        return True
    return key not in LITERAL_OK and value == EXAMPLE.get(key)


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate(recap: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if not isinstance(recap, dict):
        return ["recap must be a JSON object"]
    for key in ("title", "goal", "outcome", "phases", "moves"):
        if _unset(key, recap.get(key)):
            errs.append("missing %s" % key)
    phases = recap.get("phases") or []
    names = {p["name"] for p in phases if isinstance(p, dict) and p.get("name")}
    errs += ["phases[%d] needs a name" % i for i, p in enumerate(phases) if not (isinstance(p, dict) and p.get("name"))]
    if len(phases) > 8:
        errs.append("too many phases (%d); merge to 8 or fewer" % len(phases))
    moves = [m for m in (recap.get("moves") or []) if isinstance(m, dict)]
    ids = [m.get("id") for m in moves]
    for i, m in enumerate(moves):
        mid = m.get("id")
        if not mid:
            errs.append("moves[%d] needs an id" % i)
        elif ids.index(mid) != i:
            errs.append("duplicate move id %s" % mid)
        for key in ("you", "happened"):
            if _unset(key, m.get(key)) or m.get(key) == EXAMPLE["moves"][0][key]:
                errs.append("move %s: missing %s" % (mid, key))
        if m.get("outcome") not in OUTCOMES:
            errs.append("move %s: outcome must be one of %s" % (mid, ", ".join(OUTCOMES)))
        if m.get("mark") not in (None, "") and m["mark"] not in MARKS:
            errs.append("move %s: mark must be one of %s" % (mid, ", ".join(MARKS)))
        if m.get("t") is not None and not _num(m["t"]):
            errs.append("move %s: t must be a number (minutes from start)" % mid)
        if m.get("phase") and names and m["phase"] not in names:
            errs.append("move %s: phase %r is not in phases" % (mid, m["phase"]))
        ev = m.get("evidence")
        if ev is not None and (not isinstance(ev, list) or not all(isinstance(x, str) and x.strip() for x in ev)):
            errs.append("move %s: evidence must be a list of strings naming timeline items" % mid)
        for key in ("happened", "consequence"):
            hit = PRAISE.search(m.get(key) or "")
            if hit:
                errs.append("move %s: praise word %r in %s; state the implication instead" % (mid, hit.group(0), key))
    if len(moves) < 3:
        errs.append("fewer than 3 moves; a story needs at least what you set out to do, a turning point and where it landed")
    if len(moves) > 30:
        errs.append("more than 30 moves; merge rounds that continued one line of work")
    for i, c in enumerate(recap.get("coaching") or []):
        if not isinstance(c, dict) or c.get("focus") not in FOCUS:
            errs.append("coaching[%d]: focus must be one of %s" % (i, ", ".join(FOCUS)))
        elif not (c.get("observation") and c.get("suggestion")):
            errs.append("coaching[%d]: needs observation and suggestion" % i)
        elif (c.get("move") or c.get("step")) and (c.get("move") or c.get("step")) not in ids:
            errs.append("coaching[%d]: move %r is not a move id" % (i, c.get("move") or c.get("step")))
    for i, t in enumerate(recap.get("time_sinks") or []):
        if not isinstance(t, dict) or not t.get("what") or (t.get("minutes") is not None and not _num(t["minutes"])):
            errs.append("time_sinks[%d]: needs `what` and a numeric `minutes`" % i)
    return errs


def moves_from_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """v2 typed steps -> moves. Each prompt step opens a move; what followed it is what happened;
    the next prompt is how you responded. Lossy, but old maps keep playing."""
    moves: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for s in steps:
        if not isinstance(s, dict):
            continue
        kind, line = s.get("kind"), (s.get("title") or "") + ((": " + s["detail"]) if s.get("detail") else "")
        if cur is None or kind == "prompt":
            cur = {"id": s.get("id"), "t": s.get("t") or 0, "phase": s.get("phase"), "branch": s.get("branch"),
                   "you": s.get("title") or "" if kind == "prompt" else "", "prompt": s.get("prompt"),
                   "happened": "" if kind == "prompt" else line, "consequence": "", "outcome": LEGACY_OUTCOME.get(kind, "partly"),
                   "response": "", "mark": None if kind == "prompt" else kind, "files": list(s.get("files") or []), "_detail": s.get("detail") or ""}
            moves.append(cur)
        else:
            cur["happened"] = (cur["happened"] + " " if cur["happened"] else "") + line
            cur["files"] += [f for f in s.get("files") or [] if f not in cur["files"]]
            if kind in LEGACY_OUTCOME and (cur["mark"] is None or kind in ("dead_end", "fix", "pivot")):
                cur["mark"], cur["outcome"] = kind, LEGACY_OUTCOME[kind]
    for m in moves:
        m["happened"] = m["happened"] or m.pop("_detail", "") or m["you"]
        m.pop("_detail", None)
    for a, b in zip(moves, moves[1:]):
        a["response"] = b["you"]
    return moves


def normalize(recap: Dict[str, Any], digest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill derivable fields from the digest. The model's real values win; placeholders don't."""
    r = copy.deepcopy(recap)
    r["schema"] = SCHEMA
    if r.get("voice") == "technical":
        r["voice"] = "native"
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
    if not r.get("moves") and r.get("steps"):
        r["moves"] = moves_from_steps(r["steps"])
    for m in r.get("moves") or []:
        if isinstance(m, dict):
            m.setdefault("files", [])
            if m.get("t") is None:
                m["t"] = 0
            if not m.get("outcome"):
                m["outcome"] = "partly"
    for c in r.get("coaching") or []:
        if isinstance(c, dict) and c.get("step") and not c.get("move"):
            c["move"] = c.pop("step")
    return r


# ------------------------------------------------------------ appraisal

def is_appraisal(data: Any) -> bool:
    return isinstance(data, dict) and str(data.get("schema") or "").startswith("cartographer.appraisal")


def validate_appraisal(a: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if not isinstance(a, dict):
        return ["appraisal must be a JSON object"]
    if _unset("verdict", a.get("verdict")) or a.get("verdict") == APPRAISAL_EXAMPLE["verdict"]:
        errs.append("missing verdict")
    hit = PRAISE.search(a.get("verdict") or "")
    if hit:
        errs.append("verdict: praise word %r; say what the record shows instead" % hit.group(0))
    if a.get("result") not in RESULTS:
        errs.append("result must be one of %s" % ", ".join(RESULTS))
    for key in ("got_you_there", "cost_you", "carried_forward", "prompting"):
        items = a.get(key)
        if not isinstance(items, list):
            errs.append("missing %s (use [] when the record shows nothing)" % key)
            continue
        for i, it in enumerate(items):
            if not isinstance(it, dict) or not (it.get("what") or it.get("pattern")):
                errs.append("%s[%d]: needs `what`" % (key, i))
            elif not (isinstance(it.get("evidence"), list) and it["evidence"]):
                errs.append("%s[%d]: needs evidence (session ids and move ids); an item without evidence is invented" % (key, i))
            elif key == "cost_you" and it.get("minutes") is not None and not _num(it["minutes"]):
                errs.append("cost_you[%d]: minutes must be a number" % i)
    if not isinstance(a.get("next_time"), list):
        errs.append("missing next_time")
    return errs
