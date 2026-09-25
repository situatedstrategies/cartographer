"""Replay renderer: recaps -> one self-contained HTML page that tells the story.

The unit is a move: what you did, what happened, what it meant, how you
responded. Press "Replay the build" and the story reveals itself one part
at a time, chapter by chapter (phases), across every session of a project.
Switch to the map view and the same moves become a trail: it climbs with
outcomes that worked and dips with setbacks; achievements (a good situated
outcome from a prompt that needed no repair) are ringed in gold. Below it: a
time strip (each session a segment, each move at its minute), the playbook (coaching, reusable prompts, patterns, time sinks, prompting
profile) and a session list. No external assets; works from file:// and in
both color schemes. `BASE_CSS` is shared with the local dashboard.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

from . import lang, recap, store


def render_html(recaps: List[Dict[str, Any]], title: str, appraisals: Optional[List[Dict[str, Any]]] = None) -> str:
    clean = []
    for r in recaps:
        r = recap.normalize(r) if not r.get("moves") else r   # older maps: typed steps -> moves
        clean.append({k: v for k, v in r.items() if k != "_path"})
    payload = json.dumps({"title": title, "sessions": clean, "appraisals": appraisals or [], "scores": score_moves(clean)}, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__CSS__", BASE_CSS + STORY_CSS).replace("__JS__", THEME_JS).replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)


def render_recaps(recaps: List[Dict[str, Any]], title: str, out: str, appraisals: Optional[List[Dict[str, Any]]] = None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_html(recaps, title, appraisals))
    return out


def render_project(project: str, out: Optional[str] = None) -> str:
    entry = store.find_project(project)
    if not entry:
        raise LookupError("no project matching %r; run `cartographer projects`" % project)
    recaps = store.load_recaps(entry["slug"])
    if not recaps:
        raise LookupError("project %s has no wrapped sessions yet" % entry["name"])
    return render_recaps(recaps, entry["name"], out or os.path.join(store.REPLAYS, "%s.html" % entry["slug"]), store.load_appraisals(entry["slug"]))


OUTCOME_SCORE = {"worked": 3, "partly": 2, "opened": 1, "wrong_way": 0, "broke": 0}
OUTCOME_WORDS = {"worked": "worked", "partly": "partly worked", "opened": "opened a question", "wrong_way": "went the wrong way", "broke": "broke"}


def score_moves(sessions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Achievement tiers for the map view, from two things the record supports: the situated outcome the mapper
    judged for the move (0-3), and how the prompt that governs the move fared (0-3: it was not repaired by the
    user's next prompt, it was specific, it was anchored to files, symbols or errors). A repair prompt ("no, I
    meant…") recovers rather than achieves, so it caps at solid. A move without a prompt
    (the agent's own work) is governed by the most recent prompt before it. Achievement: worked, prompt not
    repaired, and either the prompt was specific or the move made or fixed something. Keyed "<session>:<move id>"."""
    scores: Dict[str, Dict[str, Any]] = {}
    for si, s in enumerate(sessions):
        moves = sorted([m for m in s.get("moves") or [] if isinstance(m, dict)], key=lambda m: m.get("t") or 0)
        prompted = [(i, (m.get("prompt") or "").strip()) for i, m in enumerate(moves) if (m.get("prompt") or "").strip()]
        read = {i: lang.analyze_prompt(t) for i, t in prompted}
        for i, m in enumerate(moves):
            oc = OUTCOME_SCORE.get(m.get("outcome"), 1)
            why = [OUTCOME_WORDS.get(m.get("outcome"), "outcome unclear")]
            gov = max([j for j, _ in prompted if j <= i], default=None)   # the prompt this move answers to
            ps, spec, anchored, repaired, repair = 0, None, False, False, False
            if gov is not None:
                a = read[gov]
                after = [j for j, _ in prompted if j > gov]
                repaired = bool(after) and read[after[0]]["intent"] == "repair"
                anchored = any([a["anchors"]["paths"], a["anchors"]["symbols"], a["anchors"]["error_text"], a["anchors"]["line_refs"]])
                spec, repair = a["specificity"], a["intent"] == "repair"
                ps = int(not repaired) + int(spec >= 1) + int(spec >= 2 or anchored)
                why.append("prompt%s specificity %d/3%s%s, %s" % ("" if gov == i else " (%s)" % moves[gov].get("id"), spec, ", anchored" if anchored else "",
                                                                ", a repair of the turn before" if repair else "", "corrected in your next turn" if repaired else "not corrected afterwards"))
            else:
                why.append("no prompt behind this move")
            if oc == 3 and not repaired and not repair and gov is not None and (spec >= 2 or m.get("mark") in ("artifact", "fix")):
                tier = "achievement"
            elif oc == 0:
                tier = "setback"
            elif oc == 1 or repaired:
                tier = "open"
            else:
                tier = "solid"
            scores["%d:%s" % (si, m.get("id"))] = {"outcome": oc, "prompt": ps, "score": oc + ps, "specificity": spec, "anchored": anchored,
                                                   "repaired": repaired, "tier": tier, "why": " · ".join(why)}
    return scores


