"""Shared report assets: themeable CSS, navbar, code-viewer modal, and common JS.

Injected into every report (and the landing) via __CSS__, __HEAD__, __NAVBAR__, __MODAL__,
__COMMON_JS__ tokens so dark/light theming, navigation, the expandable settings panel, and the
CodeMirror code-output viewer + zip download are consistent everywhere.
"""

import base64

# Brand mark: a rounded purple tile with a white "C" arc + a synapse node — "Cortex". Scalable SVG,
# reused as the favicon (browser tab), the navbar brand, and the summary hero.
LOGO_SVG = (
    '<svg class="brandmark" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" '
    'role="img" aria-label="Cortex">'
    '<defs><linearGradient id="cx" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#7c6cff"/><stop offset="1" stop-color="#5b4ae0"/></linearGradient></defs>'
    '<rect width="32" height="32" rx="8" fill="url(#cx)"/>'
    '<path d="M22 11a7 7 0 1 0 0 10" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>'
    '<circle cx="22.5" cy="16" r="2.6" fill="#fff"/></svg>'
)
# Self-contained favicon (base64 data URI) so every standalone report tab shows the mark.
_FAVICON = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()

# CDN libs: CodeMirror (code view) + JSZip (download). ECharts is added per-report.
REPORT_HEAD = f"""
<link rel="icon" type="image/svg+xml" href="{_FAVICON}"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.css"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5/theme/material-darker.css"/>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/mode/python/python.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/mode/javascript/javascript.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jszip@3/dist/jszip.min.js"></script>
<script>(function(){{var t=localStorage.getItem('gauntlet-theme')||
(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',t);}})();</script>
"""

