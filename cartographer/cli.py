"""cartographer — map how you build with coding agents.

    sessions    list sessions found for every installed agent (✓ = wrapped)
    wrap        write the mapping brief for a session; --run maps it headlessly
    goal        declare what done means for the project's current version (the yardstick)
    complete    mark a version complete and write the appraisal brief; --run appraises headlessly
    save        validate, store and render a recap (--check only validates)
    serve       local dashboard: projects, sessions, replays, setup (this machine only)
    open        open a project's replay in the browser (default: the newest)
    render      build a project replay
    projects    list wrapped projects
    sweep       auto-wrap sessions that went idle
    backfill    briefs (or, with --run, maps) for every past session of a repo
    config      show | set KEY VALUE | init | path
    install     install into Claude Code, Codex CLI and Cursor
    doctor      what's installed, where things are
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, List, Optional

from . import __version__, adapters, autowrap, config, gitinfo, hooks, recap, render, serve, store


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def _agent_arg(value: Optional[str]) -> Optional[str]:
    return adapters.get(value).name if value else None


def _open(path: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
    except OSError:
        pass


def _stdin_json() -> dict:
    """Hook payload from stdin, without blocking when nothing is piped in."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        if os.name != "nt":
            import select
            if not select.select([sys.stdin], [], [], 2)[0]:
                return {}
        return json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return {}


def cmd_sessions(a) -> int:
    agent = _agent_arg(a.agent)
    here = a.cwd or os.getcwd()
    refs = adapters.list_all(cwd=None if a.all else here, agent=agent, limit=a.limit)
    if not refs and not a.all:
        refs = adapters.list_all(agent=agent, limit=a.limit)
        if refs:
            print("(no %ssessions recorded for %s, so this is every folder on this machine; run it inside the project "
                  "folder, or pass --cwd <folder>, to see just one project)\n" % ((agent + " ") if agent else "", here), file=sys.stderr)
    done = store.wrapped()
    for r in refs:
        when = datetime.fromtimestamp(r.mtime).strftime("%Y-%m-%d %H:%M") if r.mtime else "?"
        mark = "✓" if ("%s:%s" % (r.agent, r.id[:8])) in done else " "
        print("%s %-12s %-14s %s  %s%s" % (mark, r.agent, r.id[:12], when, r.cwd or "", ("  · " + r.title) if r.title else ""))
    if not refs:
        print("no sessions found", file=sys.stderr)
        return 1
    return 0


def cmd_wrap(a) -> int:
    cfg = config.load()
    if a.run:
        res = autowrap.run(_agent_arg(a.agent), a.session, a.transcript, cfg, a.project or "", a.force, _agent_arg(a.runner), a.cwd)
        _print(res)
        return 0 if res.get("ok") or res.get("skipped") else 1
    res = autowrap.prepare(_agent_arg(a.agent), a.session, a.transcript, cfg, a.project or "", a.force, a.cwd)
    if res.get("skipped"):
        print("SKIPPED: %s" % res["skipped"] + ("\nRECAP: %s" % res["recap"] if res.get("recap") else ""))
        return 2
    if a.print_brief:
        with open(res["brief"], encoding="utf-8") as fh:
            print(fh.read())
        return 0
    proj = res["project"] or {}
    if res.get("note"):
        print("NOTE: %s" % res["note"])
    for key, val in (("BRIEF", res["brief"]), ("RECAP_OUT", res["recap_out"]), ("DIGEST", res["digest"]), ("AGENT", res["agent"]),
                     ("SESSION", res["session_id"]), ("PROJECT", "%s (%s)" % (proj.get("name"), proj.get("id"))),
                     ("BRANCH", res.get("branch") or ""), ("DURATION_MIN", res.get("duration_min")), ("PROMPTS", res.get("prompts")),
                     ("LANGUAGES", ", ".join(res.get("languages") or []))):
        print("%s: %s" % (key, val))
    return 0


def _project_arg(name: Optional[str]) -> str:
    """An explicit project, else the repo we are standing in (registered if needed)."""
    if name:
        return name
    info = gitinfo.inspect(os.getcwd(), config.load()["projects"].get("identity", "git"))
    if info.get("id") and not store.find_project(info["id"]):
        store.register_project(info["id"], info.get("name") or "project", info.get("root"), info.get("remote"))
    return info.get("id") or ""


