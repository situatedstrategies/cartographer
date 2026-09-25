"""Replay renderer: recaps -> one self-contained HTML page that tells the story.

The unit is a move: what you did, what happened, what it meant, how you
responded. Press "Replay the build" and the story reveals itself one part
at a time, chapter by chapter (phases), across every session of a project.
Below it: a time strip (each session a segment, each move at its minute),
the playbook (coaching, reusable prompts, patterns, time sinks, prompting
profile) and a session list. No external assets; works from file:// and in
both color schemes. `BASE_CSS` is shared with the local dashboard.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

from . import recap, store


def render_html(recaps: List[Dict[str, Any]], title: str) -> str:
    clean = []
    for r in recaps:
        r = recap.normalize(r) if not r.get("moves") else r   # older maps: typed steps -> moves
        clean.append({k: v for k, v in r.items() if k != "_path"})
    payload = json.dumps({"title": title, "sessions": clean}, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__CSS__", BASE_CSS + STORY_CSS).replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)


def render_recaps(recaps: List[Dict[str, Any]], title: str, out: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_html(recaps, title))
    return out


def render_project(project: str, out: Optional[str] = None) -> str:
    entry = store.find_project(project)
    if not entry:
        raise LookupError("no project matching %r; run `cartographer projects`" % project)
    recaps = store.load_recaps(entry["slug"])
    if not recaps:
        raise LookupError("project %s has no wrapped sessions yet" % entry["name"])
    return render_recaps(recaps, entry["name"], out or os.path.join(store.REPLAYS, "%s.html" % entry["slug"]))


# Monospace is for things that are literally code or the user's exact words: prompts, commands, file names. Everything else is the sans.
BASE_CSS = r"""
:root{--sans:-apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --bg:#dfe5e0;--panel:#f3f6f3;--panel2:#e7ece8;--ink:#121915;--muted:#4d5a54;--line:#c1ccc4;--accent:#155a63;--accent-ink:#fff;
  --shadow:0 1px 2px rgba(18,25,21,.06),0 12px 30px rgba(18,25,21,.09);
  --k-prompt:#2a5fa3;--k-decision:#6747a3;--k-question:#177f7c;--k-dead_end:#b0362a;--k-fix:#2a7a42;--k-artifact:#9c6c16;--k-pivot:#bf5520;--k-insight:#526270;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0c1110;--panel:#141a18;--panel2:#1b2320;--ink:#e4ebe6;--muted:#93a39b;--line:#28332e;--accent:#5fb9c2;--accent-ink:#0c1110;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 12px 30px rgba(0,0,0,.32);
  --k-prompt:#79a9e8;--k-decision:#b090e8;--k-question:#52c2bc;--k-dead_end:#ee7062;--k-fix:#66c586;--k-artifact:#e2b05a;--k-pivot:#f28f5a;--k-insight:#9fb0bf;color-scheme:dark}}
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
<style>__CSS__</style></head>
<body><div class="wrap">
<header><div class="eyebrow">Cartographer · the story of the build</div><h1 id="title"></h1><p class="sub" id="subtitle"></p><div class="chips" id="meta"></div></header>
<div class="tiles" id="stats"></div>
<div class="panel">
  <div class="toolbar">
    <button class="primary" id="play">▶ Replay the build</button>
    <button class="small" id="prev" aria-label="Previous move">◀</button><button class="small" id="next" aria-label="Next move">▶</button>
    <span class="count" id="count"></span><span class="grow"></span>
    <select id="branch" aria-label="Branch filter" hidden></select><button class="small" id="voice" hidden>Plain words</button>
  </div>
  <div class="story" id="story"></div>
</div>
<div class="tl" id="tl" tabindex="0" role="slider" aria-label="Timeline: each session is a segment, each move sits at its minute"></div>
<div class="legend" id="legend"></div>
<section class="playbook" id="playbook"></section>
<section class="sessions" id="sessions"></section>
<footer>Made by Cartographer · <b>/wrap</b> maps a session, <b>/replay</b> tells the story of a project · space plays, arrow keys step, click the strip to jump.</footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const OUT = {worked:'Worked', partly:'Partly worked', broke:'Broke', wrong_way:'Wrong direction', opened:'Opened a question'};
const OCOL = {worked:'var(--k-fix)', partly:'var(--k-artifact)', broke:'var(--k-dead_end)', wrong_way:'var(--k-pivot)', opened:'var(--k-question)'};
const MARKS = {decision:'Decision', question:'Question', dead_end:'Dead end', fix:'Fix', artifact:'Made something', pivot:'Pivot', insight:'Insight'};
const PARTS = [['you','You'],['happened','What happened'],['consequence','What it meant'],['response','How you responded']];
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
let voice = (hasPlain && last.voice === 'plain') ? 'plain' : 'technical';
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
      + `<div class="bh"><span class="n">${b.order + 1}</span><span>${b.t != null ? 'minute ' + Math.round(b.t) : ''}</span>${b.mark ? `<span class="mk">${esc(MARKS[b.mark] || b.mark)}</span>` : ''}<span class="oc">${esc(OUT[b.outcome] || '')}</span></div>`
      + b.parts.map(([k, label], j) => `<div class="part ${k}" id="p${b.first + j}"><b>${label}</b><div><p>${esc(txt(b, k))}</p>`
          + (k === 'you' && b.prompt ? `<blockquote>${esc(b.prompt)}</blockquote>` : '')
          + (k === 'happened' && (b.files || []).length ? `<div class="files">${b.files.map(f => `<span>${esc(f)}</span>`).join('')}</div>` : '') + '</div></div>').join('')
      + (coachingBy[b.gid] || []).map(c => `<div class="coach"><b>${esc(c.focus)} coaching</b>${esc(c.observation)}<span>${esc(c.suggestion)}</span>${c.rewrite ? `<code>${esc(c.rewrite)}</code>` : ''}</div>`).join('')
      + '</article>';
  });
  $('story').innerHTML = out;
}
function renderStrip() {
  let out = D.sessions.slice(1).map((_, i) => `<span class="sess" style="left:${(i + 1) / nS * 100}%"></span>`).join(''), lastCh = null, lastLabel = -99, row = 0;
  beats.forEach(b => { const ch = `${b.session}|${b.phase}`; if (ch !== lastCh) { row = (b.px - lastLabel < 16) ? 1 - row : 0; out += `<span class="ch" style="left:${b.px}%;top:${row ? -36 : -19}px">${esc(b.phase)}</span>`; lastLabel = b.px; lastCh = ch; } });
  $('tl').innerHTML = out + beats.map(b => `<i id="t${b.order}" style="left:${b.px}%;background:${OCOL[b.outcome] || 'var(--muted)'}" title="${esc(txt(b, 'you'))}"></i>`).join('');
}
renderStory(); renderStrip();

