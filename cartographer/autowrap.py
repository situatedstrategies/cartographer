"""Prepare a wrap (digest + brief), run it headlessly, sweep idle sessions,
and backfill old ones.

`prepare` is what the interactive skills call: it writes the brief and says
where the recap goes. `run` does the same and then drives the agent's own
headless CLI (`claude -p`, `codex exec`, `cursor-agent -p`) to write the recap
without a human in the loop.
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
    done = store.wrapped_path(ad.name, ref.id)
    if done and not force:
        return {"skipped": "already wrapped", "agent": ad.name, "session_id": ref.id, "recap": done}
    d = digest.build(ad.load(ref), cfg)
    d["desired"] = store.desired_for((d.get("project") or {}).get("id") or "")   # the yardstick, when one was declared
    if (d["stats"].get("prompts") or 0) < int(cfg["wrap"].get("min_prompts", 2)) and not force:
        return {"skipped": "too short (%d prompts)" % d["stats"].get("prompts", 0), "agent": ad.name, "session_id": ref.id}
    key = "%s_%s" % (ad.name, ref.id[:12])
    digest_path = store.write_json(os.path.join(store.DIGESTS, key + ".json"), d)
    recap_out = os.path.join(store.BRIEFS, key + ".recap.json")
    brief_path = os.path.join(store.BRIEFS, key + ".md")
    with open(brief_path, "w", encoding="utf-8") as fh:
        fh.write(brief.build(d, cfg, recap_out, project_name))
    return {"agent": ad.name, "session_id": ref.id, "transcript": ref.path, "brief": brief_path, "recap_out": recap_out,
            "digest": digest_path, "project": d["project"], "branch": d.get("branch"), "duration_min": d.get("duration_min"),
            "prompts": d["stats"].get("prompts", 0), "languages": [l["lang"] for l in d["languages"][:4]]}


def save_recap_file(path: str, cfg: Optional[Dict[str, Any]] = None, digest_path: Optional[str] = None,
                    check: bool = False) -> Dict[str, Any]:
    """Normalize + validate a recap file; unless `check`, store it and render the project replay."""
    cfg = cfg or config.load()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": ["cannot read %s: %s" % (path, exc)]}
    if recap.is_appraisal(data):
        errors = recap.validate_appraisal(data)
        if errors or check:
            return {"ok": not errors, "errors": errors}
        saved = store.save_appraisal(data, cfg)
        proj = data["project"]
        try:
            replay = render.render_project(proj["slug"])
        except LookupError:
            replay = None
        return {"ok": True, "saved": saved, "replay": replay, "project": proj.get("name"), "slug": proj.get("slug"), "appraisal": data.get("version")}
    if digest_path is None:
        guess = os.path.join(store.DIGESTS, os.path.basename(path).replace(".recap.json", ".json"))
        digest_path = guess if os.path.exists(guess) else None
    data = recap.normalize(data, store.read_json(digest_path, None) if digest_path else None)
    errors = recap.validate(data)
    if errors or check:
        return {"ok": not errors, "errors": errors}
    saved = store.save_recap(data, cfg)
    proj = data.get("project") or {}
    try:
        replay = render.render_project(proj.get("slug") or proj.get("name") or "")
    except LookupError:
        replay = None
    return {"ok": True, "saved": saved, "replay": replay, "project": proj.get("name"), "slug": proj.get("slug")}


def headless_command(agent: str, cfg: Dict[str, Any]) -> Optional[List[str]]:
    override = ((cfg.get("agents") or {}).get(agent) or {}).get("headless")
    if override:
        return list(override) if isinstance(override, list) else str(override).split()
    cmd = {"claude-code": ["claude", "-p", "--allowedTools", "Read,Write"],
           "codex": ["codex", "exec", "--sandbox", "workspace-write"],
           "cursor": ["cursor-agent", "-p", "--force"]}.get(agent)
    if not cmd:
        return None
    if agent == "cursor" and not shutil.which(cmd[0]) and shutil.which("agent"):
        cmd[0] = "agent"
    return cmd if shutil.which(cmd[0]) else None


def run(agent: Optional[str] = None, session_id: Optional[str] = None, transcript: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None, project_name: str = "", force: bool = False,
        runner: Optional[str] = None, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Prepare, then have an agent map the session headlessly. `runner` picks
    which agent's CLI does the mapping (default: the one that made the session)."""
    cfg = cfg or config.load()
    prep = prepare(agent, session_id, transcript, cfg, project_name, force, cwd)
    if prep.get("skipped"):
        return prep
    _headless(runner or prep["agent"], cfg, prep["brief"], prep["recap_out"], prep)
    if prep.get("error"):
        return prep
    if store.is_wrapped(prep["agent"], prep["session_id"]) and not force:
        prep["saved"] = store.wrapped_path(prep["agent"], prep["session_id"])  # the runner saved it itself
    else:
        prep.update(save_recap_file(prep["recap_out"], cfg, prep["digest"]))
    return prep


