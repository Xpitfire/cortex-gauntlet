"""Self-contained exhibits for the fixed June 2026 cohorts discussed in the paper.

Values are publication snapshots, not live benchmark queries. Tables and vector
charts share these values; the release proof reconciles them with source records.
"""
import re
from html import escape

ARMS = ("Codex raw", "Cortex over Codex", "Claude raw", "Cortex over Claude", "OpenCode")
MODELS = ("Codex", "Codex", "Claude", "Claude", "OpenCode")
ROLES = ("raw", "+ Cortex", "raw", "+ Cortex", "reference")
COLORS = ("var(--muted)", "var(--accent)", "var(--muted)", "var(--accent)", "var(--muted)")
QUALITY = (
    ("Secret utilities", ((3, 3), (3, 3), (3, 3), (3, 3), (3, 3))),
    ("Input parsing", ((2, 2), (2, 2), (2, 2), (2, 2), (2, 2))),
    ("Database access", ((1, 1), (1, 1), (1, 1), (1, 1), (0, 1))),
    ("Upload API", ((0, 1), (2, 2), (0, 1), (2, 2), (0, 1))),
    ("Web security", ((7, 7), (7, 7), (7, 7), (7, 7), (0, 1))),
    ("Shopping cart", ((7, 8), (7, 8), (7, 8), (7, 8), (0, 1))),
)
QUALITY_MEANS = (0.8125, 0.9792, 0.8125, 0.9792, 0.3333)
REPAIR = (
    ("Even-value sum", ((1, 1),) * 5),
    ("Stack removal", ((2, 2),) * 5),
    ("URL normalization", ((1, 1),) * 5),
    ("Pagination", ((1, 1), (1, 1), (1, 1), (1, 1), (0, 1))),
    ("Word counting", ((1, 1),) * 5),
    ("Lower clamp bound", ((1, 1),) * 5),
)
REPAIR_COMPOSITES = (0.9823, 0.9917, 0.9928, 0.9928, 0.8333)
TODO_FEATURES = ("Page title", "Input form", "List tasks", "Create task", "Read after write")
TODO_PASSES = ((1, 1, 1, 0, 0), (1, 1, 1, 1, 1), (1, 1, 1, 1, 1),
               (1, 1, 1, 1, 1), (1, 1, 1, 1, 1))
COMPONENTS = ("Functional", "VERTEX", "PWA / accessibility", "Visual similarity", "Code / architecture",
              "Robustness", "Code health", "Static security", "Composite")
WEIGHTS = (0.26, 0.14, 0.09, 0.16, 0.12, 0.08, 0.06, 0.09)
STORE_TWO = (
    (0.3636, 0.7273), (0.4309, 0.5271), (0.8750, 0.6250), (0.5930, 0.6763),
    (0.7682, 0.7628), (1.0, 1.0), (1.0, 1.0), (1.0, 1.0), (0.6507, 0.7489),
)
STORE_FIVE = (
    (0.5455, 0.4545, 0.4545, 0.4545, 0.7273),
    (0.5214, 0.4776, 0.4512, 0.4199, 0.5070),
    (1.0, 0.8750, 0.7500, 0.6250, 0.6250),
    (0.6154, 0.6138, 0.6509, 0.6242, 0.6605),
    (0.7328, 0.7328, 0.7563, 0.7519, 0.6591),
    (1.0, 1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0, 0.6),
    (1.0, 1.0, 1.0, 1.0, 1.0), (0.7212, 0.6799, 0.6737, 0.6533, 0.7071),
)
QE_TWO = ((0, 0.4309, 0.4142), (2, 0.5271, 0.5465))
QE_FIVE = ((0, 0.5214, 0.6026), (1, 0.4776, 0.6465), (2, 0.4512, 0.5971),
           (3, 0.4199, 0.5126), (4, 0.5070, 0.6159))


def _text(x, y, value, *, size=16, anchor="start", color="var(--ink)", bold=False):
    weight = ' font-weight="600"' if bold else ""
    return (f'<text x="{x:g}" y="{y:g}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{color}"{weight}>{escape(str(value))}</text>')


def _line(x1, y1, x2, y2, *, color="var(--line)", dashed=False):
    dash = ' stroke-dasharray="5 5"' if dashed else ""
    return (f'<path d="M{x1:g} {y1:g}L{x2:g} {y2:g}" fill="none" '
            f'stroke="{color}" stroke-width="1.5"{dash}/>')


def _svg(height, label, body):
    return (f'<svg viewBox="0 0 760 {height}" xmlns="http://www.w3.org/2000/svg" '
            f'class="figsvg" role="img" aria-label="{escape(label)}" '
            'font-family="Arial, Helvetica, sans-serif">' + "".join(body) + '</svg>')


