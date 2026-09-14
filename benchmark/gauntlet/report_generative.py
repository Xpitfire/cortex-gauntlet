"""Track G (generative capability) report — long-horizon decay + side-by-side app gallery."""

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
<title>Gauntlet G — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__
  .shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
  .shots figure{margin:0} .shots img{width:100%;border-radius:10px;border:1px solid var(--line)}
  .shots figcaption{font-size:12px;color:var(--muted);margin-top:6px}
  .fgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px;margin-top:6px}
  .feat{font-size:12px;padding:3px 8px;border-radius:6px}
  .feat.pass{background:#e7f8ee;color:#137a3a}.feat.fail{background:#f3f0f4;color:#8a8f9c}
  .feat.claim{box-shadow:inset 0 0 0 1px #e5484d}
</style>
</head>
<body>
__NAVBAR__
<div class="wrap">
  <header class="hero">
    <div>
      <h1>Gauntlet — Track G (generative capability)</h1>
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
    <h2><span class="chip" style="background:#6d5efb"></span>Completeness by final feature-list position</h2>
    <div class="hint">Bins summarize checks by final feature-list position, not elapsed time or observed completion milestones.</div>
    <div class="chart" id="c_horizon" style="height:340px"></div>
  </section>

  <div class="grid2">
    <section class="block">
      <h2><span class="chip" style="background:#16a34a"></span>Feature completeness by harness</h2>
      <div class="hint">Recorded feature completeness · bootstrap 95% CI whiskers stay attached to their harness</div>
      <div class="chart" id="c_complete"></div>
    </section>
    <section class="block">
      <h2><span class="chip" style="background:#0f1222"></span>Generative dimensions</h2>
      <div class="hint">build · completeness · visual · plan/trajectory · honesty</div>
      <div class="chart" id="c_radar"></div>
    </section>
  </div>

  <section class="block">
    <h2><span class="chip" style="background:#d97757"></span>Side-by-side app gallery</h2>
    <div class="hint" id="gallery-hint">Per-harness app render — figure caption shows features delivered &amp; passed e2e.</div>
    <div id="gallery"></div>
  </section>

  <section class="block" id="illuSection" style="display:none">
    <h2><span class="chip" style="background:#d97757"></span>Illustrative app render — <span id="illuTitle"></span></h2>
    <div class="hint" id="illuNote"></div>
    <div id="illuGallery" class="shots" style="margin-top:10px"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#0f1222"></span>App explorer</h2>
    <div class="hint">Click a row for the feature checklist, the milestone plan, and scores. Red outline = claimed-but-failed (dishonest).</div>
    <div class="filters" id="filters"></div>
    <table><thead><tr>
      <th>App</th><th>Harness</th><th>Lang</th><th>Build</th><th>Completeness</th><th>Plan</th><th>Honesty</th>
    </tr></thead><tbody id="rows"></tbody></table>
  </section>

  <footer id="method"></footer>
</div>

__MODAL__
<script id="data" type="application/json">__RUN_JSON__</script>
<script>
const RUN = JSON.parse(document.getElementById('data').textContent);
buildSettings(RUN);
const H={}; RUN.harnesses.forEach(h=>H[h.id]=h);
const colorOf=id=>harnessColor(H[id].family);  // theme-aware (shared with every report)
const pct=v=>v==null?'n/a':(v*100).toFixed(1)+'%';
const labelOf=id=>H[id].label;
// pass^k reliability (τ-bench style): only meaningful with multiple seeds
const relRow=r=>(r&&r.k&&r.k.length>1)?`<div class="row"><span>reliability pass^${r.k[r.k.length-1]}</span><b>${pct(r.pass_hat_k[r.pass_hat_k.length-1])}</b></div>`:'';
const ph=RUN.aggregates.per_harness;
const cardComparison=metricComparison(RUN.harnesses.map(h=>h.id),id=>ph[id]?.evaluable===false?null:ph[id]?.g_score);
const ids=cardComparison.rows;
const briefById={}; RUN.cases.forEach(b=>briefById[b.id]=b);

document.getElementById('runmeta').textContent =
  `run ${RUN.run_id} · ${RUN.created_at} · ${RUN.cases.length} apps × ${RUN.harnesses.length} harnesses × ${RUN.config.seeds} seeds · ${RUN.aggregates.feature_count} features · ${(RUN.skipped||[]).length} skipped`;
document.getElementById('attest').textContent = `${RUN.config.live?'LIVE sandboxed measurement':'SYNTHETIC modeled run — non-competitive'} · ${RUN.containment.mode}`;

// cards
const cards=document.getElementById('cards');
function card(t,c,h,b){const d=document.createElement('div');d.className='card';
  d.innerHTML=`<h3><span class="chip" style="background:${c}"></span>${t}</h3><div class="hint">${h}</div>${b}`;cards.appendChild(d);return d;}
RUN.harnesses.forEach(h=>{const m=ph[h.id];
  const evaluable=m.evaluable!==false&&m.g_score!=null;
  const score=evaluable
    ? `<div class="metric" style="color:${colorOf(h.id)}">${pct(m.g_score)} <span class="badge g-${gradeFor(m.g_score)}" style="font-size:14px;vertical-align:middle">${gradeFor(m.g_score)}</span></div>`
    : `<div class="metric">UNEVALUABLE</div><div class="hint">missing: ${(m.degraded||['unqualified']).join(', ')}</div>`;
  card(labelOf(h.id),colorOf(h.id),`${h.model} · capability score (gated composite)`,
    score+
    `<div class="row"><span>completeness</span><b>${pct(m.completeness)}</b></div>`+
    `<div class="row"><span>build rate</span><b>${pct(m.build_rate)}</b></div>`+
    relRow(m.reliability)+
    `<div class="row"><span>plan/trajectory</span><b>${m.plan==null?'n/a':m.plan}</b></div>`+
    `<div class="row"><span>visual</span><b>${pct(m.visual)}</b></div>`+
    `<div class="row"><span>honesty</span><b>${pct(m.honesty)}</b></div>`+
    (m.robustness!=null?`<div class="row"><span>robustness (held-out)</span><b>${pct(m.robustness)}</b></div>`:'')+
    (m.security!=null?`<div class="row"><span>security</span><b>${pct(m.security)}</b></div>`:'')+
    (m.code_quality!=null?`<div class="row"><span>code health</span><b>${pct(m.code_quality)}</b></div>`:'')).dataset.harness=h.id;});
const dl=RUN.aggregates.synapse_delta;
if(dl?.synapse&&Number.isFinite(dl.g_score?.delta)){const gd=dl.g_score.delta;card('Cortex vs raw comparison','#6d5efb',`${H[dl.synapse].label} vs ${H[dl.raw].label} · positive = improvement`,
    `<div class="metric" style="color:${deltaColor(gd)}">${deltaText(gd)}</div>`+
    `<div class="row"><span>capability score change</span><b style="color:${deltaColor(gd)}">${deltaText(gd)}</b></div>`+
    `<div class="row"><span>completeness change</span><b style="color:${deltaColor(dl.completeness?.delta)}">${deltaText(dl.completeness?.delta)}</b></div>`+
    (dl.robustness?`<div class="row"><span>robustness change</span><b style="color:${deltaColor(dl.robustness.delta)}">${deltaText(dl.robustness.delta)}</b></div>`:'')+
    (dl.security?`<div class="row"><span>security change</span><b style="color:${deltaColor(dl.security.delta)}">${deltaText(dl.security.delta)}</b></div>`:''));}

// charts (theme-aware; re-rendered on toggle via window.__charts)
const axisStyle=()=>({axisLine:{lineStyle:{color:gridInk()}},axisLabel:{color:axisInk()}});
const dashed=()=>({splitLine:{lineStyle:{type:'dashed',color:gridInk()}}});
const pctAxis=()=>Object.assign({type:'value',max:1,axisLabel:{formatter:v=>(v*100)+'%',color:axisInk()}},dashed());
const inkLabel=harnessInk;
function chartOn(el){const dom=document.getElementById(el);return echarts.getInstanceByDom(dom)||echarts.init(dom);}
// category x-axis with interval:0 so every harness label renders (ECharts auto-hides otherwise);
// long harness names rotate + truncate with ellipsis so they never overlap
function catAxis(labels, rotate){
  return Object.assign({type:'category',data:labels},axisStyle(),
    {axisLabel:{interval:0, rotate:rotate==null?22:rotate, hideOverlap:true, width:90,
      overflow:'truncate', color:axisInk(), fontSize:11}});
}
// CI whiskers + the value % rendered ABOVE the top cap so the label never collides with the whisker
function ciWhiskers(quads){const st={stroke:harnessInk(),lineWidth:1.5}; const fill=inkLabel();
  return {type:'custom',z:6,silent:true,data:quads,renderItem:(p,api)=>{const xi=api.value(0);
    const lo=api.coord([xi,api.value(1)]),hi=api.coord([xi,api.value(2)]),w=7;
    return {type:'group',children:[
      {type:'line',shape:{x1:lo[0],y1:lo[1],x2:hi[0],y2:hi[1]},style:st},
      {type:'line',shape:{x1:hi[0]-w,y1:hi[1],x2:hi[0]+w,y2:hi[1]},style:st},
      {type:'line',shape:{x1:lo[0]-w,y1:lo[1],x2:lo[0]+w,y2:lo[1]},style:st},
      {type:'text',style:{text:pct(api.value(3)),x:hi[0],y:hi[1]-8,textAlign:'center',
        textVerticalAlign:'bottom',fill,fontWeight:600,fontSize:12}}]};}};}
function renderCharts(){
  rankCards(cardComparison,labelOf,pct,'Gated capability score');
  comparisonCue('c_horizon','higher','Higher means more checks passed at that feature-list position.','Position is not elapsed time. Colors identify harnesses; unmeasured gaps are not interpolated.');
  // horizon decay line
  const bins=ph[ids[0]].horizon_curve.length;
  const xlabels=[...Array(bins)].map((_,i)=>`${Math.round(i*100/bins)}–${Math.round((i+1)*100/bins)}%`);
  chartOn('c_horizon').setOption({
    grid:{left:50,right:20,top:24,bottom:54},tooltip:{trigger:'axis',valueFormatter:v=>v==null?'—':pct(v)},
    legend:{bottom:0,textStyle:{fontSize:11,color:harnessInk()}},
    xAxis:Object.assign({type:'category',data:xlabels,name:'feature position →',nameLocation:'middle',nameGap:34},
      axisStyle(),{axisLabel:{interval:0,color:axisInk(),fontSize:11}}),
    yAxis:pctAxis(),
    series:ids.map(id=>({name:labelOf(id),type:'line',smooth:false,connectNulls:false,symbol:'circle',symbolSize:6,
      lineStyle:{width:2,color:colorOf(id)},itemStyle:{color:colorOf(id)},data:ph[id].horizon_curve}))}, true);
  // completeness with CI whiskers
  const comparison=metricComparison(ids,id=>ph[id].completeness),ordered=comparison.rows;
  scalarCue('c_complete',comparison,labelOf,pct);
  const whisk=ordered.map((id,i)=>[i,ph[id].completeness_ci?.[0],ph[id].completeness_ci?.[1],ph[id].completeness]).filter(v=>v.slice(1).every(Number.isFinite));
  chartOn('c_complete').setOption({
    grid:{left:50,right:20,top:40,bottom:64},  // headroom for the % label above a near-100% CI cap + rotated names
    tooltip:{trigger:'item',formatter:p=>(p.data&&p.data.ci)?`${p.name}<br/>completeness <b>${pct(p.value)}</b><br/>95% CI ${pct(p.data.ci[0])}–${pct(p.data.ci[1])}`:''},
    xAxis:catAxis(ordered.map(labelOf)),yAxis:pctAxis(),
    series:[{type:'bar',barWidth:'46%',
      data:ordered.map(id=>({value:ph[id].completeness,ci:ph[id].completeness_ci,itemStyle:{color:comparisonColor(comparison,id),borderRadius:[6,6,0,0]}}))},
      ciWhiskers(whisk)]}, true);
  // radar
  const dims=[['build','build_rate'],['complete','completeness'],['visual','visual'],['plan','plan'],['honesty','honesty']]
    .filter(d=>ids.every(id=>ph[id][d[1]]!=null));
  comparisonCue('c_radar','higher','Farther outward means a higher recorded score in that dimension.','Colors identify harnesses, not an overall winner; only dimensions available for every arm are shown.');
  chartOn('c_radar').setOption({tooltip:{},legend:{bottom:0,textStyle:{fontSize:11,color:harnessInk()}},
    radar:{indicator:dims.map(d=>({name:d[0],max:1})),radius:'62%',splitLine:{lineStyle:{color:gridInk()}}},
    series:[{type:'radar',data:ids.map(id=>({name:labelOf(id),value:dims.map(d=>ph[id][d[1]]),
      lineStyle:{color:colorOf(id)},itemStyle:{color:colorOf(id)},areaStyle:{opacity:0.05}}))}]}, true);
}
renderCharts();
window.__charts=renderCharts;  // toggleTheme() re-runs this so charts recolor for the new theme
window.addEventListener('resize',()=>document.querySelectorAll('.chart').forEach(e=>echarts.getInstanceByDom(e)&&echarts.getInstanceByDom(e).resize()));

// gallery: per brief, all harness screenshots side by side
const gallery=document.getElementById('gallery');
comparisonCue('gallery','neutral','Grouped by app brief; images and scores retain their recorded provenance.','Within a brief, harness order follows the named capability-card metric, not visual aesthetics.');
// real Playwright captures are PNGs; the offline fallback renders mock SVGs — say which the run used
const shots=RUN.results.map(r=>r.screenshot).filter(Boolean);
const realShots=shots.some(s=>/\.png(\?|$)/i.test(s));
document.getElementById('gallery-hint').textContent=RUN.publication?.evidence_redacted
  ? 'Captured app media withheld from this public evidence view.'
  : realShots ? 'Real sandboxed Playwright screenshots per harness — captions show features passing e2e.'
  : (RUN.config.live?'No sandboxed screenshot was available.':'Synthetic mock renders — not measured app screenshots.');
RUN.cases.forEach(b=>{
  const wrap=document.createElement('div'); wrap.style.marginBottom='18px';
  wrap.innerHTML=`<div style="font-weight:600;margin:6px 0">${b.title} <span style="color:#6b7280;font-weight:400">· ${b.stack}</span></div>`;
  const grid=document.createElement('div'); grid.className='shots';
  RUN.results.filter(r=>r.brief_id===b.id).sort((a,b)=>ids.indexOf(a.harness_id)-ids.indexOf(b.harness_id)).forEach(r=>{
    if(!r.screenshot) return;
    const passed=r.rep_features.filter(f=>f.passed).length;
    const fig=document.createElement('figure');
    fig.innerHTML=`<img src="${r.screenshot}" alt="${r.harness_id}"/><figcaption>${labelOf(r.harness_id)} — ${passed}/${r.feature_count} features</figcaption>`;
    grid.appendChild(fig);
  });
  wrap.appendChild(grid); gallery.appendChild(wrap);
});

// illustrative gallery: real Playwright captures from another build whose per-harness scores were
// not preserved — shown for visual reference only, kept OUT of the scored gallery/explorer above so
// it cannot inflate any composite. Caption/note carry the provenance and a link to the scored run.
(function(){
  const g=RUN.illustrative_gallery; if(!g||!Array.isArray(g.shots)||!g.shots.length) return;
  document.getElementById('illuSection').style.display='';
  document.getElementById('illuTitle').textContent=g.title||'';
  document.getElementById('illuNote').innerHTML=g.note||'';
  const grid=document.getElementById('illuGallery');
  g.shots.forEach(s=>{ if(!s.screenshot) return;
    const fig=document.createElement('figure');
    fig.innerHTML=`<img src="${s.screenshot}" alt="${s.harness_id||''}" loading="lazy"/>`+
      `<figcaption>${labelOf(s.harness_id)}${s.caption?' — '+s.caption:''}</figcaption>`;
    grid.appendChild(fig);
  });
})();

// explorer
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function uniq(v){return [...new Set(v)];}
function buildFilters(){const f=document.getElementById('filters');
  [['harness',uniq(RUN.results.map(r=>r.harness_id)).map(i=>[i,labelOf(i)])],
   ['app',uniq(RUN.results.map(r=>r.brief_id)).map(t=>[t,t])]].forEach(([k,opts])=>{
    const s=document.createElement('select');s.id='f_'+k;
    s.innerHTML=`<option value="">all ${k}s</option>`+opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    s.onchange=renderRows;f.appendChild(s);});}
function renderRows(){
  const fv=k=>(document.getElementById('f_'+k)||{}).value||'';
  const body=document.getElementById('rows');body.innerHTML='';
  RUN.results.forEach((r,i)=>{const b=briefById[r.brief_id];
    if(fv('harness')&&r.harness_id!==fv('harness'))return;
    if(fv('app')&&r.brief_id!==fv('app'))return;
    const comp=r.seed_completeness.reduce((a,c)=>a+c,0)/r.seed_completeness.length;
    const tr=document.createElement('tr');tr.className='case';
    tr.innerHTML=`<td>${b.title}</td><td>${labelOf(r.harness_id)}</td><td>${r.language}</td>`+
      `<td>${pct(r.build_pass/r.n_seeds)}</td><td>${pct(comp)}</td><td>${(r.degraded||[]).includes('trajectory')?'n/a':r.plan_score}</td><td>${(r.degraded||[]).includes('honesty')?'n/a':pct(r.honesty)}</td>`;
    const det=document.createElement('tr');det.style.display='none';
    const feats=r.rep_features.map(f=>`<span class="feat ${f.passed?'pass':'fail'}${(f.claimed&&!f.passed)?' claim':''}">${f.passed?'✓':'·'} ${esc(f.name)}</span>`).join('');
    const codeBtn=Object.keys(r.files||{}).length?`<button class="codebtn" onclick="openCode('${esc(b.title)} — ${labelOf(r.harness_id)}', RUN.results[${i}].files||{})">⟨⟩ view generated app + download .zip</button>`:'';
    det.innerHTML=`<td colspan="7"><div class="detail">
      ${codeBtn}
      <h4>Spec</h4><div>${esc(b.instruction)}</div>
      ${b.architecture?'<h4>Architecture</h4><div>'+esc(b.architecture)+'</div>':''}
      ${b.acceptance?'<h4>Acceptance</h4><div>'+esc(b.acceptance)+'</div>':''}
      ${r.screenshot?'<h4>Rendered app</h4><img src="'+r.screenshot+'" style="max-width:420px;border-radius:10px;border:1px solid #ececf1"/>':''}
      <h4>Feature checklist (representative seed)</h4><div class="fgrid">${feats}</div>
      <h4>Plan / milestones (Synapse backend: ${r.synapse_backend})</h4><div>${(r.degraded||[]).includes('trajectory')?'Not captured; no observed trajectory score.':r.milestones.map(esc).join(' → ')||'(no recorded milestones)'}</div>
      <h4>Scores</h4><div>build ${pct(r.build_pass/r.n_seeds)} · completeness ${pct(comp)} · visual ${(r.degraded||[]).includes('visual')?'n/a':r.visual_score} · plan ${(r.degraded||[]).includes('trajectory')?'n/a':r.plan_score} · honesty ${(r.degraded||[]).includes('honesty')?'n/a':pct(r.honesty)}${r.guardrail_score===null?'':' · guardrail '+r.guardrail_score}${(r.degraded||[]).length?' · unevaluable composite ('+r.degraded.join(', ')+')':''}</div>
      </div></td>`;
    tr.onclick=()=>{det.style.display=det.style.display==='none'?'table-row':'none';};
    body.appendChild(tr);body.appendChild(det);});
}
buildFilters();renderRows();

function downloadCsv(){
  const head=['app','harness','language','build_rate','completeness','visual','plan','honesty','guardrail','feature_count'];
  const lines=[head.join(',')];
  RUN.results.forEach(r=>{const comp=r.seed_completeness.reduce((a,c)=>a+c,0)/r.seed_completeness.length;
    lines.push([r.brief_id,r.harness_id,r.language,(r.build_pass/r.n_seeds).toFixed(3),comp.toFixed(3),
      (r.degraded||[]).includes('visual')?'':r.visual_score,
      (r.degraded||[]).includes('trajectory')?'':r.plan_score,
      (r.degraded||[]).includes('honesty')?'':r.honesty,r.guardrail_score,r.feature_count].join(','));});
  const blob=new Blob([lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=RUN.run_id+'.csv';a.click();
}
const m=RUN.methodology;
document.getElementById('method').innerHTML=
  `Methodology — ${m.scoring}. Synapse: ${m.synapse} ${m.note}<br/>`+
  `Generated __GENERATED__ · schema ${RUN.schema_version} · report-v0 (ECharts).`;
__COMMON_JS__
</script>
</body>
</html>
"""


def build_generative_report(record: dict, out_path: Path, links: dict | None = None) -> str:
    run_json = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    html = (
        inject_common(_TEMPLATE, "Generative", links=links).replace("__RUN_JSON__", run_json)
        .replace("__TITLE__", str(record.get("run_id", "run")))
        .replace("__GENERATED__", datetime.now().isoformat(timespec="seconds"))
    )
    out_path.write_text(html, encoding="utf-8")
    return html
