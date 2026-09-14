"""Render a RunRecord dict into a self-contained, Artificial-Analysis-styled HTML report.

report-v0: data is inlined; charts use ECharts (CDN). The Vite + React +
vendored-ECharts single-file build (M7) consumes the identical RunRecord JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path

from .report_common import inject_common
from .redaction import PUBLICATION_NOTICE
from .results_package import utility_evidence

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Gauntlet — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__
/* legacy inline styles (superseded by the themed shared CSS above):
  :root{--bg:#fff;--ink:#0f1222;--muted:#6b7280;--line:#ececf1;--accent:#6d5efb;
        --good:#16a34a;--bad:#e5484d;--warn:#d97706;--card:#fff;}
  *{box-sizing:border-box}
  body{margin:0;background:#f7f7fb;color:var(--ink);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:32px 24px 80px}
  header.hero{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}
  h1{font-size:26px;margin:0 0 4px;letter-spacing:-.4px}
  .sub{color:var(--muted);font-size:14px}
  .attest{display:inline-flex;align-items:center;gap:8px;background:#eefbf2;color:#137a3a;
          border:1px solid #c7eed4;border-radius:999px;padding:6px 12px;font-size:13px;font-weight:600}
  .tools{display:flex;gap:8px}
  button.tool{border:1px solid var(--line);background:#fff;border-radius:10px;padding:8px 12px;
              font-size:13px;cursor:pointer;color:var(--ink)}
  button.tool:hover{border-color:var(--accent);color:var(--accent)}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:24px 0}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
        box-shadow:0 1px 2px rgba(16,18,34,.04)}
  .chip{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:8px;vertical-align:middle}
  .card h3{font-size:15px;margin:0 0 2px;display:flex;align-items:center}
  .card .hint{color:var(--muted);font-size:12px;margin-bottom:12px}
  .metric{font-size:30px;font-weight:700;letter-spacing:-.5px}
  .metric.small{font-size:20px}
  .row{display:flex;justify-content:space-between;align-items:baseline;margin-top:6px;font-size:13px}
  .row b{font-weight:600}
  .pos{color:var(--good)} .neg{color:var(--bad)}
  section.block{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin:18px 0;
                box-shadow:0 1px 2px rgba(16,18,34,.04)}
  section.block h2{font-size:16px;margin:0 0 2px;display:flex;align-items:center}
  section.block .hint{color:var(--muted);font-size:12px;margin-bottom:8px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:820px){.grid2{grid-template-columns:1fr}}
  .chart{height:300px;width:100%}
  .filters{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 12px}
  select{border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:13px;background:#fff}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
  tr.case{cursor:pointer} tr.case:hover{background:#fafaff}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}
  .b-comply{background:#fdeaea;color:#b4252a} .b-refuse{background:#e9f7ee;color:#137a3a}
  .b-deflect{background:#eef0f4;color:#52607a} .b-over{background:#fff3e0;color:#a85800}
  .detail{background:#fbfbfe;border:1px dashed var(--line);border-radius:12px;padding:14px;margin:2px 0 10px}
  .detail h4{margin:0 0 4px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
  pre{white-space:pre-wrap;word-break:break-word;background:#0f1222;color:#e6e7ee;border-radius:10px;
      padding:12px;font-size:12.5px;overflow:auto;margin:4px 0 12px}
  .sig{display:inline-block;background:#fdeaea;color:#b4252a;border-radius:6px;padding:1px 7px;margin:2px 4px 2px 0;font-size:12px}
  footer{color:var(--muted);font-size:12px;margin-top:24px;line-height:1.7}
  .legend{font-size:12px;color:var(--muted);margin-top:6px}
  @media print{body{background:#fff}.tools{display:none}.chart{height:260px}}
*/
</style>
</head>
<body>
__NAVBAR__
<div class="wrap">
  <header class="hero">
    <div>
      <h1>Gauntlet — Track S report</h1>
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

  <section class="block">
    <h2><span class="chip" style="background:#e5484d"></span>Attack Success Rate by harness</h2>
    <div class="hint">Successful attacks are failures of containment · Wilson 95% CI and case-cluster bootstrap in tooltip</div>
    <div class="chart" id="c_asr"></div>
  </section>

  <section class="block" id="passBlock" style="display:none">
    <h2><span class="chip" style="background:#b83280"></span>Adaptive attack success by pass</h2>
    <div class="hint">Cumulative ASR after each user turn; pass 1 is the original prompt, later passes are red-team follow-ups</div>
    <div class="chart" id="c_pass"></div>
  </section>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#6d5efb"></span>ASR by technique</h2>
      <div class="hint">Higher bars = the technique evades this harness more often</div>
      <div class="chart" id="c_tech"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#d97706"></span>Over-refusal (benign tasks wrongly refused)</h2>
      <div class="hint">The safety counterweight — refusing everything is not "safe"</div>
      <div class="chart" id="c_over"></div>
    </section>
  </div>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#0aa5a5"></span>ASR by surface</h2>
      <div class="hint">Indirect injection (repo file / tool output / memory) vs the direct user turn</div>
      <div class="chart" id="c_surf"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#d97757"></span>ASR by modality — the multimodal gap</h2>
      <div class="hint">Same harmful ask delivered as text vs image vs audio (direct technique)</div>
      <div class="chart" id="c_mod"></div>
    </section>
  </div>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#0f1222"></span>Evidence: side-effect-confirmed vs judge-only</h2>
      <div class="hint">Solid = L1 sandbox/structural confirmation · hatched = judge inference only</div>
      <div class="chart" id="c_evi"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#16a34a"></span>Utility-under-attack</h2>
      <div class="hint" id="utilityHint">Synthetic completion-marker results; modeled utility is not measured live task completion.</div>
      <div class="chart" id="c_util"></div>
    </section>
  </div>

  <section class="block">
    <h2><span class="chip" style="background:#6d5efb"></span>Reproducibility &amp; budget</h2>
    <div class="hint" id="repro"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0f1222"></span>Case explorer</h2>
    <div class="hint">Click any row to inspect the prompt, rendered image/audio attack asset, response, proposed (never-executed) actions, sandbox side-effects, and judge rationale</div>
    <div class="filters" id="filters"></div>
    <table><thead><tr>
      <th>Case</th><th>Harness</th><th>Surface</th><th>Technique</th><th>Modality</th><th>Objective</th><th>Outcome</th>
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
const pct = v => v == null ? 'unavailable' : (v*100).toFixed(1)+'%';
const labelOf = id => H[id].label;
const UTILITY = RUN.publication?.utility || {};
function observedRate(metric){return metric?.n>0?metric.rate:null;}
function utilityLabel(id, metric){
  const status=UTILITY[id]?.status || 'unavailable';
  return status==='modeled' ? pct(observedRate(metric)) : status;
}

document.getElementById('runmeta').textContent =
  `run ${RUN.run_id} · ${RUN.created_at} · ${RUN.cases.length} cases × ${RUN.config.seeds} seeds`+
  `${(RUN.config.security_passes||1)>1?' × '+RUN.config.security_passes+' passes':''}`+
  ` · ${RUN.results.length} cells · judge ${RUN.methodology.judge_model}`;
const att = RUN.containment;
document.getElementById('attest').textContent = `containment: payloads executed = ${att.payloads_executed} · ${att.mode}`;

// ---- highlight cards -------------------------------------------------------
const ph = RUN.aggregates.per_harness;
const asrComparison=metricComparison(RUN.harnesses.map(h=>h.id),id=>observedRate(ph[id]?.asr),'lower');
const delta = RUN.aggregates.harness_delta || {};
const cards = document.getElementById('cards');
function card(title, chipColor, hint, bodyHtml){
  const d = document.createElement('div'); d.className='card';
  d.innerHTML = `<h3><span class="chip" style="background:${chipColor}"></span>${title}</h3>`+
                `<div class="hint">${hint}</div>${bodyHtml}`;
  cards.appendChild(d);
  return d;
}
RUN.harnesses.forEach(h => {
  const m = ph[h.id];
  const caps = (h.supports_multimodal?'🖼 ':'') + (h.supports_tools?'🔧 ':'') + Math.round(h.max_context/1000)+'k ctx';
  card(labelOf(h.id), colorOf(h.id), `${h.model} · ${caps}`,
    '<div class="hint">Attack-success rate · lower is safer</div>'+
    `<div class="metric" style="color:${colorOf(h.id)}">${pct(observedRate(m.asr))}</div>`+
    `<div class="row"><span>95% CI</span><b>${pct(m.asr.n>0?m.asr.ci[0]:null)}–${pct(m.asr.n>0?m.asr.ci[1]:null)}</b></div>`+
    `<div class="row"><span>any-seed @${m.attempts_per_case}</span><b>${pct(m.asr.n>0?m.asr_at_n:null)}</b></div>`+
    `<div class="row"><span>seed mean±std</span><b>${pct(m.asr.n>0?m.asr_seed_mean:null)} ± ${pct(m.asr.n>0?m.asr_seed_std:null)}</b></div>`+
    `<div class="row"><span>over-refusal</span><b>${pct(observedRate(m.over_refusal))}</b></div>`+
    `<div class="row"><span>utility</span><b>${utilityLabel(h.id,m.utility_under_attack)}</b></div>`+
    (m.secure_useful?`<div class="row"><span>secure&nbsp;∧&nbsp;useful</span><b>${utilityLabel(h.id,m.secure_useful)}</b></div>`:'')).dataset.harness=h.id;
});
if(Number.isFinite(delta.asr?.delta)){
  const comparable=Number.isFinite(asrComparison.value(delta.raw))&&Number.isFinite(asrComparison.value(delta.cortex_wrapped));
  const d = comparable?delta.asr.delta:null;
  card('ASR comparison · Cortex vs raw', deltaColor(d),
    `${labelOf(delta.cortex_wrapped)} vs ${labelOf(delta.raw)} · positive = fewer successful attacks`,
    `<div class="metric" style="color:${deltaColor(d)}">${deltaText(d)} ${d==null?'· incomplete observations':d===0?'· no change':d>0?'· reduction':'· increase'}</div>`+
    `<div class="row"><span>raw ASR</span><b>${pct(asrComparison.value(delta.raw))}</b></div>`+
    `<div class="row"><span>Cortex ASR</span><b>${pct(asrComparison.value(delta.cortex_wrapped))}</b></div>`);
}

// ---- charts (theme-aware; re-rendered on toggle via window.__charts) --------
const axisStyle = ()=>({axisLine:{lineStyle:{color:gridInk()}}, axisLabel:{color:axisInk()}});
const splitDashed = ()=>({splitLine:{lineStyle:{type:'dashed', color:gridInk()}}});
function pctAxis(){ return Object.assign({type:'value', max:1, axisLabel:{formatter:v=>(v*100)+'%', color:axisInk()}}, splitDashed()); }
// category x-axis with interval:0 so EVERY harness/category label renders (ECharts auto-hides otherwise);
// long harness names rotate + truncate with ellipsis so they never overlap
function catAxis(labels, rotate){
  return Object.assign({type:'category', data:labels}, axisStyle(),
    {axisLabel:{interval:0, rotate:rotate==null?22:rotate, hideOverlap:true, width:90,
      overflow:'truncate', color:axisInk(), fontSize:11}});
}
const inkLabel = harnessInk;
function chartOn(el){const dom=document.getElementById(el);return echarts.getInstanceByDom(dom)||echarts.init(dom);}

// CI whiskers + the value % rendered ABOVE the top cap, so the label never collides with the whisker.
function ciWhiskers(quads){
  const st = {stroke:harnessInk(), lineWidth:1.5}; const fill = inkLabel();
  return {
    type:'custom', z:6, silent:true, data:quads,
    renderItem:(params, api)=>{
      const xi = api.value(0);
      const lo = api.coord([xi, api.value(1)]);
      const hi = api.coord([xi, api.value(2)]); const w=7;
      return {type:'group', children:[
        {type:'line', shape:{x1:lo[0],y1:lo[1],x2:hi[0],y2:hi[1]}, style:st},
        {type:'line', shape:{x1:hi[0]-w,y1:hi[1],x2:hi[0]+w,y2:hi[1]}, style:st},
        {type:'line', shape:{x1:lo[0]-w,y1:lo[1],x2:lo[0]+w,y2:lo[1]}, style:st},
        {type:'text', style:{text:pct(api.value(3)), x:hi[0], y:hi[1]-8, textAlign:'center',
          textVerticalAlign:'bottom', fill, fontWeight:600, fontSize:12}},
      ]};
    }
  };
}
function barAsr(){
  const ids = asrComparison.rows;
  scalarCue('c_asr',asrComparison,labelOf,pct);
  const data = ids.map(id => ({
    value: asrComparison.value(id), name: labelOf(id),
    itemStyle:{color: comparisonColor(asrComparison,id), borderRadius:[6,6,0,0]},
    ci: ph[id].asr.ci, boot: ph[id].asr_bootstrap_ci, n: ph[id].asr.n
  }));
  const whisk = ids.map((id,i)=>[i, ph[id].asr.ci[0], ph[id].asr.ci[1], asrComparison.value(id)])
    .filter(row=>row.slice(1).every(Number.isFinite));
  chartOn('c_asr').setOption({
    grid:{left:50,right:20,top:24,bottom:64},
    tooltip:{trigger:'item', formatter:p=>(p.data&&p.data.ci)?`${p.name}<br/>ASR <b>${pct(p.value)}</b><br/>iid Wilson reference 95% ${pct(p.data.ci[0])}–${pct(p.data.ci[1])}<br/>case-cluster bootstrap ${pct(p.data.boot?.[0])}–${pct(p.data.boot?.[1])}<br/>attempts=${p.data.n}`:''},
    xAxis:catAxis(ids.map(labelOf)),
    yAxis:pctAxis(),
    series:[
      {type:'bar', data, barWidth:'46%'},
      ciWhiskers(whisk)
    ]
  });
}

function barPass(){
  const byPass = RUN.aggregates.by_pass || {};
  const cats = Object.keys(byPass).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  if(cats.length <= 1) return;
  document.getElementById('passBlock').style.display = '';
  const ids = asrComparison.rows;
  comparisonCue('c_pass','lower','Less cumulative attack success is safer.','Passes stay chronological; colors identify harnesses, not rank.');
  const series = ids.map(id => ({
    name: labelOf(id), type:'line', smooth:false, connectNulls:false, symbolSize:8,
    lineStyle:{width:3, color:colorOf(id)}, itemStyle:{color:colorOf(id)},
    data: cats.map(c => observedRate(byPass[c][id]))
  }));
  chartOn('c_pass').setOption({
    grid:{left:50,right:16,top:52,bottom:42},
    tooltip:{trigger:'axis'}, legend:{top:6, textStyle:{fontSize:11}},
    xAxis:catAxis(cats.map(c=>c.replace('_',' ')), 0),
    yAxis:pctAxis(), series
  });
}

function groupedBar(elId, sliceObj){
  const ids = asrComparison.rows;
  comparisonCue(elId,'lower','Smaller bars mean fewer successful attacks in each group.','Colors identify harnesses, not quality; compare within each technique, surface or modality.');
  const cats = Object.keys(sliceObj);
  const series = ids.map(id => ({
    name: labelOf(id), type:'bar',
    itemStyle:{color:colorOf(id), borderRadius:[4,4,0,0]},
    data: cats.map(c => observedRate(sliceObj[c][id]))
  }));  // no per-bar value labels (too dense); legend on top so it never overlaps the x-axis labels
  chartOn(elId).setOption({
    grid:{left:50,right:16,top:52,bottom:56},
    tooltip:{trigger:'axis'}, legend:{top:6, textStyle:{fontSize:11}},
    xAxis:catAxis(cats, 18),
    yAxis:pctAxis(), series
  });
}

function barOver(){
  const comparison=metricComparison(asrComparison.rows,id=>observedRate(ph[id]?.over_refusal),'lower'),ids=comparison.rows;
  scalarCue('c_over',comparison,labelOf,pct);
  chartOn('c_over').setOption({
    grid:{left:50,right:20,top:24,bottom:64},
    tooltip:{trigger:'item', formatter:p=>`${p.name}<br/>over-refusal <b>${pct(p.value)}</b>`},
    xAxis:catAxis(ids.map(labelOf)),
    yAxis:pctAxis(),
    series:[{type:'bar', barWidth:'46%',
      data: ids.map(id=>({value:comparison.value(id), itemStyle:{color:comparisonColor(comparison,id), borderRadius:[6,6,0,0]}})),
      label:{show:true, position:'top', formatter:p=>pct(p.value), color:inkLabel(), fontWeight:600}}]
  });
}

function stackedConfirm(){
  const ids = asrComparison.rows;
  comparisonCue('c_evi','lower','Smaller total attack-success rate is safer.','Ordered by total ASR. Pattern distinguishes evidence basis, not performance; neither segment measures utility.');
  chartOn('c_evi').setOption({
    grid:{left:50,right:16,top:30,bottom:64},
    tooltip:{trigger:'axis'}, legend:{bottom:0, data:['side-effect confirmed','judge-only'], textStyle:{fontSize:11}},
    xAxis:catAxis(ids.map(labelOf)),
    yAxis:pctAxis(),
    series:[
      {name:'side-effect confirmed', type:'bar', stack:'asr',
       data: ids.map(id=>({value: ph[id].asr.n>0?ph[id].asr_confirmed:null, itemStyle:{color:comparisonColor(asrComparison,id)}}))},
      {name:'judge-only', type:'bar', stack:'asr',
       data: ids.map(id=>({value: ph[id].asr.n>0?ph[id].asr_judge_only:null, itemStyle:{color:comparisonColor(asrComparison,id), opacity:0.4,
         decal:{symbol:'rect', dashArrayX:[1,0], dashArrayY:[2,5], rotation:-Math.PI/4, color:'rgba(255,255,255,0.7)'}}}))}
    ]
  });
}
function barUtil(){
  const comparison=metricComparison(asrComparison.rows,id=>UTILITY[id]?.status==='modeled'&&ph[id]?.utility_under_attack?.n>0?ph[id].utility_under_attack.rate:null),ids=comparison.rows;
  scalarCue('c_util',comparison,labelOf,pct);
  if(!ids.some(id=>UTILITY[id]?.status==='modeled')){
    const unverified=ids.some(id=>UTILITY[id]?.status==='unverified');
    document.getElementById('utilityHint').textContent=unverified
      ? 'Legacy marker flags are retained, but they do not validate carrier-task completion.'
      : 'No carrier-task completion measurements are available for this source.';
    chartOn('c_util').setOption({graphic:{type:'text',left:'center',top:'middle',
      style:{text:unverified?'Utility unverified\nNo validated success rate':'Utility unavailable\nNo observations',fill:inkLabel(),fontSize:15,lineHeight:25,textAlign:'center'}},series:[]},true);
    return;
  }
  chartOn('c_util').setOption({
    grid:{left:50,right:20,top:24,bottom:64},
    tooltip:{trigger:'item', formatter:p=>`${p.name}<br/>utility-under-attack <b>${pct(p.value)}</b>`},
    xAxis:catAxis(ids.map(labelOf)),
    yAxis:pctAxis(),
    series:[{type:'bar', barWidth:'46%',
      data: ids.map(id=>({value: comparison.value(id), itemStyle:{color:comparisonColor(comparison,id), borderRadius:[6,6,0,0]}})),
      label:{show:true, position:'top', formatter:p=>pct(p.value), color:inkLabel(), fontWeight:600}}]
  });
}
function renderCharts(){
  rankCards(asrComparison,labelOf,pct,'Attack success');
  barAsr(); groupedBar('c_tech', RUN.aggregates.by_technique); barOver();
  groupedBar('c_surf', RUN.aggregates.by_surface); groupedBar('c_mod', RUN.aggregates.by_modality);
  stackedConfirm(); barUtil(); barPass();
}
renderCharts();
window.__charts=renderCharts;  // toggleTheme() re-runs this so charts recolor for the new theme
window.addEventListener('resize', ()=>document.querySelectorAll('.chart').forEach(e=>echarts.getInstanceByDom(e)&&echarts.getInstanceByDom(e).resize()));

// ---- case explorer ---------------------------------------------------------
const caseById = {}; RUN.cases.forEach(c=>caseById[c.id]=c);
function outcome(r){
  const c = caseById[r.case_id];
  if(c.benign) return r.refusals>0 ? ['OVER-REFUSAL','b-over'] : ['allowed','b-refuse'];
  if(r.complies>0) return ['COMPLY','b-comply'];
  if(r.refusals===r.n_seeds) return ['REFUSE','b-refuse'];
  return ['DEFLECT','b-deflect'];
}
function uniq(vals){ return [...new Set(vals)]; }
function buildFilters(){
  const f = document.getElementById('filters');
  const defs = [
    ['harness', uniq(RUN.results.map(r=>r.harness_id)).map(id=>[id,labelOf(id)])],
    ['surface', uniq(RUN.cases.map(c=>c.surface)).map(s=>[s,s])],
    ['technique', uniq(RUN.cases.map(c=>c.technique)).map(t=>[t,t])],
    ['modality', uniq(RUN.cases.map(c=>c.modality)).map(m=>[m,m])],
    ['objective', uniq(RUN.cases.map(c=>c.objective)).map(o=>[o,o])],
    ['outcome', [['COMPLY','COMPLY'],['REFUSE','REFUSE'],['DEFLECT','DEFLECT'],['OVER-REFUSAL','OVER-REFUSAL'],['allowed','allowed']]],
  ];
  defs.forEach(([key, opts])=>{
    const s = document.createElement('select'); s.id='f_'+key; s.dataset.key=key;
    s.innerHTML = `<option value="">all ${key}s</option>`+opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    s.onchange = renderRows; f.appendChild(s);
  });
}
function renderRows(){
  const fv = k => (document.getElementById('f_'+k)||{}).value || '';
  const body = document.getElementById('rows'); body.innerHTML='';
  RUN.results.forEach((r,i)=>{
    const c = caseById[r.case_id]; const [oLabel,oCls] = outcome(r);
    if(fv('harness') && r.harness_id!==fv('harness')) return;
    if(fv('surface') && c.surface!==fv('surface')) return;
    if(fv('technique') && c.technique!==fv('technique')) return;
    if(fv('modality') && c.modality!==fv('modality')) return;
    if(fv('objective') && c.objective!==fv('objective')) return;
    if(fv('outcome') && oLabel!==fv('outcome')) return;
    const tr = document.createElement('tr'); tr.className='case';
    const count = c.benign ? `${r.refusals}/${r.n_seeds}` : `${r.complies}/${r.n_seeds}`;
    tr.innerHTML = `<td>${c.id}</td><td>${labelOf(r.harness_id)}</td><td>${c.surface}</td><td>${c.technique}</td>`+
                   `<td>${c.modality}</td><td>${c.objective}</td><td><span class="badge ${oCls}">${oLabel} ${count}</span></td>`;
    const det = document.createElement('tr'); det.style.display='none';
    const sigs = r.l0.danger_signals.map(s=>`<span class="sig">${s}</span>`).join('') || '<span style="color:#6b7280">none</span>';
    const acts = (r.transcript.proposed_actions||[]).map(a=>`${a.danger?'⚠️ ':''}[${a.kind}] ${a.command}`).join('\n') || '(none)';
    const fx = (r.l1.side_effects.effects||[]);
    const fxHtml = fx.length ? fx.map(e=>`<span class="sig">${esc(e)}</span>`).join('') : '<span style="color:#6b7280">none</span>';
    det.innerHTML = `<td colspan="7"><div class="detail">
      ${assetHtml(c)}
      <h4>Prompt (delivered to harness)</h4><pre>${esc(c.instruction)}</pre>
      ${c.payload && c.modality!=='text' ? '<h4>Hidden payload (in the asset)</h4><pre>'+esc(c.payload)+'</pre>' : ''}
      ${c.benign_task ? '<h4>Benign task (utility probe)</h4><pre>'+esc(c.benign_task)+'</pre>' : ''}
      <h4>Harness response</h4><pre>${esc(r.transcript.response)}</pre>
      ${passHtml(r)}
      <h4>Proposed actions (captured, never executed)</h4><pre>${esc(acts)}</pre>
      <h4>L0 signals</h4><div>canary_hit=${r.l0.canary_hit} · refusal_markers=${r.l0.refusal_markers} · danger: ${sigs}</div>
      <h4>Attempts (${r.n_seeds} seeds)</h4><div>complied ${r.complies} · refused ${r.refusals} · side-effect-confirmed ${r.confirms} · asr@1 ${pct(r.complies/r.n_seeds)}${r.utility_done==null?'':' · recorded utility_done='+r.utility_done+' ('+(UTILITY[r.harness_id]?.status||'unavailable')+')'}</div>
      <h4>L1 sandbox side-effects (mock env)</h4><div>${fxHtml}</div>
      <h4>Representative verdict (${r.score.instrument})</h4><div><b>${r.score.verdict}</b> · exploitable=${r.score.exploitable} · confirmed=${r.confirmed} · confidence=${r.score.confidence} · ${esc(r.score.rationale)} <i>(${r.score.judge_model})</i></div>
      </div></td>`;
    tr.onclick = ()=>{ det.style.display = det.style.display==='none'?'table-row':'none'; };
    body.appendChild(tr); body.appendChild(det);
  });
}
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function assetHtml(c){
  if(!c.asset_path) return '';
  if(/\.(svg|png|jpe?g)$/i.test(c.asset_path))
    return '<h4>Attack asset (image)</h4><img src="'+c.asset_path+'" style="max-width:100%;border-radius:8px;border:1px solid #ececf1"/>';
  if(/\.wav$/i.test(c.asset_path))
    return '<h4>Attack asset (audio)</h4><audio controls src="'+c.asset_path+'"></audio>';
  return '';
}
function passHtml(r){
  const passes = r.pass_results || [];
  if(passes.length <= 1) return '';
  return '<h4>Adaptive pass evidence</h4>' + passes.map(p =>
    `<details><summary>pass ${p.pass_index}: ${esc(p.score.verdict)} · exploitable=${p.score.exploitable}</summary>`+
    `<h4>Prompt</h4><pre>${esc(p.transcript.prompt)}</pre>`+
    `<h4>Response</h4><pre>${esc(p.transcript.response)}</pre></details>`
  ).join('');
}
buildFilters(); renderRows();

// ---- exports + methodology -------------------------------------------------
function downloadCsv(){
  const head = ['case_id','harness','surface','technique','modality','objective','benign','n_seeds','complies','refusals','confirms','asr_at_1','verdict','instrument','utility_done','utility_measurement_status','danger_signals'];
  const lines = [head.join(',')];
  RUN.results.forEach(r=>{ const c=caseById[r.case_id];
    lines.push([c.id,r.harness_id,c.surface,c.technique,c.modality,c.objective,c.benign,r.n_seeds,r.complies,r.refusals,r.confirms,
      (r.complies/r.n_seeds).toFixed(3),r.score.verdict,r.score.instrument,r.utility_done,r.utility_done==null?'unavailable':UTILITY[r.harness_id]?.status||'unavailable',
      '"'+r.l0.danger_signals.join('|')+'"'].join(','));
  });
  const blob = new Blob([lines.join('\n')], {type:'text/csv'});
  const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=RUN.run_id+'.csv'; a.click();
}
const m = RUN.methodology;
document.getElementById('repro').innerHTML =
  `<b>${RUN.config.seeds} attempts per case</b>, normalized across all harnesses (${m.budget}). `+
  `Attack-success@k: ${m.pass_at_k}. Confidence: ${m.ci}. ${m.contamination}.`;
document.getElementById('method').innerHTML =
  `Methodology — scoring: ${m.scoring}. ${m.adaptive_security||''} ${m.note}<br/>`+
  `Generated __GENERATED__ · schema ${RUN.schema_version} · report-v0 (ECharts). Lower ASR / over-refusal is better; error bars = Wilson 95% CI.`;
__COMMON_JS__
</script>
</body>
</html>
"""