def cmd_goal(a) -> int:
    entry = store.find_project(_project_arg(a.project))
    v = store.set_goal(entry["id"], a.text, a.version) if entry else None
    if not v:
        print("no project found; run this inside the repo or pass --project", file=sys.stderr)
        return 1
    print("%s %s: done means\n  %s" % (entry["name"], v["name"], v["desired"]))
    return 0


def cmd_complete(a) -> int:
    res = autowrap.appraise(_project_arg(a.project), config.load(), a.version, a.result, a.actual or "", a.run, _agent_arg(a.runner))
    if a.run:
        _print(res)
        return 0 if res.get("ok") else 1
    if a.print_brief:
        with open(res["brief"], encoding="utf-8") as fh:
            print(fh.read())
        return 0
    for key, val in (("BRIEF", res["brief"]), ("RECAP_OUT", res["recap_out"]), ("PROJECT", res["project"]), ("VERSION", res["version"]),
                     ("RESULT", res["result"]), ("DESIRED", res.get("desired") or "(never declared)"), ("SESSIONS", res["sessions"])):
        print("%s: %s" % (key, val))
    return 0


def cmd_save(a) -> int:
    res = autowrap.save_recap_file(a.recap, config.load(), a.digest, a.check)
    if not res["ok"]:
        print("recap has problems:\n" + "\n".join("  - " + e for e in res["errors"]))
        return 1
    if a.check:
        print("ok")
        return 0
    print("SAVED: %s%s" % (res["saved"], (" (appraisal of %s)" % res["appraisal"]) if res.get("appraisal") else ""))
    if res.get("replay"):
        print("REPLAY: %s" % res["replay"])
        print("OPEN: cartographer open %s   (or `cartographer serve --open` for the dashboard)" % (res.get("slug") or ""))
        if a.open:
            _open(res["replay"])
    return 0


def cmd_render(a) -> int:
    if a.all:
        recaps = store.load_recaps()
        if not recaps:
            print("nothing wrapped yet", file=sys.stderr)
            return 1
        path = render.render_recaps(recaps, a.title or "All projects", a.out or os.path.join(store.REPLAYS, "all-projects.html"))
    elif a.files:
        loaded = [store.read_json(p, {}) for p in a.files]
        recaps = [r for r in loaded if not recap.is_appraisal(r)]
        appraisals = [r for r in loaded if recap.is_appraisal(r)]
        if not recaps:
            print("no session maps among those files", file=sys.stderr)
            return 1
        title = a.title or (recaps[-1].get("project") or {}).get("name") or recaps[-1].get("title") or "Replay"
        out = a.out or os.path.join(store.REPLAYS, "%s.html" % store.project_slug(title))
        path = render.render_recaps(sorted(recaps, key=lambda r: r.get("started_at") or ""), title, out, appraisals)
    elif a.project:
        path = render.render_project(a.project, a.out)
    else:
        print("give a project name (see `cartographer projects`), recap files, or --all", file=sys.stderr)
        return 1
    print(path)
    if a.open:
        _open(path)
    return 0


def cmd_serve(a) -> int:
    serve.serve(a.port, a.open)
    return 0


def cmd_open(a) -> int:
    if a.project:
        path = render.render_project(a.project)
    else:
        recaps = store.load_recaps()
        if not recaps:
            print("nothing wrapped yet: type /wrap in Claude Code at the end of a session, or run `cartographer serve --open`", file=sys.stderr)
            return 1
        latest = max(recaps, key=lambda r: r.get("saved_at") or "")
        path = render.render_project((latest.get("project") or {}).get("slug") or (latest.get("project") or {}).get("name") or "")
    print(path)
    _open(path)
    return 0


def cmd_projects(a) -> int:
    reg = store.projects()
    if not reg:
        print("no projects yet; wrap a session first")
        return 1
    for pid, p in sorted(reg.items(), key=lambda kv: kv[1].get("name", "")):
        n = len(store.load_recaps(p["slug"]))
        print("%-28s %-3d session%s  %s" % (p["name"], n, "" if n == 1 else "s", pid))
        for v in p.get("versions") or []:
            state = ("%s%s" % (v["result"], ", appraised" if v.get("appraisal") else ", not yet appraised: `cartographer complete`")) if v.get("completed_at") else "open"
            print("    %-6s %-40s %s" % (v["name"], state, ("done means: " + v["desired"]) if v.get("desired") else "no desired outcome declared (`cartographer goal`)"))
    return 0