# Monospace is for things that are literally code or the user's exact words: prompts, commands, file names. Everything else is the sans.
# Cool tan paper with map-ink blue in the light; warm charcoal with a tan accent in the dark. Outcome colours stay semantic.
LIGHT = ("--bg:#d9d2c5;--panel:#f3efe8;--panel2:#e8e2d7;--ink:#1e1a15;--muted:#5e564b;--line:#c7bdad;--accent:#2f4a72;--accent-ink:#fff;"
         "--shadow:0 1px 2px rgba(50,40,25,.07),0 12px 30px rgba(50,40,25,.10);"
         "--k-prompt:#2f4a72;--k-question:#3f6aa3;--k-fix:#4f7d43;--k-artifact:#b08528;--k-dead_end:#b0402f;--k-pivot:#c0672a;--k-insight:#6a625a;--k-decision:#6b4d8f;color-scheme:light")
DARK = ("--bg:#1b1916;--panel:#262320;--panel2:#302b26;--ink:#ece6db;--muted:#a89f92;--line:#403931;--accent:#d3b076;--accent-ink:#1b1916;"
        "--shadow:0 1px 2px rgba(0,0,0,.35),0 12px 30px rgba(0,0,0,.30);"
        "--k-prompt:#93b3e8;--k-question:#89ade0;--k-fix:#8cc07a;--k-artifact:#dfb861;--k-dead_end:#e77862;--k-pivot:#ea995f;--k-insight:#a89f93;--k-decision:#b79fdc;color-scheme:dark")
THEME_CSS = (":root{--sans:-apple-system,BlinkMacSystemFont,\"SF Pro Text\",Inter,\"Segoe UI\",Roboto,\"Helvetica Neue\",Arial,sans-serif;"
             "--mono:ui-monospace,\"SF Mono\",Menlo,Consolas,monospace;%s}\n"
             ":root[data-theme=dark]{%s}\n@media (prefers-color-scheme:dark){:root:not([data-theme=light]){%s}}") % (LIGHT, DARK, DARK)
# Runs in <head> so a remembered theme applies before first paint. Buttons marked data-theme-btn cycle auto -> dark -> light.
THEME_JS = r"""(function(){var k='cartographer-theme',d=document.documentElement,t=null;try{t=localStorage.getItem(k)}catch(e){}if(t)d.dataset.theme=t;
function label(){var c=d.dataset.theme||'auto';return c==='dark'?'\u263E Dark':c==='light'?'\u2600 Light':'\u25D0 Auto'}
function paint(){document.querySelectorAll('[data-theme-btn]').forEach(function(b){b.textContent=label()})}
window.setTheme=function(v){try{v?localStorage.setItem(k,v):localStorage.removeItem(k)}catch(e){}if(v)d.dataset.theme=v;else delete d.dataset.theme;paint()};
window.cycleTheme=function(){var c=d.dataset.theme||'auto';setTheme(c==='auto'?'dark':c==='dark'?'light':null)};
document.addEventListener('DOMContentLoaded',function(){document.querySelectorAll('[data-theme-btn]').forEach(function(b){b.onclick=cycleTheme});paint()})})();"""

BASE_CSS = THEME_CSS + r"""
*{box-sizing:border-box}[hidden],.hidden{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1120px;margin:0 auto;padding:24px 20px 60px}
.eyebrow,h2{font:700 12px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 14px}
h1{font:700 clamp(28px,3.8vw,40px)/1.12 var(--sans);letter-spacing:-.02em;margin:8px 0 6px}
.sub{color:var(--muted);margin:0 0 8px;max-width:70ch;font-size:16px}
.meta{font-size:13px;color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.card{padding:20px 22px}
.chips{display:flex;flex-wrap:wrap;gap:6px 8px;margin:10px 0 18px;font-size:12.5px;color:var(--muted)}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 11px;background:var(--panel)}.chip.agent{border-color:var(--accent);color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin:0 0 20px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.tile b{display:block;font:700 24px/1.15 var(--sans);letter-spacing:-.02em;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tile span{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
@media (max-width:600px){.tiles{grid-template-columns:repeat(3,1fr);gap:8px}.tile{padding:10px 12px;border-radius:12px}.tile b{font-size:19px}.wrap{padding:18px 14px 48px}}
button,.btn,select{font:600 13.5px/1 var(--sans);padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
button.primary,.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
button.on{border-color:var(--accent);color:var(--accent)}
button.small,.btn.small{padding:7px 11px;font-size:12.5px;border-radius:8px}
button:disabled{opacity:.5;cursor:default}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tag{font:700 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-right:6px}
kbd{font:12.5px var(--mono);background:var(--panel2);padding:2px 7px;border-radius:6px;white-space:nowrap}
code,blockquote{display:block;margin:8px 0 0;padding:10px 12px;background:var(--panel);border:1px solid var(--line);font:12.5px/1.5 var(--mono);white-space:pre-wrap;border-radius:10px;overflow-wrap:anywhere}
.files{display:flex;flex-wrap:wrap;gap:4px 6px;margin-top:8px}.files span{font:11.5px var(--mono);color:var(--muted);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:2px 7px}
footer{margin-top:40px;font-size:12.5px;color:var(--muted)}
"""