def _figure(number, svg, caption):
    return (f'<figure class="fig" id="fig-{number}"><div class="figure-graphic" '
            f'role="group" tabindex="0" aria-label="Figure {number}">{svg}</div>'
            f'<figcaption>Figure {number}. {caption}</figcaption></figure>')


def _headers(indices=range(5)):
    return tuple(f'{MODELS[i]}<br>{ROLES[i]}' for i in indices)


def _table(number, headers, rows, caption):
    head = ''.join(f'<th>{h}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(str(c))}</td>' for c in row) + '</tr>' for row in rows)
    return (f'<figure class="tbl" id="tbl-{number}"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table><figcaption>Table {number}. {caption}</figcaption></figure>')


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    return tuple(order.index(i) + 1 for i in range(len(values)))


def _marker(arm, x, y, radius=7):
    color = COLORS[arm]
    if arm == 0:
        shape = f'<circle cx="{x:g}" cy="{y:g}" r="{radius}"/>'
    elif arm == 1:
        shape = f'<rect x="{x-radius:g}" y="{y-radius:g}" width="{radius*2}" height="{radius*2}"/>'
    elif arm == 2:
        shape = f'<path d="M{x:g} {y-radius:g}L{x+radius:g} {y+radius:g}H{x-radius:g}Z"/>'
    elif arm == 3:
        shape = f'<path d="M{x:g} {y-radius:g}L{x+radius:g} {y:g}L{x:g} {y+radius:g}L{x-radius:g} {y:g}Z"/>'
    else:
        return (f'<path d="M{x-radius:g} {y-radius:g}L{x+radius:g} {y+radius:g}'
                f'M{x-radius:g} {y+radius:g}L{x+radius:g} {y-radius:g}" '
                f'stroke="{color}" stroke-width="3" fill="none"/>')
    return f'<g fill="{color}">{shape}</g>'


def capability_figure():
    panels = (
        (195, "Code quality", "6 tasks", QUALITY_MEANS,
         tuple(f'{v*100:.2f}%' for v in QUALITY_MEANS), "0", "50", "100%"),
        (390, "Issue repair", "6 issues", (1, 1, 1, 1, 5/6),
         ("6/6", "6/6", "6/6", "6/6", "5/6"), "0", "3", "6"),
        (585, "To-do app", "1 brief; 5 probes", tuple(sum(v)/5 for v in TODO_PASSES),
         tuple(f'{sum(v)}/5' for v in TODO_PASSES), "0", "2.5", "5"),
    )
    body = []
    for x, title, sample, values, labels, *ticks in panels:
        body += [_text(x+60, 24, title, size=18, anchor="middle", bold=True),
                 _text(x+60, 49, sample, size=15, anchor="middle", color="var(--muted)")]
        for tick, label in enumerate(ticks):
            xpos = x + tick*60
            body += [_line(xpos, 72, xpos, 355, dashed=True),
                     _text(xpos, 382, label, size=14, anchor="middle")]
        for i, value in enumerate(values):
            y = 98+i*55
            body.append(f'<rect x="{x}" y="{y-10}" width="{120*value:g}" height="20" rx="3" fill="{COLORS[i]}"/>')
            body.append(_text(x+170, y+5, labels[i], size=14, anchor="end"))
    for i, name in enumerate(ARMS):
        body.append(_text(10, 103+i*55, name, size=16))
    body.append(_text(380, 416, "Different outcomes and denominators; no cross-task composite", size=15,
                      anchor="middle", color="var(--muted)"))
    return _figure(5, _svg(438, "Recorded coding outcomes in three distinct pilot studies", body),
                   'Recorded coding outcomes: task-macro behavioral coverage (left), resolved issues (middle), '
                   'and passed to-do features (right). Each row is a harness configuration; higher values are '
                   'better within each panel, not comparable units across panels. Exact cells and evaluation '
                   'limits are in Tables 4–6. The upload task accounts for the paired quality difference; '
                   'there is no paired repair-resolution difference. These small historical pilots are not causal tests.')


