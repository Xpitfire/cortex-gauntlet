"""Visual entry points around the existing, screened interactive reports."""

from __future__ import annotations

import json
import re
from html import escape

from .redaction import PUBLIC_EVIDENCE_REDACTED
from .report_common import (
    COMMON_JS, COMPARISON_CSS, COMPARISON_JS, REPORT_CSS, REPORT_HEAD, navbar,
)

# These describe saved metrics, not a new cross-track score.
# Tuple fields: metric path, label, lower-is-better flag, description.
HIGHLIGHTS = {
    "security": (
        "asr.rate",
        "Attack success",
        True,
        "Attacks, defenses, and the cost of refusing too much.",
    ),
    "quality": (
        "checks.overall.rate",
        "Checks passed",
        False,
        "Requirement coverage, code health, and output security.",
    ),
    "generative": (
        "completeness",
        "Feature completeness",
        False,
        "Feature delivery, build reliability, and generated app galleries.",
    ),
    "project": (
        "composite",
        "Build composite",
        False,
        "Whole-repository builds, signal vectors, and visual targets.",
    ),
    "repo": (
        "resolution_rate",
        "Issues resolved (shown)",
        False,
        "Issue resolution, held-out checks, and patch inspection.",
    ),
}


def category_path(track: str, collection: str | None = None, *, default: str = "reference") -> str:
    slug = "bugfix" if track == "repo" else track
    return (
        f"{slug}.html"
        if collection is None or collection == default
        else f"{slug}-{collection}.html"
    )


def _collections(package: dict) -> list[dict]:
    return sorted(package["collections"], key=lambda c: c["id"] != "reference")


def _source_label(collection: dict) -> str:
    return {"reference": "Modeled reference", "captured": "Captured outputs"}.get(
        collection["id"], collection["title"]
    )


def _experiment_cards(metas: list[dict], root: str) -> str:
    cards = []
    for meta in sorted(metas, key=lambda m: (m["cases"], m["created_at"]), reverse=True):
        rid = escape(meta["run_id"])
        search = escape(f"{meta['run_id']} {meta['created_at']}".lower())
        cards.append(
            f'<a class="experiment-card filter-item" data-search="{search}" '
            f'href="{root}runs/{rid}/report.html">'
            f'<span class="eyebrow">{escape(meta["created_at"][:10])} · '
            f"{'Qualified' if meta['qualified'] else 'Historical run'}</span>"
            f"<strong>{meta['cases']} cases <span>× {meta['harnesses']} harnesses</span></strong>"
            f'<span class="run-identity">{rid}</span>'
            '<span class="card-action">Plots, evidence &amp; explorer →</span></a>'
        )
    return _filter_panel("experiments", "Explore experiments", "Search run IDs or dates", cards)


def _filter_panel(name: str, title: str, placeholder: str, cards: list[str]) -> str:
    return (
        f'<section class="visual-section filter-panel" id="{name}">'
        f'<div class="section-heading"><div><p class="eyebrow">Inspect the evidence</p>'
        f'<h2>{title}</h2></div><span class="filter-count" aria-live="polite">{len(cards)} items</span></div>'
        f'<label class="search-label">{placeholder}<input type="search" '
        f'aria-label="{placeholder}" placeholder="{placeholder}"></label>'
        f'<div class="inspect-grid">{"".join(cards)}</div>'
        '<button class="tool show-more" type="button">Show all items</button></section>'
    )