REPORT_CSS = r"""
  :root{--page:#f7f7fb;--card:#fff;--bg:#fff;--ink:#0f1222;--muted:#6b7280;--line:#ececf1;
        --accent:#6d5efb;--good:#16a34a;--bad:#e5484d;--warn:#d97706;--navbg:rgba(255,255,255,.85)}
  [data-theme="dark"]{--page:#0c0d13;--card:#161823;--bg:#161823;--ink:#e7e8ef;--muted:#9aa0b4;
        --line:#262936;--navbg:rgba(18,20,28,.85)}
  *{box-sizing:border-box}
  body{margin:0;background:var(--page);color:var(--ink);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:24px 24px 80px}
  .publication-note{max-width:1132px;margin:20px auto;padding:16px 20px;border:1px solid var(--warn);
                    border-radius:12px;background:var(--card);color:var(--ink)}
  .package-note a{color:var(--accent)}
  nav.bar{position:sticky;top:0;z-index:40;backdrop-filter:saturate(1.4) blur(8px);
          background:var(--navbg);border-bottom:1px solid var(--line)}
  nav.bar .inner{max-width:1180px;margin:0 auto;padding:11px 24px;display:flex;align-items:center;gap:18px}
  nav.bar .brand{font-weight:700;letter-spacing:-.3px;color:var(--ink);text-decoration:none;font-size:15px;display:inline-flex;align-items:center;gap:8px}
  nav.bar .brand .sq{display:inline-block;width:12px;height:12px;border-radius:3px;background:var(--accent);margin-right:8px;vertical-align:-1px}
  .brandmark{width:22px;height:22px;border-radius:6px;flex:none}
  nav.bar .navlinks{display:flex;align-items:center;gap:18px}
  nav.bar a.lnk{color:var(--muted);text-decoration:none;font-size:13.5px;padding:4px 2px}
  nav.bar a.lnk:hover,nav.bar a.lnk.active{color:var(--accent)}
  nav.bar .spacer{flex:1}
  nav.bar button.navtoggle{display:none;border:1px solid var(--line);background:var(--card);color:var(--ink);
                    border-radius:9px;padding:6px 10px;font-size:15px;line-height:1;cursor:pointer}
  @media(max-width:880px){
    nav.bar button.navtoggle{display:inline-block}
    nav.bar .navlinks{display:none;position:absolute;top:100%;left:0;right:0;flex-direction:column;
      align-items:flex-start;gap:0;background:var(--card);border-bottom:1px solid var(--line);
      padding:8px 24px 12px;box-shadow:0 6px 16px rgba(16,18,34,.08)}
    nav.bar.open .navlinks{display:flex}
    nav.bar .navlinks a.lnk{padding:8px 2px;font-size:14px;width:100%}
  }
  nav.bar button.tt{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;
                    padding:6px 10px;font-size:13px;cursor:pointer}
  header.hero{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap;margin-top:18px}
  h1{font-size:26px;margin:0 0 4px;letter-spacing:-.4px}
  .sub{color:var(--muted);font-size:14px}
  .attest{display:inline-flex;align-items:center;gap:8px;background:rgba(109,94,251,.10);color:var(--accent);
          border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:600}
  .tools{display:flex;gap:8px}
  button.tool{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:8px 12px;
              font-size:13px;cursor:pointer;color:var(--ink)}
  button.tool:hover{border-color:var(--accent);color:var(--accent)}
  details.settings{margin:16px 0;border:1px solid var(--line);border-radius:14px;background:var(--card);padding:0 16px}
  details.settings>summary{cursor:pointer;padding:14px 0;font-weight:600;font-size:14px;list-style:none}
  details.settings>summary::-webkit-details-marker{display:none}
  details.settings>summary::before{content:'▸ ';color:var(--accent)}
  details.settings[open]>summary::before{content:'▾ '}
  details.settings .body{padding:0 0 14px}
  details.settings table{width:100%;border-collapse:collapse;font-size:12.5px}
  details.settings td,details.settings th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:20px 0}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:0 1px 2px rgba(16,18,34,.04)}
  .chip{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:8px;vertical-align:middle}
  .card h3{font-size:15px;margin:0 0 2px;display:flex;align-items:center}
  .card .hint{color:var(--muted);font-size:12px;margin-bottom:12px}
  .metric{font-size:30px;font-weight:700;letter-spacing:-.5px}
  .grade{font-size:34px;font-weight:800;letter-spacing:-1px}
  .row{display:flex;justify-content:space-between;align-items:baseline;margin-top:6px;font-size:13px}
  .row b{font-weight:600}
  .pos{color:var(--good)} .neg{color:var(--bad)}
  section.block{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin:18px 0;box-shadow:0 1px 2px rgba(16,18,34,.04)}
  section.block h2{font-size:16px;margin:0 0 2px;display:flex;align-items:center}
  section.block .hint{color:var(--muted);font-size:12px;margin-bottom:8px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:820px){.grid2{grid-template-columns:1fr}}
  .chart{height:300px;width:100%}
  .filters{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 12px}
  select{border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:13px;background:var(--card);color:var(--ink)}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;
        overflow-wrap:anywhere;word-break:break-word}
  td.err,.err{overflow-wrap:anywhere;word-break:break-word}
  .errbox{max-height:120px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;
          font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
  th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
  tr.case{cursor:pointer} tr.case:hover{background:rgba(109,94,251,.05)}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}
  .codebtn{border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:7px;padding:2px 8px;font-size:11px;cursor:pointer}
  .g-A{background:#e7f8ee;color:#137a3a}.g-B{background:#eef7e7;color:#4d7a13}
  .g-C{background:#fff7e0;color:#a87900}.g-D{background:#fdeede;color:#b4622a}.g-E{background:#fdeaea;color:#b4252a}
  .sev-critical{background:#fdeaea;color:#b4252a}.sev-high{background:#fdeede;color:#b4622a}
  .sev-medium{background:#fff7e0;color:#a87900}.sev-low{background:#eef0f4;color:#52607a}
  .b-comply{background:#fdeaea;color:#b4252a} .b-refuse{background:#e9f7ee;color:#137a3a}
  .b-deflect{background:#eef0f4;color:#52607a} .b-over{background:#fff3e0;color:#a85800}
  .detail{background:var(--page);border:1px dashed var(--line);border-radius:12px;padding:14px;margin:2px 0 10px}
  .detail h4{margin:0 0 4px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
  pre{white-space:pre-wrap;word-break:break-word;background:#0f1222;color:#e6e7ee;border-radius:10px;padding:12px;font-size:12.5px;overflow:auto;margin:4px 0 12px}
  .sig{display:inline-block;background:#fdeaea;color:#b4252a;border-radius:6px;padding:1px 7px;margin:2px 4px 2px 0;font-size:12px}
  .ok{display:inline-block;background:#e7f8ee;color:#137a3a;border-radius:6px;padding:1px 7px;margin:2px 4px 2px 0;font-size:12px}
  footer{color:var(--muted);font-size:12px;margin-top:24px;line-height:1.7}
  .modal{position:fixed;inset:0;z-index:60;background:rgba(8,9,14,.55);display:none}
  .modal.open{display:flex;align-items:center;justify-content:center;padding:24px}
  .modal .box{background:var(--card);border:1px solid var(--line);border-radius:16px;width:min(1000px,96vw);height:min(80vh,820px);display:flex;flex-direction:column;overflow:hidden}
  .modal .top{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
  .modal .top b{font-size:14px}.modal .top .spacer{flex:1}
  .modal .main{display:flex;flex:1;min-height:0}
  .modal .tree{width:280px;border-right:1px solid var(--line);overflow:auto;padding:8px;font-size:12.5px}
  .modal .tree .node{display:flex;align-items:center;gap:4px;padding:4px 8px;border-radius:7px;cursor:pointer;color:var(--ink);white-space:nowrap;width:max-content;min-width:100%}
  .modal .tree .node:hover{background:rgba(109,94,251,.08)}
  .modal .tree .node.sel{background:rgba(109,94,251,.14);color:var(--accent);font-weight:600}
  .modal .tree .dir{font-weight:600}
  .modal .tree .tw{display:inline-block;width:14px;color:var(--muted);flex:none}
  .modal .tree .name{overflow:visible;text-overflow:clip}
  .modal .tree .empty{color:var(--muted);padding:8px}
  .modal .view{flex:1;min-width:0;overflow:auto}
  .modal .CodeMirror{height:100%;font-size:12.5px}
  pre.preview{max-height:220px}
  @media print{nav.bar,.tools,.codebtn{display:none}.chart{height:260px}}
"""