STORY_CSS = r"""
.toolbar{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}.toolbar .grow{flex:1}
.count{font-size:13px;color:var(--muted);min-width:56px;font-variant-numeric:tabular-nums}
.story{max-height:72vh;overflow:auto;padding:4px 20px 20px;border-radius:0 0 16px 16px}
.chapter{position:sticky;top:0;z-index:1;background:var(--panel);padding:16px 0 8px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid var(--line)}
.chapter span{font:700 13px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.chapter small{color:var(--muted);font-size:13px}.chapter em{font-style:normal;color:var(--accent);font-size:12.5px}
.beat{border:1px solid var(--line);border-left:4px solid var(--o);border-radius:14px;padding:12px 18px 8px;margin:14px 0;background:var(--panel2);transition:box-shadow .2s}
.beat.current{box-shadow:0 0 0 2px var(--o)}.beat.off{opacity:.3}.beat:focus-visible{outline:2px solid var(--accent)}
.bh{display:flex;gap:10px;align-items:center;font-size:12.5px;color:var(--muted);margin-bottom:4px;flex-wrap:wrap}
.bh .n{width:23px;height:23px;border-radius:50%;background:var(--o);color:#fff;display:inline-grid;place-items:center;font-weight:700;font-size:11.5px}
.bh .mk{border:1px solid var(--line);border-radius:999px;padding:2px 9px;background:var(--panel)}
.bh .oc{margin-left:auto;color:var(--o);font-weight:600}
.part{display:grid;grid-template-columns:138px 1fr;gap:8px 14px;padding:10px 0;border-top:1px solid var(--line);animation:fade .45s ease-out}
.part b{font:700 11.5px/1.5 var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding-top:3px}
.part.you b{color:var(--k-prompt)}.part.consequence b{color:var(--o)}.part.response b{color:var(--accent)}
.part p{margin:0}.part.now{background:linear-gradient(90deg,color-mix(in srgb,var(--o) 12%,transparent),transparent 70%);margin:0 -8px;padding-left:8px;padding-right:8px;border-radius:8px}
.part blockquote{border-left:3px solid var(--k-prompt);max-height:200px;overflow:auto}
@keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
@media (max-width:640px){.part{grid-template-columns:1fr;gap:4px}}
.coach{border-top:1px dashed var(--line);padding:10px 0 4px;font-size:14px;color:var(--muted)}.coach b{color:var(--accent);margin-right:6px}.coach span{display:block;color:var(--ink)}
.tl{position:relative;height:36px;margin:44px 0 0;border-radius:10px;background:var(--panel2);cursor:pointer;touch-action:none}
.tl i{position:absolute;top:9px;width:6px;height:18px;border-radius:3px;transform:translateX(-50%);opacity:.7}
.tl i.cur{opacity:1;top:5px;height:26px;width:8px;box-shadow:0 0 0 2px var(--panel),0 0 0 4px var(--ink)}
.tl .sess{position:absolute;top:0;bottom:0;border-left:1px dashed var(--line)}
.tl .ch{position:absolute;top:-19px;font-size:11px;font-weight:600;color:var(--accent);white-space:nowrap;letter-spacing:.04em;text-transform:uppercase}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel)}.seg button{border:0;border-radius:0;padding:7px 11px;font-size:12.5px;background:transparent}.seg button.on{background:var(--accent);color:var(--accent-ink)}
.ach{font:600 11.5px var(--sans);color:var(--k-artifact);border:1px solid var(--k-artifact);border-radius:999px;padding:2px 9px;background:var(--panel)}.ach.setback{color:var(--k-dead_end);border-color:var(--k-dead_end)}
.map{padding:10px 16px 18px;border-radius:0 0 16px 16px}.map #mapSvg{overflow-x:auto}.map svg{width:100%;min-width:720px;height:auto;display:block;font-family:var(--sans)}
.map .terrain,.map .trail,.map .band,.map .sd,.map .chl{pointer-events:none}.map .terrain{fill:var(--accent);opacity:.09}.map .trail{fill:none;stroke:var(--accent);stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
.map .band{fill:var(--ink);opacity:.035}.map .chl{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;fill:var(--accent)}.map .sd{stroke:var(--line);stroke-dasharray:4 4}
.map .node{cursor:pointer;outline:none}.map .nn{font-size:9px;font-weight:700;fill:#fff;text-anchor:middle;pointer-events:none}
.map .nl{font-size:11.5px;font-weight:600;text-anchor:middle;fill:var(--muted)}.map .nl.achievement{fill:var(--k-artifact)}.map .nl.setback{fill:var(--k-dead_end)}
.map .ring{fill:none;stroke:var(--k-artifact);stroke-width:2.5}.map .node.setback .dot{stroke:var(--k-dead_end);stroke-width:2;stroke-dasharray:3 2}
.map .node.cur .dot{stroke:var(--ink);stroke-width:3;stroke-dasharray:none}.map .node:focus-visible .dot{stroke:var(--accent);stroke-width:3}.map .node.off{opacity:.25}
.mapdetail{margin-top:10px;border:1px solid var(--line);border-left:4px solid var(--o);border-radius:14px;padding:12px 18px 8px;background:var(--panel2)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:12px 0 0;font-size:12.5px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.playbook{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:30px}
.card.wide{grid-column:1/-1}.card ul{margin:0;padding-left:18px}.card li{margin:0 0 10px}.card small{color:var(--muted)}
.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}.numbers div{background:var(--panel2);border-radius:10px;padding:10px 12px}
.numbers b{display:block;font:700 20px/1.1 var(--sans);letter-spacing:-.01em;font-variant-numeric:tabular-nums}.numbers span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.sessions{margin-top:30px}.sess{border-top:1px solid var(--line);padding:14px 0;display:grid;gap:4px}.sess b{font-size:16px}.sess p{margin:0}
@media (prefers-reduced-motion:reduce){.part{animation:none}.beat{transition:none}}
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Cartographer</title>
<style>__CSS__</style><script>__JS__</script></head>
<body><div class="wrap">
<header><div class="eyebrow">Cartographer · the story of the build</div><h1 id="title"></h1><p class="sub" id="subtitle"></p><p class="sub" id="desired" hidden></p><div class="chips" id="meta"></div></header>
<div class="tiles" id="stats"></div>
<div class="panel">
  <div class="toolbar">
    <button class="primary" id="play">▶ Replay the build</button>
    <button class="small" id="prev" aria-label="Previous move">◀</button><button class="small" id="next" aria-label="Next move">▶</button>
    <span class="count" id="count"></span><span class="grow"></span>
    <select id="branch" aria-label="Branch filter" hidden></select>
    <span class="seg" id="view" role="group" aria-label="View"><button data-v="story" class="on">Story</button><button data-v="map">Map</button></span>
    <span class="seg" id="voice" role="group" aria-label="Voice" hidden><button data-v="plain">Plain</button><button data-v="native">Native</button></span>
    <button class="small" data-theme-btn aria-label="Theme"></button>
  </div>
  <div class="story" id="story"></div>
  <div class="map" id="map" hidden><div id="mapSvg"></div><div class="mapdetail" id="mapDetail"></div></div>
</div>
<div class="tl" id="tl" tabindex="0" role="slider" aria-label="Timeline: each session is a segment, each move sits at its minute"></div>
<div class="legend" id="legend"></div>
<section class="playbook" id="playbook"></section>
<section class="sessions" id="sessions"></section>
<footer>Made by Cartographer · <b>/wrap</b> maps a session, <b>/replay</b> tells the story of a project · space plays, arrow keys step, click the strip to jump. In the map, the trail climbs with outcomes that worked and dips with setbacks; gold rings are achievements (a good outcome from a prompt that needed no repair).</footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const OUT = {worked:'Worked', partly:'Partly worked', broke:'Broke', wrong_way:'Wrong direction', opened:'Opened a question'};
const OCOL = {worked:'var(--k-fix)', partly:'var(--k-artifact)', broke:'var(--k-dead_end)', wrong_way:'var(--k-pivot)', opened:'var(--k-question)'};
const MARKS = {decision:'Decision', question:'Question', dead_end:'Dead end', fix:'Fix', artifact:'Made something', pivot:'Pivot', insight:'Insight'};
const PARTS = [['you','You'],['happened','What happened'],['consequence','What it meant'],['response','How you responded']];
const SC = D.scores || {}, TIER = {achievement:'★ Achievement', solid:'Solid', open:'Open', setback:'Setback'};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $ = id => document.getElementById(id);
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const last = D.sessions.at(-1) || {}, proj = last.project || {}, nS = Math.max(1, D.sessions.length);

// Flatten sessions -> beats (moves) in order; parts within a beat are the replay's ticks.
const beats = [], coachingBy = {}, ticks = [];
D.sessions.forEach((s, si) => {
  const phases = (s.phases && s.phases.length) ? s.phases : [{name:'Session'}];
  (s.moves || []).forEach(m => beats.push({...m, gid: `${si}:${m.id}`, session: si, phase: m.phase || phases[0].name,
    branch: m.branch || (phases.find(p => p.name === m.phase) || {}).branch || s.branch || ''}));
  (s.coaching || []).forEach(c => { const k = c.move || c.step; if (k) (coachingBy[`${si}:${k}`] ||= []).push(c); });
});
beats.sort((a, b) => a.session - b.session || (a.t ?? 0) - (b.t ?? 0));
beats.forEach((b, i) => { b.order = i; b.parts = PARTS.filter(([k]) => b[k]); b.first = ticks.length; b.parts.forEach(([k]) => ticks.push({beat: i, key: k})); b.last = ticks.length - 1; });
const branches = [...new Set(beats.map(b => b.branch).filter(Boolean))], multiBranch = branches.length > 1;
const hasPlain = beats.some(b => b.plain && b.plain.you);
let voice = (hasPlain && last.voice === 'plain') ? 'plain' : 'native';
const tierChip = b => { const s = SC[b.gid]; return s && (s.tier === 'achievement' || s.tier === 'setback') ? `<span class="ach ${s.tier}" title="${esc(s.why)}">${TIER[s.tier]}</span>` : ''; };
const txt = (b, k) => (voice === 'plain' && b.plain && b.plain[k]) || b[k] || '';
const durOf = si => Math.max(D.sessions[si].duration_min || 0, ...beats.filter(b => b.session === si).map(b => b.t || 0), 1);
let lastPx = -9; beats.forEach(b => { b.px = (b.session + Math.min(1, (b.t || 0) / durOf(b.session))) / nS * 100; if (b.px - lastPx < 0.6) b.px = lastPx + 0.6; lastPx = b.px; });

function renderStory() {
  let out = '', lastCh = null;
  beats.forEach(b => {
    const ch = `${b.session}|${b.phase}`;
    if (ch !== lastCh) {
      const s = D.sessions[b.session] || {}, ph = (s.phases || []).find(p => p.name === b.phase) || {};
      out += `<div class="chapter" id="c${b.order}"><span>${nS > 1 ? esc(s.title || 'Session ' + (b.session + 1)) + ' · ' : ''}${esc(b.phase)}</span>${ph.summary ? `<small>${esc(ph.summary)}</small>` : ''}${multiBranch && b.branch ? `<em>⎇ ${esc(b.branch)}</em>` : ''}</div>`;
      lastCh = ch;
    }
    out += `<article class="beat" id="b${b.order}" data-i="${b.order}" style="--o:${OCOL[b.outcome] || 'var(--muted)'}" tabindex="0">`
      + `<div class="bh"><span class="n">${b.order + 1}</span><span>${b.t != null ? 'minute ' + Math.round(b.t) : ''}</span>${b.mark ? `<span class="mk">${esc(MARKS[b.mark] || b.mark)}</span>` : ''}${tierChip(b)}<span class="oc">${esc(OUT[b.outcome] || '')}</span></div>`
      + b.parts.map(([k, label], j) => `<div class="part ${k}" id="p${b.first + j}"><b>${label}</b><div><p>${esc(txt(b, k))}</p>`
          + (k === 'you' && b.prompt ? `<blockquote>${esc(b.prompt)}</blockquote>` : '')
          + (k === 'happened' && (b.files || []).length ? `<div class="files">${b.files.map(f => `<span>${esc(f)}</span>`).join('')}</div>` : '') + '</div></div>').join('')
      + (coachingBy[b.gid] || []).map(c => `<div class="coach"><b>${esc(c.focus)} coaching</b>${esc(c.observation)}<span>${esc(c.suggestion)}</span>${c.rewrite ? `<code>${esc(c.rewrite)}</code>` : ''}</div>`).join('')
      + ((b.evidence || []).length ? `<div class="meta" style="padding:6px 0 4px">Evidence: ${esc(b.evidence.join(' · '))}</div>` : '')
      + '</article>';
  });
  $('story').innerHTML = out;
}
function renderStrip() {
  let out = D.sessions.slice(1).map((_, i) => `<span class="sess" style="left:${(i + 1) / nS * 100}%"></span>`).join(''), lastCh = null, lastLabel = -99, row = 0;
  beats.forEach(b => { const ch = `${b.session}|${b.phase}`; if (ch !== lastCh) { row = (b.px - lastLabel < 16) ? 1 - row : 0; out += `<span class="ch" style="left:${b.px}%;top:${row ? -36 : -19}px">${esc(b.phase)}</span>`; lastLabel = b.px; lastCh = ch; } });
  $('tl').innerHTML = out + beats.map(b => `<i id="t${b.order}" style="left:${b.px}%;background:${OCOL[b.outcome] || 'var(--muted)'}" title="${esc(txt(b, 'you'))}"></i>`).join('');
}
// Map view: a trail through the moves. x is the order of moves (time lives on the strip), y is cumulative outcome; chapters are bands.
const DELTA = {worked:2, partly:1, opened:.5, wrong_way:-1, broke:-1.5};
function renderMap() {
  const W = 1000, H = 380, L = 30, R = 24, T = 56, B = 40; let alt = 0; const alts = beats.map(b => alt += (DELTA[b.outcome] ?? 0));
  const lo = Math.min(0, ...alts), hi = Math.max(1, ...alts), X = i => L + (i + 0.5) / beats.length * (W - L - R), Y = a => T + (hi - a) / (hi - lo) * (H - T - B);
  const pts = beats.map((b, i) => [X(i), Y(alts[i])]), P = p => p[0].toFixed(1) + ' ' + p[1].toFixed(1);
  if (!pts.length) { $('mapSvg').innerHTML = ''; return; }
  const line = 'M' + P([L, Y(0)]) + pts.map(p => ' L' + P(p)).join(''), area = line + ` L${pts.at(-1)[0].toFixed(1)} ${H - B} L${L} ${H - B} Z`;
  const spans = []; let lastCh = null;
  beats.forEach((b, i) => { const k = `${b.session}|${b.phase}`; if (k !== lastCh) { spans.push({phase: b.phase, from: i, to: i}); lastCh = k; } else spans.at(-1).to = i; });
  let labEnd = -99, row = 0;
  const bands = spans.map((s, i) => { const x0 = i ? (pts[s.from][0] + pts[s.from - 1][0]) / 2 : L, x1 = i < spans.length - 1 ? (pts[s.to][0] + pts[s.to + 1][0]) / 2 : W - R;
    row = x0 + 6 < labEnd ? 1 - row : 0; labEnd = x0 + 6 + s.phase.length * 8.2;
    return `${i % 2 ? `<rect class="band" x="${x0.toFixed(1)}" y="${T - 46}" width="${(x1 - x0).toFixed(1)}" height="${H - T - B + 46}"/>` : ''}<text class="chl" x="${(x0 + 6).toFixed(1)}" y="${row ? T - 30 : T - 14}">${esc(s.phase)}</text>`; }).join('');
  const sess = D.sessions.slice(1).map((_, si) => { const i = beats.findIndex(b => b.session === si + 1); if (i < 0) return ''; const x = ((pts[i][0] + pts[i - 1][0]) / 2).toFixed(1); return `<line class="sd" x1="${x}" x2="${x}" y1="${T - 46}" y2="${H - B}"/>`; }).join('');
  let lastLab = {1: -99, '-1': -99}, labRow = {1: 0, '-1': 0};
  const nodes = beats.map((b, i) => { const s = SC[b.gid] || {}, [x, y] = pts[i], r = s.tier === 'achievement' ? 9 : 6.5, big = s.tier === 'achievement' || s.tier === 'setback';
    return `<g class="node ${s.tier || ''}" id="n${b.order}" data-i="${b.order}" tabindex="0" role="button" aria-label="Move ${b.order + 1}: ${esc(txt(b, 'you'))}"><title>${esc(txt(b, 'you'))}${s.why ? '\n' + esc(s.why) : ''}</title>`
      + (s.tier === 'achievement' ? `<circle class="ring" cx="${x}" cy="${y}" r="${r + 5}"/>` : '') + `<circle class="dot" cx="${x}" cy="${y}" r="${r}" fill="${OCOL[b.outcome] || 'var(--muted)'}"/><text class="nn" x="${x}" y="${(y + 3.3).toFixed(1)}">${b.order + 1}</text>`
      + (big ? label(x, y, r, s.tier, MARKS[b.mark] || OUT[b.outcome] || '') : '') + '</g>'; }).join('');
  function label(x, y, r, tier, text) {   // achievements above the node, setbacks below; a second row when neighbours would collide; hug the edges
    const dir = tier === 'setback' ? -1 : 1, w = text.length * 6.6, anchor = x - w / 2 < L ? 'start' : x + w / 2 > W - R ? 'end' : 'middle';
    labRow[dir] = x - lastLab[dir] < w + 8 ? 1 - labRow[dir] : 0; lastLab[dir] = x;
    const ly = dir > 0 ? y - r - 9 - labRow[dir] * 14 : y + r + 15 + labRow[dir] * 14;
    return `<text class="nl ${tier}" x="${x}" y="${ly.toFixed(1)}" text-anchor="${anchor}">${esc(text)}</text>`;
  }
  $('mapSvg').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of the build: each move is a point; the trail climbs with outcomes that worked and dips with setbacks">${bands}${sess}<path class="terrain" d="${area}"/><path class="trail" d="${line}"/>${nodes}</svg>`;
}
function renderDetail(bi) {
  const b = beats[bi]; if (!b) { $('mapDetail').innerHTML = ''; return; } const s = SC[b.gid] || {};
  $('mapDetail').style.setProperty('--o', OCOL[b.outcome] || 'var(--muted)');
  $('mapDetail').innerHTML = `<div class="bh"><span class="n" style="background:var(--o)">${b.order + 1}</span><span>${b.t != null ? 'minute ' + Math.round(b.t) : ''}</span>${b.mark ? `<span class="mk">${esc(MARKS[b.mark] || b.mark)}</span>` : ''}${tierChip(b)}<span class="oc" style="color:var(--o)">${esc(OUT[b.outcome] || '')}</span></div>`
    + (s.why ? `<div class="meta" style="padding:2px 0 6px">${esc(TIER[s.tier] || '')} · ${esc(s.why)}</div>` : '')
    + b.parts.map(([k, label], j) => `<div class="part ${k}" id="d${b.first + j}"><b>${label}</b><div><p>${esc(txt(b, k))}</p>${k === 'you' && b.prompt ? `<blockquote>${esc(b.prompt)}</blockquote>` : ''}</div></div>`).join('')
    + ((b.evidence || []).length ? `<div class="meta" style="padding:6px 0 4px">Evidence: ${esc(b.evidence.join(' · '))}</div>` : '');
}
renderStory(); renderStrip(); renderMap();

// Header, meta, stats, legend
const totalMin = D.sessions.reduce((n, s) => n + (s.duration_min || 0), 0), sum = k => D.sessions.reduce((n, s) => n + ((s.stats || {})[k] || 0), 0);
$('title').textContent = D.title;
$('subtitle').textContent = nS > 1 ? `${nS} sessions · ${[D.sessions[0].date, last.date].filter(Boolean).join(' → ')}` : (last.goal || last.date || '');
const appr = (D.appraisals || []).at(-1), desired = (appr && appr.desired) || last.desired;
if (appr) $('subtitle').textContent += ` · ${appr.version || ''} ${appr.result || ''}`.replace(/\s+$/, '');
if (desired) { $('desired').hidden = false; $('desired').innerHTML = `<b>Done meant:</b> ${esc(desired)}${appr && appr.actual ? ` <span class="meta">· what happened: ${esc(appr.actual)}</span>` : ''}`; }
else if (!appr) { $('desired').hidden = false; $('desired').innerHTML = `<span class="meta">No desired outcome declared yet, so every verdict here is provisional. <b>cartographer goal "…"</b> sets the yardstick; <b>/complete</b> appraises against it.</span>`; }
const agents = [...new Set(D.sessions.map(s => s.agent).filter(Boolean))], langs = [...new Set(D.sessions.flatMap(s => s.languages || []))].slice(0, 8);
$('meta').innerHTML = [proj.id ? `<span class="chip">${esc(proj.id)}</span>` : '', ...agents.map(a => `<span class="chip agent">${esc(a)}</span>`),
  ...branches.map(b => `<span class="chip">⎇ ${esc(b)}</span>`), ...langs.map(l => `<span class="chip">${esc(l)}</span>`)].join('');
$('stats').innerHTML = [[nS, nS === 1 ? 'session' : 'sessions'], [totalMin ? (totalMin >= 90 ? (totalMin / 60).toFixed(1) + 'h' : Math.round(totalMin) + 'm') : 0, 'time'], [sum('prompts'), 'prompts'],
  [beats.length, 'moves', 1], [beats.filter(b => b.outcome === 'worked').length, 'worked', 1], [beats.filter(b => b.outcome === 'broke' || b.outcome === 'wrong_way').length, 'setbacks', 1], [sum('files_touched'), 'files changed']]
  .filter(([v, l, keep]) => keep || v).map(([v, l]) => `<div class="tile"><b>${v}</b><span>${l}</span></div>`).join('');
$('legend').innerHTML = Object.entries(OUT).filter(([k]) => beats.some(b => b.outcome === k)).map(([k, l]) => `<span><i style="background:${OCOL[k]}"></i>${l}</span>`).join('')
  + (beats.some(b => (SC[b.gid] || {}).tier === 'achievement') ? `<span><i style="background:transparent;border:2px solid var(--k-artifact)"></i>Achievement: worked, from a specific prompt that needed no repair (or the agent's own fix or artifact)</span>` : '');

// Branch filter, voice toggle
let branchFilter = '';
if (multiBranch) { const sel = $('branch'); sel.hidden = false; sel.innerHTML = `<option value="">All branches</option>` + branches.map(b => `<option value="${esc(b)}">⎇ ${esc(b)}</option>`).join(''); sel.onchange = () => { branchFilter = sel.value; show(cur, false); }; }
const seg = (id, v) => $(id).querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.v === v));
const setVoice = v => { voice = v; seg('voice', v); renderStory(); renderStrip(); renderMap(); show(cur, false); renderPlaybook(); };
if (hasPlain) { $('voice').hidden = false; seg('voice', voice); $('voice').onclick = e => { const b = e.target.closest('button'); if (b) setVoice(b.dataset.v); }; }
let view = 'story';
const setView = v => { view = v; seg('view', v); $('story').hidden = v !== 'story'; $('map').hidden = v !== 'map'; show(cur, false); };
$('view').onclick = e => { const b = e.target.closest('button'); if (b) setView(b.dataset.v); };
$('mapSvg').addEventListener('click', e => { const g = e.target.closest('.node'); if (g) jump(+g.dataset.i, false); });
$('mapSvg').addEventListener('keydown', e => { const g = e.target.closest('.node'); if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); jump(+g.dataset.i, false); } });

// Replay engine: a tick is one part of one move.
let cur = 0, timer = null;
function show(k, reveal) {
  cur = Math.max(0, Math.min(ticks.length - 1, k));
  const bi = ticks.length ? ticks[cur].beat : 0;
  beats.forEach(b => { const el = $('b' + b.order), t = $('t' + b.order), c = $('c' + b.order);
    if (el) { el.classList.toggle('hidden', reveal && b.first > cur); el.classList.toggle('current', b.order === bi); el.classList.toggle('off', !!branchFilter && b.branch !== branchFilter); }
    if (t) t.classList.toggle('cur', b.order === bi);
    const n = $('n' + b.order); if (n) { n.classList.toggle('cur', b.order === bi); n.classList.toggle('off', (reveal && b.first > cur) || (!!branchFilter && b.branch !== branchFilter)); }
    if (c) c.classList.toggle('hidden', reveal && b.first > cur); });
  if (view === 'map') { renderDetail(bi); ticks.forEach((t, i) => { const el = $('d' + i); if (el) { el.classList.toggle('hidden', reveal && i > cur); el.classList.toggle('now', i === cur); } }); }
  ticks.forEach((t, i) => { const el = $('p' + i); if (el) { el.classList.toggle('hidden', reveal && i > cur); el.classList.toggle('now', i === cur); } });
  $('count').textContent = ticks.length ? `${bi + 1} / ${beats.length}` : '';
  $('tl').setAttribute('aria-valuenow', bi + 1);
  if (reveal && view === 'story') { const el = $('p' + cur); if (el) el.scrollIntoView({block: 'center', behavior: reduced ? 'auto' : 'smooth'}); }
}
function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶ Replay the build'; }
function jump(bi, reveal) { const b = beats[Math.max(0, Math.min(beats.length - 1, bi))]; if (b) { stop(); show(b.last, reveal); } }
$('play').onclick = () => {
  if (timer) return stop();
  if (cur >= ticks.length - 1) show(0, true); else show(cur, true);
  $('play').textContent = '❚❚ Pause';
  timer = setInterval(() => cur >= ticks.length - 1 ? stop() : show(cur + 1, true), 1300);
};
$('prev').onclick = () => jump(ticks[cur].beat - 1, true); $('next').onclick = () => jump(ticks[cur].beat + 1, true);
const pick = e => { const r = $('tl').getBoundingClientRect(), px = (e.clientX - r.left) / r.width * 100; let best = 0; beats.forEach(b => { if (Math.abs(b.px - px) < Math.abs(beats[best].px - px)) best = b.order; }); jump(best, true); };
$('tl').addEventListener('pointerdown', e => { pick(e); $('tl').setPointerCapture(e.pointerId); });
$('tl').addEventListener('pointermove', e => { if (e.buttons) pick(e); });
$('story').addEventListener('click', e => { const a = e.target.closest('.beat'); if (a && !e.target.closest('blockquote,code')) jump(+a.dataset.i, false); });
$('story').addEventListener('keydown', e => { const a = e.target.closest('.beat'); if (a && e.key === 'Enter') { e.preventDefault(); jump(+a.dataset.i, false); } });
document.addEventListener('keydown', e => { if (e.target.closest('input,select,textarea')) return; if (e.key === ' ') { e.preventDefault(); $('play').click(); } else if (e.key === 'ArrowRight') $('next').click(); else if (e.key === 'ArrowLeft') $('prev').click(); });
$('tl').setAttribute('aria-valuemin', 1); $('tl').setAttribute('aria-valuemax', beats.length);
if (ticks.length) show(0, false);

// Playbook (merged across sessions)
function renderPlaybook() {
  const all = k => D.sessions.flatMap(s => s[k] || []), cards = [];
  const coaching = all('coaching'), prompts = all('reusable_prompts'), pats = all('patterns'), sinks = all('time_sinks'), next = last.next_steps || [];
  const ev = i => (i && i.evidence && i.evidence.length) ? `<div class="meta">${esc(i.evidence.join(' · '))}</div>` : '';
  const section = (h, items, f) => (items && items.length) ? `<h2 style="margin-top:16px">${h}</h2><ul>${items.map(i => `<li>${f(i)}${ev(i)}</li>`).join('')}</ul>` : '';
  (D.appraisals || []).forEach(a => cards.push([`Appraisal · ${esc(a.version || '')} · ${esc(a.result || '')}`,
    `<p style="margin:0 0 6px;font-size:16px"><b>${esc(a.verdict || '')}</b></p>`
    + section('What got you there', a.got_you_there, i => `${esc(i.what)}${i.why ? `<br><small>${esc(i.why)}</small>` : ''}`)
    + section('What cost you', a.cost_you, i => `${i.minutes != null ? `<b>${esc(i.minutes)}m</b> · ` : ''}${esc(i.what)}`)
    + section('Carried into the result', a.carried_forward, i => `${esc(i.what)}<br><small>${esc(i.risk || '')}${i.since ? ' · since ' + esc(i.since) : ''}</small>`)
    + section('How you prompted, and what it did', a.prompting, i => `${esc(i.pattern || i.what || '')}${i.effect ? `<br><small>${esc(i.effect)}</small>` : ''}`)
    + section('Next time', a.next_time, i => esc(i)), true]));
  if (coaching.length) cards.push(['Coaching', `<ul>${coaching.map(c => `<li><span class="tag">${esc(c.focus)}</span>${esc(c.observation)}<br><small>${esc(c.suggestion)}</small>${c.rewrite ? `<code>${esc(c.rewrite)}</code>` : ''}</li>`).join('')}</ul>`, true]);
  if (prompts.length) cards.push(['Prompts worth reusing', `<ul>${prompts.map(p => `<li>${p.language ? `<span class="tag">${esc(p.language)}</span>` : ''}<code>${esc(p.prompt)}</code><small>${esc(p.why || '')}</small></li>`).join('')}</ul>`]);
  if (pats.length) cards.push(['How you build', `<ul>${pats.map(p => `<li>${esc(p)}</li>`).join('')}</ul>`]);
  if (sinks.length) cards.push(['Where time went', `<ul>${sinks.map(t => `<li><b>${esc(t.minutes ?? '?')}m</b> · ${esc(t.what)}</li>`).join('')}</ul>`]);
  const profs = D.sessions.map(s => s.prompting).filter(p => p && p.prompts);
  if (profs.length) {
    const n = profs.reduce((a, p) => a + p.prompts, 0), avg = k => profs.reduce((a, p) => a + (p[k] || 0) * p.prompts, 0) / n, pct = k => Math.round(100 * avg(k)) + '%';
    const tiles = [[n, 'prompts'], [avg('avg_words').toFixed(0), 'avg words'], [avg('avg_specificity').toFixed(1) + '/3', 'specificity'], [pct('anchored_ratio'), 'anchored'], [pct('vague_ratio'), 'vague'],
      [pct('delegation_ratio'), 'delegating'], [pct('acceptance_ratio'), 'with done-condition'], [pct('repair_ratio'), 'repairs'], [pct('accept_ratio'), 'bare go-aheads']];
    cards.push(['Prompting profile', `<div class="numbers">${tiles.map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join('')}</div>`]);
  }
  if (next.length) cards.push(['Next time', `<ul>${next.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`]);
  $('playbook').innerHTML = cards.map(([h, b, wide]) => `<div class="card panel${wide ? ' wide' : ''}"><h2>${h}</h2>${b}</div>`).join('');
}
renderPlaybook();
$('sessions').innerHTML = `<h2>Sessions</h2>` + D.sessions.map(s =>
  `<div class="sess"><b>${esc(s.title || 'Session')}</b><div class="meta">${esc(s.date || '')} · ${esc(s.agent || '')}${s.branch ? ' · ⎇ ' + esc(s.branch) : ''} · ${Math.round(s.duration_min || 0)}m · ${(s.stats||{}).prompts || 0} prompts${(s.languages||[]).length ? ' · ' + esc(s.languages.slice(0,4).join(', ')) : ''}</div>`
  + `<p>${esc(s.goal || '')}${s.outcome ? ' <br><small>→ ' + esc(s.outcome) + '</small>' : ''}</p></div>`).join('');
</script></body></html>
"""