def _dataset(record: dict, current_path: str) -> str:
    cards = []
    for case in record.get("cases", []):
        cid = str(case.get("id", ""))
        title = str(case.get("title") or case.get("name") or cid)
        tags = [
            str(case[k])
            for k in ("surface", "technique", "modality", "language", "objective")
            if case.get(k)
        ]
        prompt = next(
            (
                case[k]
                for k in ("instruction", "prompt", "problem_statement", "description")
                if case.get(k)
            ),
            None,
        )
        if prompt == PUBLIC_EVIDENCE_REDACTED:
            content = (
                '<p class="hint">Prompt text is withheld in this restricted evidence view.</p>'
            )
        elif isinstance(prompt, str):
            content = f"<pre>{escape(prompt)}</pre>"
        else:
            content = '<p class="hint">No prompt text was recorded in this source.</p>'
        specs = []
        for field in ("requirements", "features"):
            for item in case.get(field, []) if isinstance(case.get(field), list) else []:
                if isinstance(item, dict):
                    text = item.get("description") or item.get("title") or item.get("id")
                    if isinstance(text, str) and text != PUBLIC_EVIDENCE_REDACTED:
                        specs.append(f"<li>{escape(text)}</li>")
        if specs:
            content += '<ul class="dataset-specs">' + "".join(specs) + "</ul>"
        search = escape(" ".join([cid, title, *tags]).lower())
        cards.append(
            f'<details class="dataset-card filter-item" data-search="{search}">'
            f'<summary><span class="eyebrow">{escape(cid)}</span><strong>{escape(title)}</strong>'
            f'<span class="dataset-tags">{escape(" · ".join(tags))}</span></summary>'
            f'<div class="dataset-content">{content}'
            f'<a href="../../{current_path}#rows">Open scored results ↓</a></div></details>'
        )
    return _filter_panel("dataset", "Inside the dataset", "Search dataset items", cards)


def render_category(
    report_html: str,
    record: dict,
    source: dict,
    collection: dict,
    package: dict,
    metas: list[dict],
    track_names: dict,
) -> str:
    """Decorate a canonical run report; its data, charts, modals and asset base stay intact."""
    track = source["track"]
    default = _collections(package)[0]["id"]
    current = category_path(track, collection["id"], default=default)
    track_note = next(t.get("note", "") for t in collection["tracks"] if t["track"] == track)
    tabs = []
    for other in _collections(package):
        if any(t["track"] == track for t in other["tracks"]):
            active = ' aria-current="page"' if other["id"] == collection["id"] else ""
            tabs.append(
                f'<a{active} href="../../{category_path(track, other["id"], default=default)}">{escape(_source_label(other))}</a>'
            )
    intro = (
        '<section class="category-context"><div class="source-tabs" aria-label="Historical source">'
        + "".join(tabs)
        + "</div>"
        f"<p>{escape(HIGHLIGHTS[track][3])}</p>"
        f'<p class="hint">{escape(collection.get("note", ""))}</p>'
        f'<p class="hint">{escape(track_note)}</p>'
        '<div class="category-jumps">'
        f'<a href="../../{current}#cards">Highlights &amp; plots</a>'
        f'<a href="../../{current}#dataset">Dataset · {source["cases"]} items</a>'
        f'<a href="../../{current}#experiments">Experiments · {len(metas)} runs</a>'
        f'<a href="../../{source["href"]}">Original report ↗</a>'
        f'<a href="../../results.html#package-{track}">All result tables ↗</a></div></section>'
    )
    title = track_names[track][0]
    html = report_html.replace("<head>", f'<head><base href="runs/{escape(source["run_id"])}/">', 1)
    html = html.replace("<body>", '<body class="category-page">', 1)
    html = html.replace("</head>", f"<style>{VISUAL_CSS}</style></head>", 1)
    html = re.sub(
        r"<title>.*?</title>", f"<title>Gauntlet — {escape(title)}</title>", html, count=1
    )
    html = re.sub(r"<h1>.*?</h1>", f"<h1>{escape(title)}</h1>", html, count=1)
    html = html.replace("</header>", "</header>" + intro, 1)
    footer = '<footer id="method">'
    if footer not in html:
        raise ValueError(f"Report is missing its explorer footer: {track}")
    html = html.replace(
        footer, _dataset(record, current) + _experiment_cards(metas, "../../") + footer, 1
    )
    return html.replace("</body>", f"<script>{FILTER_JS}</script></body>", 1)