def navbar(home_href: str, active: str, links: dict | None = None) -> str:
    """A sticky nav. With `links` (built site) it renders resolved cross-page deep links; without them
    (a standalone single-run report opened straight from results/<id>/) it renders a minimal bar —
    brand + theme only — so nav clicks never 404 against a site layout that isn't there."""

    site = bool(links)
    links = links or {}

    def lnk(label: str, anchor: str) -> str:
        href = links.get(label)
        if not href:  # no resolved target → inert (avoids ERR_FILE_NOT_FOUND on a standalone report)
            return ""
        cls = "lnk active" if label == active else "lnk"
        return f'<a class="{cls}" href="{href}">{label}</a>'

    nav_links = (
        f'{lnk("Overview", "overview")}'
        f'{lnk("Security", "security")}{lnk("Quality", "quality")}'
        f'{lnk("Generative", "generative")}{lnk("Project", "project")}{lnk("Bugfix", "repo")}'
        f'{lnk("Results", "results")}{lnk("Paper", "paper")}'
        if site else ""
    )
    brand_href = home_href if (site and home_href) else "#"
    # On narrow screens the horizontal links collapse behind a hamburger (.navtoggle); the links live in
    # a .navlinks container that becomes a dropdown panel when nav.bar gets the `open` class.
    toggle = (
        '<button class="navtoggle" aria-label="Menu" aria-expanded="false" '
        'onclick="toggleNav()">☰</button>'
        if nav_links else ""
    )
    return (
        '<nav class="bar"><div class="inner">'
        f'<a class="brand" href="{brand_href}">{LOGO_SVG}Gauntlet</a>'
        f'<div class="navlinks" id="navlinks">{nav_links}</div>'
        '<span class="spacer"></span>'
        f'{toggle}'
        '<button class="tt" id="themeBtn" onclick="toggleTheme()" title="Toggle theme">☾</button>'
        '</div></nav>'
    )


def inject_common(
    html: str, active: str, home_href: str = "../../index.html", links: dict | None = None
) -> str:
    """Apply the shared head/css/navbar/modal/js tokens to a report template."""

    return (
        html.replace("__HEAD__", REPORT_HEAD).replace("__CSS__", REPORT_CSS + COMPARISON_CSS)
        .replace("__NAVBAR__", navbar(home_href, active, links)).replace("__MODAL__", MODAL_HTML)
        .replace("__COMMON_JS__", COMMON_JS + COMPARISON_JS)
    )


