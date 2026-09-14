"""Track Q (code quality & output security) report — Artificial-Analysis-styled, self-contained."""

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
<title>Gauntlet Q — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__</style>
</head>
<body>
__NAVBAR__
<div class="wrap">
  <header class="hero">
    <div>
      <h1>Gauntlet — Track Q (code quality &amp; output security)</h1>
      <div class="sub" id="runmeta"></div>
      <div style="margin-top:10px"><span class="attest" id="attest"></span></div>
    </div>
    <div class="tools">
      <button class="tool" onclick="downloadCsv()">⤓ CSV</button>
      <button class="tool" onclick="window.print()">⎙ PDF / Print</button>
    </div>
  </header>

  <div class="cards" id="cards"></div>
  <details class="settings"><summary>Models &amp; settings — click to expand</summary><div class="body" id="settingsBody"></div></details>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#16a34a"></span>Requirement coverage by harness</h2>
      <div class="hint">Recorded requirement coverage · compare the observed values, not the provider colors</div>
      <div class="chart" id="c_cov"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#e5484d"></span>Maintainability debt by harness</h2>
      <div class="hint">Lower is better · debt = vulns + smells + skipped work; value (debt) on bars</div>
      <div class="chart" id="c_debt"></div>
    </section>
  </div>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#b4252a"></span>Vulnerabilities by CWE</h2>
      <div class="hint">Output-security flaws in generated code (SAST-lite), grouped by CWE</div>
      <div class="chart" id="c_cwe"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#6d5efb"></span>Code-quality judge (architecture / readability / interface)</h2>
      <div class="hint">Per-dimension rubric · higher is better</div>
      <div class="chart" id="c_radar"></div>
    </section>
  </div>

  <section class="block">
    <h2><span class="chip" style="background:#0f1222"></span>Code explorer</h2>
    <div class="hint">Click a row to view the generated code, SAST findings, dependency flags, and the requirements flagged as skipped during validation</div>
    <div class="filters" id="filters"></div>
    <table><thead><tr>
      <th>Task</th><th>Harness</th><th>Lang</th><th>Grade</th><th>Coverage</th><th>Functional</th><th>Vulns</th><th>Skipped</th>
    </tr></thead><tbody id="rows"></tbody></table>
  </section>

  <footer id="method"></footer>
</div>

__MODAL__
<script id="data" type="application/json">__RUN_JSON__</script>
<script>
const RUN = JSON.parse(document.getElementById('data').textContent);
buildSettings(RUN);
const H = {}; RUN.harnesses.forEach(h => H[h.id] = h);
const colorOf = id => harnessColor(H[id].family);  // theme-aware (shared with every report)
const pct = v => v==null?'unavailable':(v*100).toFixed(1)+'%';
const labelOf = id => H[id].label;
const ph = RUN.aggregates.per_harness;
const cardComparison=metricComparison(RUN.harnesses.map(h=>h.id),id=>ph[id]?.checks?.overall?.rate);
const ids = cardComparison.rows;

document.getElementById('runmeta').textContent =
  `run ${RUN.run_id} · ${RUN.created_at} · ${RUN.cases.length} tasks × ${RUN.harnesses.length} harnesses · judge ${RUN.methodology.judge_model}`;
document.getElementById('attest').textContent = `Cortex validation ${RUN.aggregates.synapse_delta.synapse ? 'active' : 'n/a'} · ${(RUN.containment&&RUN.containment.mode)||'temp-dir test sandbox'} — static analysis + hidden tests via pytest/node`;