def render_overview(
    package: dict, metas: list[dict], track_names: dict, links: dict, published_records: dict
) -> str:
    collections = _collections(package)
    default = collections[0]
    tabs = "".join(
        f'<button type="button" data-collection="{escape(c["id"])}" '
        f'aria-pressed="{str(c["id"] == default["id"]).lower()}">{escape(_source_label(c))}</button>'
        for c in collections
    )
    track_cards = []
    for track, (name, color, codename) in track_names.items():
        if not any(t["track"] == track for t in default["tracks"]):
            continue
        _path, label, _lower_is_better, description = HIGHLIGHTS[track]
        track_cards.append(
            f'<article class="track-card" data-track="{track}" style="--track-color:{color}">'
            f'<a class="track-heading" href="{category_path(track, default["id"], default=default["id"])}">'
            f'<span class="eyebrow">{escape(codename)}</span><h2>{escape(name)}</h2></a>'
            f'<p>{escape(description)}</p><div class="track-highlight"><strong data-best>—</strong>'
            f'<span><b data-leader></b><small>{escape(label)} · <span data-rank-note></span></small></span></div>'
            f'<div class="mini-chart" id="plot-{track}" role="img" aria-label="{escape(label)} by harness"></div>'
            '<p class="source-caption" data-source-caption></p>'
            f'<a class="card-action" data-category-link href="{category_path(track, default["id"], default=default["id"])}">Explore plots &amp; dataset →</a></article>'
        )
    payload = {
        "collections": collections,
        "security_counts": {
            t["primary"]["run_id"]: {
                row["id"]: published_records[t["primary"]["run_id"]]
                .get("aggregates", {}).get("per_harness", {})
                .get(row["id"], {}).get("asr", {}).get("n")
                for row in t["primary"]["rows"]
            }
            for c in collections for t in c["tracks"] if t["track"] == "security"
        },
        "highlights": HIGHLIGHTS,
        "paths": {
            c["id"]: {
                t["track"]: category_path(t["track"], c["id"], default=default["id"])
                for t in c["tracks"]
            }
            for c in collections
        },
    }
    html = OVERVIEW.replace("__HEAD__", REPORT_HEAD).replace(
        "__CSS__", REPORT_CSS + COMPARISON_CSS + VISUAL_CSS
    )
    return (
        html.replace("__NAV__", navbar("index.html", "Overview", links))
        .replace("__TABS__", tabs)
        .replace("__TRACKS__", "".join(track_cards))
        .replace("__COUNT__", str(len(metas)))
        .replace("__DATA__", json.dumps(payload).replace("</", "<\\/"))
        .replace("__COMMON_JS__", COMMON_JS + COMPARISON_JS)
        .replace("__OVERVIEW_JS__", OVERVIEW_JS)
    )


