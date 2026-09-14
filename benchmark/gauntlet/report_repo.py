"""Track R (repository issue-resolution) report — per-harness resolution rate + per-task resolution grid."""

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
<title>Gauntlet Bugfix — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__
  td.ok{color:#16a34a;font-weight:700} td.no{color:#e5484d;font-weight:700} td.err{color:#d97706;font-weight:700}
</style>
</head>
<body>
__NAVBAR__
<div class="wrap">
  <header class="hero">
    <div><h1>Gauntlet — Bugfix Track (issue resolution)</h1>
      <div class="hint" style="margin-top:4px">SWE-bench-Pro-style graded scoring: each arm fixes a buggy
        repo from the issue. <b>Resolved</b> = the shown hidden test passes (FAIL_TO_PASS). <b>Strict</b>
        also requires held-out anti-overfit tests + PASS_TO_PASS regression tests (the arm never sees
        them) with no test-file edits. The <b>composite</b> [0–100] grades robustness, regression,
        patch minimality/locality and code health — so two arms that both "resolve" still separate.</div>
      <div class="sub" id="runmeta"></div>
      <div style="margin-top:10px"><span class="attest" id="attest"></span></div>
    </div>
    <div class="tools"><button class="tool" onclick="downloadCsv()">⤓ CSV</button>
      <button class="tool" onclick="window.print()">⎙ PDF / Print</button></div>
  </header>
  <div class="cards" id="cards"></div>
  <details class="settings"><summary>Models &amp; settings — click to expand</summary><div class="body" id="settingsBody"></div></details>

  <section class="block">
    <h2><span class="chip" style="background:#0ea5e9"></span>Patch-quality composite by harness</h2>
    <div class="hint">Graded quality-of-fix [0–100]: robustness (held-out) 40% · regression 25% · minimality 15% · locality 10% · code health 10%, gated on resolution (blended 80/20 with the semantic patch judge when one is configured — the live default)</div>
    <div class="chart" id="c_comp" style="height:340px"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0ea5e9"></span>Resolution: shown vs strict (held-out + regression)</h2>
    <div class="hint">Lenient = shown hidden test passes. Strict = held-out anti-overfit + PASS_TO_PASS regression also pass (no test edits). A gap = overfit/regressing patches.</div>
    <div class="chart" id="c_res" style="height:340px"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0f1222"></span>Resolution explorer</h2>
    <div class="hint">Per issue × harness: composite, strict resolution, held-out (anti-overfit) + regression pass counts, patch minimality, and the patched files.</div>
    <table><thead><tr><th>Issue</th><th>Harness</th><th>Composite</th><th>Strict</th><th>Hidden</th><th>Held-out</th><th>Regression</th><th>Minimality</th><th>Backend</th><th></th></tr></thead>
      <tbody id="rows"></tbody></table>
  </section>
  <footer id="method"></footer>
</div>
__MODAL__
<script id="data" type="application/json">__RUN_JSON__</script>
<script>
const RUN = JSON.parse(document.getElementById('data').textContent);
buildSettings(RUN);
const H={}; RUN.harnesses.forEach(h=>H[h.id]=h);
const colorOf=id=>harnessColor(H[id].family);
const pct=v=>v==null?'unavailable':(v*100).toFixed(0)+'%';
const labelOf=id=>H[id].label;
const ph=RUN.aggregates.per_harness;
const cardComparison=metricComparison(RUN.harnesses.map(h=>h.id),id=>ph[id]?.resolution_rate),ids=cardComparison.rows;
const titleById={}; RUN.cases.forEach(c=>titleById[c.id]=c.title||c.id);
const promptById={}; RUN.cases.forEach(c=>promptById[c.id]=c.problem_statement||'');
function showIssue(id){openCode((titleById[id]||id)+' · issue prompt', {'issue.md': promptById[id]||'(no prompt recorded)'});}
// rotate + truncate long harness names so they never overlap on the x-axis
function catAxis(labels){return {type:'category',data:labels,axisLine:{lineStyle:{color:gridInk()}},
  axisLabel:{interval:0,rotate:22,hideOverlap:true,width:90,overflow:'truncate',color:axisInk(),fontSize:11}};}
const pctAxis=()=>({type:'value',max:1,axisLabel:{formatter:v=>(v*100)+'%',color:axisInk()},splitLine:{lineStyle:{type:'dashed',color:gridInk()}}});
function chartOn(el){const dom=document.getElementById(el);return echarts.getInstanceByDom(dom)||echarts.init(dom);}

document.getElementById('runmeta').textContent =
  `run ${RUN.run_id} · ${RUN.created_at} · ${RUN.cases.length} issues × ${RUN.harnesses.length} harnesses · basis ${RUN.config.basis||'—'}`;
document.getElementById('attest').textContent = `containment: ${RUN.containment.mode} · payloads executed = ${RUN.containment.payloads_executed}`;

const cards=document.getElementById('cards');
function card(t,c,h,b){const d=document.createElement('div');d.className='card';
  d.innerHTML=`<h3><span class="chip" style="background:${c}"></span>${t}</h3><div class="hint">${h}</div>${b}`;cards.appendChild(d);return d;}
RUN.harnesses.forEach(h=>{const m=ph[h.id];
  const tiers=m.by_difficulty||{};
  const tierRow=Object.keys(tiers).length
    ? `<div class="row"><span>strict easy/hard</span><b>${tiers.easy?pct(tiers.easy.strict_rate):'—'} / ${tiers.hard?pct(tiers.hard.strict_rate):'—'}</b></div>` : '';
  card(labelOf(h.id), colorOf(h.id), `${h.model} · issue resolution`,
    `<div class="hint">Issues resolved (shown)</div><div class="metric" style="color:${colorOf(h.id)}">${pct(m.resolution_rate)}</div>`+
    `<div class="row"><span>composite</span><b>${pct(m.composite)}</b></div>`+
    `<div class="row"><span>strict resolved</span><b>${m.strict_rate==null?'unavailable':m.strict_resolved+'/'+m.n+' ('+pct(m.strict_rate)+')'}</b></div>`+
    `<div class="row"><span>resolved (shown)</span><b>${m.resolved}/${m.n}</b></div>`+
    `<div class="row"><span>robustness · regression</span><b>${pct(m.robustness)} · ${pct(m.regression)}</b></div>`+
    `<div class="row"><span>minimality · locality</span><b>${pct(m.minimality)} · ${pct(m.locality)}</b></div>`+
    tierRow+
    (m.cheats?`<div class="row"><span>cheats (test edits)</span><b class="err">${m.cheats}</b></div>`:'')+
    (m.errors?`<div class="row"><span>codegen errors</span><b>${m.errors}</b></div>`:'')).dataset.harness=h.id;});
const d=RUN.aggregates.synapse_delta;
if(d && d.composite){
  card('Cortex vs raw comparison','#6d5efb',`${H[d.cortex_wrapped].label} vs ${H[d.raw].label} · positive = improvement · ${RUN.config.basis||''}`,
  `<div class="metric" style="color:${deltaColor(d.composite.delta)}">${deltaText(d.composite.delta)}</div>`+
  `<div class="row"><span>composite change</span><b style="color:${deltaColor(d.composite.delta)}">${deltaText(d.composite.delta)}</b></div>`+
  (d.strict_rate?`<div class="row"><span>strict-resolution change</span><b style="color:${deltaColor(d.strict_rate.delta)}">${deltaText(d.strict_rate.delta)}</b></div>`:''));}

function renderCharts(){
  rankCards(cardComparison,labelOf,pct,'Issues resolved (shown)');
  const comparison=metricComparison(ids,id=>ph[id].composite),ordered=comparison.rows;
  const strictComparison=metricComparison(ids,id=>ph[id].strict_rate);
  scalarCue('c_comp',comparison,labelOf,pct);
  comparisonCue('c_res','higher','Shown: '+comparisonSummary(cardComparison,labelOf,pct)+' · Strict: '+comparisonSummary(strictComparison,labelOf,pct),'Ordered by shown resolution. Green identifies each metric’s leader; hatching marks the stricter gate. A larger shown–strict gap is worse; missing strict results are unmeasured.');
  chartOn('c_comp').setOption({
    grid:{left:48,right:16,top:20,bottom:64}, tooltip:{trigger:'item',formatter:p=>`${p.name}<br/><b>${pct(p.value)}</b> composite`},
    graphic:ids.every(id=>ph[id].composite==null)?{type:'text',left:'center',top:'middle',
      style:{text:'Composite not recorded in this historical source',fill:harnessInk(),fontSize:13}}:[],
    xAxis:catAxis(ordered.map(labelOf)), yAxis:pctAxis(),
    series:[{type:'bar',barWidth:'46%',label:{show:true,position:'top',formatter:p=>pct(p.value),color:harnessInk(),fontWeight:600},
      data:ordered.map(id=>({value:ph[id].composite,itemStyle:{color:comparisonColor(comparison,id),borderRadius:[6,6,0,0]}}))}]}, true);
  chartOn('c_res').setOption({
    grid:{left:48,right:16,top:30,bottom:64},
    legend:{data:['resolved (shown)','strict (held-out+regression)'],textStyle:{color:axisInk()},top:0},
    tooltip:{trigger:'axis',formatter:ps=>ps.map(p=>`${p.seriesName}: <b>${pct(p.value)}</b>`).join('<br/>')},
    xAxis:catAxis(ids.map(labelOf)), yAxis:pctAxis(),
    series:[
      {name:'resolved (shown)',type:'bar',barWidth:'30%',label:{show:true,position:'top',formatter:p=>pct(p.value),color:harnessInk(),fontSize:10},
        data:ids.map(id=>({value:ph[id].resolution_rate,itemStyle:{color:comparisonColor(cardComparison,id),opacity:0.6,borderRadius:[6,6,0,0]}}))},
      {name:'strict (held-out+regression)',type:'bar',barWidth:'30%',label:{show:true,position:'top',formatter:p=>pct(p.value),color:harnessInk(),fontSize:10,fontWeight:700},
        data:ids.map(id=>({value:ph[id].strict_rate,itemStyle:{color:comparisonColor(strictComparison,id),borderRadius:[6,6,0,0],decal:{symbol:'rect',dashArrayX:[1,0],dashArrayY:[2,4],rotation:-Math.PI/4,color:gridInk()}}}))}]}, true);
}
renderCharts();
window.__charts=renderCharts;
window.addEventListener('resize',()=>document.querySelectorAll('.chart').forEach(e=>echarts.getInstanceByDom(e)&&echarts.getInstanceByDom(e).resize()));

const body=document.getElementById('rows');
const ho=r=>r.held_out_total?`${r.held_out_passed}/${r.held_out_total}`:'—';
const rg=r=>r.regression_total?`${r.regression_passed}/${r.regression_total}`:'—';
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
RUN.results.forEach((r,i)=>{const tr=document.createElement('tr'); tr.className='case';
  const strict=r.gen_error?`<td class="err">⚠ error</td>`
    :(r.cheated?`<td class="err">⚠ cheat</td>`:(r.strict_resolved?`<td class="ok">✓ strict</td>`
      :(r.resolved?`<td class="err">~ shown-only</td>`:`<td class="no">✗ unresolved</td>`)));
  const files=Object.keys(r.files||{}).length?`<button class="codebtn" onclick="openCode('${labelOf(r.harness_id)} · ${r.task_id}', RUN.results[${i}].files||{})">⟨⟩ files</button>`:'';
  // grade chip on the composite (0..1, higher=better) — same gradeFor() letter as everywhere on the site
  const g=r.composite==null?'':gradeFor(r.composite);
  tr.innerHTML=`<td><a href="#" onclick="showIssue('${r.task_id}');return false;" style="color:inherit;text-decoration:underline dotted">${titleById[r.task_id]||r.task_id}</a></td><td>${labelOf(r.harness_id)}</td>`+
    `<td><b>${pct(r.composite)}</b>${g?` <span class="badge g-${g}">${g}</span>`:''}</td>${strict}`+
    `<td>${r.tests_passed}/${r.tests_total}</td><td>${ho(r)}</td><td>${rg(r)}</td><td>${pct(r.patch_minimality)}</td><td>${r.backend}</td><td>${files}</td>`;
  body.appendChild(tr);
  // codegen-error stream printed in its own row, clamped + truncated so a long raw JSON stream can
  // never blow out the page width (errbox scrolls; the text is capped before render as a hard backstop)
  if(r.gen_error){const raw=String(r.gen_error);
    const shown=raw.length>600?raw.slice(0,600)+'… (truncated)':raw;
    const er=document.createElement('tr');
    er.innerHTML=`<td colspan="10" class="err"><div class="errbox">${esc(shown)}</div></td>`;
    body.appendChild(er);}});

function downloadCsv(){const head=['task','harness','composite','strict_resolved','resolved','tests_passed','tests_total','held_out_passed','held_out_total','regression_passed','regression_total','minimality','locality','code_quality','cheated','backend','gen_error'];
  const lines=[head.join(',')]; RUN.results.forEach(r=>{
    lines.push([r.task_id,r.harness_id,r.composite,r.strict_resolved,r.resolved,r.tests_passed,r.tests_total,r.held_out_passed,r.held_out_total,r.regression_passed,r.regression_total,r.patch_minimality,r.patch_locality,r.code_quality,r.cheated,r.backend,JSON.stringify(r.gen_error||'')].join(','));});
  const blob=new Blob([lines.join('\n')],{type:'text/csv'}); const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download=RUN.run_id+'.csv'; a.click();}
const m=RUN.methodology;
document.getElementById('method').innerHTML=`Methodology — ${m.scoring}<br/>Synapse: ${m.synapse} ${m.note}<br/>`+
  `Generated __GENERATED__ · schema ${RUN.schema_version}.`;
__COMMON_JS__
</script>
</body></html>
"""


def build_repo_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    run_json = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    html = (
        inject_common(_TEMPLATE, "Bugfix", links=links).replace("__RUN_JSON__", run_json)
        .replace("__TITLE__", str(record.get("run_id", "run")))
        .replace("__GENERATED__", datetime.now().isoformat(timespec="seconds"))
    )
    out_path.write_text(html, encoding="utf-8")
    return html
