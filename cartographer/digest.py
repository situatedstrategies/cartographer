"""Session -> digest.

The digest is the agent-agnostic, compressed view of a session that the
mapping model reads: a timeline of prompts (with pragmatic annotations),
replies, tool bursts, errors, branch changes and pauses, plus project, language
and prompting statistics. It is deterministic and cheap; judgment happens later.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from . import config, gitinfo, lang
from .adapters.base import BRANCH, ERROR, NOTE, PROMPT, REPLY, TOOL, Event, Session, sort_events

SCHEMA = "cartographer.digest/v2"
MAX_EVENTS = 450
PAUSE_MIN = 10          # a gap this long becomes a visible "pause" event
REPLY_CLIP = 420
ERROR_CLIP = 320
TOOL_RUN_KEEP = 6


def clip(text: str, n: int) -> str:
    text = re.sub(r"[ \t]+", " ", (text or "")).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def relpath(path: str, root: Optional[str]) -> str:
    if root and path.startswith(root.rstrip("/") + "/"):
        return path[len(root.rstrip("/")) + 1:]
    return path


def build(session: Session, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or config.load()
    eff = config.effective(cfg)
    events = sort_events(session.events)
    start = session.started
    git = gitinfo.inspect(session.cwd, cfg["projects"].get("identity", "git"))
    root = git.get("root")

    touched: Counter = Counter()
    read: Counter = Counter()
    tools: Counter = Counter()
    fences: List[str] = []
    prompt_texts: List[str] = []
    profiles: List[Dict[str, Any]] = []
    branches: List[str] = [b for b in [session.branch] if b]
    timeline: List[Dict[str, Any]] = []
    stats = Counter()
    last_ts = None

    def t_of(e: Event) -> Optional[float]:
        return round((e.ts - start).total_seconds() / 60, 1) if (e.ts and start) else None

    for e in events:
        if e.ts and last_ts and (e.ts - last_ts).total_seconds() >= PAUSE_MIN * 60:
            gap = round((e.ts - last_ts).total_seconds() / 60)
            timeline.append({"t": t_of(e), "kind": "pause", "minutes": gap})
        if e.ts:
            last_ts = e.ts

        if e.kind == PROMPT:
            stats["prompts"] += 1
            prompt_texts.append(e.text)
            profile = lang.analyze_prompt(e.text)
            fences.extend(profile["code_blocks"])
            profiles.append(profile)
            text = e.text if eff["keep_exact_prompts"] else clip(e.text, 240)
            timeline.append({"t": t_of(e), "kind": "prompt", "n": stats["prompts"], "text": text,
                             "read": _profile_line(profile), "pasted": bool(e.meta.get("pasted")), "mid_turn": bool(e.meta.get("mid_turn")),
                             "attached": [relpath(p, root) for p in e.meta.get("attached", [])][:6]})
        elif e.kind == REPLY:
            stats["replies"] += 1
            timeline.append({"t": t_of(e), "kind": "reply", "text": clip(e.text, 1200 if eff["store_replies"] else REPLY_CLIP)})
        elif e.kind == TOOL:
            stats["tool_calls"] += 1
            tools[e.tool] += 1
            for f in e.files:
                touched[relpath(f, root)] += 1
            if e.meta.get("read"):
                read[relpath(e.meta["read"], root)] += 1
            if e.meta.get("subagent"):
                stats["subagents"] += 1
            line = "%s: %s" % (e.tool, clip(relpath(e.text, root), 140)) if e.text else e.tool
            prev = timeline[-1] if timeline else None
            if prev and prev["kind"] == "tools":
                prev["calls"].append(line)
            else:
                timeline.append({"t": t_of(e), "kind": "tools", "calls": [line]})
        elif e.kind == ERROR:
            stats["errors"] += 1
            timeline.append({"t": t_of(e), "kind": "error", "tool": e.tool, "text": clip(e.text, ERROR_CLIP)})
        elif e.kind == BRANCH:
            stats["branch_changes"] += 1
            if e.text not in branches:
                branches.append(e.text)
            timeline.append({"t": t_of(e), "kind": "branch", "to": e.text, "from": e.meta.get("from")})
        elif e.kind == NOTE:
            timeline.append({"t": t_of(e), "kind": "note", "text": clip(e.text, 160)})

    for item in timeline:
        if item["kind"] == "tools" and len(item["calls"]) > TOOL_RUN_KEEP + 2:
            extra = len(item["calls"]) - TOOL_RUN_KEEP
            counts = Counter(c.split(":", 1)[0] for c in item["calls"][TOOL_RUN_KEEP:])
            item["calls"] = item["calls"][:TOOL_RUN_KEEP] + ["… %d more (%s)" % (extra, ", ".join("%s×%d" % kv for kv in counts.most_common(4)))]

    if len(timeline) > MAX_EVENTS:
        keep = [x for x in timeline if x["kind"] in ("prompt", "error", "branch", "pause")]
        rest = [x for x in timeline if x["kind"] not in ("prompt", "error", "branch", "pause")]
        step = max(1, len(rest) // max(1, MAX_EVENTS - len(keep)))
        kept = set(id(x) for x in keep + rest[::step])
        timeline = [x for x in timeline if id(x) in kept]

    files_all = list(touched) + list(read)
    languages = lang.detect_languages(files_all, fences, prompt_texts)
    frameworks = lang.detect_frameworks(prompt_texts + [x.get("text", "") for x in timeline if x["kind"] == "reply"], files_all)
    ended = session.ended
    duration = round((ended - start).total_seconds() / 60, 1) if start and ended else None
    stats["files_touched"] = len(touched)
    stats["files_read"] = len(read)
    stats["subagent_events"] = session.meta.get("subagent_events", 0)

    return {
        "schema": SCHEMA,
        "agent": session.agent,
        "session_id": session.id,
        "transcript": session.path,
        "title": session.title,
        "model": session.model,
        "cwd": session.cwd,
        "project": {"id": git.get("id"), "name": git.get("name"), "root": root, "remote": git.get("remote"),
                    "kind": git.get("kind"), "exists": git.get("exists")},
        "branch": session.branch or git.get("branch"),
        "branches": branches or ([git["branch"]] if git.get("branch") else []),
        "started_at": start.isoformat() if start else None,
        "ended_at": ended.isoformat() if ended else None,
        "duration_min": duration,
        "stats": dict(stats),
        "tools": dict(tools.most_common()),
        "files": [f for f, _ in touched.most_common(40)],
        "files_read": [f for f, _ in read.most_common(25)],
        "languages": languages,
        "frameworks": frameworks,
        "prompting": lang.aggregate(profiles),
        "timeline": timeline,
    }


def _profile_line(p: Dict[str, Any]) -> str:
    """One line the model can scan: intent/mode/scope/specificity plus the signals."""
    bits = ["%s %s" % (p["mode"], p["intent"]), "scope=%s" % p["scope"], "spec=%d/3" % p["specificity"]]
    a = p["anchors"]
    anchors = []
    if a["paths"]:
        anchors.append("files:" + ",".join(a["paths"][:3]))
    if a["symbols"]:
        anchors.append("symbols:" + ",".join(a["symbols"][:3]))
    if a["error_text"]:
        anchors.append("error text")
    if anchors:
        bits.append("anchors=" + " ".join(anchors))
    if p["constraints"]:
        bits.append("constraints=%d" % p["constraints"])
    if p["acceptance"]:
        bits.append("has done-condition")
    if p["vague"]:
        bits.append("vague=" + "|".join(p["vague"][:3]))
    if p["delegation"]:
        bits.append("delegates")
    if p["code_blocks"]:
        bits.append("pasted=" + ",".join(p["code_blocks"][:3]))
    if p["languages"] or p["frameworks"]:
        bits.append("names=" + ",".join((p["languages"] + p["frameworks"])[:4]))
    if p["signals"]:
        bits.append("signals: " + "; ".join(p["signals"]))
    return " · ".join(bits)