VISUAL_CSS = r"""
.visual-home .wrap,.category-page .wrap{max-width:1240px}
.visual-home a,.category-page .visual-section a,.category-context a{color:var(--accent)}
.visual-home .eyebrow,.category-page .eyebrow{display:block;font-size:11px;font-weight:750;letter-spacing:1.3px;text-transform:uppercase;color:var(--muted)}
.visual-hero{display:grid;grid-template-columns:1fr 1.08fr;gap:32px;align-items:center;margin:22px 0 30px}
.visual-hero h1{font-size:clamp(34px,4vw,54px);line-height:1.07;letter-spacing:-1.8px;margin:16px 0 20px}
.visual-hero h1 span{color:var(--accent)}
.visual-hero p{font-size:16px;color:var(--muted);line-height:1.7}
.hero-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}
.hero-actions a,.category-jumps a{display:inline-block;border:1px solid var(--line);padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:600}
.hero-actions .primary-action{background:var(--accent);color:white;border-color:var(--accent)}
.spotlight{border:1px solid var(--line);border-radius:24px;padding:25px;background:radial-gradient(ellipse at top right,rgba(109,94,251,.14),transparent 65%),var(--card)}
.spotlight h2{margin:8px 0 0;font-size:20px}.spotlight .chart{height:300px}
.spotlight .source-caption{min-height:35px}.spotlight .metric-note{font-size:12px;color:var(--muted)}
.section-heading{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:18px}
.section-heading h2{font-size:25px;margin:6px 0}.section-heading p{margin:0;color:var(--muted)}
.source-tabs{display:flex;gap:5px;padding:5px;background:var(--card);border:1px solid var(--line);border-radius:12px;width:fit-content;flex-wrap:wrap}
.source-tabs button,.source-tabs a{border:0;padding:9px 14px;border-radius:8px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none;background:transparent;color:var(--muted)}
.source-tabs [aria-pressed="true"],.source-tabs [aria-current="page"]{background:var(--accent);color:white}
.source-explanation{color:var(--muted);font-size:13px;line-height:1.6;margin:14px 0 24px;max-width:950px}
.track-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
.track-card{position:relative;min-width:0;padding:24px;border:1px solid var(--line);border-radius:18px;background:var(--card);border-top:3px solid var(--track-color)}
.track-card .track-heading{color:var(--ink);text-decoration:none}.track-card h2{font-size:19px;line-height:1.3;margin:6px 0 12px}
.track-card p{color:var(--muted);font-size:13px;min-height:42px}.track-highlight{display:flex;align-items:center;gap:12px;margin:20px 0 4px}
.track-highlight strong{font-size:31px;letter-spacing:-1px;color:var(--metric-neutral)}.track-highlight.is-leader strong{color:var(--metric-good)}.track-highlight span{font-size:12px}.track-highlight small{display:block;color:var(--muted);margin-top:5px;font-size:11px}.track-highlight small span{font-size:inherit}
.mini-chart{height:196px;min-width:0}.source-caption{font-size:11px!important;line-height:1.5;overflow-wrap:anywhere}
.card-action{display:block;font-size:13px;font-weight:700;text-decoration:none;margin-top:14px}
.archive-card{--track-color:#6d5efb;display:flex;flex-direction:column;justify-content:center;background:linear-gradient(145deg,rgba(109,94,251,.1),transparent),var(--card)}
.archive-card .archive-number{font-size:70px;line-height:1;color:var(--accent);font-weight:750;letter-spacing:-3px;margin:20px 0}
.visual-home footer{margin-top:34px}.visual-section{scroll-margin-top:90px;margin:36px 0}
.category-page .package-note{display:none}.category-page .hero{margin-bottom:18px}.category-page .hero h1{font-size:34px;letter-spacing:-.8px}
.category-context{padding:22px;border:1px solid var(--line);border-radius:16px;background:var(--card);margin-bottom:24px}
.category-context p{margin:12px 0}.category-jumps{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.category-jumps a{font-size:12px;padding:8px 11px}
.category-page #cards,.category-page #rows{scroll-margin-top:90px}.category-page .cards{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.category-page .cards .card{padding:16px;min-width:0}.category-page .cards .metric{font-size:30px}.category-page .cards h3{overflow-wrap:anywhere}
.search-label{display:block;color:var(--muted);font-size:12px;margin:0 0 18px}.search-label input{display:block;width:min(100%,440px);margin-top:7px;padding:11px 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font:inherit;font-size:14px}
.inspect-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;align-items:start}
.experiment-card,.dataset-card{display:block;border:1px solid var(--line);border-radius:13px;background:var(--card);min-width:0;overflow:hidden}
.experiment-card{padding:18px;text-decoration:none}.experiment-card:hover{border-color:var(--accent)}
.experiment-card strong{display:block;color:var(--ink);font-size:19px;margin:12px 0}.experiment-card strong span{font-size:12px;color:var(--muted);font-weight:400}
.run-identity{display:block;overflow-wrap:anywhere;font-size:11px;color:var(--muted)}
.dataset-card summary{cursor:pointer;padding:18px}.dataset-card summary strong{display:block;font-size:14px;margin:10px 0;overflow-wrap:anywhere}
.dataset-tags{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.dataset-content{border-top:1px solid var(--line);padding:16px;font-size:12px}
.dataset-content pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;margin:0 0 15px;line-height:1.6}.dataset-specs{max-height:240px;overflow:auto;padding-left:18px}
.filter-count{font-size:12px;color:var(--muted)}.filter-panel .show-more{margin-top:16px}.filter-item[hidden]{display:none}
@media(max-width:1050px){.track-grid,.inspect-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.visual-hero{gap:20px}.visual-hero h1{font-size:39px}.category-page .cards{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}}
@media(max-width:700px){.visual-home .wrap,.category-page .wrap{padding:20px 16px 50px}.visual-hero{grid-template-columns:1fr;margin-top:0}.visual-hero h1{font-size:38px}.spotlight{padding:18px}.track-grid,.inspect-grid{grid-template-columns:1fr}.section-heading{align-items:start;flex-direction:column}.category-context{padding:16px}.category-page .hero{display:block}.category-page .hero .tools{margin-top:14px}.category-page .block{overflow-x:auto}.category-page .grid2{grid-template-columns:1fr}.category-page .chart{min-width:0}.category-page h1{font-size:28px!important}.category-page .shots{overflow-x:auto}}
"""