// Header, meta, stats, legend
const totalMin = D.sessions.reduce((n, s) => n + (s.duration_min || 0), 0), sum = k => D.sessions.reduce((n, s) => n + ((s.stats || {})[k] || 0), 0);
$('title').textContent = D.title;
$('subtitle').textContent = nS > 1 ? `${nS} sessions · ${[D.sessions[0].date, last.date].filter(Boolean).join(' → ')}` : (last.goal || last.date || '');
const agents = [...new Set(D.sessions.map(s => s.agent).filter(Boolean))], langs = [...new Set(D.sessions.flatMap(s => s.languages || []))].slice(0, 8);
$('meta').innerHTML = [proj.id ? `<span class="chip">${esc(proj.id)}</span>` : '', ...agents.map(a => `<span class="chip agent">${esc(a)}</span>`),
  ...branches.map(b => `<span class="chip">⎇ ${esc(b)}</span>`), ...langs.map(l => `<span class="chip">${esc(l)}</span>`)].join('');
$('stats').innerHTML = [[nS, nS === 1 ? 'session' : 'sessions'], [totalMin ? (totalMin >= 90 ? (totalMin / 60).toFixed(1) + 'h' : Math.round(totalMin) + 'm') : 0, 'time'], [sum('prompts'), 'prompts'],
  [beats.length, 'moves', 1], [beats.filter(b => b.outcome === 'worked').length, 'worked', 1], [beats.filter(b => b.outcome === 'broke' || b.outcome === 'wrong_way').length, 'setbacks', 1], [sum('files_touched'), 'files changed']]
  .filter(([v, l, keep]) => keep || v).map(([v, l]) => `<div class="tile"><b>${v}</b><span>${l}</span></div>`).join('');
$('legend').innerHTML = Object.entries(OUT).filter(([k]) => beats.some(b => b.outcome === k)).map(([k, l]) => `<span><i style="background:${OCOL[k]}"></i>${l}</span>`).join('');

// Branch filter, voice toggle
let branchFilter = '';
if (multiBranch) { const sel = $('branch'); sel.hidden = false; sel.innerHTML = `<option value="">All branches</option>` + branches.map(b => `<option value="${esc(b)}">⎇ ${esc(b)}</option>`).join(''); sel.onchange = () => { branchFilter = sel.value; show(cur, false); }; }
const setVoice = v => { voice = v; const b = $('voice'); b.textContent = v === 'plain' ? 'Technical words' : 'Plain words'; b.classList.toggle('on', v === 'plain'); renderStory(); renderStrip(); show(cur, false); renderPlaybook(); };
if (hasPlain) { $('voice').hidden = false; $('voice').onclick = () => setVoice(voice === 'plain' ? 'technical' : 'plain'); }

// Replay engine: a tick is one part of one move.
let cur = 0, timer = null;
function show(k, reveal) {
  cur = Math.max(0, Math.min(ticks.length - 1, k));
  const bi = ticks.length ? ticks[cur].beat : 0;
  beats.forEach(b => { const el = $('b' + b.order), t = $('t' + b.order), c = $('c' + b.order);
    if (el) { el.classList.toggle('hidden', reveal && b.first > cur); el.classList.toggle('current', b.order === bi); el.classList.toggle('off', !!branchFilter && b.branch !== branchFilter); }
    if (t) t.classList.toggle('cur', b.order === bi);
    if (c) c.classList.toggle('hidden', reveal && b.first > cur); });
  ticks.forEach((t, i) => { const el = $('p' + i); if (el) { el.classList.toggle('hidden', reveal && i > cur); el.classList.toggle('now', i === cur); } });
  $('count').textContent = ticks.length ? `${bi + 1} / ${beats.length}` : '';
  $('tl').setAttribute('aria-valuenow', bi + 1);
  if (reveal) { const el = $('p' + cur); if (el) el.scrollIntoView({block: 'center', behavior: reduced ? 'auto' : 'smooth'}); }
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