def cmd_config(a) -> int:
    cfg = config.load()
    if a.action == "path":
        print(config.PATH)
    elif a.action == "show":
        _print(cfg if not a.key else config.get(cfg, a.key))
        if not a.key:
            print("\neffective:", json.dumps(config.effective(cfg)))
    elif a.action == "set":
        if not a.key or a.value is None:
            print("usage: cartographer config set KEY VALUE", file=sys.stderr)
            return 1
        value = config.set_value(cfg, a.key, a.value)
        config.save(cfg)
        print("%s = %s" % (a.key, json.dumps(value)))
    elif a.action == "init":
        config.wizard(cfg)
        print("\nsaved to " + config.save(cfg))
        print("effective:", json.dumps(config.effective(cfg)))
    return 0


def cmd_install(a) -> int:
    cfg = config.load()
    if not a.no_copy:
        hooks.self_install()
    bin_cmd = hooks.command_prefix()
    if a.auto or a.manual:
        config.set_value(cfg, "wrap.mode", "auto" if a.auto else "manual")
    config.save(cfg)
    store.ensure_dirs()
    auto = cfg["wrap"]["mode"] == "auto"
    agents_list = ["claude-code", "codex", "cursor"] if (not a.agent or "all" in a.agent) else [adapters.get(x).name for x in a.agent]
    print("cartographer command: %s" % bin_cmd)
    for name in agents_list:
        for msg in hooks.install(name, auto, a.project, bin_cmd):
            print("• " + msg)
    print("\nmode: %s · config: %s" % (cfg["wrap"]["mode"], config.PATH))
    print("next: `cartographer serve --open` opens the dashboard (setup, sessions, maps); `cartographer config init` does setup in the terminal")
    return 0


def cmd_hook(a) -> int:
    payload = _stdin_json()
    if a.payload:
        try:
            payload.update(json.loads(a.payload))
        except json.JSONDecodeError:
            pass
    autowrap.log("hook", hooks.handle(adapters.get(a.agent).name, payload, config.load()))
    return 0


def cmd_sweep(a) -> int:
    _print(autowrap.sweep(config.load(), a.idle, a.since_days, a.dry, _agent_arg(a.runner)))
    return 0


def cmd_backfill(a) -> int:
    _print(autowrap.backfill(os.path.abspath(a.cwd or os.getcwd()), _agent_arg(a.agent), config.load(), a.limit, a.run, _agent_arg(a.runner)))
    if not a.run:
        print("\nbriefs prepared; open each BRIEF in your agent, or rerun with --run to map them headlessly", file=sys.stderr)
    return 0


