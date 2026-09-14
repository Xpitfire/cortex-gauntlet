"""Track P (project) report — the full multi-signal vector per harness + reference screenshots."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .report_common import inject_common

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Gauntlet P — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__
  .shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:8px}
  .shots img{width:100%;border-radius:10px;border:1px solid var(--line)}
  .shots figcaption{font-size:12px;color:var(--muted);margin-top:4px}
  .shot-missing{font-size:12px;color:var(--muted);border:1px dashed var(--line);border-radius:10px;
    padding:20px 10px;text-align:center;background:rgba(127,127,127,.06)}
</style>
</head>
<body>
__NAVBAR__
<div class="wrap">
  <header class="hero">
    <div><h1>Gauntlet — Track P (full-repo project build)</h1>
      <div class="sub" id="runmeta"></div>
      <div style="margin-top:10px"><span class="attest" id="attest"></span></div>
    </div>
    <div class="tools"><button class="tool" onclick="downloadCsv()">⤓ CSV</button>
      <button class="tool" onclick="window.print()">⎙ PDF / Print</button></div>
  </header>
  <div class="cards" id="cards"></div>
  <details class="settings"><summary>Models &amp; settings — click to expand</summary><div class="body" id="settingsBody"></div></details>

  <section class="block">
    <h2><span class="chip" style="background:#6d5efb"></span>Signal vector by harness</h2>
    <div class="hint">Separate objective, similarity and judge signals; the saved composite is one dimension, not a new sum of these bars</div>
    <div class="chart" id="c_signals" style="height:340px"></div>
  </section>

  <div class="grid2">
    <section class="block"><h2><span class="chip" style="background:#16a34a"></span>Composite by harness</h2>
      <div class="hint">build-gated weighted sum of all signals</div><div class="chart" id="c_comp"></div></section>
    <section class="block"><h2><span class="chip" style="background:#0aa5a5"></span>VERTEX trajectory similarity</h2>
      <div class="hint">capability + architecture cross-similarity vs the hidden reference (baseline-normalized)</div>
      <div class="chart" id="c_vertex"></div></section>
  </div>

  <section class="block">
    <h2><span class="chip" style="background:#6d5efb"></span>Build prompt (what the harness receives)</h2>
    <pre id="briefprompt" style="white-space:pre-wrap;font-size:13px;color:var(--muted);background:var(--card,#0000);
      border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:8px;overflow:auto;max-height:360px"></pre>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#d97757"></span>Reference frames (visual target)</h2>
    <div class="hint">Reference frames requested by the brief. Unavailable retained image files are marked below.</div>
    <div class="shots" id="refshots"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0aa5a5"></span>Captured app renders (per harness)</h2>
    <div class="hint">Retained app captures per harness. Images are evidence to inspect, not a visual ranking.</div>
    <div id="appshots"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0f1222"></span>Build explorer</h2>
    <div class="hint">Per harness: the full signal vector + the captured repo.</div>
    <table><thead><tr><th>Harness</th><th>Build</th><th>Functional</th><th>VERTEX</th><th>Visual</th>
      <th>Code/Arch</th><th>Security</th><th>PWA/a11y</th><th>Robust</th><th>Composite</th><th></th></tr></thead>
      <tbody id="rows"></tbody></table>
  </section>
  <footer id="method"></footer>
</div>
__MODAL__
<script id="data" type="application/json">__RUN_JSON__</script>
<script>
const RUN = JSON.parse(document.getElementById('data').textContent);
const BUNDLED_IMAGES = new Set(__BUNDLED_IMAGES_JSON__);
buildSettings(RUN);
const H={}; RUN.harnesses.forEach(h=>H[h.id]=h);
const colorOf=id=>harnessColor(H[id].family);  // theme-aware (shared with every report)
const pct=v=>v==null?'n/a':(v*100).toFixed(0)+'%';
const labelOf=id=>H[id].label;
// pass^k reliability (τ-bench style): only meaningful with multiple seeds
const relRow=r=>(r&&r.k&&r.k.length>1)?`<div class="row"><span>reliability pass^${r.k[r.k.length-1]}</span><b>${pct(r.pass_hat_k[r.pass_hat_k.length-1])}</b></div>`:'';
const ph=RUN.aggregates.per_harness;
const cardComparison=metricComparison(RUN.harnesses.map(h=>h.id),id=>ph[id]?.composite),ids=cardComparison.rows;
const brief=RUN.cases[0]||{};
const inkLabel=harnessInk;
// rotate + truncate long harness names so they never overlap on the x-axis
function catAxis(labels){return {type:'category',data:labels,axisLine:{lineStyle:{color:gridInk()}},
  axisLabel:{interval:0,rotate:22,hideOverlap:true,width:90,overflow:'truncate',color:axisInk(),fontSize:11}};}
const pctAxis=()=>({type:'value',max:1,axisLabel:{formatter:v=>(v*100)+'%',color:axisInk()},splitLine:{lineStyle:{type:'dashed',color:gridInk()}}});
function chartOn(el){const dom=document.getElementById(el);return echarts.getInstanceByDom(dom)||echarts.init(dom);}

document.getElementById('runmeta').textContent =
  `run ${RUN.run_id} · ${RUN.created_at} · 1 brief × ${RUN.harnesses.length} harnesses · seeds ${RUN.config.seeds} · judge ${RUN.methodology.judge_model} · basis ${RUN.config.basis||'—'}`;
document.getElementById('attest').textContent = `containment: ${RUN.containment.mode} · payloads executed = ${RUN.containment.payloads_executed}`;

const cards=document.getElementById('cards');
function card(t,c,h,b){const d=document.createElement('div');d.className='card';
  d.innerHTML=`<h3><span class="chip" style="background:${c}"></span>${t}</h3><div class="hint">${h}</div>${b}`;cards.appendChild(d);return d;}
RUN.harnesses.forEach(h=>{const s=ph[h.id]||{}; const g=gradeFor(s.composite);
  card(labelOf(h.id), colorOf(h.id), `${h.model} · composite`,
    `<div class="metric" style="color:${colorOf(h.id)}">${pct(s.composite)} <span class="badge g-${g}" style="font-size:14px;vertical-align:middle">${g}</span></div>`+
    `<div class="row"><span>build</span><b>${s.build==null?'n/a':s.build? '✓':'✗'}</b></div>`+
    `<div class="row"><span>functional</span><b>${pct(s.functional)}</b></div>`+
    relRow(s.reliability)+
    `<div class="row"><span>VERTEX</span><b>${pct(s.vertex)}</b></div>`+
    `<div class="row"><span>visual</span><b>${pct(s.visual)}</b></div>`).dataset.harness=h.id;});
const d=RUN.aggregates.synapse_delta;
if(d && d.composite){card('Cortex vs raw comparison','#6d5efb',`${H[d.synapse].label} vs ${H[d.raw].label} · positive = improvement · ${d.basis||RUN.config.basis||''}`,
  `<div class="metric" style="color:${deltaColor(d.composite.delta)}">${deltaText(d.composite.delta)}</div>`+
  `<div class="row"><span>composite change</span><b style="color:${deltaColor(d.composite.delta)}">${deltaText(d.composite.delta)}</b></div>`+
  `<div class="row"><span>functional change</span><b style="color:${deltaColor(d.functional?.delta)}">${deltaText(d.functional?.delta)}</b></div>`+
  `<div class="row"><span>VERTEX change</span><b style="color:${deltaColor(d.vertex?.delta)}">${deltaText(d.vertex?.delta)}</b></div>`);}

// signal vector grouped bars
const SIGS=[['functional','functional'],['vertex','VERTEX'],['pwa_a11y','PWA/a11y'],['visual','visual'],['code_arch','code/arch'],['security','security'],['robustness','robust'],['composite','composite']];
function bar(el,key){
  const comparison=metricComparison(ids,id=>ph[id]?.[key]),ordered=comparison.rows;
  scalarCue(el,comparison,labelOf,pct);
  chartOn(el).setOption({
    grid:{left:48,right:16,top:20,bottom:64},tooltip:{trigger:'item',formatter:p=>`${p.name}<br/><b>${pct(p.value)}</b>`},
    xAxis:catAxis(ordered.map(labelOf)),yAxis:pctAxis(),
    series:[{type:'bar',barWidth:'46%',label:{show:true,position:'top',formatter:p=>pct(p.value),color:inkLabel(),fontWeight:600},
      data:ordered.map(id=>({value:ph[id]?.[key]??null,itemStyle:{color:comparisonColor(comparison,id),borderRadius:[6,6,0,0]}}))}]},true);
}
function renderCharts(){
  rankCards(cardComparison,labelOf,pct,'Build composite');
  comparisonCue('c_signals','higher','Taller means a higher recorded score within that dimension.','Colors identify harnesses; the dimensions are not interchangeable and are not a new pooled ranking.');
  chartOn('c_signals').setOption({
    grid:{left:48,right:16,top:52,bottom:64}, tooltip:{trigger:'axis',valueFormatter:v=>pct(v)},
    legend:{top:6,textStyle:{fontSize:11,color:harnessInk()}}, xAxis:catAxis(SIGS.map(s=>s[1])), yAxis:pctAxis(),
    series:ids.map(id=>({name:labelOf(id),type:'bar',itemStyle:{color:colorOf(id),borderRadius:[3,3,0,0]},
      data:SIGS.map(s=>ph[id]?.[s[0]]??null)}))}, true);
  bar('c_comp','composite'); bar('c_vertex','vertex');
}
renderCharts();
window.__charts=renderCharts;  // toggleTheme() re-runs this so bars/labels recolor for the new theme
window.addEventListener('resize',()=>document.querySelectorAll('.chart').forEach(e=>echarts.getInstanceByDom(e)&&echarts.getInstanceByDom(e).resize()));

// the build prompt the harness receives (BRIEF.md)
const bp=document.getElementById('briefprompt'); if(bp) bp.textContent=brief.prompt||'(no prompt recorded)';
// Availability belongs to the generated artifact, not to the historical measurement record.
function appendShot(parent,path,name) {
  const fig=document.createElement('figure');
  if(BUNDLED_IMAGES.has(path)) {
    const img=document.createElement('img');img.src=path;img.alt=name;img.loading='lazy';fig.appendChild(img);
  } else {
    const missing=document.createElement('div');missing.className='shot-missing';
    missing.textContent='Image unavailable in retained artifacts';fig.appendChild(missing);
  }
  const caption=document.createElement('figcaption');caption.textContent=name;fig.appendChild(caption);
  parent.appendChild(fig);
}
const rs=document.getElementById('refshots');
(brief.screenshots||[]).forEach(s=>appendShot(rs,s,s.split('/').pop()));
if(RUN.publication?.evidence_redacted)rs.textContent='Reference media withheld from this public evidence view.';

// captured per-harness app renders — real sandbox Playwright PNGs (absent for unbuilt/unserved/mock arms)
const as=document.getElementById('appshots');
comparisonCue('appshots','neutral','Harness groups follow the build-composite card order.','Screenshots do not establish a separate winner; retained provenance and missing media remain explicit.');
[...RUN.results].sort((a,b)=>ids.indexOf(a.harness_id)-ids.indexOf(b.harness_id)).forEach(r=>{const shots=r.screenshots||{};const screens=Object.keys(shots);if(!screens.length)return;
  const wrap=document.createElement('div');wrap.style.marginBottom='16px';
  wrap.innerHTML=`<div style="font-weight:600;margin:6px 0;color:${colorOf(r.harness_id)}">${labelOf(r.harness_id)}</div>`;
  const grid=document.createElement('div');grid.className='shots';
  screens.forEach(name=>appendShot(grid,shots[name],name));
  wrap.appendChild(grid);as.appendChild(wrap);});
if(!as.children.length){as.innerHTML='<div class="hint">'+(RUN.publication?.evidence_redacted
  ? 'Captured app media withheld from this public evidence view.'
  : 'No app renders captured (mock run, or no arm served in the sandbox).')+'</div>';}

// explorer
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
const body=document.getElementById('rows');
RUN.results.forEach((r,i)=>{const s=r.signals; const tr=document.createElement('tr'); tr.className='case';
  tr.innerHTML=`<td>${labelOf(r.harness_id)}</td><td>${s.build?'✓':'✗'}</td><td>${pct(s.functional)}</td>`+
    `<td>${pct(s.vertex)}</td><td>${pct(s.visual)}</td><td>${pct(s.code_arch)}</td><td>${pct(s.security)}</td><td>${pct(s.pwa_a11y)}</td>`+
    `<td>${pct(s.robustness)}</td><td><b>${pct(s.composite)}</b></td>`+
    `<td>${Object.keys(r.files||{}).length?`<button class="codebtn" onclick="openCode('${labelOf(r.harness_id)}', RUN.results[${i}].files||{})">⟨⟩ files</button>`:''}</td>`;
  body.appendChild(tr);});

function downloadCsv(){const head=['harness','build','functional','vertex','pwa_a11y','visual','code_arch','security','robustness','code_health','ux','composite'];
  const lines=[head.join(',')]; RUN.results.forEach(r=>{const s=r.signals;
    lines.push([r.harness_id,s.build,s.functional,s.vertex,s.pwa_a11y,s.visual,s.code_arch,s.security,s.robustness,s.code_health,s.ux,s.composite].join(','));});
  const blob=new Blob([lines.join('\n')],{type:'text/csv'}); const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download=RUN.run_id+'.csv'; a.click();}
const m=RUN.methodology;
document.getElementById('method').innerHTML=`Methodology — ${m.signals}<br/>VERTEX: ${m.vertex}<br/>Synapse: ${m.synapse} ${m.note}<br/>`+
  `Generated __GENERATED__ · schema ${RUN.schema_version}. Composite is build-gated; judges are gated by + cross-checked against objective signals.`;
__COMMON_JS__
</script>
</body></html>
"""


def build_project_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    run_json = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    root = out_path.parent.resolve()
    references = {image for case in record.get("cases", []) for image in case.get("screenshots", [])}
    references.update(image for result in record.get("results", [])
                      for image in result.get("screenshots", {}).values())
    bundled = []
    for image in sorted(references):
        if Path(image).is_absolute() or "\\" in image:
            continue
        path = (root / image).resolve()
        if path.is_relative_to(root) and path.is_file():
            bundled.append(image)
    bundled_json = json.dumps(bundled, ensure_ascii=False).replace("</", "<\\/")
    html = (
        inject_common(_TEMPLATE, "Project", links=links)
        .replace("__BUNDLED_IMAGES_JSON__", bundled_json).replace("__RUN_JSON__", run_json)
        .replace("__TITLE__", str(record.get("run_id", "run")))
        .replace("__GENERATED__", datetime.now().isoformat(timespec="seconds"))
    )
    return html
