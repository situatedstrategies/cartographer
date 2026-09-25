"""Replay renderer: recaps -> one self-contained HTML page.

The page is the killer moment: press "Replay the build" and the map draws
itself step by step, across every session of a project. It also carries the
playbook (reusable prompts, patterns, time sinks, coaching) and a session
list. No external assets, works from file:// and in both themes.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

from . import store


def render_recaps(recaps: List[Dict[str, Any]], title: str, out: str) -> str:
    clean = []
    for r in recaps:
        r = dict(r)
        r.pop("_path", None)
        clean.append(r)
    payload = json.dumps({"title": title, "sessions": clean}, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out


def render_project(project: str, out: Optional[str] = None) -> str:
    entry = store.find_project(project)
    if not entry:
        raise LookupError("no project matching %r; run `cartographer projects`" % project)
    recaps = store.load_recaps(entry["slug"])
    if not recaps:
        raise LookupError("project %s has no wrapped sessions yet" % entry["name"])
    out = out or os.path.join(store.REPLAYS, "%s.html" % entry["slug"])
    return render_recaps(recaps, entry["name"], out)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Cartographer</title>
<style>
:root{
  --bg:#eef1ec; --panel:#f8faf6; --ink:#17211d; --muted:#56655e; --line:#c6d0c9; --grid:#dfe6e0;
  --accent:#1f6f78; --marker:#d9a21b;
  --k-prompt:#2d64a8; --k-decision:#6d4aa8; --k-question:#1f8a86; --k-dead_end:#b8392c;
  --k-fix:#2d7f45; --k-artifact:#a8741a; --k-pivot:#c65a24; --k-insight:#5a6a78;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#101614; --panel:#161e1b; --ink:#e1e9e4; --muted:#93a39b; --line:#2c3833; --grid:#1d2622;
  --accent:#5cb6c0; --marker:#e6b83d;
  --k-prompt:#74a6e6; --k-decision:#ad8ce6; --k-question:#4fc0ba; --k-dead_end:#ec6c5e;
  --k-fix:#62c381; --k-artifact:#e0ad55; --k-pivot:#f08b55; --k-insight:#9aabba;
  color-scheme:dark;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1320px;margin:0 auto;padding:28px 20px 60px}
.eyebrow{font:600 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
h1{font:700 clamp(30px,4.5vw,44px)/1.05 "Barlow Condensed","Arial Narrow",system-ui,sans-serif;text-transform:uppercase;letter-spacing:.03em;margin:8px 0 6px}
.sub{color:var(--muted);margin:0 0 6px}
.meta{display:flex;flex-wrap:wrap;gap:6px 10px;margin:8px 0 18px;font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.chip{border:1px solid var(--line);border-radius:999px;padding:2px 9px;background:var(--panel)}
.chip.agent{border-color:var(--accent);color:var(--accent)}
.stats{display:flex;flex-wrap:wrap;gap:10px 28px;margin:0 0 22px;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.stat b{display:block;font:600 22px/1.1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
.stat span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.stage{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px}
@media (max-width:900px){.stage{grid-template-columns:1fr}}
.map{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:auto;max-height:70vh}
.map svg{display:block}
.side{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;align-self:start;position:sticky;top:12px;display:grid;gap:8px}
.side .kind{font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase}
.side h3{margin:0;font:600 19px/1.25 Georgia,serif}
.side .when{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.side p{margin:0}
.side blockquote{margin:4px 0 0;padding:10px 12px;border-left:3px solid var(--k-prompt);background:var(--bg);font:13px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;border-radius:0 6px 6px 0;max-height:220px;overflow:auto}
.side .files{font:12px ui-monospace,Menlo,monospace;color:var(--muted);word-break:break-all}
.side .coach{border-top:1px dashed var(--line);padding-top:8px;font-size:13.5px}
.side .coach b{color:var(--accent)}
.controls{display:flex;align-items:center;gap:10px;margin:14px 0 0;flex-wrap:wrap}
button,select{font:600 13px/1 inherit;padding:9px 12px;border-radius:7px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.on{border-color:var(--accent);color:var(--accent)}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input[type=range]{flex:1;min-width:140px;accent-color:var(--accent)}
.count{font:12px ui-monospace,Menlo,monospace;color:var(--muted);min-width:64px;text-align:right}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:12px 0 0;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.node{cursor:pointer;transition:opacity .35s}
.node rect.box{fill:var(--panel);stroke-width:1.5}
.node.hidden{opacity:0;pointer-events:none}
.node.off{opacity:.15}
.node.current rect.box{stroke-width:3}
.node text{fill:var(--ink);font:12.5px/1 ui-sans-serif,-apple-system,sans-serif}
.node .k{font:600 9.5px ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase}
.node .b{font:9.5px ui-monospace,Menlo,monospace;fill:var(--muted)}
.edge{fill:none;transition:opacity .35s}
.edge.hidden{opacity:0}
.colhead{font:600 11px ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;fill:var(--muted)}
.colbranch{font:10px ui-monospace,Menlo,monospace;fill:var(--accent)}
.colsess{font:600 12px Georgia,serif;fill:var(--accent)}
.playbook{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:30px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px}
.card.wide{grid-column:1/-1}
.card h2{font:600 13px ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:0 0 12px}
.card ul{margin:0;padding-left:18px}.card li{margin:0 0 10px}
.card code{display:block;font:12.5px/1.45 ui-monospace,Menlo,monospace;background:var(--bg);padding:8px 10px;border-radius:6px;margin:4px 0 2px;white-space:pre-wrap}
.card small{color:var(--muted)}
.card .tag{font:600 10px ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-right:6px}
.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.numbers div{background:var(--bg);border-radius:6px;padding:8px 10px}
.numbers b{display:block;font:600 20px/1.1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
.numbers span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.sessions{margin-top:30px}
.sessions h2{font:600 13px ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.sess{border-top:1px solid var(--line);padding:14px 0;display:grid;gap:4px}
.sess b{font:600 17px Georgia,serif}
.sess .m{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.sess p{margin:0}
footer{margin-top:40px;font-size:12px;color:var(--muted)}
@media (prefers-reduced-motion:reduce){.node,.edge{transition:none}}
</style></head>
<body><div class="wrap">
<header>
  <div class="eyebrow">Cartographer · replay</div>
  <h1 id="title"></h1>
  <p class="sub" id="subtitle"></p>
  <div class="meta" id="meta"></div>
</header>
<div class="stats" id="stats"></div>
<div class="stage">
  <div>
    <div class="map" id="map"></div>
    <div class="controls">
      <button class="primary" id="play">▶ Replay the build</button>
      <button id="prev" aria-label="Previous step">◀</button>
      <button id="next" aria-label="Next step">▶</button>
      <input type="range" id="scrub" min="0" value="0" aria-label="Timeline">
      <span class="count" id="count"></span>
      <select id="branch" aria-label="Branch filter" hidden></select>
      <button id="voice" hidden>Plain words</button>
    </div>
    <div class="legend" id="legend"></div>
  </div>
  <aside class="side" id="side"></aside>
</div>
<section class="playbook" id="playbook"></section>
<section class="sessions" id="sessions"></section>
<footer>Generated by Cartographer · <code>/wrap</code> maps a session, <code>/replay</code> replays a project.</footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const KINDS = {prompt:'Prompt',decision:'Decision',question:'Question',dead_end:'Dead end',fix:'Fix',artifact:'Artifact',pivot:'Pivot',insight:'Insight'};
const REL = {led_to:'var(--muted)', blocked_by:'var(--k-dead_end)', reverted:'var(--k-pivot)', reused:'var(--k-fix)', answered:'var(--k-question)'};
const col = k => `var(--k-${KINDS[k] ? k : 'insight'})`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $ = id => document.getElementById(id);
let voice = 'technical';
const T = s => (voice === 'plain' && s.plain && s.plain.title) ? s.plain.title : s.title;
const DT = s => (voice === 'plain' && s.plain && s.plain.detail) ? s.plain.detail : (s.detail || '');

// Flatten sessions -> ordered steps with globally unique ids and phase columns.
const steps = [], columns = [], coachingBy = {};
D.sessions.forEach((s, si) => {
  const phases = (s.phases && s.phases.length) ? s.phases : [{name:'Session'}];
  const colIndex = {};
  phases.forEach((p, pi) => { colIndex[p.name] = columns.length; columns.push({session: si, phase: p, first: pi === 0, label: s.title || `Session ${si+1}`, agent: s.agent}); });
  const fallback = columns.length - phases.length;
  (s.steps || []).forEach(st => {
    steps.push({...st, gid: `${si}:${st.id}`, session: si, col: colIndex[st.phase] ?? fallback,
      branch: st.branch || (phases.find(p => p.name === st.phase) || {}).branch || s.branch || '',
      links: (st.links || []).map(l => ({...l, to: String(l.to).includes(':') ? l.to : `${si}:${l.to}`}))});
  });
  (s.coaching || []).forEach(c => { if (c.step) (coachingBy[`${si}:${c.step}`] = coachingBy[`${si}:${c.step}`] || []).push(c); });
});
steps.sort((a, b) => a.session - b.session || (a.t ?? 0) - (b.t ?? 0));
steps.forEach((s, i) => s.order = i);
const branches = [...new Set(steps.map(s => s.branch).filter(Boolean))];
const multiBranch = branches.length > 1;
const hasPlain = steps.some(s => s.plain && s.plain.title);

// Layout: phases left->right, steps stacked in order within their column.
const W = 214, H = 60, GX = 46, GY = 16, TOP = 70, LEFT = 20;
const perCol = columns.map(() => 0);
steps.forEach(s => { s.x = LEFT + s.col * (W + GX); s.y = TOP + perCol[s.col]++ * (H + GY); });
const width = LEFT * 2 + columns.length * (W + GX) - GX;
const height = TOP + Math.max(1, ...perCol) * (H + GY) + 20;
const byId = Object.fromEntries(steps.map(s => [s.gid, s]));
const edges = [];
steps.forEach((s, i) => { const n = steps[i+1]; if (n && n.session === s.session) edges.push({from: s, to: n, rel: 'seq'}); });
steps.forEach(s => s.links.forEach(l => byId[l.to] && edges.push({from: s, to: byId[l.to], rel: l.rel in REL ? l.rel : 'led_to'})));
edges.forEach((e, i) => e.el = 'e' + i);

function wrapText(t, n) { const words = String(t || '').split(/\s+/), lines = ['']; for (const w of words) { if ((lines.at(-1) + ' ' + w).trim().length > n) { if (lines.length === 2) { lines[1] = lines[1].replace(/\s*\S*$/, '') + '…'; break; } lines.push(w); } else lines[lines.length-1] = (lines.at(-1) + ' ' + w).trim(); } return lines; }

function renderMap() {
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  svg += `<defs>${Object.entries(REL).map(([k,c]) => `<marker id="m-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="${c}"/></marker>`).join('')}</defs>`;
  columns.forEach((c, i) => {
    const x = LEFT + i * (W + GX);
    if (c.first) svg += `<text class="colsess" x="${x}" y="20">${esc(c.label.length > 30 ? c.label.slice(0,29)+'…' : c.label)}${D.sessions.length > 1 && c.agent ? ` · ${esc(c.agent)}` : ''}</text>`;
    svg += `<text class="colhead" x="${x}" y="44">${esc(c.phase.name)}</text>`;
    if (multiBranch && c.phase.branch) svg += `<text class="colbranch" x="${x}" y="57">⎇ ${esc(c.phase.branch)}</text>`;
    svg += `<line x1="${x}" x2="${x+W}" y1="61" y2="61" stroke="var(--line)"/>`;
  });
  edges.forEach(e => {
    const a = e.from, b = e.to, seq = e.rel === 'seq';
    const x1 = a.x + (b.col > a.col ? W : b.col < a.col ? 0 : W), y1 = a.y + H/2;
    const x2 = b.x + (b.col > a.col ? 0 : b.col < a.col ? W : W), y2 = b.y + H/2;
    const bend = a.col === b.col ? 40 : Math.abs(x2 - x1) / 2;
    const d = a.col === b.col ? `M${x1},${y1} C${x1+bend},${y1} ${x2+bend},${y2} ${x2},${y2}` : `M${x1},${y1} C${x1+Math.sign(x2-x1)*bend},${y1} ${x2-Math.sign(x2-x1)*bend},${y2} ${x2},${y2}`;
    svg += seq ? `<path id="${e.el}" class="edge" d="${d}" stroke="var(--line)" stroke-width="1.2" stroke-dasharray="3 4"/>`
               : `<path id="${e.el}" class="edge" d="${d}" stroke="${REL[e.rel]}" stroke-width="1.8" marker-end="url(#m-${e.rel})"/>`;
  });
  steps.forEach(s => {
    const lines = wrapText(T(s), 30);
    const head = `${KINDS[s.kind] || s.kind}${s.t != null ? ` · ${Math.round(s.t)}m` : ''}`;
    svg += `<g class="node" id="n${s.order}" data-i="${s.order}" tabindex="0"><rect class="box" x="${s.x}" y="${s.y}" width="${W}" height="${H}" rx="8" stroke="${col(s.kind)}"/>`
        + `<rect x="${s.x}" y="${s.y}" width="5" height="${H}" rx="2" fill="${col(s.kind)}" stroke="none"/>`
        + `<text class="k" x="${s.x+14}" y="${s.y+16}" style="fill:${col(s.kind)}">${esc(head)}</text>`
        + (multiBranch && s.branch ? `<text class="b" x="${s.x+W-8}" y="${s.y+16}" text-anchor="end">⎇ ${esc(s.branch.length > 16 ? s.branch.slice(0,15)+'…' : s.branch)}</text>` : '')
        + lines.map((l, j) => `<text x="${s.x+14}" y="${s.y+35+j*15}">${esc(l)}</text>`).join('') + `</g>`;
  });
  $('map').innerHTML = svg + '</svg>';
}
renderMap();

// Header, meta, stats
const last = D.sessions.at(-1) || {};
const proj = last.project || {};
$('title').textContent = D.title;
const totalMin = D.sessions.reduce((n, s) => n + (s.duration_min || 0), 0);
const sum = k => D.sessions.reduce((n, s) => n + ((s.stats || {})[k] || 0), 0);
$('subtitle').textContent = D.sessions.length > 1
  ? `${D.sessions.length} sessions · ${[D.sessions[0].date, last.date].filter(Boolean).join(' → ')}`
  : (last.goal || last.date || '');
const agents = [...new Set(D.sessions.map(s => s.agent).filter(Boolean))];
const langs = [...new Set(D.sessions.flatMap(s => s.languages || []))].slice(0, 8);
$('meta').innerHTML = [proj.id ? `<span class="chip">${esc(proj.id)}</span>` : '', ...agents.map(a => `<span class="chip agent">${esc(a)}</span>`),
  ...branches.map(b => `<span class="chip">⎇ ${esc(b)}</span>`), ...langs.map(l => `<span class="chip">${esc(l)}</span>`)].join('');
$('stats').innerHTML = [
  [D.sessions.length, 'sessions'], [totalMin >= 90 ? (totalMin/60).toFixed(1)+'h' : Math.round(totalMin)+'m', 'time'],
  [sum('prompts'), 'prompts'], [steps.filter(s => s.kind === 'decision').length, 'decisions'],
  [steps.filter(s => s.kind === 'dead_end').length, 'dead ends'], [sum('errors'), 'errors'], [sum('files_touched'), 'files changed'],
].map(([v, l]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join('');
$('legend').innerHTML = Object.entries(KINDS).filter(([k]) => steps.some(s => s.kind === k))
  .map(([k, l]) => `<span><i style="background:${col(k)}"></i>${l}</span>`).join('')
  + `<span><i style="background:var(--k-dead_end)"></i>→ blocked by</span><span><i style="background:var(--k-pivot)"></i>→ reverted</span><span><i style="background:var(--k-fix)"></i>→ reused</span><span><i style="background:var(--k-question)"></i>→ answered</span>`;

// Branch filter + voice toggle
let branchFilter = '';
if (multiBranch) { const sel = $('branch'); sel.hidden = false; sel.innerHTML = `<option value="">All branches</option>` + branches.map(b => `<option value="${esc(b)}">⎇ ${esc(b)}</option>`).join(''); sel.onchange = () => { branchFilter = sel.value; show(cur, false); }; }
if (hasPlain) { const b = $('voice'); b.hidden = false; b.onclick = () => { voice = voice === 'plain' ? 'technical' : 'plain'; b.textContent = voice === 'plain' ? 'Technical words' : 'Plain words'; b.classList.toggle('on', voice === 'plain'); renderMap(); show(cur, false); renderPlaybook(); }; }

// Replay engine
let cur = 0, timer = null;
const scrub = $('scrub'); scrub.max = Math.max(0, steps.length - 1);
function show(i, reveal) {
  cur = Math.max(0, Math.min(steps.length - 1, i)); scrub.value = cur;
  steps.forEach(s => { const el = $('n' + s.order); if (!el) return; el.classList.toggle('hidden', reveal && s.order > cur); el.classList.toggle('current', s.order === cur); el.classList.toggle('off', !!branchFilter && s.branch !== branchFilter); });
  edges.forEach(e => { const el = $(e.el); if (el) el.classList.toggle('hidden', reveal && (e.from.order > cur || e.to.order > cur)); });
  const s = steps[cur]; if (!s) return;
  $('count').textContent = `${cur + 1} / ${steps.length}`;
  const sess = D.sessions[s.session] || {};
  const coach = coachingBy[s.gid] || [];
  $('side').innerHTML = `<div class="kind" style="color:${col(s.kind)}">${esc(KINDS[s.kind] || s.kind)}</div><h3>${esc(T(s))}</h3>`
    + `<div class="when">${esc(sess.title || '')}${s.t != null ? ' · minute ' + Math.round(s.t) : ''}${s.phase ? ' · ' + esc(s.phase) : ''}${s.branch ? ' · ⎇ ' + esc(s.branch) : ''}</div>`
    + (DT(s) ? `<p>${esc(DT(s))}</p>` : '') + (s.prompt ? `<blockquote>${esc(s.prompt)}</blockquote>` : '')
    + ((s.files || []).length ? `<div class="files">${(s.files || []).map(esc).join('<br>')}</div>` : '')
    + coach.map(c => `<div class="coach"><b>${esc(c.focus)} coaching</b> · ${esc(c.observation)}<br>${esc(c.suggestion)}${c.rewrite ? `<code style="display:block;white-space:pre-wrap;margin-top:6px;font-size:12px">${esc(c.rewrite)}</code>` : ''}</div>`).join('');
  const map = $('map');
  if (reveal) map.scrollTo({left: Math.max(0, s.x - map.clientWidth / 2 + W / 2), top: Math.max(0, s.y - map.clientHeight / 2), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶ Replay the build'; }
$('play').onclick = () => {
  if (timer) return stop();
  if (cur >= steps.length - 1) show(0, true);
  $('play').textContent = '❚❚ Pause';
  timer = setInterval(() => { if (cur >= steps.length - 1) return stop(); show(cur + 1, true); }, 1400);
};
$('prev').onclick = () => { stop(); show(cur - 1, true); };
$('next').onclick = () => { stop(); show(cur + 1, true); };
scrub.oninput = () => { stop(); show(+scrub.value, true); };
$('map').addEventListener('click', e => { const g = e.target.closest('.node'); if (g) { stop(); show(+g.dataset.i, false); } });
$('map').addEventListener('keydown', e => { const g = e.target.closest('.node'); if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); stop(); show(+g.dataset.i, false); } });
if (steps.length) show(0, false);

// Playbook (merged across sessions)
function renderPlaybook() {
  const all = k => D.sessions.flatMap(s => s[k] || []);
  const cards = [];
  const coaching = all('coaching');
  if (coaching.length) cards.push(['Coaching', `<ul>${coaching.map(c => `<li><span class="tag">${esc(c.focus)}</span>${esc(c.observation)}<br><small>${esc(c.suggestion)}</small>${c.rewrite ? `<code>${esc(c.rewrite)}</code>` : ''}</li>`).join('')}</ul>`, true]);
  const prompts = all('reusable_prompts');
  if (prompts.length) cards.push(['Prompts worth reusing', `<ul>${prompts.map(p => `<li>${p.language ? `<span class="tag">${esc(p.language)}</span>` : ''}<code>${esc(p.prompt)}</code><small>${esc(p.why || '')}</small></li>`).join('')}</ul>`]);
  const pats = all('patterns');
  if (pats.length) cards.push(['How you build', `<ul>${pats.map(p => `<li>${esc(p)}</li>`).join('')}</ul>`]);
  const sinks = all('time_sinks');
  if (sinks.length) cards.push(['Where time went', `<ul>${sinks.map(t => `<li><b>${esc(t.minutes ?? '?')}m</b> · ${esc(t.what)}</li>`).join('')}</ul>`]);
  const profs = D.sessions.map(s => s.prompting).filter(p => p && p.prompts);
  if (profs.length) {
    const n = profs.reduce((a, p) => a + p.prompts, 0);
    const wavg = k => (profs.reduce((a, p) => a + (p[k] || 0) * p.prompts, 0) / n);
    cards.push(['Prompting profile', `<div class="numbers"><div><b>${n}</b><span>prompts</span></div><div><b>${wavg('avg_words').toFixed(0)}</b><span>avg words</span></div><div><b>${wavg('avg_specificity').toFixed(1)}/3</b><span>specificity</span></div><div><b>${Math.round(100*wavg('anchored_ratio'))}%</b><span>anchored</span></div><div><b>${Math.round(100*wavg('vague_ratio'))}%</b><span>vague</span></div><div><b>${Math.round(100*wavg('delegation_ratio'))}%</b><span>delegating</span></div><div><b>${Math.round(100*wavg('acceptance_ratio'))}%</b><span>with done-condition</span></div></div>`]);
  }
  const next = last.next_steps || [];
  if (next.length) cards.push(['Next time', `<ul>${next.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`]);
  $('playbook').innerHTML = cards.map(([h, b, wide]) => `<div class="card${wide ? ' wide' : ''}"><h2>${h}</h2>${b}</div>`).join('');
}
renderPlaybook();

$('sessions').innerHTML = `<h2>Sessions</h2>` + D.sessions.map(s =>
  `<div class="sess"><b>${esc(s.title || 'Session')}</b><div class="m">${esc(s.date || '')} · ${esc(s.agent || '')}${s.branch ? ' · ⎇ ' + esc(s.branch) : ''} · ${Math.round(s.duration_min || 0)}m · ${(s.stats||{}).prompts || 0} prompts${(s.languages||[]).length ? ' · ' + esc((s.languages||[]).slice(0,4).join(', ')) : ''}</div>`
  + `<p>${esc(s.goal || '')}${s.outcome ? ' <br><small>→ ' + esc(s.outcome) + '</small>' : ''}</p></div>`).join('');
</script></body></html>
"""
