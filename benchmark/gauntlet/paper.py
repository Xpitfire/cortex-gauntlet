"""Build a source-only arXiv upload and PDF from the canonical web paper.

Pandoc and librsvg run at publication time only. The uploaded source compiles with
standard pdfLaTeX, without Python, Pandoc, SVG conversion, network or shell escape.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .docs import CITES, _paper_md
from .paths import ROOT
from .report_common import REPORT_CSS

PAPER_URL = "https://benchmark.cortex.a2olabs.com"
CORTEX_URL = "https://cortex.a2olabs.com"
REPOSITORY_URL = "https://github.com/Xpitfire/cortex-gauntlet"
PDF_NAME = "cortex-gauntlet.pdf"
SOURCE_NAME = "cortex-gauntlet-arxiv.zip"
TEMPLATE = Path(__file__).with_name("paper_template.tex")
STYLE_FILES = tuple(TEMPLATE.with_name(name) for name in (
    "iclr2027_conference.sty", "iclr2027_conference.bst",
))


def source_digest() -> str:
    source = {"paper": _paper_md(), "citations": {key: item["meta"] for key, item in CITES.items()}}
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def template_digest() -> str:
    digest = hashlib.sha256()
    for path in (Path(__file__), TEMPLATE, *STYLE_FILES):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    for url in (PAPER_URL, CORTEX_URL, REPOSITORY_URL):
        digest.update(url.encode() + b"\0")
    return digest.hexdigest()


def _run(argv: list[str], *, text: str | None = None, cwd: Path | None = None,
         env: dict | None = None) -> str:
    result = subprocess.run(argv, input=text, text=True, capture_output=True,
                            cwd=cwd, env=env, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed:\n{(result.stdout + result.stderr)[-8000:]}")
    return result.stdout


def _parse(text: str, reader: str = "markdown+tex_math_dollars+native_divs+native_spans") -> dict:
    return json.loads(_run(["pandoc", "--from", reader, "--to", "json"], text=text))


def _render(document: dict, writer: str = "latex") -> str:
    return _run(["pandoc", "--from", "json", "--to", writer, "--wrap=none", "--no-highlight"],
                text=json.dumps(document))


def _nodes(value):
    if isinstance(value, dict):
        if "t" in value:
            yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _raw(text: str) -> dict:
    return {"t": "RawBlock", "c": ["latex", text]}


def _fragment(text: str) -> list[dict]:
    return _parse(text, "html+tex_math_dollars")["blocks"]


def _inline_text(text: str) -> str:
    return _render(_parse(text), "plain").strip()


def _ascii(text: str) -> str:
    replacements = {"—": "--", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "\u00a0": " "}
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text.encode("ascii")  # Reject unsupported metadata rather than dropping characters.
    return text


def _typeset_formal_blocks(document: dict) -> None:
    """Replace web blockquotes with numbered, flush-left amsthm statements."""
    counters: Counter[str] = Counter()
    blocks = []
    for block in document["blocks"]:
        if block["t"] == "BlockQuote":
            paragraphs = block["c"]
            inlines = paragraphs[0]["c"]
            if (paragraphs[0]["t"] != "Para" or len(inlines) < 2
                    or inlines[0]["t"] != "Span" or inlines[1]["t"] != "Strong"):
                raise ValueError("Formal statement must start with an anchor and heading")
            heading = _render({**document, "blocks": [{"t": "Plain", "c": inlines[1]["c"]}]},
                              "plain").strip()
            match = re.fullmatch(r"(Theorem|Proposition) (\d+)(?: \((.+)\))?\.", heading)
            if match is None:
                raise ValueError(f"Unsupported formal statement heading: {heading}")
            kind, number, title = match.groups()
            environment = kind.lower()
            counters[kind] += 1
            identifier = ("thm" if kind == "Theorem" else "prop") + "-" + number
            if int(number) != counters[kind] or inlines[0]["c"][0][0] != identifier:
                raise ValueError(f"Formal statement numbering is not consecutive: {heading}")
            note = "[" + _render(_parse(title)).strip() + "]" if title else ""
            blocks.append(_raw(r"\begin{" + environment + "}" + note + r"\label{" + identifier + "}"))
            paragraphs[0]["c"] = inlines[2:]
            blocks.extend(paragraphs)
            blocks.append(_raw(r"\end{" + environment + "}"))
        elif (block["t"] == "Para" and block["c"]
              and block["c"][0] == {"t": "Emph", "c": [{"t": "Str", "c": "Proof."}]}):
            inlines = block["c"][1:]
            if (inlines and inlines[-1]["t"] == "Math"
                    and inlines[-1]["c"][1] == r"\square"):
                inlines.pop()  # amsthm places the proof-ending symbol.
            inlines.append({"t": "RawInline", "c": ["latex", r"\qedhere"]})
            blocks.extend([_raw(r"\begin{proof}"), {"t": "Para", "c": inlines}, _raw(r"\end{proof}")])
        else:
            blocks.append(block)
    document["blocks"] = blocks


def _prepare(work: Path) -> tuple[dict, dict]:
    source = re.sub(r"\n## Cite this work\n.*?(?=\n## |\Z)", "", _paper_md(),
                    count=1, flags=re.DOTALL)
    title = re.search(r"^# (.+)$", source, re.MULTILINE)[1]
    authors = re.findall(r'<span class="author">(.*?)</span>', source)
    affiliation = re.search(r'<div class="affil">(.*?)</div>', source)[1]
    abstract = source.split("## Abstract\n", 1)[1].split("\n## ", 1)[0].strip()
    metadata = {"title": title, "authors": authors, "affiliation": affiliation,
                "abstract": _ascii(_inline_text(abstract)), "paper_url": PAPER_URL,
                "repository_url": REPOSITORY_URL}
    if len(metadata["abstract"]) > 1920:
        raise ValueError("The canonical abstract exceeds arXiv's 1920-character metadata limit")
    # Title/authors become TeX metadata; social controls are web UI, not paper content.
    body = "## Abstract\n" + source.split("## Abstract\n", 1)[1]
    replacements: dict[str, list[dict]] = {}
    table_count = 0
    figures = work / "figures"
    figures.mkdir()
    light = re.search(r":root\{(.*?)\}", REPORT_CSS, re.DOTALL)[1]
    palette = dict(re.findall(r"(--[\w-]+):([^;}]+)", light))

    def figure(match: re.Match) -> str:
        nonlocal table_count
        identifier, content = match[1], match[2]
        caption = re.search(r"<figcaption>(.*?)</figcaption>", content, re.DOTALL)[1]
        token = "PAPERBLOCK" + identifier.replace("-", "").upper()
        if identifier.startswith("fig-"):
            svg = re.search(r"<svg\b.*?</svg>", content, re.DOTALL)[0]
            svg = re.sub(r"var\((--[\w-]+)\)", lambda m: palette[m[1]].strip(), svg)
            svg_path = work / f"{identifier}.svg"
            svg_path.write_text(svg)
            relative = f"figures/{identifier}.pdf"
            _run(["rsvg-convert", "--format=pdf", "--output", str(work / relative), str(svg_path)])
            # Native Figure captions are numbered by LaTeX; preserve the canonical text after its label.
            caption = re.sub(r"^Figure \d+\.\s*", "", caption)
            caption_blocks = _fragment(caption)
            image = {"t": "Image", "c": [["", [], [["width", "100%"]]], [], [relative, ""]]}
            replacements[token] = [{"t": "Figure", "c": [
                [identifier, [], []], [None, caption_blocks], [{"t": "Plain", "c": [image]}]]}]
        else:
            table_count += 1
            label = re.match(r"^Table (\d+)\.\s*", caption)
            if label is None or int(label[1]) != table_count or identifier != f"tbl-{table_count}":
                raise ValueError(f"Table numbering and anchors must follow document order: {identifier}")
            table = _fragment(re.search(r"<table>.*?</table>", content, re.DOTALL)[0])[0]
            table["c"][0][0] = identifier
            table["c"][1] = [None, _fragment(caption[label.end():])]
            replacements[token] = [table]
        return "\n\n" + token + "\n\n"

    body = re.sub(r'<figure class="(?:fig|tbl)" id="((?:fig|tbl)-\d+)">(.*?)</figure>',
                  figure, body, flags=re.DOTALL)
    references = re.search(r'<ol class="refs">(.*?)</ol>', body, re.DOTALL)
    entries = re.findall(r'<li id="(ref-\d+)">(.*?)</li>', references[1], re.DOTALL)
    if [key for key, _ in entries] != [f"ref-{n}" for n in range(1, len(CITES) + 1)]:
        raise ValueError("Canonical bibliography IDs do not match citation metadata")
    bibliography = [_raw(r"\begin{thebibliography}{99}")]
    for key, content in sorted(entries, key=lambda entry: CITES[entry[0][4:]]["meta"].casefold()):
        authors, year = re.match(r"(.+), (\d{4})\b", CITES[key[4:]]["meta"]).groups()
        if "," in authors:
            authors = authors.split(",", 1)[0] + " et al."
        label = _render(_parse(authors)).strip()
        bibliography.append(_raw(r"\bibitem[" + label + "(" + year + ")]{" + key + "}"))
        bibliography.extend(_fragment(content))
    bibliography.append(_raw(r"\end{thebibliography}"))
    replacements["PAPERBIBLIOGRAPHY"] = bibliography
    body = body[:references.start()] + "\nPAPERBIBLIOGRAPHY\n" + body[references.end():]
    body = body.replace("## References\n", "")  # thebibliography supplies the same heading.

    def citation(match: re.Match) -> str:
        ids = re.findall(r'href="#(ref-\d+)"', match[1])
        if not ids or any(key not in {item[0] for item in entries} for key in ids):
            raise ValueError("Unresolved canonical citation")
        return r" \citep{" + ",".join(ids) + "}"

    body = re.sub(r"<sup>(.*?)</sup>", citation, body, flags=re.DOTALL)
    body = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                  lambda m: f"[{html.unescape(m[2])}]({html.unescape(m[1])})", body, flags=re.DOTALL)
    document = _parse(body)

    def expand(blocks: list[dict]) -> list[dict]:
        result = []
        for block in blocks:
            if (block["t"] in {"Para", "Plain"} and len(block["c"]) == 1
                    and block["c"][0].get("t") == "Str" and block["c"][0]["c"] in replacements):
                result.extend(replacements[block["c"][0]["c"]])
            elif block["t"] == "Div":
                block["c"][1] = expand(block["c"][1])
                result.append(block)
            else:
                result.append(block)
        return result

    document["blocks"] = expand(document["blocks"])
    for node in _nodes(document):
        if node["t"] in {"RawBlock", "RawInline"} and node["c"][0] == "html":
            raise ValueError(f"Unhandled substantive HTML in paper export: {node['c'][1][:120]}")
        if node["t"] == "Table":
            columns = node["c"][2]
            widths = {2: [0.32, 0.68], 3: [0.16, 0.38, 0.46], 4: [0.34, 0.20, 0.23, 0.23]}[len(columns)]
            for column, width in zip(columns, widths, strict=True):
                column[1] = {"t": "ColWidth", "c": width}
    expected_math = Counter(
        ("DisplayMath" if display else "InlineMath", re.sub(r"\s+", "", html.unescape(display or inline)))
        for display, inline in re.findall(
            r"\$\$(.*?)\$\$|(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", source, re.DOTALL
        )
    )
    actual_math = Counter((node["c"][0]["t"], re.sub(r"\s+", "", node["c"][1]))
                          for node in _nodes(document) if node["t"] == "Math")
    if expected_math != actual_math:
        raise ValueError("Paper export changed or omitted a canonical mathematical expression")
    counts = {kind: sum(n["t"] == kind for n in _nodes(document))
              for kind in ("Header", "Figure", "Table", "BlockQuote", "Math")}
    counts["display_math"] = sum(n["t"] == "Math" and n["c"][0]["t"] == "DisplayMath"
                                 for n in _nodes(document))
    counts["references"] = len(entries)
    if (counts["Figure"], counts["Table"], counts["BlockQuote"]) != (4, 3, 6):
        raise ValueError(f"Paper structure changed; review export coverage: {counts}")
    metadata["content_inventory"] = counts
    return document, metadata


def build_paper(out_dir: Path, *, publication_date: date | None = None) -> dict:
    for program in ("pandoc", "rsvg-convert", "pdflatex", "pdfinfo"):
        if shutil.which(program) is None:
            raise RuntimeError(f"Paper publication requires {program}; no browser-print fallback is used")
    publication_date = publication_date or date.today()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gauntlet-paper-") as temporary:
        work = Path(temporary)
        document, metadata = _prepare(work)
        _typeset_formal_blocks(document)
        # Use article-level headings and a semantic abstract. Reflow widely spaced
        # equation groups without changing their mathematical expressions.
        for node in _nodes(document):
            if node["t"] == "Header":
                node["c"][0] -= 1
            elif node["t"] == "Code":
                # Keep literal code while allowing identifiers/paths to wrap at the ICLR width.
                text = node["c"][1]
                node.update(t="RawInline", c=[
                    "latex", r"{\urlstyle{tt}\nolinkurl{" + text + "}}",
                ])
            elif node["t"] == "Math" and node["c"][0]["t"] == "DisplayMath":
                expression = node["c"][1]
                if expression.count(r"\qquad") >= 2:
                    node["c"][1] = r"\begin{gathered}" + expression.replace(r"\qquad", r"\\") + r"\end{gathered}"
        blocks = document["blocks"]
        abstract_end = next(i for i, b in enumerate(blocks)
                            if i > 0 and b["t"] == "Header" and b["c"][0] == 1)
        blocks[0] = _raw(r"\begin{abstract}")
        blocks.insert(abstract_end, _raw(r"\end{abstract}"))
        body = _render(document)
        tex = (TEMPLATE.read_text().replace("__TITLE__", metadata["title"])
               .replace("__AUTHORS__", r" \& ".join(metadata["authors"]))
               .replace("__AFFILIATION__", metadata["affiliation"])
               .replace("__PAPER_URL__", PAPER_URL)
               .replace("__CORTEX_URL__", CORTEX_URL)
               .replace("__REPOSITORY_URL__", REPOSITORY_URL)
               .replace("__DATE__", publication_date.strftime("%B %d, %Y").replace(" 0", " "))
               .replace("__BODY__", body))
        (work / "main.tex").write_text(tex)
        for style in STYLE_FILES:
            shutil.copyfile(style, work / style.name)
        epoch = int(datetime.combine(publication_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch), "FORCE_SOURCE_DATE": "1"}
        for _ in range(3):
            _run(["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                 cwd=work, env=env)
        log = (work / "main.log").read_text()
        for failure in ("undefined references", "undefined citations", "Missing character:", "LaTeX Error:"):
            if failure in log:
                raise RuntimeError(f"Paper compilation has unresolved content: {failure}")
        metadata["layout_warnings"] = [line for line in log.splitlines() if "Overfull" in line]
        pdf = (work / "main.pdf").read_bytes()
        info = _run(["pdfinfo", str(work / "main.pdf")])
        metadata["pages"] = int(re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)[1])
        metadata["publication_date"] = publication_date.isoformat()
        metadata["source_sha256"] = source_digest()
        metadata["template_sha256"] = template_digest()
        members = [work / "main.tex", *(work / style.name for style in STYLE_FILES),
                   *sorted((work / "figures").glob("*.pdf"))]
        metadata["source_files"] = {p.relative_to(work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in members}
        archive = work / SOURCE_NAME
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for member in members:
                entry = zipfile.ZipInfo(member.relative_to(work).as_posix(),
                                        (publication_date.year, publication_date.month, publication_date.day, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                package.writestr(entry, member.read_bytes())
        metadata["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
        metadata["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        (out_dir / PDF_NAME).write_bytes(pdf)
        shutil.copyfile(archive, out_dir / SOURCE_NAME)
        (out_dir / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
        instructions = (
            "Gauntlet arXiv submission preparation\n\n"
            "Upload cortex-gauntlet-arxiv.zip, not the rendered PDF. Select main.tex and pdfLaTeX.\n"
            "arXiv currently defaults to TeX Live 2025. Inspect its generated PDF before submitting.\n"
            "The source archive contains main.tex, the official ICLR 2027 style files and four PDF figures.\n"
            "The bibliography is embedded; the document is a named preprint, not an ICLR submission.\n"
            "No external conversion, Python, network, shell escape or private data is required.\n"
            "Confirm author details and coauthor consent; choose an appropriate category and license.\n"
            "Account registration, possible endorsement and moderation remain arXiv's requirements.\n"
            "No arXiv identifier or acceptance is claimed.\n\n"
            f"Title: {metadata['title']}\nAuthors: {', '.join(metadata['authors'])} ({metadata['affiliation']})\n"
            f"Abstract: {metadata['abstract']}\n"
            f"Comments: {metadata['pages']} pages, four figures. Paper and latest results: {PAPER_URL} . "
            f"Benchmark source: {REPOSITORY_URL} .\n\n"
            "Suggested primary category for author review: cs.AI. Leave journal reference and DOI blank unless assigned.\n"
            "Recompile after extracting the ZIP: pdflatex -no-shell-escape main.tex (run twice).\n\n"
            "Official instructions:\nhttps://info.arxiv.org/help/submit/index.html\n"
            "https://info.arxiv.org/help/submit_tex.html\nhttps://info.arxiv.org/help/faq/texlive.html\n"
            "https://info.arxiv.org/help/prep.html\n"
        )
        (out_dir / "submission.txt").write_text(instructions)
        return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "site" / "public" / "paper")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="fixed publication date, YYYY-MM-DD")
    args = parser.parse_args()
    metadata = build_paper(args.output, publication_date=args.date)
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