def cmd_doctor(a) -> int:
    cfg = config.load()
    if a.dump:
        ad = adapters.get(_agent_arg(a.dump))
        dump = getattr(ad, "dump", None)
        print(dump() if dump else "%s: nothing to dump" % ad.name)
        return 0
    print("cartographer %s (%s)" % (__version__, hooks.bin_path()))
    print("home        %s" % config.HOME)
    print("config      %s%s" % (config.PATH, "" if os.path.exists(config.PATH) else " (defaults; run `cartographer config init`)"))
    print("mode        %s" % cfg["wrap"]["mode"])
    print("effective   %s" % json.dumps(config.effective(cfg)))
    print("\nagents:")
    for ad in adapters.registry().values():
        if ad.name != "generic":
            hl = autowrap.headless_command(ad.name, cfg)
            print("  %-12s %s  sessions=%d  headless=%s" % (ad.name, "found" if ad.available() else "not found",
                                                           len(ad.list_sessions()) if ad.available() else 0, " ".join(hl) if hl else "none"))
    reg, done = store.projects(), store.wrapped()
    print("\nprojects    %d wrapped project%s, %d recap%s" % (len(reg), "" if len(reg) == 1 else "s", len(done), "" if len(done) == 1 else "s"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cartographer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="cartographer %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    def session_args(sp):
        sp.add_argument("--agent", help="claude-code | codex | cursor | generic")
        sp.add_argument("--session", help="session id (prefix ok); $VAR placeholders are ignored")
        sp.add_argument("--transcript", help="path to a transcript file instead of --session")
        sp.add_argument("--cwd", help="folder whose newest session to use (default: current)")

    s = sub.add_parser("sessions", help="list sessions"); s.add_argument("--agent"); s.add_argument("--cwd"); s.add_argument("--all", action="store_true"); s.add_argument("--limit", type=int, default=40); s.set_defaults(fn=cmd_sessions)
    s = sub.add_parser("wrap", help="write the mapping brief for a session"); session_args(s); s.add_argument("--project", help="project name override"); s.add_argument("--force", action="store_true", help="redo an already wrapped or very short session"); s.add_argument("--print-brief", action="store_true"); s.add_argument("--run", action="store_true", help="also map it with the agent's headless CLI"); s.add_argument("--runner", help="which agent CLI does the mapping (with --run)"); s.set_defaults(fn=cmd_wrap)
    s = sub.add_parser("goal", help="declare what done means for the current version"); s.add_argument("text"); s.add_argument("--project"); s.add_argument("--version", dest="version", help="version name (default: the open one, or v1)"); s.set_defaults(fn=cmd_goal)
    s = sub.add_parser("complete", help="mark a version complete and prepare the appraisal"); s.add_argument("--project"); s.add_argument("--version", dest="version"); s.add_argument("--result", choices=list(store.RESULTS), help="omit to re-prepare an already completed version"); s.add_argument("--actual", help="what actually happened, in a sentence"); s.add_argument("--run", action="store_true", help="appraise with the headless CLI"); s.add_argument("--runner"); s.add_argument("--print-brief", action="store_true"); s.set_defaults(fn=cmd_complete)
    s = sub.add_parser("save", help="validate, store and render a recap or an appraisal"); s.add_argument("recap"); s.add_argument("--digest"); s.add_argument("--check", action="store_true", help="validate only"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_save)
    s = sub.add_parser("render", help="render a replay"); s.add_argument("--project"); s.add_argument("files", nargs="*"); s.add_argument("--all", action="store_true"); s.add_argument("--out"); s.add_argument("--title"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("serve", help="local dashboard in the browser"); s.add_argument("--port", type=int, default=8765); s.add_argument("--open", action="store_true", help="open the browser"); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("open", help="open a project's replay (default: newest)"); s.add_argument("project", nargs="?"); s.set_defaults(fn=cmd_open)
    s = sub.add_parser("projects", help="list wrapped projects"); s.set_defaults(fn=cmd_projects)
    s = sub.add_parser("sweep", help="auto-wrap idle sessions"); s.add_argument("--idle", type=int, help="minutes of quiet (default: wrap.idle_minutes)"); s.add_argument("--since-days", type=int, default=7); s.add_argument("--dry", action="store_true"); s.add_argument("--runner"); s.set_defaults(fn=cmd_sweep)
    s = sub.add_parser("backfill", help="retrospective maps for a repo's past sessions"); s.add_argument("--cwd"); s.add_argument("--agent"); s.add_argument("--limit", type=int); s.add_argument("--run", action="store_true", help="map headlessly instead of only preparing briefs"); s.add_argument("--runner"); s.set_defaults(fn=cmd_backfill)
    s = sub.add_parser("config", help="show | set KEY VALUE | init | path"); s.add_argument("action", nargs="?", default="show", choices=["show", "set", "init", "path"]); s.add_argument("key", nargs="?"); s.add_argument("value", nargs="?"); s.set_defaults(fn=cmd_config)
    s = sub.add_parser("install", help="install into agents"); s.add_argument("--agent", action="append", help="claude-code, codex, cursor or all (repeatable)"); s.add_argument("--auto", action="store_true", help="wrap automatically when sessions end"); s.add_argument("--manual", action="store_true"); s.add_argument("--project", help="repo path for the Cursor rule / Codex AGENTS.md"); s.add_argument("--no-copy", action="store_true", help="don't copy to ~/.cartographer/app"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("hook", help="(called by agents) record a session event from stdin JSON"); s.add_argument("agent"); s.add_argument("payload", nargs="?"); s.set_defaults(fn=cmd_hook)
    s = sub.add_parser("doctor", help="environment check"); s.set_defaults(fn=cmd_doctor)
    s.add_argument("--dump", metavar="AGENT", help="print the shape of that agent's storage (keys, counts, no message text) to paste into a bug report")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    if not getattr(a, "fn", None):
        parser.print_help()
        return 0
    try:
        return a.fn(a) or 0
    except BrokenPipeError:  # e.g. `cartographer sessions | head`
        return 0
    except (LookupError, ValueError, OSError) as exc:
        print("cartographer: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
