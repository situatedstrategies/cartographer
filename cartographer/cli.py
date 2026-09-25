"""cartographer — map how you build with coding agents.

    sessions     list sessions found for every installed agent
    wrap         prepare a brief for a session (what /wrap runs)
    save         validate + store a recap and render the replay
    render       build a project replay
    autowrap     wrap a session with the agent's headless CLI
    sweep        auto-wrap sessions that ended or went idle
    backfill     retrospective maps for every past session of a repo
    config       show / set / init settings
    install      install into Claude Code, Codex CLI or Cursor
    doctor       what's installed, where things are
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, List, Optional

from . import adapters, autowrap, config, digest, hooks, recap, render, store


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def _agent_arg(value: Optional[str]) -> Optional[str]:
    return adapters.get(value).name if value else None


def cmd_sessions(a) -> int:
    refs = adapters.list_all(cwd=None if a.all else (a.cwd or os.getcwd()), agent=_agent_arg(a.agent), limit=a.limit)
    if not refs and not a.all:
        refs = adapters.list_all(agent=_agent_arg(a.agent), limit=a.limit)
        if refs:
            print("(no sessions for this folder; showing all)\n", file=sys.stderr)
    wrapped = store.wrapped()
    for r in refs:
        when = datetime.fromtimestamp(r.mtime).strftime("%Y-%m-%d %H:%M") if r.mtime else "?"
        mark = "✓" if ("%s:%s" % (r.agent, r.id)) in wrapped else " "
        print("%s %-12s %-14s %s  %s%s" % (mark, r.agent, r.id[:12], when, (r.cwd or ""), ("  · " + r.title) if r.title else ""))
    if not refs:
        print("no sessions found", file=sys.stderr)
        return 1
    return 0


def cmd_digest(a) -> int:
    cfg = config.load()
    session = adapters.load(a.session, a.transcript, _agent_arg(a.agent), a.cwd)
    d = digest.build(session, cfg)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1, ensure_ascii=False)
        print(a.out)
    else:
        _print(d)
    return 0


def cmd_wrap(a) -> int:
    cfg = config.load()
    res = autowrap.prepare(_agent_arg(a.agent), a.session, a.transcript, cfg, a.project or "", a.force, a.cwd)
    if res.get("skipped"):
        print("SKIPPED: %s" % res["skipped"])
        if res.get("recap"):
            print("RECAP: %s" % res["recap"])
        return 2
    if a.print_brief:
        with open(res["brief"], encoding="utf-8") as fh:
            print(fh.read())
        return 0
    print("BRIEF: %s" % res["brief"])
    print("RECAP_OUT: %s" % res["recap_out"])
    print("DIGEST: %s" % res["digest"])
    print("AGENT: %s" % res["agent"])
    print("SESSION: %s" % res["session_id"])
    print("PROJECT: %s (%s)" % ((res["project"] or {}).get("name"), (res["project"] or {}).get("id")))
    print("BRANCH: %s" % (res.get("branch") or ""))
    print("DURATION_MIN: %s" % res.get("duration_min"))
    print("PROMPTS: %s" % res.get("prompts"))
    print("LANGUAGES: %s" % ", ".join(res.get("languages") or []))
    return 0


def cmd_save(a) -> int:
    res = autowrap.save_recap_file(a.recap, config.load(), a.digest)
    if not res["ok"]:
        print("recap has problems:")
        for e in res["errors"]:
            print("  - " + e)
        return 1
    print("SAVED: %s" % res["saved"])
    if res.get("replay"):
        print("REPLAY: %s" % res["replay"])
    if a.open and res.get("replay"):
        _open(res["replay"])
    return 0


def cmd_validate(a) -> int:
    with open(a.recap, encoding="utf-8") as fh:
        errs = recap.validate(recap.normalize(json.load(fh)))
    if errs:
        for e in errs:
            print("  - " + e)
        return 1
    print("ok")
    return 0


def cmd_render(a) -> int:
    if a.all:
        recaps = store.load_recaps()
        if not recaps:
            print("nothing wrapped yet", file=sys.stderr)
            return 1
        out = a.out or os.path.join(store.REPLAYS, "all-projects.html")
        print(render.render_recaps(recaps, "All projects", out))
        return 0
    if a.files:
        recaps = []
        for p in a.files:
            with open(p, encoding="utf-8") as fh:
                recaps.append(json.load(fh))
        title = a.title or (recaps[-1].get("project") or {}).get("name") or recaps[-1].get("title") or "Replay"
        out = a.out or os.path.join(store.REPLAYS, "%s.html" % store.project_slug(title))
        path = render.render_recaps(sorted(recaps, key=lambda r: r.get("started_at") or ""), title, out)
    else:
        if not a.project:
            print("give a project name (see `cartographer projects`) or recap files", file=sys.stderr)
            return 1
        path = render.render_project(a.project, a.out)
    print(path)
    if a.open:
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
    bin_cmd = hooks.self_install() if not a.no_copy else hooks.bin_path()
    auto = a.auto or (cfg["wrap"]["mode"] == "auto" and not a.manual)
    if a.auto:
        config.set_value(cfg, "wrap.mode", "auto")
    if a.manual:
        config.set_value(cfg, "wrap.mode", "manual")
    config.save(cfg)
    store.ensure_dirs()
    agents_list = ["claude-code", "codex", "cursor"] if (not a.agent or "all" in a.agent) else [adapters.get(x).name for x in a.agent]
    print("cartographer command: %s" % bin_cmd)
    for name in agents_list:
        for msg in hooks.install(name, auto, a.project, bin_cmd):
            print("• " + msg)
    if a.launchd:
        print("• launchd sweep installed: %s" % hooks.install_launchd(bin_cmd))
    print("\nmode: %s · config: %s" % (cfg["wrap"]["mode"], config.PATH))
    if not os.path.exists(config.PATH) or a.init:
        print("run `cartographer config init` to set your aptitude profile and feedback preferences")
    return 0


def cmd_hook(a) -> int:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except json.JSONDecodeError:
        payload = {}
    if a.payload:
        try:
            payload.update(json.loads(a.payload))
        except json.JSONDecodeError:
            pass
    res = hooks.handle(adapters.get(a.agent).name, payload, config.load())
    autowrap._log("hook", res)
    return 0


def cmd_autowrap(a) -> int:
    res = autowrap.run(_agent_arg(a.agent), a.session, a.transcript, config.load(), a.project or "", a.force, _agent_arg(a.runner))
    _print(res)
    return 0 if res.get("ok") or res.get("skipped") else 1


def cmd_sweep(a) -> int:
    res = autowrap.sweep(config.load(), a.idle, a.since_days, a.dry, _agent_arg(a.runner))
    _print(res)
    return 0


def cmd_backfill(a) -> int:
    res = autowrap.backfill(os.path.abspath(a.cwd or os.getcwd()), _agent_arg(a.agent), config.load(), a.limit, a.run, _agent_arg(a.runner))
    _print(res)
    if not a.run:
        print("\nbriefs prepared; open each BRIEF in your agent, or rerun with --run to map them headlessly", file=sys.stderr)
    return 0


def cmd_doctor(a) -> int:
    cfg = config.load()
    print("cartographer %s" % hooks.bin_path())
    print("home        %s" % config.HOME)
    print("config      %s%s" % (config.PATH, "" if os.path.exists(config.PATH) else " (defaults; run `cartographer config init`)"))
    print("mode        %s" % cfg["wrap"]["mode"])
    print("effective   %s" % json.dumps(config.effective(cfg)))
    print("\nagents:")
    for ad in adapters.registry().values():
        if ad.name == "generic":
            continue
        n = len(ad.list_sessions()) if ad.available() else 0
        hl = autowrap.headless_command(ad.name, cfg)
        print("  %-12s %s  sessions=%d  headless=%s" % (ad.name, "found" if ad.available() else "not found", n, " ".join(hl) if hl else "none"))
    reg = store.projects()
    print("\nprojects    %d wrapped project%s, %d recap%s" % (len(reg), "" if len(reg) == 1 else "s", len(store.wrapped()), "" if len(store.wrapped()) == 1 else "s"))
    return 0


def _open(path: str) -> None:
    opener = "open" if sys.platform == "darwin" else ("start" if os.name == "nt" else "xdg-open")
    try:
        subprocess.Popen([opener, path], shell=(os.name == "nt"))
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cartographer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    def session_args(sp):
        sp.add_argument("--agent", help="claude-code | codex | cursor | generic")
        sp.add_argument("--session", help="session id (prefix ok); $VAR placeholders are ignored")
        sp.add_argument("--transcript", help="path to a transcript file instead of --session")
        sp.add_argument("--cwd", help="folder whose newest session to use (default: current)")

    s = sub.add_parser("sessions", help="list sessions"); s.add_argument("--agent"); s.add_argument("--cwd"); s.add_argument("--all", action="store_true"); s.add_argument("--limit", type=int, default=40); s.set_defaults(fn=cmd_sessions)
    s = sub.add_parser("digest", help="print the digest for a session"); session_args(s); s.add_argument("--out"); s.set_defaults(fn=cmd_digest)
    s = sub.add_parser("wrap", help="prepare the mapping brief for a session"); session_args(s); s.add_argument("--project", help="project name override"); s.add_argument("--force", action="store_true"); s.add_argument("--print-brief", action="store_true"); s.set_defaults(fn=cmd_wrap)
    s = sub.add_parser("brief", help="alias of wrap --print-brief"); session_args(s); s.add_argument("--project"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_wrap, print_brief=True)
    s = sub.add_parser("save", help="validate, store and render a recap"); s.add_argument("recap"); s.add_argument("--digest"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_save)
    s = sub.add_parser("validate", help="check a recap file"); s.add_argument("recap"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("render", help="render a replay"); s.add_argument("--project"); s.add_argument("files", nargs="*"); s.add_argument("--all", action="store_true"); s.add_argument("--out"); s.add_argument("--title"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("projects", help="list wrapped projects"); s.set_defaults(fn=cmd_projects)
    s = sub.add_parser("config", help="show | set KEY VALUE | init | path"); s.add_argument("action", nargs="?", default="show", choices=["show", "set", "init", "path"]); s.add_argument("key", nargs="?"); s.add_argument("value", nargs="?"); s.set_defaults(fn=cmd_config)
    s = sub.add_parser("install", help="install into agents"); s.add_argument("--agent", action="append", help="claude-code, codex, cursor or all (repeatable)"); s.add_argument("--auto", action="store_true", help="wrap automatically when sessions end"); s.add_argument("--manual", action="store_true"); s.add_argument("--project", help="repo path for Cursor rule / Codex AGENTS.md"); s.add_argument("--launchd", action="store_true", help="macOS: sweep every 20 min"); s.add_argument("--no-copy", action="store_true", help="don't copy to ~/.cartographer/app"); s.add_argument("--init", action="store_true"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("hook", help="(called by agents) record a session event from stdin JSON"); s.add_argument("agent"); s.add_argument("payload", nargs="?"); s.set_defaults(fn=cmd_hook)
    s = sub.add_parser("autowrap", help="map a session with a headless agent"); session_args(s); s.add_argument("--project"); s.add_argument("--force", action="store_true"); s.add_argument("--runner", help="which agent CLI does the mapping"); s.set_defaults(fn=cmd_autowrap)
    s = sub.add_parser("sweep", help="auto-wrap ended/idle sessions"); s.add_argument("--idle", type=int); s.add_argument("--since-days", type=int, default=7); s.add_argument("--dry", action="store_true"); s.add_argument("--runner"); s.set_defaults(fn=cmd_sweep)
    s = sub.add_parser("backfill", help="retrospective maps for a repo's past sessions"); s.add_argument("--cwd"); s.add_argument("--agent"); s.add_argument("--limit", type=int); s.add_argument("--run", action="store_true", help="map headlessly instead of only preparing briefs"); s.add_argument("--runner"); s.set_defaults(fn=cmd_backfill)
    s = sub.add_parser("doctor", help="environment check"); s.set_defaults(fn=cmd_doctor)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    if not getattr(a, "fn", None):
        parser.print_help()
        return 0
    try:
        return a.fn(a) or 0
    except (LookupError, KeyError, ValueError, OSError) as exc:
        print("cartographer: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
