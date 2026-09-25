"""Prepare a wrap (digest + brief), run it headlessly, sweep idle sessions,
and backfill old ones.

`prepare` is what the interactive skills call: it writes the brief and tells
the agent where to put the recap. `run` does the same and then drives the
agent's own headless CLI (`claude -p`, `codex exec`, `cursor-agent -p`) to
produce the recap without a human in the loop.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import adapters, brief, config, digest, recap, render, store

TIMEOUT_S = 15 * 60


def prepare(agent: Optional[str] = None, session_id: Optional[str] = None, transcript: Optional[str] = None,
            cfg: Optional[Dict[str, Any]] = None, project_name: str = "", force: bool = False,
            cwd: Optional[str] = None) -> Dict[str, Any]:
    cfg = cfg or config.load()
    store.ensure_dirs()
    ad, ref = adapters.resolve(session_id, transcript, agent, cwd)
    key = "%s_%s" % (ad.name, ref.id[:12])
    if not force and store.is_wrapped(ad.name, ref.id):
        return {"skipped": "already wrapped", "agent": ad.name, "session_id": ref.id, "recap": store.wrapped().get("%s:%s" % (ad.name, ref.id))}
    session = ad.load(ref)
    d = digest.build(session, cfg)
    if (d["stats"].get("prompts") or 0) < int(cfg["wrap"].get("min_prompts", 2)) and not force:
        return {"skipped": "too short (%d prompts)" % d["stats"].get("prompts", 0), "agent": ad.name, "session_id": ref.id}
    digest_path = os.path.join(store.DIGESTS, key + ".json")
    with open(digest_path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)
    recap_out = os.path.join(store.BRIEFS, key + ".recap.json")
    text = brief.build(d, cfg, recap_out, project_name)
    brief_path = os.path.join(store.BRIEFS, key + ".md")
    with open(brief_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return {"agent": ad.name, "session_id": ref.id, "transcript": ref.path, "brief": brief_path, "recap_out": recap_out,
            "digest": digest_path, "project": d["project"], "branch": d.get("branch"), "duration_min": d.get("duration_min"),
            "prompts": d["stats"].get("prompts", 0), "languages": [l["lang"] for l in d["languages"][:4]]}


def save_recap_file(path: str, cfg: Optional[Dict[str, Any]] = None, digest_path: Optional[str] = None) -> Dict[str, Any]:
    cfg = cfg or config.load()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    d = None
    if digest_path is None:
        guess = os.path.join(store.DIGESTS, os.path.basename(path).replace(".recap.json", ".json"))
        digest_path = guess if os.path.exists(guess) else None
    if digest_path and os.path.exists(digest_path):
        with open(digest_path, encoding="utf-8") as fh:
            d = json.load(fh)
    data = recap.normalize(data, d)
    errors = recap.validate(data)
    if errors:
        return {"ok": False, "errors": errors}
    saved = store.save_recap(data, cfg)
    proj = data.get("project") or {}
    replay = None
    try:
        replay = render.render_project(proj.get("slug") or proj.get("name") or "")
    except LookupError:
        pass
    return {"ok": True, "saved": saved, "replay": replay, "project": proj.get("name"), "slug": proj.get("slug")}


def headless_command(agent: str, cfg: Dict[str, Any]) -> Optional[List[str]]:
    override = ((cfg.get("agents") or {}).get(agent) or {}).get("headless")
    if override:
        return list(override) if isinstance(override, list) else str(override).split()
    default = list(adapters.get(agent).headless)
    if not default:
        return None
    if agent == "cursor" and not shutil.which(default[0]) and shutil.which("agent"):
        default[0] = "agent"
    if agent == "claude-code":
        default = ["claude", "-p", "--allowedTools", "Read,Write"]
    if agent == "codex":
        default = ["codex", "exec", "--sandbox", "workspace-write"]
    return default if shutil.which(default[0]) else None


def run(agent: Optional[str] = None, session_id: Optional[str] = None, transcript: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None, project_name: str = "", force: bool = False,
        runner: Optional[str] = None) -> Dict[str, Any]:
    """Prepare, then have an agent map the session headlessly. `runner` picks
    which agent's CLI does the mapping (default: the one that made the session)."""
    cfg = cfg or config.load()
    prep = prepare(agent, session_id, transcript, cfg, project_name, force)
    if prep.get("skipped"):
        return prep
    runner = runner or prep["agent"]
    cmd = headless_command(runner, cfg)
    if not cmd:
        prep["error"] = "no headless CLI found for %s; open the brief in your agent instead" % runner
        return prep
    prompt = ("Read the file %s and follow it exactly. Write the recap JSON to %s. Do not run the save command and do not "
              "touch any other file; Cartographer saves it for you. Reply with one line when done." % (prep["brief"], prep["recap_out"]))
    started = time.time()
    try:
        proc = subprocess.run(cmd + [prompt], cwd=store.BRIEFS, capture_output=True, text=True, timeout=TIMEOUT_S)
        prep["runner_exit"] = proc.returncode
        prep["runner_tail"] = (proc.stdout or proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        prep["error"] = "runner timed out after %d s" % TIMEOUT_S
        return prep
    except OSError as exc:
        prep["error"] = "could not start runner: %s" % exc
        return prep
    prep["runner_seconds"] = round(time.time() - started)
    if not os.path.exists(prep["recap_out"]):
        prep["error"] = "runner finished but wrote no recap"
        return prep
    if store.is_wrapped(prep["agent"], prep["session_id"]) and not force:
        prep["saved"] = store.wrapped().get("%s:%s" % (prep["agent"], prep["session_id"]))
        return prep
    result = save_recap_file(prep["recap_out"], cfg, prep["digest"])
    prep.update(result)
    return prep


def sweep(cfg: Optional[Dict[str, Any]] = None, idle_min: Optional[int] = None, since_days: int = 7,
          dry: bool = False, runner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Wrap every session that ended (queue) or went quiet (idle) and isn't wrapped yet."""
    cfg = cfg or config.load()
    idle = idle_min or int(cfg["wrap"].get("idle_minutes", 30))
    now = time.time()
    candidates: Dict[str, Dict[str, Any]] = {}
    for item in store.drain_queue():
        if item.get("session_id"):
            candidates["%s:%s" % (item["agent"], item["session_id"])] = item
    for ad in adapters.installed():
        if not ((cfg.get("agents") or {}).get(ad.name) or {}).get("enabled", True):
            continue
        for ref in ad.list_sessions():
            age_min = (now - ref.mtime) / 60
            if age_min < idle or age_min > since_days * 24 * 60 or store.is_wrapped(ad.name, ref.id):
                continue
            candidates.setdefault("%s:%s" % (ad.name, ref.id), {"agent": ad.name, "session_id": ref.id, "transcript": ref.path if ad.name != "cursor" else None})
    results = []
    for key, item in candidates.items():
        if store.is_wrapped(item["agent"], item["session_id"]):
            continue
        if dry:
            results.append({"would_wrap": key})
            continue
        try:
            results.append(run(item["agent"], item["session_id"], item.get("transcript"), cfg, runner=runner))
        except Exception as exc:  # keep sweeping; report per session
            results.append({"agent": item["agent"], "session_id": item["session_id"], "error": str(exc)})
    _log("sweep", results)
    return results


def backfill(cwd: str, agent: Optional[str] = None, cfg: Optional[Dict[str, Any]] = None, limit: Optional[int] = None,
             execute: bool = False, runner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrospective maps: every past session for a folder, oldest first."""
    cfg = cfg or config.load()
    refs = adapters.list_all(cwd=cwd, agent=agent)
    refs.sort(key=lambda r: r.mtime)
    if limit:
        refs = refs[-limit:]
    out = []
    for ref in refs:
        if store.is_wrapped(ref.agent, ref.id):
            continue
        fn = run if execute else prepare
        try:
            out.append(fn(ref.agent, ref.id, ref.path if ref.agent != "cursor" else None, cfg, **({"runner": runner} if execute else {})))
        except Exception as exc:
            out.append({"agent": ref.agent, "session_id": ref.id, "error": str(exc)})
    return out


def _log(kind: str, payload: Any) -> None:
    try:
        with open(os.path.join(config.HOME, "cartographer.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), kind: payload}, default=str) + "\n")
    except OSError:
        pass