// ---- highlight cards -------------------------------------------------------
const cards = document.getElementById('cards');
function card(title, chipColor, hint, bodyHtml){
  const d=document.createElement('div'); d.className='card';
  d.innerHTML=`<h3><span class="chip" style="background:${chipColor}"></span>${title}</h3><div class="hint">${hint}</div>${bodyHtml}`;
  cards.appendChild(d);
  return d;
}
// test-counted success: count each check, attributed to its category, so a 6/7-functional cell with
// clean lint/types reads ~90% rather than one all-or-nothing FAIL (functionality/quality/security)
function chk(m, cat){const c=(m.checks||{})[cat]; return (!c||c.rate==null)?'n/a':pct(c.rate);}
RUN.harnesses.forEach(h=>{
  const m=ph[h.id];
  const ov=(m.checks||{}).overall;
  // grade reflects the same headline shown below (overall per-check success) — higher = better letter,
  // identical to gradeFor() everywhere on the site (no longer the inverted maintainability-debt grade)
  const g=(ov&&ov.rate!=null)?gradeFor(ov.rate):'–';
  card(labelOf(h.id), colorOf(h.id), `${h.model} · overall success`,
    `<div class="grade g-${g}" style="display:inline-block;padding:2px 14px;border-radius:12px">${g}</div>`+
    (ov?`<div class="row"><span>overall success (per-check)</span><b>${ov.rate==null?'n/a':pct(ov.rate)} <small>(${ov.passed}/${ov.total})</small></b></div>`:'')+
    `<div class="row"><span>· functionality (pytest)</span><b>${chk(m,'functionality')}</b></div>`+
    `<div class="row"><span>· quality (ruff+mypy)</span><b>${chk(m,'quality')}</b></div>`+
    `<div class="row"><span>· security (SAST)</span><b>${chk(m,'security')}</b></div>`+
    `<div class="row"><span>requirement coverage</span><b>${pct(m.requirement_coverage)}</b></div>`+
    `<div class="row"><span>vulns / task</span><b>${m.vulns_per_task}</b></div>`+
    `<div class="row"><span>bad deps</span><b>${m.bad_deps}</b></div>`).dataset.harness=h.id;
});
const d = RUN.aggregates.synapse_delta;
if(d.synapse){
  // all four deltas are oriented >0 = Cortex better (vulns/debt are pre-sign-flipped in the aggregate),
  // so one sign/class helper covers them — a negative delta must render red with its real sign.
  const signed=v=>Number.isFinite(v)?(v>0?'+':'')+v:'unavailable';
  card('Cortex vs raw comparison', '#6d5efb', `${H[d.synapse].label} vs ${H[d.raw].label} · positive = improvement`,
    `<div class="metric" style="color:${deltaColor(d.requirement_coverage.delta)}">${deltaText(d.requirement_coverage.delta)}</div>`+
    `<div class="row"><span>coverage change</span><b style="color:${deltaColor(d.requirement_coverage.delta)}">${deltaText(d.requirement_coverage.delta)}</b></div>`+
    `<div class="row"><span>functional change</span><b style="color:${deltaColor(d.functional_rate.delta)}">${deltaText(d.functional_rate.delta)}</b></div>`+
    `<div class="row"><span>fewer vulns / task</span><b style="color:${deltaColor(d.vulns_per_task.delta)}">${signed(d.vulns_per_task.delta)}</b></div>`+
    `<div class="row"><span>less debt</span><b style="color:${deltaColor(d.debt.delta)}">${signed(d.debt.delta)}</b></div>`);
}

// ---- charts (theme-aware; re-rendered on toggle via window.__charts) --------
const axisStyle=()=>({axisLine:{lineStyle:{color:gridInk()}},axisLabel:{color:axisInk()}});
const dashed=()=>({splitLine:{lineStyle:{type:'dashed',color:gridInk()}}});
const inkLabel=harnessInk;
// category x-axis with interval:0 so every harness/CWE label renders (ECharts auto-hides otherwise);
// long harness names rotate + truncate with ellipsis so they never overlap
function catAxis(labels, rotate){
  return Object.assign({type:'category',data:labels},axisStyle(),
    {axisLabel:{interval:0, rotate:rotate==null?22:rotate, hideOverlap:true, width:90,
      overflow:'truncate', color:axisInk(), fontSize:11}});
}
function chartOn(el){const dom=document.getElementById(el);return echarts.getInstanceByDom(dom)||echarts.init(dom);}
function simpleBar(el,value,fmt,direction='higher'){
  const comparison=metricComparison(ids,value,direction),ordered=comparison.rows;
  scalarCue(el,comparison,labelOf,fmt);
  chartOn(el).setOption({
    grid:{left:50,right:20,top:24,bottom:64},
    tooltip:{trigger:'item',formatter:p=>`${p.name}<br/><b>${fmt(p.value)}</b>`},
    xAxis:catAxis(ordered.map(labelOf)),
    yAxis:Object.assign({type:'value',min:0,max:direction==='higher'?1:undefined,axisLabel:{color:axisInk(),formatter:direction==='higher'?v=>pct(v):undefined}},dashed()),
    series:[{type:'bar',barWidth:'46%',
      data:ordered.map(id=>({value:value(id),itemStyle:{color:comparisonColor(comparison,id),borderRadius:[6,6,0,0]}})),
      label:{show:true,position:'top',formatter:p=>fmt(p.value),color:inkLabel(),fontWeight:600}}]
  },true);
}
function renderCharts(){
  rankCards(cardComparison,labelOf,pct,'Overall checks passed');
  simpleBar('c_cov',id=>ph[id].requirement_coverage,pct);
  simpleBar('c_debt',id=>ph[id].maintainability.debt,v=>v==null?'unavailable':v.toFixed(2),'lower');
  // vulns by CWE grouped (no per-bar labels; legend on top, clear of x-axis)
  const cwes=Object.keys(RUN.aggregates.by_cwe);
  comparisonCue('c_cwe','lower','Fewer recorded vulnerabilities is better.','CWE categories are a breakdown, not a ranking; colors identify harnesses.');
  chartOn('c_cwe').setOption({
    grid:{left:40,right:16,top:52,bottom:60}, tooltip:{trigger:'axis'}, legend:{top:6,textStyle:{fontSize:11,color:harnessInk()}},
    xAxis:catAxis(cwes, 18),
    yAxis:Object.assign({type:'value',axisLabel:{color:axisInk()}},dashed()),
    series:ids.map(id=>({name:labelOf(id),type:'bar',itemStyle:{color:colorOf(id),borderRadius:[3,3,0,0]},
      data:cwes.map(c=>RUN.aggregates.by_cwe[c][id]??null)}))}, true);
  // judge radar
  const dims=['architecture','readability','interface'];
  comparisonCue('c_radar','higher','Farther outward means a higher rubric score in that dimension.','Colors identify harnesses, not a pooled winner; compare like dimensions.');
  chartOn('c_radar').setOption({
    tooltip:{}, legend:{bottom:0,textStyle:{fontSize:11,color:harnessInk()}},
    radar:{indicator:dims.map(d=>({name:d,max:1})), radius:'62%', splitLine:{lineStyle:{color:gridInk()}}},
    series:[{type:'radar', data: ids.map(id=>({name:labelOf(id), value:dims.map(d=>ph[id].judge[d]),
      lineStyle:{color:colorOf(id)}, itemStyle:{color:colorOf(id)}, areaStyle:{opacity:0.05}}))}]
  }, true);
}
renderCharts();
window.__charts=renderCharts;  // toggleTheme() re-runs this so charts recolor for the new theme
window.addEventListener('resize',()=>document.querySelectorAll('.chart').forEach(e=>echarts.getInstanceByDom(e)&&echarts.getInstanceByDom(e).resize()));

