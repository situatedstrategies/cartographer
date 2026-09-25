"""Replay renderer: recaps -> one self-contained HTML page.

Press "Replay the build" and the map draws itself step by step across every
session of a project. The page also carries a time strip (each session a
segment, each step placed by minute), the playbook (coaching, reusable
prompts, patterns, time sinks, prompting profile) and a session list. No
external assets; works from file:// and in both color schemes. `BASE_CSS` is
shared with the local home page (`cartographer serve`).
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

from . import store


def render_html(recaps: List[Dict[str, Any]], title: str) -> str:
    clean = [{k: v for k, v in r.items() if k != "_path"} for r in recaps]
    payload = json.dumps({"title": title, "sessions": clean}, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__CSS__", BASE_CSS + MAP_CSS).replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)


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


BASE_CSS = r"""
:root{--bg:#eef1ec;--panel:#fbfcfa;--panel2:#f0f4ef;--ink:#17211d;--muted:#5b6a63;--line:#d3dcd5;--accent:#1f6f78;--accent-ink:#fff;
  --shadow:0 1px 2px rgba(23,33,29,.05),0 10px 28px rgba(23,33,29,.07);
  --k-prompt:#2d64a8;--k-decision:#6d4aa8;--k-question:#1f8a86;--k-dead_end:#b8392c;--k-fix:#2d7f45;--k-artifact:#a8741a;--k-pivot:#c65a24;--k-insight:#5a6a78;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0f1513;--panel:#171f1c;--panel2:#1f2925;--ink:#e3ebe6;--muted:#97a79f;--line:#2b3733;--accent:#5cb6c0;--accent-ink:#0f1513;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 10px 28px rgba(0,0,0,.28);
  --k-prompt:#74a6e6;--k-decision:#ad8ce6;--k-question:#4fc0ba;--k-dead_end:#ec6c5e;--k-fix:#62c381;--k-artifact:#e0ad55;--k-pivot:#f08b55;--k-insight:#9aabba;color-scheme:dark}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Inter,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1320px;margin:0 auto;padding:24px 20px 60px}
.eyebrow{font:600 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
h1{font:700 clamp(26px,3.6vw,38px)/1.15 inherit;letter-spacing:-.015em;margin:8px 0 4px}
h2{font:600 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:0 0 14px}
.sub{color:var(--muted);margin:0 0 8px;max-width:72ch}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.card{padding:20px 22px}
.chips{display:flex;flex-wrap:wrap;gap:6px 8px;margin:10px 0 18px;font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--panel)}.chip.agent{border-color:var(--accent);color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin:0 0 20px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.tile b{display:block;font:600 22px/1.15 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tile span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
@media (max-width:600px){.tiles{grid-template-columns:repeat(3,1fr);gap:8px}.tile{padding:10px 12px;border-radius:12px}.tile b{font-size:18px}.wrap{padding:18px 14px 48px}}
button,.btn,select{font:600 13px/1 inherit;padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
button.primary,.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
button.on{border-color:var(--accent);color:var(--accent)}
button.small,.btn.small{padding:7px 11px;font-size:12px;border-radius:8px}
button:disabled{opacity:.5;cursor:default}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tag{font:600 10px ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-right:6px}
.mono{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
kbd{font:12.5px ui-monospace,Menlo,monospace;background:var(--panel2);padding:2px 7px;border-radius:6px;white-space:nowrap}
code,blockquote{display:block;margin:6px 0 0;padding:10px 12px;background:var(--panel2);font:12.5px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;border-radius:10px;overflow-wrap:anywhere}
footer{margin-top:40px;font-size:12px;color:var(--muted)}
"""

MAP_CSS = r"""
.stage{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px}@media (max-width:960px){.stage{grid-template-columns:1fr}}
.toolbar{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}.toolbar .grow{flex:1}
.map{overflow:auto;max-height:66vh;border-radius:0 0 16px 16px}.map svg{display:block}
.side{padding:20px 22px;align-self:start;position:sticky;top:12px;display:grid;gap:10px}
.side .kind{display:inline-flex;align-items:center;gap:7px;font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase}
.side .kind i{width:10px;height:10px;border-radius:3px;display:inline-block}
.side h3{margin:0;font:600 20px/1.3 inherit;letter-spacing:-.01em}
.side .when{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}.side p{margin:0}
blockquote{border-left:3px solid var(--k-prompt);border-radius:0 10px 10px 0;max-height:220px;overflow:auto}
.files{display:flex;flex-wrap:wrap;gap:4px 6px}.files span{font:11px ui-monospace,Menlo,monospace;color:var(--muted);background:var(--panel2);border-radius:6px;padding:2px 7px}
.coach{border-top:1px dashed var(--line);padding-top:10px;font-size:13.5px}.coach b{color:var(--accent)}
.tl{position:relative;height:36px;margin:14px 0 0;border-radius:10px;background:var(--panel2);cursor:pointer;touch-action:none}
.tl i{position:absolute;top:9px;width:6px;height:18px;border-radius:3px;transform:translateX(-50%);opacity:.7}
.tl i.cur{opacity:1;top:5px;height:26px;width:8px;box-shadow:0 0 0 2px var(--panel),0 0 0 4px var(--ink)}
.tl .sess{position:absolute;top:0;bottom:0;border-left:1px dashed var(--line)}
.count{font:12px ui-monospace,Menlo,monospace;color:var(--muted);min-width:64px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:12px 0 0;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.node{cursor:pointer;transition:opacity .35s}.node rect.box{fill:var(--panel);stroke-width:1.5}
.node.hidden{opacity:0;pointer-events:none}.node.off{opacity:.15}.node.current rect.box{stroke-width:3}
.node text{fill:var(--ink);font:13px/1 ui-sans-serif,-apple-system,sans-serif}
.node .k{font:600 9.5px ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase}
.node .b,.colhead,.colbranch{font:10px ui-monospace,Menlo,monospace;fill:var(--muted)}
.colhead{font-weight:600;font-size:11px;letter-spacing:.1em;text-transform:uppercase}.colbranch{fill:var(--accent)}
.colsess{font:600 12.5px ui-sans-serif,-apple-system,sans-serif;fill:var(--accent)}
.edge{fill:none;transition:opacity .35s}.edge.hidden{opacity:0}
.playbook{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:30px}
.card.wide{grid-column:1/-1}.card ul{margin:0;padding-left:18px}.card li{margin:0 0 10px}.card small{color:var(--muted)}
.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}.numbers div{background:var(--panel2);border-radius:10px;padding:10px 12px}
.numbers b{display:block;font:600 20px/1.1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}.numbers span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.sessions{margin-top:30px}.sess{border-top:1px solid var(--line);padding:14px 0;display:grid;gap:4px}.sess b{font:600 16px inherit}.sess p{margin:0}.sess .m{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
@media (prefers-reduced-motion:reduce){.node,.edge{transition:none}}
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Cartographer</title>
<style>__CSS__</style></head>
<body><div class="wrap">
<header><div class="eyebrow">Cartographer · replay</div><h1 id="title"></h1><p class="sub" id="subtitle"></p><div class="chips" id="meta"></div></header>
<div class="tiles" id="stats"></div>
<div class="stage">
  <div>
    <div class="panel">
      <div class="toolbar">
        <button class="primary" id="play">▶ Replay the build</button>
        <button class="small" id="prev" aria-label="Previous step">◀</button><button class="small" id="next" aria-label="Next step">▶</button>
        <span class="count" id="count"></span><span class="grow"></span>
        <select id="branch" aria-label="Branch filter" hidden></select><button class="small" id="voice" hidden>Plain words</button>
        <button class="small" id="zout" aria-label="Zoom out">−</button><button class="small" id="zfit">Fit</button><button class="small" id="zin" aria-label="Zoom in">+</button>
      </div>
      <div class="map" id="map"></div>
    </div>
    <div class="tl" id="tl" tabindex="0" role="slider" aria-label="Timeline: each session is a segment, each step sits at its minute"></div>
    <div class="legend" id="legend"></div>
  </div>
  <aside class="side panel" id="side"></aside>
</div>
<section class="playbook" id="playbook"></section>
<section class="sessions" id="sessions"></section>
<footer>Generated by Cartographer · <b>/wrap</b> maps a session, <b>/replay</b> replays a project · space plays, arrow keys step, click the strip to jump.</footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const KINDS = {prompt:'Prompt',decision:'Decision',question:'Question',dead_end:'Dead end',fix:'Fix',artifact:'Artifact',pivot:'Pivot',insight:'Insight'};
const REL = {led_to:'var(--muted)', blocked_by:'var(--k-dead_end)', reverted:'var(--k-pivot)', reused:'var(--k-fix)', answered:'var(--k-question)'};
const col = k => `var(--k-${KINDS[k] ? k : 'insight'})`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $ = id => document.getElementById(id);
const last = D.sessions.at(-1) || {}, proj = last.project || {}, nS = Math.max(1, D.sessions.length);

// Flatten sessions -> ordered steps with globally unique ids and phase columns.
const steps = [], columns = [], coachingBy = {};
D.sessions.forEach((s, si) => {
  const phases = (s.phases && s.phases.length) ? s.phases : [{name:'Session'}], colIndex = {};
  phases.forEach((p, pi) => { colIndex[p.name] = columns.length; columns.push({phase: p, first: pi === 0, label: s.title || `Session ${si+1}`, agent: s.agent}); });
  const fallback = columns.length - phases.length;
  (s.steps || []).forEach(st => steps.push({...st, gid: `${si}:${st.id}`, session: si, col: colIndex[st.phase] ?? fallback,
    branch: st.branch || (phases.find(p => p.name === st.phase) || {}).branch || s.branch || '',
    links: (st.links || []).map(l => ({...l, to: String(l.to).includes(':') ? l.to : `${si}:${l.to}`}))}));
  (s.coaching || []).forEach(c => { if (c.step) (coachingBy[`${si}:${c.step}`] ||= []).push(c); });
});
steps.sort((a, b) => a.session - b.session || (a.t ?? 0) - (b.t ?? 0));
steps.forEach((s, i) => s.order = i);
const branches = [...new Set(steps.map(s => s.branch).filter(Boolean))], multiBranch = branches.length > 1;
const hasPlain = steps.some(s => s.plain && s.plain.title);
let voice = (hasPlain && last.voice === 'plain') ? 'plain' : 'technical';
const T = s => (voice === 'plain' && s.plain?.title) || s.title, DT = s => (voice === 'plain' && s.plain?.detail) || s.detail || '';

// Layout: phases left->right, steps stacked in order within their column; time strip: each session a segment, steps by minute.
const W = 236, H = 76, GX = 44, GY = 14, TOP = 72, LEFT = 20, perCol = columns.map(() => 0);
steps.forEach(s => { s.x = LEFT + s.col * (W + GX); s.y = TOP + perCol[s.col]++ * (H + GY); });
const width = LEFT * 2 + columns.length * (W + GX) - GX, height = TOP + Math.max(1, ...perCol) * (H + GY) + 20;
const durOf = si => Math.max(D.sessions[si].duration_min || 0, ...steps.filter(s => s.session === si).map(s => s.t || 0), 1);
let lastPx = -9; steps.forEach(s => { s.px = (s.session + Math.min(1, (s.t || 0) / durOf(s.session))) / nS * 100; if (s.px - lastPx < 0.6) s.px = lastPx + 0.6; lastPx = s.px; });
const byId = Object.fromEntries(steps.map(s => [s.gid, s])), edges = [];
steps.forEach((s, i) => { const n = steps[i+1]; if (n && n.session === s.session) edges.push({from: s, to: n, rel: 'seq'}); });
steps.forEach(s => s.links.forEach(l => byId[l.to] && edges.push({from: s, to: byId[l.to], rel: l.rel in REL ? l.rel : 'led_to'})));
edges.forEach((e, i) => e.el = 'e' + i);
let zoom = 1;
const clip = (t, n) => t.length > n ? t.slice(0, n - 1) + '…' : t;
function wrapText(t, n, max) { const lines = ['']; for (const w of String(t || '').split(/\s+/)) { const cand = (lines.at(-1) + ' ' + w).trim(); if (cand.length > n && lines.at(-1)) { if (lines.length === max) { lines[max-1] = clip(lines[max-1] + ' ' + w, n); break; } lines.push(w); } else lines[lines.length-1] = cand; } return lines; }

function renderMap() {
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.round(width*zoom)}" height="${Math.round(height*zoom)}" viewBox="0 0 ${width} ${height}"><defs>`
    + Object.entries(REL).map(([k,c]) => `<marker id="m-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="${c}"/></marker>`).join('') + '</defs>';
  columns.forEach((c, i) => {
    const x = LEFT + i * (W + GX);
    if (c.first) svg += `<text class="colsess" x="${x}" y="20">${esc(clip(c.label, 32))}${nS > 1 && c.agent ? ` · ${esc(c.agent)}` : ''}</text>`;
    svg += `<text class="colhead" x="${x}" y="46">${esc(c.phase.name)}</text>`;
    if (multiBranch && c.phase.branch) svg += `<text class="colbranch" x="${x}" y="59">⎇ ${esc(c.phase.branch)}</text>`;
    svg += `<line x1="${x}" x2="${x+W}" y1="63" y2="63" stroke="var(--line)"/>`;
  });
  edges.forEach(e => {
    const a = e.from, b = e.to, same = a.col === b.col, dir = Math.sign(b.col - a.col);
    const x1 = a.x + (dir < 0 ? 0 : W), y1 = a.y + H/2, x2 = b.x + (dir > 0 ? 0 : W), y2 = b.y + H/2, bend = same ? 40 : Math.abs(x2 - x1) / 2;
    const d = same ? `M${x1},${y1} C${x1+bend},${y1} ${x2+bend},${y2} ${x2},${y2}` : `M${x1},${y1} C${x1+dir*bend},${y1} ${x2-dir*bend},${y2} ${x2},${y2}`;
    svg += e.rel === 'seq' ? `<path id="${e.el}" class="edge" d="${d}" stroke="var(--line)" stroke-width="1.2" stroke-dasharray="3 4"/>`
                           : `<path id="${e.el}" class="edge" d="${d}" stroke="${REL[e.rel]}" stroke-width="1.8" marker-end="url(#m-${e.rel})"/>`;
  });
  steps.forEach(s => {
    const head = `${KINDS[s.kind] || s.kind}${s.t != null ? ` · ${Math.round(s.t)}m` : ''}`;
    svg += `<g class="node" id="n${s.order}" data-i="${s.order}" tabindex="0"><rect class="box" x="${s.x}" y="${s.y}" width="${W}" height="${H}" rx="12" stroke="${col(s.kind)}"/>`
        + `<rect x="${s.x}" y="${s.y+12}" width="4" height="${H-24}" rx="2" fill="${col(s.kind)}" stroke="none"/><text class="k" x="${s.x+16}" y="${s.y+18}" style="fill:${col(s.kind)}">${esc(head)}</text>`
        + (multiBranch && s.branch ? `<text class="b" x="${s.x+W-10}" y="${s.y+18}" text-anchor="end">⎇ ${esc(clip(s.branch, 16))}</text>` : '')
        + wrapText(T(s), 30, 3).map((l, j) => `<text x="${s.x+16}" y="${s.y+37+j*15}">${esc(l)}</text>`).join('') + '</g>';
  });
  $('map').innerHTML = svg + '</svg>';
}
function renderStrip() {
  $('tl').innerHTML = D.sessions.slice(1).map((_, i) => `<span class="sess" style="left:${(i+1)/nS*100}%"></span>`).join('')
    + steps.map(s => `<i id="t${s.order}" style="left:${s.px}%;background:${col(s.kind)}"><title>${esc(T(s))}</title></i>`).join('');
}
renderMap(); renderStrip();

// Header, meta, stats, legend
const totalMin = D.sessions.reduce((n, s) => n + (s.duration_min || 0), 0), sum = k => D.sessions.reduce((n, s) => n + ((s.stats || {})[k] || 0), 0);
$('title').textContent = D.title;
$('subtitle').textContent = nS > 1 ? `${nS} sessions · ${[D.sessions[0].date, last.date].filter(Boolean).join(' → ')}` : (last.goal || last.date || '');
const agents = [...new Set(D.sessions.map(s => s.agent).filter(Boolean))], langs = [...new Set(D.sessions.flatMap(s => s.languages || []))].slice(0, 8);
$('meta').innerHTML = [proj.id ? `<span class="chip">${esc(proj.id)}</span>` : '', ...agents.map(a => `<span class="chip agent">${esc(a)}</span>`),
  ...branches.map(b => `<span class="chip">⎇ ${esc(b)}</span>`), ...langs.map(l => `<span class="chip">${esc(l)}</span>`)].join('');
$('stats').innerHTML = [[nS, nS === 1 ? 'session' : 'sessions'], [totalMin ? (totalMin >= 90 ? (totalMin/60).toFixed(1)+'h' : Math.round(totalMin)+'m') : 0, 'time'], [sum('prompts'), 'prompts'],
  [steps.filter(s => s.kind === 'decision').length, 'decisions', 1], [steps.filter(s => s.kind === 'dead_end').length, 'dead ends', 1], [sum('errors'), 'errors'], [sum('files_touched'), 'files changed']]
  .filter(([v, l, keep]) => keep || v).map(([v, l]) => `<div class="tile"><b>${v}</b><span>${l}</span></div>`).join('');  // stats a recap never recorded stay off the page
$('legend').innerHTML = Object.entries(KINDS).filter(([k]) => steps.some(s => s.kind === k)).map(([k, l]) => `<span><i style="background:${col(k)}"></i>${l}</span>`).join('')
  + Object.entries(REL).filter(([k]) => k !== 'led_to').map(([k, c]) => `<span><i style="background:${c}"></i>→ ${k.replace('_', ' ')}</span>`).join('');

// Branch filter, voice toggle, zoom
let branchFilter = '';
if (multiBranch) { const sel = $('branch'); sel.hidden = false; sel.innerHTML = `<option value="">All branches</option>` + branches.map(b => `<option value="${esc(b)}">⎇ ${esc(b)}</option>`).join(''); sel.onchange = () => { branchFilter = sel.value; show(cur, false); }; }
const setVoice = v => { voice = v; const b = $('voice'); b.textContent = v === 'plain' ? 'Technical words' : 'Plain words'; b.classList.toggle('on', v === 'plain'); renderMap(); renderStrip(); show(cur, false); renderPlaybook(); };
if (hasPlain) { $('voice').hidden = false; $('voice').onclick = () => setVoice(voice === 'plain' ? 'technical' : 'plain'); }
const setZoom = z => { zoom = Math.min(1.6, Math.max(0.45, z)); renderMap(); show(cur, false); };
$('zin').onclick = () => setZoom(zoom * 1.2); $('zout').onclick = () => setZoom(zoom / 1.2);
$('zfit').onclick = () => setZoom(($('map').clientWidth - 2) / width);

// Replay engine
let cur = 0, timer = null;
function show(i, reveal) {
  cur = Math.max(0, Math.min(steps.length - 1, i));
  steps.forEach(s => { const el = $('n' + s.order), t = $('t' + s.order); if (el) { el.classList.toggle('hidden', reveal && s.order > cur); el.classList.toggle('current', s.order === cur); el.classList.toggle('off', !!branchFilter && s.branch !== branchFilter); } if (t) t.classList.toggle('cur', s.order === cur); });
  edges.forEach(e => { const el = $(e.el); if (el) el.classList.toggle('hidden', reveal && (e.from.order > cur || e.to.order > cur)); });
  const s = steps[cur]; if (!s) return;
  $('count').textContent = `${cur + 1} / ${steps.length}`; $('tl').setAttribute('aria-valuenow', cur + 1); $('tl').setAttribute('aria-valuetext', T(s));
  const sess = D.sessions[s.session] || {};
  $('side').innerHTML = `<div class="kind" style="color:${col(s.kind)}"><i style="background:${col(s.kind)}"></i>${esc(KINDS[s.kind] || s.kind)}</div><h3>${esc(T(s))}</h3>`
    + `<div class="when">${esc(sess.title || '')}${s.t != null ? ' · minute ' + Math.round(s.t) : ''}${s.phase ? ' · ' + esc(s.phase) : ''}${s.branch ? ' · ⎇ ' + esc(s.branch) : ''}</div>`
    + (DT(s) ? `<p>${esc(DT(s))}</p>` : '') + (s.prompt ? `<blockquote>${esc(s.prompt)}</blockquote>` : '')
    + ((s.files || []).length ? `<div class="files">${s.files.map(f => `<span>${esc(f)}</span>`).join('')}</div>` : '')
    + (coachingBy[s.gid] || []).map(c => `<div class="coach"><b>${esc(c.focus)} coaching</b> · ${esc(c.observation)}<br>${esc(c.suggestion)}${c.rewrite ? `<code>${esc(c.rewrite)}</code>` : ''}</div>`).join('');
  if (reveal) $('map').scrollTo({left: Math.max(0, s.x * zoom - $('map').clientWidth / 2 + W * zoom / 2), top: Math.max(0, s.y * zoom - $('map').clientHeight / 2), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶ Replay the build'; }
function step(d) { stop(); show(cur + d, true); }
$('play').onclick = () => {
  if (timer) return stop();
  if (cur >= steps.length - 1) show(0, true);
  $('play').textContent = '❚❚ Pause';
  timer = setInterval(() => cur >= steps.length - 1 ? stop() : show(cur + 1, true), 1400);
};
$('prev').onclick = () => step(-1); $('next').onclick = () => step(1);
const pick = e => { const r = $('tl').getBoundingClientRect(), px = (e.clientX - r.left) / r.width * 100; let best = 0; steps.forEach(s => { if (Math.abs(s.px - px) < Math.abs(steps[best].px - px)) best = s.order; }); stop(); show(best, true); };
$('tl').addEventListener('pointerdown', e => { pick(e); $('tl').setPointerCapture(e.pointerId); });
$('tl').addEventListener('pointermove', e => { if (e.buttons) pick(e); });
$('map').addEventListener('click', e => { const g = e.target.closest('.node'); if (g) { stop(); show(+g.dataset.i, false); } });
$('map').addEventListener('keydown', e => { const g = e.target.closest('.node'); if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); stop(); show(+g.dataset.i, false); } });
document.addEventListener('keydown', e => { if (e.target.closest('input,select,textarea,.node')) return; if (e.key === ' ') { e.preventDefault(); $('play').click(); } else if (e.key === 'ArrowRight') step(1); else if (e.key === 'ArrowLeft') step(-1); });
$('tl').setAttribute('aria-valuemin', 1); $('tl').setAttribute('aria-valuemax', steps.length);
if (steps.length) show(0, false);

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
  `<div class="sess"><b>${esc(s.title || 'Session')}</b><div class="m">${esc(s.date || '')} · ${esc(s.agent || '')}${s.branch ? ' · ⎇ ' + esc(s.branch) : ''} · ${Math.round(s.duration_min || 0)}m · ${(s.stats||{}).prompts || 0} prompts${(s.languages||[]).length ? ' · ' + esc(s.languages.slice(0,4).join(', ')) : ''}</div>`
  + `<p>${esc(s.goal || '')}${s.outcome ? ' <br><small>→ ' + esc(s.outcome) + '</small>' : ''}</p></div>`).join('');
</script></body></html>
"""