def _headless(runner: str, cfg: Dict[str, Any], brief_path: str, out_path: str, res: Dict[str, Any]) -> None:
    """Drive an agent CLI through a brief; report into `res` (error, runner_exit, runner_tail, runner_seconds)."""
    cmd = headless_command(runner, cfg)
    if not cmd:
        res["error"] = "no headless CLI found for %s; open the brief in your agent instead" % runner
        return
    prompt = ("Read the file %s and follow it exactly. Write the JSON it asks for to %s. Do not run the save command and do not "
              "touch any other file; Cartographer saves it for you. Reply with one line when done." % (brief_path, out_path))
    started = time.time()
    try:
        proc = subprocess.run(cmd + [prompt], cwd=store.BRIEFS, capture_output=True, text=True, timeout=TIMEOUT_S)
        res["runner_exit"], res["runner_tail"] = proc.returncode, (proc.stdout or proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        res["error"] = "runner timed out after %d s" % TIMEOUT_S
        return
    except OSError as exc:
        res["error"] = "could not start runner: %s" % exc
        return
    res["runner_seconds"] = round(time.time() - started)
    if not os.path.exists(out_path):
        res["error"] = "runner finished but wrote nothing"


def appraise(project: str, cfg: Optional[Dict[str, Any]] = None, version: Optional[str] = None, result: Optional[str] = None,
             actual: str = "", execute: bool = False, runner: Optional[str] = None) -> Dict[str, Any]:
    """Mark a version complete (when `result` is given) and prepare the appraisal brief; `execute` maps it headlessly."""
    cfg = cfg or config.load()
    store.ensure_dirs()
    entry = store.find_project(project)
    if not entry:
        raise LookupError("no project matching %r; wrap a session of it first" % project)
    if result:
        v = store.complete(entry["id"], result, actual, version)
    else:
        v = store.get_version(entry["id"], version)
        if not v or not v.get("completed_at"):
            raise LookupError("%s has no completed version%s; pass --result shipped|partial|abandoned" % (entry["name"], (" named %s" % version) if version else ""))
    recaps = store.load_recaps(entry["slug"])
    if not recaps:
        raise LookupError("%s has no wrapped sessions; nothing to appraise" % entry["name"])
    key = "%s_%s" % (entry["slug"], store.project_slug(v["name"]))
    out = os.path.join(store.BRIEFS, key + ".appraisal.json")
    path = os.path.join(store.BRIEFS, key + ".appraisal.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(brief.build_appraisal(entry, v, recaps, cfg, out))
    res: Dict[str, Any] = {"project": entry["name"], "slug": entry["slug"], "version": v["name"], "result": v.get("result"),
                           "desired": v.get("desired"), "sessions": len(recaps), "brief": path, "recap_out": out}
    if execute:
        _headless(runner or "claude-code", cfg, path, out, res)
        if not res.get("error"):
            res.update(save_recap_file(out, cfg))
    return res


def sweep(cfg: Optional[Dict[str, Any]] = None, idle_min: Optional[int] = None, since_days: int = 7,
          dry: bool = False, runner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Wrap every session that has been quiet for `idle_min` minutes and isn't wrapped yet."""
    cfg = cfg or config.load()
    idle = idle_min or int(cfg["wrap"].get("idle_minutes", 30))
    now = time.time()
    results = []
    for ad in adapters.installed():
        if not ((cfg.get("agents") or {}).get(ad.name) or {}).get("enabled", True):
            continue
        for ref in ad.list_sessions():
            age_min = (now - ref.mtime) / 60
            if age_min < idle or age_min > since_days * 1440 or store.is_wrapped(ad.name, ref.id):
                continue
            if dry:
                results.append({"would_wrap": "%s:%s" % (ad.name, ref.id)})
                continue
            try:
                results.append(run(ad.name, ref.id, _transcript(ad.name, ref.path), cfg, runner=runner))
            except Exception as exc:  # keep sweeping; report per session
                results.append({"agent": ad.name, "session_id": ref.id, "error": str(exc)})
    log("sweep", results)
    return results


def backfill(cwd: str, agent: Optional[str] = None, cfg: Optional[Dict[str, Any]] = None, limit: Optional[int] = None,
             execute: bool = False, runner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrospective maps: every past session for a folder, oldest first."""
    cfg = cfg or config.load()
    refs = sorted(adapters.list_all(cwd=cwd, agent=agent), key=lambda r: r.mtime)
    out = []
    for ref in refs[-limit:] if limit else refs:
        if store.is_wrapped(ref.agent, ref.id):
            continue
        try:
            if execute:
                out.append(run(ref.agent, ref.id, _transcript(ref.agent, ref.path), cfg, runner=runner))
            else:
                out.append(prepare(ref.agent, ref.id, _transcript(ref.agent, ref.path), cfg))
        except Exception as exc:
            out.append({"agent": ref.agent, "session_id": ref.id, "error": str(exc)})
    return out


def _transcript(agent: str, path: str) -> Optional[str]:
    return None if agent == "cursor" else path  # Cursor sessions live in one shared database, so go by id


def log(kind: str, payload: Any) -> None:
    try:
        with open(os.path.join(config.HOME, "cartographer.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), kind: payload}, default=str) + "\n")
    except OSError:
        pass
