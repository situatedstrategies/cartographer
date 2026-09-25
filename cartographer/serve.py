"""Local dashboard: `cartographer serve`.

Projects, sessions, replays, setup and agent connection on one page, served
only to this machine by the standard library's HTTP server. Every button that
changes something is a POST carrying a per-run token, so a page open in
another tab cannot trigger it, and requests whose Host header is not local are
refused. Single user by design: this is the front door to ~/.cartographer.
"""
from __future__ import annotations

import html
import os
import secrets
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from . import __version__, adapters, autowrap, config, hooks, render, store

TOKEN = secrets.token_urlsafe(16)
JOBS: Dict[str, Dict[str, Any]] = {}   # "agent:session" -> {"status": running|done|error, "result": {...}}
FLASH: List[str] = []                  # one-shot messages shown on the next page
e = html.escape

FIELDS = config.WIZARD
HELP = config.HELP

CSS = r"""
.nav{display:flex;gap:18px;align-items:center;margin:0 0 26px;font-weight:600}.nav a{text-decoration:none;color:var(--muted)}.nav a.brand{color:var(--ink);font-size:18px;letter-spacing:-.01em}.nav a.here{color:var(--accent)}.nav .grow{flex:1}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px;margin:0 0 22px}
.row{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--line)}.row:first-child{border-top:0}.row .grow{flex:1;min-width:0}.row b{display:block}
.row .meta{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.notice{background:var(--panel2);border-radius:12px;padding:14px 16px;margin:0 0 18px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}.notice .grow{flex:1}
form.setup{display:grid;gap:18px;max-width:640px}form.setup label{display:grid;gap:6px;font-weight:600}form.setup small{font-weight:400;color:var(--muted)}
.ok{color:var(--k-fix)}.warn{color:var(--k-dead_end)}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
ul.plain{margin:0;padding-left:18px}ul.plain li{margin:0 0 8px}
"""
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#2f4a72"/>'
           '<path d="M8 22 L14 10 L19 18 L24 12" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
           '<circle cx="24" cy="12" r="2.5" fill="#d3b076"/></svg>')
SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s · Cartographer</title><link rel="icon" href="/favicon.ico"><style>%(css)s</style><script>%(js)s</script></head><body><div class="wrap">
<nav class="nav"><a href="/" class="brand">Cartographer</a>%(links)s<span class="grow"></span><span class="meta">v%(version)s · this machine only</span><button class="small" data-theme-btn aria-label="Theme"></button></nav>
%(flash)s%(body)s
<footer>Local dashboard · started with <kbd>cartographer serve</kbd> · nothing here leaves your machine</footer></div></body></html>"""


def page(title: str, body: str, here: str = "/") -> str:
    links = "".join('<a href="%s"%s>%s</a>' % (p, ' class="here"' if p == here else "", n) for p, n in (("/", "Home"), ("/setup", "Setup"), ("/connect", "Connect")))
    flash = "".join('<div class="notice">%s</div>' % e(m) for m in FLASH)
    FLASH.clear()
    return SHELL % {"title": e(title), "css": render.BASE_CSS + CSS, "js": render.THEME_JS, "links": links, "version": __version__, "flash": flash, "body": body}


def token_field() -> str:
    return '<input type="hidden" name="token" value="%s">' % TOKEN


def tiles(items) -> str:
    return '<div class="tiles">%s</div>' % "".join('<div class="tile"><b>%s</b><span>%s</span></div>' % (e(str(v)), e(l)) for v, l in items)


def slug_of(recap_path: str) -> str:
    return os.path.basename(os.path.dirname(recap_path))


# ---------------------------------------------------------------- pages

def home(q: Dict[str, str]) -> str:
    cfg = config.load()
    eff = config.effective(cfg)
    out = []
    if not os.path.exists(config.PATH):
        out.append('<div class="notice"><div class="grow"><b>Welcome.</b> Two minutes of setup tells Cartographer how to speak to you and what to give feedback on.</div>'
                   '<a class="btn primary" href="/setup">Set up your profile</a></div>')
    cc = adapters.get("claude-code")
    done = store.wrapped()
    reg = store.projects()
    out.append(tiles([(len(reg), "projects"), (len(done), "maps"), (len(cc.list_sessions()) if cc.available() else 0, "claude code sessions"),
                      (cfg["wrap"]["mode"], "wrap mode"), (eff["voice"], "voice"), ("on" if eff["feedback"] else "off", "feedback")]))
    out.append('<div class="grid">')
    # projects
    rows = []
    for pid, p in sorted(reg.items(), key=lambda kv: kv[1].get("name", "")):
        recaps = store.load_recaps(p["slug"])
        latest = recaps[-1] if recaps else {}
        v = store.open_version(p) or ((p.get("versions") or [None])[-1])
        state = ("%s · %s" % (v["name"], ("done means: " + v["desired"][:60] + ("…" if len(v["desired"]) > 60 else "")) if v.get("desired") else "no desired outcome yet")) if v and not v.get("completed_at") \
            else ("%s %s%s" % (v["name"], v.get("result"), "" if v.get("appraisal") else " · not appraised")) if v else "no desired outcome yet"
        rows.append('<div class="row"><div class="grow"><b>%s</b><span class="meta">%s · %d session%s%s</span><span class="meta">%s</span></div>'
                    '<a class="btn small" href="/project/%s">Outcome</a><a class="btn small primary" href="/replay/%s">Open map</a></div>'
                    % (e(p["name"]), e(pid), len(recaps), "" if len(recaps) == 1 else "s", (" · last " + e(latest.get("date") or "")) if latest else "", e(state), e(p["slug"]), e(p["slug"])))
    out.append('<div class="card panel"><h2>Projects</h2>%s</div>' % ("".join(rows) or '<p class="sub">No maps yet. Map a session on the right, or type <kbd>/wrap</kbd> in Claude Code at the end of one.</p>'))
    # sessions
    rows = []
    for r in adapters.list_all(limit=20):
        key = "%s:%s" % (r.agent, r.id)
        when = datetime.fromtimestamp(r.mtime).strftime("%b %d, %H:%M") if r.mtime else "?"
        label = r.title or os.path.basename((r.cwd or "").rstrip("/")) or r.id[:12]
        job = JOBS.get(key)
        wrapped_path = done.get("%s:%s" % (r.agent, r.id[:8]))
        if wrapped_path:
            action = '<a class="btn small" href="/replay/%s">Open map</a>' % e(slug_of(wrapped_path))
        elif job and job["status"] == "running":
            action = '<span class="meta">mapping…</span>'
        elif job and job["status"] == "error":
            action = '<span class="meta warn" title="%s">failed</span>' % e(str(job.get("error"))[:200])
        else:
            action = ('<form method="post" action="/wrap">%s<input type="hidden" name="agent" value="%s"><input type="hidden" name="session" value="%s">'
                      '<button class="small">Map this session</button></form>' % (token_field(), e(r.agent), e(r.id)))
        rows.append('<div class="row"><span class="dot" style="background:%s"></span><div class="grow"><b>%s</b><span class="meta">%s · %s · %s</span></div>%s</div>'
                    % ("var(--k-fix)" if wrapped_path else "var(--line)", e(label), e(r.agent), e(when), e(r.cwd or ""), action))
    out.append('<div class="card panel"><h2>Recent sessions</h2>%s</div>' % ("".join(rows) or '<p class="sub">No agent history found on this machine yet. Have a session in Claude Code, then come back.</p>'))
    out.append('</div>')
    if not cc.available():
        out.append('<div class="notice"><div class="grow">Claude Code history not found in <kbd>~/.claude/projects</kbd>. Cartographer reads sessions from there once you have had one.</div><a class="btn" href="/connect">Connect an agent</a></div>')
    return page("Home", "".join(out))


def setup_page(q: Dict[str, str]) -> str:
    cfg = config.load()
    eff = config.effective(cfg)
    fields = []
    for key, question, options in FIELDS:
        current = config.get(cfg, key)
        current = ("true" if current else "false") if isinstance(current, bool) else str(current)
        opts = "".join('<option value="%s"%s>%s</option>' % (o, " selected" if o == current else "", o) for o in options)
        fields.append('<label>%s<small>%s</small><select name="%s">%s</select></label>' % (e(question), e(HELP.get(key, "")), e(key), opts))
    body = ('<div class="eyebrow">Setup</div><h1>How should Cartographer speak to you?</h1><p class="sub">Press Enter to keep a value. Everything can be changed later; maps already made keep the voice they were written in.</p>'
            '<div class="card panel"><form class="setup" method="post" action="/setup">%s%s<div><button class="primary">Save</button></div></form></div>'
            '<p class="sub" style="margin-top:14px">Right now: coding <b>%s</b>, prompting <b>%s</b>, voice <b>%s</b>, feedback <b>%s</b>%s. Config file: <kbd>%s</kbd></p>'
            % (token_field(), "".join(fields), e(eff["coding"]), e(eff["prompting"]), e(eff["voice"]), "on, focus " + e(eff["focus"]) if eff["feedback"] else "off",
               "" if os.path.exists(config.PATH) else " (defaults, not saved yet)", e(config.PATH)))
    return page("Setup", body, "/setup")


def connect_page(q: Dict[str, str]) -> str:
    cfg = config.load()
    auto = cfg["wrap"]["mode"] == "auto"
    skills = os.path.join(os.path.expanduser("~"), ".claude", "skills", "wrap", "SKILL.md")
    installed = os.path.exists(skills)
    body = ('<div class="eyebrow">Connect</div><h1>Claude Code</h1>'
            '<p class="sub">Installing puts four commands into Claude Code: <kbd>/wrap</kbd> maps the session you are in, <kbd>/replay</kbd> tells the story of a project, '
            '<kbd>/complete</kbd> marks a version done and appraises it, <kbd>/cartographer-setup</kbd> changes this profile from inside the agent.%s</p>'
            '<div class="card panel"><p><span class="dot" style="background:%s"></span>%s</p>'
            '<form method="post" action="/connect" style="margin-top:12px">%s<input type="hidden" name="agent" value="claude-code"><button class="primary">%s</button></form></div>'
            '<div class="card panel" style="margin-top:18px"><h2>Then, in Claude Code</h2><ul class="plain">'
            '<li>Work as usual. Cartographer reads the history Claude Code already keeps; nothing runs during the session.</li>'
            '<li>At the end, type <kbd>/wrap</kbd>. The agent writes the map and tells you where the replay is.</li>'
            '<li>Come back here, or run <kbd>cartographer open</kbd>, to watch the build.</li>'
            '<li>Old sessions: press <b>Map this session</b> on the home page, or <kbd>/cartographer-setup backfill</kbd>.</li>'
            '<li>When a version is done, <kbd>/complete</kbd> marks it shipped, partial or abandoned and writes the honest appraisal against the outcome you declared (set it under a project\'s <b>Outcome</b>, or with <kbd>cartographer goal</kbd>).</li></ul></div>'
            '<p class="sub" style="margin-top:18px">Codex CLI and Cursor are available from the command line (<kbd>cartographer install --agent codex</kbd>, <kbd>--agent cursor --project &lt;repo&gt;</kbd>) '
            'and are not yet verified against real history.</p>'
            % (" Auto-wrap is on, so a hook will also map each session when it ends." if auto else "",
               "var(--k-fix)" if installed else "var(--line)", "Installed in ~/.claude/skills" if installed else "Not installed yet",
               token_field(), "Reinstall / update" if installed else "Install into Claude Code"))
    return page("Connect", body, "/connect")


def project_page(slug: str) -> Optional[str]:
    entry = store.find_project(slug)
    if not entry:
        return None
    versions = entry.get("versions") or []
    open_v = store.open_version(entry)
    rows = []
    for v in versions:
        if v.get("completed_at"):
            appraise = ('<a class="btn small" href="/replay/%s">See appraisal</a>' % e(entry["slug"])) if v.get("appraisal") else \
                ('<form method="post" action="/complete">%s<input type="hidden" name="project" value="%s"><input type="hidden" name="version" value="%s"><button class="small primary">Appraise</button></form>'
                 % (token_field(), e(entry["id"]), e(v["name"])))
            rows.append('<div class="row"><span class="dot" style="background:%s"></span><div class="grow"><b>%s · %s</b><span class="meta">done meant: %s</span><span class="meta">what happened: %s</span></div>%s</div>'
                        % ({"shipped": "var(--k-fix)", "partial": "var(--k-artifact)"}.get(v.get("result"), "var(--k-dead_end)"), e(v["name"]), e(v.get("result") or ""),
                           e(v.get("desired") or "never declared"), e(v.get("actual") or "(not given)"), appraise))
    goal_form = ('<form method="post" action="/goal" class="setup">%s<input type="hidden" name="project" value="%s">'
                 '<label>What does done mean for %s?<small>In your words. Every map of this project is judged against this, and the appraisal at completion uses it.</small>'
                 '<textarea name="desired" rows="3" style="font:inherit;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink)">%s</textarea></label>'
                 '<div><button class="primary">Save</button></div></form>'
                 % (token_field(), e(entry["id"]), e(open_v["name"] if open_v else "the next version"), e((open_v or {}).get("desired") or "")))
    results = "".join('<option value="%s">%s</option>' % (r, r) for r in store.RESULTS)
    complete_form = ('<form method="post" action="/complete" class="setup">%s<input type="hidden" name="project" value="%s">'
                     '<label>Result<select name="result">%s</select></label>'
                     '<label>What actually happened<small>One or two sentences. This is the other half of the yardstick.</small>'
                     '<textarea name="actual" rows="3" style="font:inherit;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink)"></textarea></label>'
                     '<div><button class="primary">Mark %s complete and appraise</button></div></form>'
                     % (token_field(), e(entry["id"]), results, e(open_v["name"] if open_v else "v%d" % (len(versions) + 1))))
    body = ('<div class="eyebrow">Project</div><h1>%s</h1><p class="sub">%s · %d wrapped session%s. Session maps are provisional; the appraisal at completion is the honest reading against the outcome you declared.</p>'
            '<div class="grid"><div class="card panel"><h2>The yardstick</h2>%s</div><div class="card panel"><h2>Mark complete</h2>%s</div></div>'
            '%s<p><a href="/">Back</a> · <a href="/replay/%s">Open map</a></p>'
            % (e(entry["name"]), e(entry["id"]), len(store.load_recaps(entry["slug"])), "" if len(store.load_recaps(entry["slug"])) == 1 else "s", goal_form, complete_form,
               ('<div class="card panel"><h2>Versions</h2>%s</div>' % "".join(rows)) if rows else "", e(entry["slug"])))
    return page(entry["name"], body)


def complete_page(form: Dict[str, str]) -> str:
    cfg = config.load()
    try:
        res = autowrap.appraise(form.get("project", ""), cfg, form.get("version") or None, form.get("result") or None, form.get("actual", ""))
    except (LookupError, ValueError, OSError) as exc:
        return page("Complete", '<h1>Could not prepare the appraisal</h1><p class="warn">%s</p><p><a href="/">Back</a></p>' % e(str(exc)))
    headless = autowrap.headless_command("claude-code", cfg)
    run_form = ('<form method="post" action="/complete-run">%s<input type="hidden" name="project" value="%s"><input type="hidden" name="version" value="%s">'
                '<button>Appraise in the background with <kbd>%s</kbd></button><small class="meta" style="display:block;margin-top:8px">A few minutes. The home page shows progress.</small></form>'
                % (token_field(), e(form.get("project", "")), e(res["version"]), e(headless[0]))) if headless else '<p class="sub"><kbd>claude</kbd> is not on PATH, so the background option is unavailable here.</p>'
    body = ('<div class="eyebrow">Appraisal</div><h1>%s · %s · %s</h1><p class="sub">Done meant: %s</p>'
            '<div class="grid"><div class="card panel"><h2>Best: from inside Claude Code</h2><p>In the repo, type:</p><code>/complete %s</code>'
            '<p class="meta" style="margin-top:8px">It reads the brief, writes the appraisal against your declared outcome from %d session map%s, and saves it.</p></div>'
            '<div class="card panel"><h2>Or: headless</h2>%s</div></div><p class="meta">Brief prepared at <kbd>%s</kbd></p><p><a href="/">Back</a></p>'
            % (e(res["project"]), e(res["version"]), e(res["result"] or ""), e(res.get("desired") or "never declared"), e(res["project"]), res["sessions"], "" if res["sessions"] == 1 else "s", run_form, e(res["brief"])))
    return page("Appraisal", body)


def start_appraisal(form: Dict[str, str]) -> None:
    project, version = form.get("project", ""), form.get("version") or None
    key = "appraise:%s:%s" % (project, version)
    if JOBS.get(key, {}).get("status") == "running":
        return

    def work():
        try:
            res = autowrap.appraise(project, None, version, None, "", True)
            JOBS[key] = {"status": "done" if res.get("ok") else "error", "result": res, "error": res.get("error") or "; ".join(res.get("errors") or [])}
        except Exception as exc:
            JOBS[key] = {"status": "error", "error": str(exc)}

    JOBS[key] = {"status": "running"}
    threading.Thread(target=work, daemon=True).start()
    FLASH.append("Appraising in the background; refresh in a few minutes.")


def wrap_page(form: Dict[str, str]) -> str:
    cfg = config.load()
    agent, sid, force = form.get("agent", "claude-code"), form.get("session", ""), form.get("force") == "1"
    try:
        res = autowrap.prepare(agent, sid, None, cfg, "", force)
    except (LookupError, OSError, ValueError) as exc:
        return page("Map", '<h1>Could not prepare</h1><p class="warn">%s</p><p><a href="/">Back</a></p>' % e(str(exc)))
    if res.get("skipped"):
        again = ('<form method="post" action="/wrap">%s<input type="hidden" name="agent" value="%s"><input type="hidden" name="session" value="%s"><input type="hidden" name="force" value="1">'
                 '<button>Map it anyway</button></form>' % (token_field(), e(agent), e(sid)))
        link = ('<a class="btn primary" href="/replay/%s">Open map</a>' % e(slug_of(res["recap"]))) if res.get("recap") else again
        return page("Map", '<h1>Skipped: %s</h1><p class="sub">%s</p>%s<p style="margin-top:14px"><a href="/">Back</a></p>'
                    % (e(res["skipped"]), "This session already has a map." if res.get("recap") else "Very short sessions rarely have a story; map it anyway if this one does.", link))
    proj = res.get("project") or {}
    headless = autowrap.headless_command(agent, cfg)
    run_form = ('<form method="post" action="/wrap-run">%s<input type="hidden" name="agent" value="%s"><input type="hidden" name="session" value="%s"><input type="hidden" name="force" value="%s">'
                '<button>Map it in the background with <kbd>%s</kbd></button><small class="meta" style="display:block;margin-top:8px">A few minutes. The home page shows progress.</small></form>'
                % (token_field(), e(agent), e(sid), "1" if force else "0", e(headless[0]))) if headless else '<p class="sub"><kbd>claude</kbd> is not on PATH, so the background option is unavailable here.</p>'
    body = ('<div class="eyebrow">Map</div><h1>%s</h1><p class="sub">%s · %s prompts · %s min · %s</p>'
            '<div class="grid"><div class="card panel"><h2>Best: from inside Claude Code</h2><p>The agent that was in the session remembers the intent behind each prompt. In <kbd>%s</kbd>, type:</p>'
            '<code>/wrap --session %s%s</code></div>'
            '<div class="card panel"><h2>Or: headless</h2>%s</div></div>'
            '<p class="meta">Brief prepared at %s</p><p><a href="/">Back</a></p>'
            % (e(proj.get("name") or "Session"), e(agent), e(str(res.get("prompts"))), e(str(res.get("duration_min"))), ", ".join(res.get("languages") or []) or "no language detected",
               e((proj.get("root") or "the project folder")), e(sid[:12]), " --force" if force else "", run_form, e(res["brief"])))
    return page("Map", body)


def start_run(form: Dict[str, str]) -> None:
    agent, sid, force = form.get("agent", "claude-code"), form.get("session", ""), form.get("force") == "1"
    key = "%s:%s" % (agent, sid)
    if JOBS.get(key, {}).get("status") == "running":
        return

    def work():
        try:
            res = autowrap.run(agent, sid, None, None, "", force)
            JOBS[key] = {"status": "done" if res.get("ok") else "error", "result": res, "error": res.get("error") or "; ".join(res.get("errors") or [])}
        except Exception as exc:  # shown on the home page
            JOBS[key] = {"status": "error", "error": str(exc)}

    JOBS[key] = {"status": "running"}
    threading.Thread(target=work, daemon=True).start()
    FLASH.append("Mapping in the background; refresh in a few minutes.")


def save_setup(form: Dict[str, str]) -> None:
    cfg = config.load()
    was_auto = cfg["wrap"]["mode"] == "auto"
    for key, _, _ in FIELDS:
        if key in form:
            config.set_value(cfg, key, form[key])
    config.save(cfg)
    FLASH.append("Saved. Maps will be written for a %s coder and %s prompter, in %s voice." % (cfg["profile"]["coding"], cfg["profile"]["prompting"], config.effective(cfg)["voice"]))
    now_auto = cfg["wrap"]["mode"] == "auto"
    if now_auto or was_auto:  # add or remove the SessionEnd hook to match
        try:
            FLASH.extend(hooks.install_claude_code(now_auto, hooks.command_prefix()))
        except (LookupError, OSError) as exc:
            FLASH.append("Could not update Claude Code hooks: %s" % exc)


def do_connect(form: Dict[str, str]) -> None:
    cfg = config.load()
    try:
        FLASH.extend(hooks.install(form.get("agent", "claude-code"), cfg["wrap"]["mode"] == "auto", None, hooks.command_prefix()))
    except (LookupError, OSError, KeyError) as exc:
        FLASH.append("Install failed: %s" % exc)


def replay_page(slug: str) -> Optional[str]:
    entry = store.find_project(slug)
    recaps = store.load_recaps(entry["slug"]) if entry else []
    return render.render_html(recaps, entry["name"], store.load_appraisals(entry["slug"])) if recaps else None


# -------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = "cartographer/" + __version__

    def log_message(self, *args) -> None:  # quiet by default
        pass

    def _local(self) -> bool:
        host = self.headers.get("Host") or ""
        host = host[1:host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "::1")

    def _send(self, status: int, body: str = "", location: Optional[str] = None, ctype: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._local():
            return self._send(403, "forbidden")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._send(200, home(q))
            if u.path == "/setup":
                return self._send(200, setup_page(q))
            if u.path == "/connect":
                return self._send(200, connect_page(q))
            if u.path.startswith("/project/"):
                body = project_page(u.path[len("/project/"):])
                return self._send(200, body) if body else self._send(404, page("Not found", "<h1>No such project</h1><p><a href='/'>Back</a></p>"))
            if u.path.startswith("/replay/"):
                body = replay_page(u.path[len("/replay/"):])
                return self._send(200, body) if body else self._send(404, page("Not found", "<h1>No map for that project yet</h1><p><a href='/'>Back</a></p>"))
            if u.path == "/health":
                return self._send(200, "ok")
            if u.path == "/favicon.ico":
                return self._send(200, FAVICON, ctype="image/svg+xml")
        except Exception as exc:  # a broken page beats a hung browser tab
            return self._send(500, page("Error", "<h1>Something broke</h1><code>%s</code><p><a href='/'>Back</a></p>" % e(str(exc))))
        self._send(404, page("Not found", "<h1>Not found</h1><p><a href='/'>Back</a></p>"))

    def do_POST(self) -> None:
        if not self._local():
            return self._send(403, "forbidden")
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}
        if form.get("token") != TOKEN:
            return self._send(403, page("Refused", "<h1>Refused</h1><p>This form was not issued by this dashboard. <a href='/'>Reload</a> and try again.</p>"))
        path = urlparse(self.path).path
        try:
            if path == "/setup":
                save_setup(form)
                return self._send(303, location="/setup")
            if path == "/connect":
                do_connect(form)
                return self._send(303, location="/connect")
            if path == "/wrap":
                return self._send(200, wrap_page(form))
            if path == "/wrap-run":
                start_run(form)
                return self._send(303, location="/")
            if path == "/goal":
                v = store.set_goal(form.get("project", ""), form.get("desired", ""), form.get("version") or None)
                FLASH.append("Saved: done for %s means %s" % (v["name"], v["desired"]))
                entry = store.find_project(form.get("project", ""))
                return self._send(303, location="/project/%s" % (entry["slug"] if entry else ""))
            if path == "/complete":
                return self._send(200, complete_page(form))
            if path == "/complete-run":
                start_appraisal(form)
                return self._send(303, location="/")
        except (ValueError, LookupError, OSError) as exc:
            FLASH.append("Error: %s" % exc)
            return self._send(303, location="/")
        self._send(404, page("Not found", "<h1>Not found</h1><p><a href='/'>Back</a></p>"))


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    store.ensure_dirs()
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = 8765, open_browser: bool = False) -> str:
    httpd = make_server(port)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("Cartographer dashboard: %s   (this machine only · Ctrl-C to stop)" % url)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return url