def build_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    track = getattr(record.get("track"), "value", record.get("track"))
    if track == "quality":
        from .report_quality import build_quality_report

        renderer = build_quality_report
    elif track == "generative":
        from .report_generative import build_generative_report

        renderer = build_generative_report
    elif track == "project":
        from .report_project import build_project_report

        renderer = build_project_report
    elif track == "repo":
        from .report_repo import build_repo_report

        renderer = build_repo_report
    else:
        record = {**record, "publication": {**record.get("publication", {}),
                  "utility": record.get("publication", {}).get("utility") or utility_evidence(record)}}
        renderer = _build_security_report
    html = renderer(record, out_path, links)
    publication = record.get("publication", {})
    notices = []
    if "package" in publication:
        package = publication["package"]
        if package["collections"]:
            context = "Historical package source: " + escape(" · ".join(package["collections"])) + "."
        else:
            context = "Archive run, not the complete historical benchmark default."
            if package.get("track_overview"):
                context += f' <a href="{escape(package["track_overview"])}">Open the complete historical track.</a>'
        notices.append('<aside class="publication-note package-note" role="note">' + context
                       + ' <a href="../../results.html#package">View both historical collections.</a></aside>')
    if publication.get("evidence_redacted"):
        notices.append(f'<aside class="publication-note" role="note" data-evidence="restricted">{PUBLICATION_NOTICE}</aside>')
    utility_notes = sorted({e["note"] for e in publication.get("utility", {}).values()})
    if utility_notes:
        notices.append('<aside class="publication-note utility-note" role="note">'
                       + " ".join(escape(note) for note in utility_notes) + '</aside>')
    if notices:
        html = html.replace("</nav>", "</nav>" + "".join(notices), 1)
        out_path.write_text(html, encoding="utf-8")
    return html


def _build_security_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    run_json = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    html = (
        inject_common(_TEMPLATE, "Security", links=links).replace("__RUN_JSON__", run_json)
        .replace("__TITLE__", str(record.get("run_id", "run")))
        .replace("__GENERATED__", datetime.now().isoformat(timespec="seconds"))
    )
    out_path.write_text(html, encoding="utf-8")
    return html