// ---- code explorer ---------------------------------------------------------
const taskById={}; RUN.cases.forEach(t=>taskById[t.id]=t);
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function uniq(v){return [...new Set(v)];}
function filesFor(r){
  if(RUN.publication?.evidence_redacted)return {};
  const files=r.files||{};
  if(Object.keys(files).length)return files;
  if(!r.code)return {};
  const ext={python:'py',typescript:'ts',javascript:'js'}[r.language]||'txt';
  return {['solution.'+ext]:r.code};
}
function fileSummary(r){
  if(RUN.publication?.evidence_redacted)return 'Generated files withheld from this public evidence view.';
  const files=filesFor(r), names=Object.keys(files);
  const lines=Object.values(files).reduce((n,v)=>n+String(v||'').split('\n').length,0);
  const sample=names.slice(0,5).map(esc).join(', ');
  return `${names.length} file${names.length===1?'':'s'} · ${lines} lines`+
    (sample?` · ${sample}${names.length>5?' …':''}`:'');
}
function previewText(s, limit){
  const raw=String(s||'');
  const text=raw.length>limit?raw.slice(0,limit)+'\n... truncated for page stability':raw;
  return esc(text);
}
function limited(items, limit, render, empty){
  if(!items.length)return empty;
  const more=items.length>limit?`<div class="hint" style="margin-top:6px">${items.length-limit} more omitted from preview</div>`:'';
  return items.slice(0,limit).map(render).join('<br/>')+more;
}
function openResultFiles(i){
  const r=RUN.results[i], t=taskById[r.task_id];
  openCode(`${t.title} — ${labelOf(r.harness_id)}`, filesFor(r));
}
function buildFilters(){
  const f=document.getElementById('filters');
  const defs=[['harness',uniq(RUN.results.map(r=>r.harness_id)).map(i=>[i,labelOf(i)])],
              ['task',uniq(RUN.results.map(r=>r.task_id)).map(t=>[t,t])],
              ['language',uniq(RUN.results.map(r=>r.language)).map(l=>[l,l])]];
  defs.forEach(([k,opts])=>{const s=document.createElement('select');s.id='f_'+k;
    s.innerHTML=`<option value="">all ${k}s</option>`+opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    s.onchange=renderRows; f.appendChild(s);});
}
function renderRows(){
  const fv=k=>(document.getElementById('f_'+k)||{}).value||'';
  const body=document.getElementById('rows'); body.innerHTML='';
  RUN.results.forEach((r,i)=>{
    const t=taskById[r.task_id]; const m=ph[r.harness_id];
    if(fv('harness')&&r.harness_id!==fv('harness'))return;
    if(fv('task')&&r.task_id!==fv('task'))return;
    if(fv('language')&&r.language!==fv('language'))return;
    const grade=gradeFor(rowOverall(r)); const tr=document.createElement('tr'); tr.className='case';
    tr.innerHTML=`<td>${t.title}</td><td>${labelOf(r.harness_id)}</td><td>${r.language}</td>`+
      `<td><span class="badge g-${grade}">${grade}</span></td><td>${pct(r.requirement_coverage)}</td>`+
      `<td>${r.dynamic_ran?(r.functional_passed+'/'+r.functional_total):'n/a'}</td>`+
      `<td>${r.findings.length}</td><td>${r.skipped_requirements.length}</td>`;
    const det=document.createElement('tr'); det.style.display='none';
    const finds=limited(r.findings,25,f=>`<span class="badge sev-${f.severity}">${f.cwe} ${f.severity}</span> ${esc(f.message)} (line ${f.line})`,'<span class="ok">no vulnerabilities</span>');
    const deps=limited(r.bad_dependencies,25,x=>`<span class="sig">${esc(x)}</span>`,'<span class="ok">clean</span>');
    const skipped=limited(r.skipped_requirements,25,x=>`<span class="sig">${esc(x)}</span>`,'<span class="ok">none — all requirements satisfied</span>');
    const fn = r.dynamic_ran ? `${r.functional_passed}/${r.functional_total} hidden tests passed (real pytest)` : 'not run';
    det.innerHTML=`<td colspan="8"><div class="detail">
      <h4>Task</h4><div>${esc(t.instruction)}</div>
      <h4>Generated files (${r.language}, Synapse backend: ${r.synapse_backend})</h4>
      <div>${fileSummary(r)}</div>
      ${RUN.publication?.evidence_redacted?'':`<div style="margin-top:8px"><button class="codebtn" onclick="openResultFiles(${i})">⟨⟩ open files + download .zip</button></div>`}
      <h4>Functional verification (dynamic)</h4><div>${fn}</div>${r.test_output?'<pre class="preview">'+previewText(r.test_output,1600)+'</pre>':''}
      <h4>SAST findings</h4><div>${finds}</div>
      <h4>Dependency flags (malicious / hallucinated)</h4><div>${deps}</div>
      <h4>Requirements skipped (surfaced by Synapse validation)</h4><div>${skipped}</div>
      <h4>Metrics &amp; judge</h4><div>complexity ${r.metrics.complexity} · functions ${r.metrics.functions} · tests ${r.metrics.has_tests} · error-handling ${r.metrics.has_error_handling} · duplication ${pct(r.metrics.duplication_pct)} · architecture ${r.judge.architecture} · readability ${r.judge.readability} · interface ${r.judge.interface}</div>
      </div></td>`;
    tr.onclick=()=>{det.style.display=det.style.display==='none'?'table-row':'none';};
    body.appendChild(tr); body.appendChild(det);
  });
}
// per-row overall success rate: the SAME micro-averaged per-check fraction the card/aggregate uses
// (functionality pytest + quality lint/types + security SAST), so the row badge is consistent with the
// card grade and with gradeFor() everywhere. Mirrors quality.metrics.check_breakdown().
function rowOverall(r){
  let p=0,t=0;
  if(r.dynamic_ran && r.functional_total){p+=r.functional_passed; t+=r.functional_total;}
  if(r.language==='python'){p+=(r.metrics.lint_score||0)+(r.metrics.type_score||0); t+=2;}
  p+=r.findings.length?0:1; t+=1;
  return t?p/t:null;
}
buildFilters(); renderRows();