MODAL_HTML = (
    '<div class="modal" id="codeModal" onclick="if(event.target===this)closeCode()">'
    '<div class="box"><div class="top"><b id="cmTitle">Model output</b>'
    '<span class="spacer"></span>'
    '<button class="tool" onclick="downloadZip()">⤓ download .zip</button>'
    '<button class="tool" onclick="closeCode()">✕ close</button></div>'
    '<div class="main"><div class="tree" id="cmTree"></div><div class="view" id="cmView"></div></div>'
    '</div></div>'
)

# Report-only presentation: Paper uses the unchanged base CSS/JS directly.
COMPARISON_CSS = r"""
:root{--metric-good:#087d52;--metric-risk:#c83540;--metric-neutral:#64748b}
[data-theme="dark"]{--metric-good:#57d9a3;--metric-risk:#fa7880;--metric-neutral:#a4aec2}
.comparison-cue{display:flex;flex-wrap:wrap;align-items:center;gap:7px 12px;margin:12px 0 8px;font-size:12px;line-height:1.5}
.direction-pill{display:inline-block;border:1px solid currentColor;border-radius:6px;padding:4px 8px;font-weight:750;color:var(--metric-good);white-space:nowrap}
.comparison-cue[data-direction="lower"] .direction-pill{color:var(--metric-risk)}
.comparison-summary{color:var(--ink);overflow-wrap:anywhere}
.comparison-order{flex-basis:100%;color:var(--muted);font-size:11px}
.rank-badge{display:block;font-size:11px;font-weight:700;letter-spacing:.2px;margin:0 0 9px;color:var(--muted)}
.card.metric-leader{border-color:var(--metric-good)}.card.metric-leader .rank-badge,.card.metric-leader .metric{color:var(--metric-good)}
.direction-pill[data-direction="neutral"]{color:var(--muted)}
"""