FILTER_JS = r"""
document.querySelectorAll('.filter-panel').forEach(panel=>{
  const items=[...panel.querySelectorAll('.filter-item')], search=panel.querySelector('input'), more=panel.querySelector('.show-more');
  let expanded=false;
  function filter(){const q=search.value.toLowerCase().trim();let matched=0,shown=0;
    items.forEach(item=>{const matches=item.dataset.search.includes(q);if(matches)matched++;
      const visible=matches&&(q||expanded||shown<6);item.hidden=!visible;if(visible)shown++;});
    panel.querySelector('.filter-count').textContent=`${shown} of ${matched} items`;
    more.hidden=!!q||matched<=6;more.textContent=expanded?'Show fewer items':`Show all ${matched} items`;}
  search.addEventListener('input',filter);more.addEventListener('click',()=>{expanded=!expanded;filter();});filter();
});
"""

OVERVIEW = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Gauntlet — Overview</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>__HEAD__<style>__CSS__</style></head>
<body class="visual-home">__NAV__<main class="wrap">
<section class="visual-hero"><div><p class="eyebrow">Gauntlet / agent evaluation</p>
<h1>Five tracks.<br><span>A closer look.</span></h1>
<p>Explore safety, code quality, generative builds, full projects, and bug fixes — from the headline plots down to individual cases and generated artifacts.</p>
<div class="hero-actions"><a class="primary-action" id="hero-explore" href="security.html">Explore Security →</a><a href="results.html">All results &amp; provenance</a><a href="https://github.com/Xpitfire/cortex-gauntlet" target="_blank" rel="noopener">GitHub</a></div>
<p class="metric-note">Historical results, with their original sources and limitations. No pooled score across unrelated experiments.</p></div>
<article class="spotlight"><p class="eyebrow">Security spotlight</p><h2>Fewest successful attacks first.</h2><p class="metric-note">ASR is a failure metric, not a capability score. Smaller is safer; it does not establish task usefulness.</p>
<div class="chart" id="overview-security" role="img" aria-label="Historical attack success by harness"></div><p class="source-caption" id="spotlight-source"></p></article></section>
<section class="visual-section"><div class="section-heading"><div><p class="eyebrow">Five ways to inspect an agent</p><h2>Follow the evidence.</h2></div>
<div class="source-tabs" aria-label="Overview source collection">__TABS__</div></div><p class="source-explanation" id="collection-context"></p>
<div class="track-grid">__TRACKS__<article class="track-card archive-card"><p class="eyebrow">The complete record</p><div class="archive-number">__COUNT__</div><h2>Experiments, not just highlights.</h2>
<p>Both historical collections, all retained runs, source provenance, and downloadable measurements. Nothing is averaged into a new overall score.</p><a class="card-action" href="results.html">Open the Results archive →</a></article></div></section>
<footer>Plots use saved per-harness values. Modeled references are not empirical performance claims; captured outputs retain their scoring and execution limits. Dataset, source code and media visibility follows each report's publication restrictions.</footer>
</main><script id="overview-data" type="application/json">__DATA__</script><script>__COMMON_JS__</script><script>__OVERVIEW_JS__</script></body></html>"""

OVERVIEW_JS = r"""
const OVERVIEW=JSON.parse(document.getElementById('overview-data').textContent);
let selectedCollection=OVERVIEW.collections[0].id;
const pct=v=>v==null?'Unavailable':(v*100).toFixed(1)+'%';
function shortHarnessLabel(row){return row.label.replace('Cortex [over ','Cortex / ').replace(']','');}
function overviewPlot(id,c,large=false){const dom=document.getElementById(id);if(!dom)return;
 const chart=echarts.getInstanceByDom(dom)||echarts.init(dom), rows=c.rows;
 comparisonCue(id,c.direction,large||!c.recorded?comparisonSummary(c,shortHarnessLabel,pct):'Ranked by recorded value');
 chart.setOption({animationDuration:350,grid:{left:large?158:132,right:48,top:8,bottom:38},
 tooltip:{trigger:'axis',axisPointer:{type:'shadow'},valueFormatter:v=>pct(v==null?null:v/100)},
 xAxis:{type:'value',min:0,max:100,name:c.direction==='lower'?'← Fewer failures':'More achieved →',nameLocation:'middle',nameGap:24,nameTextStyle:{color:axisInk(),fontSize:10},axisLabel:{color:axisInk(),formatter:'{value}%',fontSize:10},splitLine:{lineStyle:{color:gridInk(),type:'dashed'}}},
 yAxis:{type:'category',inverse:true,data:rows.map(r=>(Number.isFinite(c.value(r))&&!c.tied&&c.recorded>1?(rows.findIndex(x=>c.value(x)===c.value(r))+1)+' · ':'')+shortHarnessLabel(r)),axisTick:{show:false},axisLine:{show:false},axisLabel:{color:harnessInk(),fontSize:large?11:10,width:large?148:122,overflow:'truncate'}},
 series:[{type:'bar',barMaxWidth:large?28:15,data:rows.map(r=>({value:Number.isFinite(c.value(r))?c.value(r)*100:null,itemStyle:{color:comparisonColor(c,r),borderRadius:[0,4,4,0]}})),label:{show:true,position:'right',color:harnessInk(),fontSize:large?12:10,formatter:p=>p.value==null?'':p.value.toFixed(1)+'%'}}]},true);
}
function renderOverview(){const collection=OVERVIEW.collections.find(c=>c.id===selectedCollection);
 document.getElementById('collection-context').textContent=collection.note||collection.title;
 document.querySelectorAll('[data-collection]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.collection===selectedCollection)));
 collection.tracks.forEach(t=>{const source=t.primary, config=OVERVIEW.highlights[t.track], card=document.querySelector(`[data-track="${t.track}"]`);if(!card)return;
   const comparison=metricComparison(source.rows,r=>t.track==='security'&&!(OVERVIEW.security_counts[source.run_id]?.[r.id]>0)?null:r.values[config[0]],config[2]?'lower':'higher');
   card.querySelector('[data-best]').textContent=pct(comparison.best);
   card.querySelector('.track-highlight').classList.toggle('is-leader',comparison.leaders.length>0);
   card.querySelector('[data-leader]').textContent=comparison.leaders.length?comparison.leaders.map(shortHarnessLabel).join(' / '):comparison.tied?'Equal recorded values':comparison.recorded?shortHarnessLabel(comparison.rows[0]):'No recorded result';
   card.querySelector('[data-rank-note]').textContent=comparison.leaders.length?(comparison.direction==='lower'?'lowest recorded':'highest recorded'):comparison.recorded<2?'not ranked':'tied';
   card.querySelector('[data-source-caption]').textContent=`${source.cases} cases · ${source.cells}/${source.expected_cells} cells · ${source.run_id}`;
   card.querySelectorAll('.track-heading,[data-category-link]').forEach(a=>a.href=OVERVIEW.paths[collection.id][t.track]);
   overviewPlot('plot-'+t.track,comparison);
   if(t.track==='security'){overviewPlot('overview-security',comparison,true);document.getElementById('spotlight-source').textContent=`${collection.title} · ${source.cases} cases · ${source.run_id}`;document.getElementById('hero-explore').href=OVERVIEW.paths[collection.id][t.track];}
 });
}
document.querySelectorAll('[data-collection]').forEach(b=>b.addEventListener('click',()=>{selectedCollection=b.dataset.collection;renderOverview();}));
renderOverview();window.__charts=renderOverview;window.addEventListener('resize',()=>document.querySelectorAll('.mini-chart,#overview-security').forEach(d=>echarts.getInstanceByDom(d)?.resize()));
"""