function downloadCsv(){
  const head=['task','harness','language','requirement_coverage','vulns','cwes','bad_deps','skipped','complexity','has_tests','has_error_handling','architecture','readability','interface'];
  const lines=[head.join(',')];
  RUN.results.forEach(r=>lines.push([r.task_id,r.harness_id,r.language,r.requirement_coverage,r.findings.length,
    '"'+r.findings.map(f=>f.cwe).join('|')+'"','"'+r.bad_dependencies.join('|')+'"','"'+r.skipped_requirements.join('|')+'"',
    r.metrics.complexity,r.metrics.has_tests,r.metrics.has_error_handling,r.judge.architecture,r.judge.readability,r.judge.interface].join(',')));
  const blob=new Blob([lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=RUN.run_id+'.csv'; a.click();
}
const meth=RUN.methodology;
document.getElementById('method').innerHTML =
  `Methodology — analyzers: ${meth.analyzers}. Synapse: ${meth.synapse} ${meth.note}<br/>`+
  `Generated __GENERATED__ · schema ${RUN.schema_version} · report-v0 (ECharts). Higher coverage/judge = better; lower debt/vulns = better.`;
__COMMON_JS__
</script>
</body>
</html>
"""


def build_quality_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    run_json = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    html = (
        inject_common(_TEMPLATE, "Quality", links=links).replace("__RUN_JSON__", run_json)
        .replace("__TITLE__", str(record.get("run_id", "run")))
        .replace("__GENERATED__", datetime.now().isoformat(timespec="seconds"))
    )
    return html