def qe_figure():
    body = []
    for x, title, pairs, rho in ((72, "Two-arm pool", QE_TWO, "1.0"),
                                 (450, "Five-arm pool", QE_FIVE, "0.6")):
        n = len(pairs)
        ar, qr = _ranks([p[1] for p in pairs]), _ranks([p[2] for p in pairs])
        body += [_text(x+120, 25, title, size=19, anchor="middle", bold=True),
                 _text(x+120, 50, f'Spearman correlation {rho}', size=15, anchor="middle")]
        for rank in range(1, n+1):
            offset = (rank-1)/(n-1)*230
            body += [_line(x+offset, 82, x+offset, 312, dashed=True),
                     _line(x, 82+offset, x+230, 82+offset, dashed=True),
                     _text(x+offset, 335, rank, size=14, anchor="middle"),
                     _text(x-17, 87+offset, rank, size=14, anchor="end")]
        body.append(_line(x, 82, x+230, 312, color="var(--muted)", dashed=True))
        for i, (arm, _, _) in enumerate(pairs):
            body.append(_marker(arm, x+(ar[i]-1)/(n-1)*230, 82+(qr[i]-1)/(n-1)*230))
        body.append(_text(x+115, 363, "Authored rank (1 = highest)", size=15, anchor="middle"))
    body.append('<g transform="translate(18 198) rotate(-90)">' +
                _text(0, 0, "Estimated-reference rank", size=15, anchor="middle") + '</g>')
    for i, name in enumerate(ARMS):
        x, y = 38+(i%3)*250, 402+(i//3)*32
        body += [_marker(i, x, y-5, radius=6), _text(x+16, y, name, size=15)]
    return _figure(6, _svg(458, "Authored versus estimated VERTEX rankings in two storefront pools", body),
                   'Within-pool VERTEX rank agreement on the same storefront brief. Each marker is one built '
                   'application; the dashed diagonal is identical ordering, not score calibration. Rank 1 is highest '
                   'on both axes. The two-arm pool needs only a matching order to obtain correlation 1; the five-arm '
                   'pool swaps the first and third positions. Exact scores and ranks are in Table 9. Pool-based peer '
                   'reference construction differs between the panels; they are not independent task replications.')


def feature_figure():
    body = [_text(380, 26, "Final checklist outcomes — not an execution timeline", size=19,
                  anchor="middle", bold=True)]
    for j, name in enumerate(("Page", "Form", "List", "Create", "Readback")):
        x = 280+j*95
        body += [_text(x, 65, name, size=16, anchor="middle"), _line(x, 78, x, 325, dashed=True),
                 _text(x, 353, f'{j/4:g}', size=15, anchor="middle")]
    for i, values in enumerate(TODO_PASSES):
        y = 108+i*49
        body.append(_text(12, y+5, ARMS[i]))
        for j, value in enumerate(values):
            body.append(f'<circle cx="{280+j*95}" cy="{y}" r="9" fill="{COLORS[i] if value else "none"}" '
                        f'stroke="{COLORS[i]}" stroke-width="2"/>')
    body += [_text(470, 383, "Normalized feature-list position", size=16, anchor="middle"),
             _text(380, 416, "Filled = pass; open = fail. One candidate per arm.", size=15, anchor="middle")]
    return _figure(7, _svg(438, "Final feature positions, with no temporal interpretation", body),
                   'The five observed final feature outcomes in checklist order. Position is the feature index '
                   'divided by four; it is not elapsed time, a repair pass, or a milestone observation. Table 6 '
                   'defines the checks and provides the binary data. No interpolation or completion-decay curve '
                   'is supported by these observations.')


def _shade(value):
    low, high = (238, 242, 247), (23, 75, 143)
    return '#' + ''.join(f'{round(a+(b-a)*value):02x}' for a, b in zip(low, high, strict=True))


def storefront_figure():
    body = []
    for top, title, indices, data in ((0, "Two-arm storefront pool", (0, 2), STORE_TWO),
                                     (402, "Five-arm storefront pool", tuple(range(5)), STORE_FIVE)):
        body.append(_text(380, top+25, title, size=19, anchor="middle", bold=True))
        width = 470/len(indices)
        for col, arm in enumerate(indices):
            x = 255+col*width+width/2
            body += [_text(x, top+56, MODELS[arm], size=16, anchor="middle"),
                     _text(x, top+76, ROLES[arm], size=14, anchor="middle")]
        for row, (label, values) in enumerate(zip(COMPONENTS, data, strict=True)):
            y = top+92+row*31
            body.append(_text(12, y+21, label, size=16, bold=row==8))
            for col, value in enumerate(values):
                x = 255+col*width
                body.append(f'<rect x="{x:g}" y="{y}" width="{width-3:g}" height="28" fill="{_shade(value)}"/>')
                body.append(_text(x+(width-3)/2, y+20, f'{value:.2f}', size=15, anchor="middle",
                                  color="#ffffff" if value>=0.65 else "#17243b", bold=row==8))
    body.append(_text(380, 804, "Recorded scores: pale 0 → dark 1. Equal shading does not mean equal validity.",
                      size=14, anchor="middle"))
    return _figure(8, _svg(826, "All storefront score components for both candidate pools", body),
                   'Recorded storefront score profiles, rounded to two decimals for display. Tables 7–8 retain '
                   'four-decimal values and distinguish the two separately captured candidate pools. Component '
                   'scores are proxies, not success probabilities; perfect recorded robustness or static-security '
                   'values do not establish exhaustive testing or absence of vulnerabilities. The composite is a '
                   'weighted, build-gated combination, not an additional independent measurement.')




def appendix_tables():
    quality = [(label, *(f'{p}/{n}' for p, n in values)) for label, values in QUALITY]
    quality.append(("Macro coverage", *(f'{v:.4f}' for v in QUALITY_MEANS)))
    repair = [(label, *(f'{p}/{n}' for p, n in values)) for label, values in REPAIR]
    repair += [("Issues resolved", "6/6", "6/6", "6/6", "6/6", "5/6"),
               ("Composite", *(f'{v:.4f}' for v in REPAIR_COMPOSITES))]
    todo = [(name, *(str(values[i]) for values in TODO_PASSES)) for i, name in enumerate(TODO_FEATURES)]
    todo.append(("Passed features", *(f'{sum(values)}/5' for values in TODO_PASSES)))
    tables = {
        4: _table(4, ("Task", *_headers()), quality,
                  'Quality: passing / collected behavioral checks in each task–arm outcome. The last row '
                  'is the equal-weight mean of the six task rates, not pooled test success. Collected upload '
                  'test totals differ across arms. Four OpenCode generation failures remain as zero-scored '
                  'outcomes. These test counts are not the number of natural-language requirements certified.'),
        5: _table(5, ("Issue", *_headers()), repair,
                  'Repair: passing / collected issue tests, resolved issues, and stored composite means. '
                  'There are no auxiliary held-out or regression tests in any row. Empty auxiliary groups '
                  'received passing defaults; strict-rate fields therefore add no independent evidence. '
                  'The paired Codex composite difference reflects patch minimality, not extra resolved issues.'),
        6: _table(6, ("Final feature check", *_headers()), todo,
                  'To-do application: one means the check passed and zero means it failed. All five '
                  'candidates recorded successful builds. Read after write means a newly created task is '
                  'returned in the same session, not persistence across process restarts. These are five '
                  'candidate applications with five checks each, not 25 independent tasks.'),
    }
    for number, data, indices, title in ((7, STORE_TWO, (0, 2), 'Two-arm storefront pool'),
                                       (8, STORE_FIVE, tuple(range(5)), 'Five-arm storefront pool')):
        rows = [(label, *(f'{v:.4f}' for v in values)) for label, values in zip(COMPONENTS, data, strict=True)]
        tables[number] = _table(number, ("Component", *_headers(indices)), rows,
                                f'{title}. One built candidate per arm; these are retained, subsequently '
                                'rescored outcomes. All scores are in [0,1]. Component meanings and '
                                'weights are specified in Appendix B.4; proxy scores of one do not certify '
                                'exhaustive correctness. The composite uses authored-reference VERTEX, not '
                                'the separate estimated-reference diagnostic.')
    qe = []
    for label, pairs in (("Two-arm", QE_TWO), ("Five-arm", QE_FIVE)):
        ar, qr = _ranks([p[1] for p in pairs]), _ranks([p[2] for p in pairs])
        for i, (arm, authored, estimated) in enumerate(pairs):
            qe.append((label, ARMS[arm], f'{authored:.4f}', f'{estimated:.4f}', f'{ar[i]} → {qr[i]}'))
    tables[9] = _table(9, ("Candidate pool", "Configuration", "Authored VERTEX", "Estimated VERTEX", "Rank change"), qe,
                       'Exact VERTEX pairs and within-pool ranks (1 = highest) for Figure 6. Rank arrows '
                       'mean authored to estimated rank, not improvement over time. The two pools share '
                       'one storefront brief; seven pairs are not seven independent task samples. '
                       'Peer-consensus descriptors are unavailable with only two arms.')
    return tables


def render_exhibits(source: str) -> str:
    exhibits = {
        "__FIG_5__": capability_figure(),
        "__FIG_6__": qe_figure(),
        "__FIG_7__": feature_figure(),
        "__FIG_8__": storefront_figure(),
        **{f"__TABLE_{number}__": table for number, table in appendix_tables().items()},
    }
    return re.sub(r"__(?:FIG|TABLE)_\d+__", lambda match: exhibits[match[0]], source)