COMPARISON_JS = r"""
function metricComparison(rows,value,direction='higher'){
  const ordered=[...rows].sort((a,b)=>{const av=value(a),bv=value(b),af=Number.isFinite(av),bf=Number.isFinite(bv);
    return af&&bf?(direction==='lower'?av-bv:bv-av):af?-1:bf?1:0;});
  const recorded=ordered.filter(r=>Number.isFinite(value(r))),best=recorded.length?value(recorded[0]):null;
  const tied=recorded.length>1&&recorded.every(r=>value(r)===best);
  return {rows:ordered,value,best,direction,recorded:recorded.length,tied,
    leaders:recorded.length>1&&!tied?recorded.filter(r=>value(r)===best):[]};
}
function comparisonSummary(c,label,format){
  if(!c.recorded)return 'No comparable measurements · not ranked';
  if(c.recorded===1)return `${label(c.rows[0])} · ${format(c.best)} · only recorded value`;
  if(c.tied)return `All recorded values equal · ${format(c.best)}`;
  const edge=c.direction==='lower'?'Lowest':'Highest';
  return `${c.leaders.length>1?'Joint '+edge.toLowerCase():edge} recorded: ${c.leaders.map(label).join(' / ')} · ${format(c.best)}`;
}
function comparisonColor(c,row){
  if(c.leaders.includes(row))return isDark()?'#57d9a3':'#087d52';
  if(!Number.isFinite(c.value(row))||c.tied||c.recorded<2)return isDark()?'#a4aec2':'#64748b';
  return c.direction==='lower'?(isDark()?'#fa7880':'#c83540'):(isDark()?'#a4aec2':'#64748b');
}
function comparisonCue(id,direction,summary,order=''){
  const chart=document.getElementById(id);if(!chart)return;
  let cue=document.getElementById(id+'-comparison');
  if(!cue){cue=document.createElement('div');cue.id=id+'-comparison';cue.className='comparison-cue';chart.before(cue);}
  cue.dataset.direction=direction;cue.replaceChildren();
  for(const [kind,text] of [['direction-pill',direction==='lower'?'↓ Lower is better':direction==='higher'?'↑ Higher is better':'Descriptive · not ranked'],['comparison-summary',summary],['comparison-order',order]]){
    if(!text)continue;const span=document.createElement('span');span.className=kind;span.dataset.direction=direction;span.textContent=text;cue.append(span);}
}
function scalarCue(id,c,label,format){
  comparisonCue(id,c.direction,comparisonSummary(c,label,format),
    c.leaders.length?'Ordered by recorded point estimate, not statistical superiority. Green marks the leading value.':'Equal or unavailable values do not establish a leader.');
}
function rankCards(c,label,format,metric){
  comparisonCue('cards',c.direction,metric+' · '+comparisonSummary(c,label,format),'Harness cards follow this metric; each chart names its own comparison.');
  const container=document.getElementById('cards'),cards=new Map([...container.querySelectorAll('.card[data-harness]')].map(card=>[card.dataset.harness,card]));
  const comparisonCard=container.querySelector('.card:not([data-harness])');
  c.rows.forEach(row=>{const card=cards.get(row);if(!card)return;card.classList.remove('cortex');card.classList.toggle('metric-leader',c.leaders.includes(row));
    const headline=card.querySelector('.metric');if(headline)headline.style.color=comparisonColor(c,row);
    const badge=card.querySelector('.rank-badge')||document.createElement('span');badge.className='rank-badge';
    badge.textContent=!Number.isFinite(c.value(row))?'Not ranked · unavailable':c.tied?'Equal recorded value':c.recorded<2?'Only recorded value':c.leaders.includes(row)?(c.leaders.length>1?'Joint leader':'Leading recorded value'):`Rank ${c.rows.findIndex(r=>c.value(r)===c.value(row))+1} · ${metric}`;
    card.prepend(badge);container.insertBefore(card,comparisonCard);});
}
function deltaText(v){
  return Number.isFinite(v)?(v>0?'+':'')+(v*100).toFixed(1)+' pts':'unavailable';
}
function deltaColor(v){return !Number.isFinite(v)||v===0?'var(--metric-neutral)':v>0?'var(--metric-good)':'var(--metric-risk)';}
"""

# Theme toggle + settings panel + CodeMirror file-viewer modal + zip download.
COMMON_JS = r"""
// Theme-aware harness colors: the openai near-black is invisible on the dark page, so it (and the
// others, lightened) flip in dark mode. Reports call harnessColor()/harnessInk() at render time and
// re-render via window.__charts on toggle, so bars/labels stay legible in both themes.
function isDark(){return document.documentElement.getAttribute('data-theme')==='dark';}
function harnessColor(family){
  const light={openai:'#111827',anthropic:'#d97757',omp:'#2563eb',opencode:'#15a5a5',cortex:'#6d5efb'};
  const dark ={openai:'#cbd5e1',anthropic:'#e8896b',omp:'#60a5fa',opencode:'#2bc4c4',cortex:'#8b7dff'};
  const p=isDark()?dark:light; return p[family]||(isDark()?'#9aa0b4':'#5b6472');}
function harnessInk(){return isDark()?'#e7e8ef':'#0f1222';}
function axisInk(){return isDark()?'#9aa0b4':'#6b7280';}
function gridInk(){return isDark()?'#2a2d3a':'#ececf1';}
function updateThemeIcon(){const b=document.getElementById('themeBtn');if(!b)return;
  // show the icon of the theme you'll switch TO (opposite of current): dark→☀ (to light), light→☾ (to dark)
  b.textContent=document.documentElement.getAttribute('data-theme')==='dark'?'☀':'☾';}
function toggleTheme(){const h=document.documentElement;const n=h.getAttribute('data-theme')==='dark'?'light':'dark';
  h.setAttribute('data-theme',n);localStorage.setItem('gauntlet-theme',n);
  document.querySelectorAll('.CodeMirror').forEach(e=>{if(e.CodeMirror)e.CodeMirror.setOption('theme',n==='dark'?'material-darker':'default');});
  updateThemeIcon();
  if(window.__charts)window.__charts();}
// Single source of truth for the A–E letter grade: a monotonic function of a 0..1 "higher=better"
// score, shared identically by every report so a harness never gets two different letters.
function gradeFor(s){ if(s==null||isNaN(s)) return '–'; return s>=0.95?'A':s>=0.88?'B':s>=0.80?'C':s>=0.70?'D':'E'; }
// Mobile nav: toggle the dropdown panel under the bar (hamburger is hidden ≥880px).
function toggleNav(){const n=document.querySelector('nav.bar'); const open=n.classList.toggle('open'); const b=n.querySelector('.navtoggle'); if(b) b.setAttribute('aria-expanded', open);}
function buildSettings(RUN){
  const el=document.getElementById('settingsBody'); if(!el) return;
  const cfg=RUN.config||{}, m=RUN.methodology||{};
  let rows=RUN.harnesses.map(h=>`<tr><td><b>${h.label||h.id}</b></td><td>${h.model||''}</td><td>${h.family||''}</td>`+
    `<td>${h.reasoning||'—'}</td><td>${h.role||''}</td><td>${h.max_context?Math.round(h.max_context/1000)+'k':'—'}</td>`+
    `<td>${[h.supports_tools?'tools':'',h.supports_multimodal?'multimodal':'',h.uses_synapse?'Synapse':''].filter(Boolean).join(', ')}</td></tr>`).join('');
  const settings=Object.entries(cfg).filter(([k,v])=>v!=null).map(([k,v])=>`<b>${k}</b>=${v}`).join(' · ');
  const meth=Object.entries(m).map(([k,v])=>`<div><b>${k}:</b> ${v}</div>`).join('');
  // OpenCode is run with both configurable backends; its figures are the average of the two.
  const hasOpenCode=RUN.harnesses.some(h=>h.id==='opencode'||h.family==='opencode');
  const note=hasOpenCode?`<div style="color:var(--muted);margin-top:8px;font-size:12px">OpenCode runs configurable open-source models; its reported figures are averaged across both backends (GPT-5.5 and Opus 4.8).</div>`:'';
  el.innerHTML=`<div style="color:var(--muted);margin-bottom:8px">Run settings: ${settings}</div>`+
    `<table><thead><tr><th>harness</th><th>model</th><th>provider</th><th>reasoning</th><th>role</th><th>ctx</th><th>capabilities</th></tr></thead><tbody>${rows}</tbody></table>`+
    note+
    `<div style="margin-top:10px;font-size:12.5px;line-height:1.7">${meth}</div>`;
}
let __cmFiles={}, __cmTitle='output', __cmOpenDirs=new Set(), __cmSelectedFile='';
function openCode(title, files){
  __cmFiles=files||{}; __cmTitle=title||'output';
  document.getElementById('cmTitle').textContent=title;
  const names=Object.keys(__cmFiles).sort((a,b)=>a.localeCompare(b));
  __cmOpenDirs=new Set(); __cmSelectedFile=names[0]||'';
  if(__cmSelectedFile) openAncestors(__cmSelectedFile);
  renderFileTree();
  document.getElementById('codeModal').classList.add('open');
  if(__cmSelectedFile) showFileByName(__cmSelectedFile);
}
function buildFileTree(names){
  const root={dirs:{},files:[]};
  names.forEach(path=>{const parts=String(path).split('/').filter(Boolean); if(!parts.length)return;
    let node=root; parts.slice(0,-1).forEach(part=>{node.dirs[part]=node.dirs[part]||{dirs:{},files:[]}; node=node.dirs[part];});
    node.files.push({name:parts[parts.length-1],path:path});});
  return root;
}
function openAncestors(name){
  const parts=String(name).split('/').filter(Boolean); let key='';
  parts.slice(0,-1).forEach(part=>{key=key?key+'/'+part:part; __cmOpenDirs.add(key);});
}
function treeRow(kind,label,depth,marker){
  const row=document.createElement('div'); row.className='node '+kind; row.style.paddingLeft=(depth*14+6)+'px';
  const tw=document.createElement('span'); tw.className='tw'; tw.textContent=marker;
  const name=document.createElement('span'); name.className='name'; name.textContent=label;
  row.appendChild(tw); row.appendChild(name); return row;
}
function renderFileTree(){
  const tree=document.getElementById('cmTree'), names=Object.keys(__cmFiles).sort((a,b)=>a.localeCompare(b));
  tree.innerHTML=''; if(!names.length){tree.innerHTML='<div class="empty">(no files)</div>'; return;}
  const frag=document.createDocumentFragment();
  renderTreeNode(buildFileTree(names),0,'',frag);
  tree.appendChild(frag);
}
function renderTreeNode(node,depth,prefix,frag){
  Object.keys(node.dirs).sort((a,b)=>a.localeCompare(b)).forEach(name=>{
    const key=prefix?prefix+'/'+name:name, open=__cmOpenDirs.has(key);
    const row=treeRow('dir',name,depth,open?'▾':'▸'); row.title=key;
    row.addEventListener('click',()=>{open?__cmOpenDirs.delete(key):__cmOpenDirs.add(key); renderFileTree();});
    frag.appendChild(row); if(open)renderTreeNode(node.dirs[name],depth+1,key,frag);
  });
  node.files.sort((a,b)=>a.name.localeCompare(b.name)).forEach(file=>{
    const row=treeRow('f file',file.name,depth,''); row.title=file.path;
    if(file.path===__cmSelectedFile)row.classList.add('sel');
    row.addEventListener('click',()=>selectFile(file.path));
    frag.appendChild(row);
  });
}
function selectFile(name){
  __cmSelectedFile=name; showFileByName(name);
  document.querySelectorAll('#cmTree .file').forEach(e=>e.classList.toggle('sel',e.title===name));
}
function showFileByName(name){
  const view=document.getElementById('cmView'); view.innerHTML='';
  const dark=document.documentElement.getAttribute('data-theme')==='dark';
  const mode=/\.(ts|js|tsx|jsx|json)$/.test(name)?{name:'javascript',json:/\.json$/.test(name)}:'python';
  CodeMirror(view,{value:__cmFiles[name]||'',mode:mode,readOnly:true,lineNumbers:true,
    theme:dark?'material-darker':'default',viewportMargin:20});
}
function closeCode(){document.getElementById('codeModal').classList.remove('open');}
function downloadZip(){const zip=new JSZip();Object.entries(__cmFiles).forEach(([p,c])=>zip.file(p,c));
  zip.generateAsync({type:'blob'}).then(b=>{const a=document.createElement('a');
    a.href=URL.createObjectURL(b);a.download=(__cmTitle.replace(/[^a-z0-9_.-]+/gi,'-'))+'.zip';a.click();});}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeCode();});
updateThemeIcon();
// timed-out cells are SKIPPED (excluded from the % above) — surfaced at the end so a slow run is transparent
(function(){try{
  var sk=(typeof RUN!=='undefined'&&RUN&&RUN.skipped)||[];
  if(!sk.length)return;
  var esc=function(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});};
  var host=document.querySelector('main')||document.body;
  var sec=document.createElement('section');
  sec.style.cssText='max-width:1100px;margin:24px auto 40px;padding:0 20px';
  sec.innerHTML='<h2 style="display:flex;align-items:center;gap:8px"><span style="width:12px;height:12px;border-radius:3px;background:#9aa0b4;display:inline-block"></span>Skipped — excluded from the % ('+sk.length+')</h2>'+
    '<div style="color:var(--muted);font-size:13px;margin:4px 0 10px">Not scored (timed out, or the harness cannot receive the asset) and EXCLUDED from the percentages above — not counted as pass or fail.</div>'+
    '<table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr style="text-align:left;color:var(--muted)"><th style="padding:6px 8px">ITEM</th><th style="padding:6px 8px">HARNESS</th><th style="padding:6px 8px">REASON</th></tr></thead><tbody>'+
    sk.map(function(x){return '<tr style="border-top:1px solid var(--line)"><td style="padding:6px 8px">'+esc(x.item||x.case_id)+'</td><td style="padding:6px 8px">'+esc(x.harness||x.harness_id)+'</td><td style="padding:6px 8px;color:var(--muted)">'+esc(x.reason||'timed out')+'</td></tr>';}).join('')+
    '</tbody></table>';
  var footer=document.getElementById('method');
  if(footer)footer.before(sec);else host.appendChild(sec);
}catch(e){}})();
"""
