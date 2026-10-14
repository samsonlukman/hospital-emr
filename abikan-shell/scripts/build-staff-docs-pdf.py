#!/usr/bin/env python3
"""Build a printable HTML + PDF of the Hospital EMR staff documentation package."""

from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
OUT_DIR = DOCS / "pdf"
HTML_PATH = OUT_DIR / "Hospital EMR-EMR-Staff-Documentation.html"
PDF_PATH = OUT_DIR / "Hospital EMR-EMR-Staff-Documentation-v1.0.0-uat.pdf"

CHAPTERS = [
    "UAT_QUICK_REFERENCE.md",
    "ABIKAN_EMR_USER_MANUAL.md",
    "DEPARTMENT_GUIDE_RECEPTION.md",
    "DEPARTMENT_GUIDE_DOCTOR.md",
    "DEPARTMENT_GUIDE_NURSING.md",
    "DEPARTMENT_GUIDE_INPATIENT.md",
    "DEPARTMENT_GUIDE_LABORATORY.md",
    "DEPARTMENT_GUIDE_PHARMACY.md",
    "DEPARTMENT_GUIDE_ACCOUNTING.md",
    "DEPARTMENT_GUIDE_RADIOLOGY.md",
    "DEPARTMENT_GUIDE_HOSPITAL_ADMIN.md",
    "CLINICAL_WORKFLOWS.md",
    "BILLING_AND_PAYMENTS.md",
    "USER_ROLES_AND_PERMISSIONS.md",
    "TROUBLESHOOTING.md",
    "SYSTEM_ARCHITECTURE.md",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
html { font-size: 11pt; }
body {
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  color: #1a2330;
  line-height: 1.45;
}
.cover { page-break-after: always; padding-top: 28mm; }
.cover h1 { font-size: 28pt; margin: 0 0 8px; }
.cover p { margin: 6px 0; color: #334155; }
.chapter { page-break-before: always; }
.chapter:first-of-type { page-break-before: auto; }
h1 { font-size: 18pt; margin: 0 0 12px; color: #0f3d2e; }
h2 { font-size: 14pt; margin: 18px 0 8px; color: #14532d; }
h3 { font-size: 12pt; margin: 14px 0 6px; }
p, li { orphans: 3; widows: 3; }
a { color: inherit; text-decoration: none; }
code, pre {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 9.5pt;
}
pre {
  background: #f4f6f8;
  border: 1px solid #d8dee6;
  padding: 10px 12px;
  white-space: pre-wrap;
  page-break-inside: avoid;
}
table { border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 10pt; }
th, td { border: 1px solid #c5cdd6; padding: 5px 7px; vertical-align: top; }
th { background: #e8f0ea; text-align: left; }
tr { page-break-inside: avoid; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 16px 0; }
.footer-note { font-size: 9pt; color: #64748b; margin-top: 24px; }
"""


def inline(text: str) -> str:
    parts: list[str] = []
    i = 0
    pattern = re.compile(
        r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))"
    )
    for match in pattern.finditer(text):
        parts.append(html.escape(text[i : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            parts.append(f"<strong>{html.escape(token[2:-2])}</strong>")
        elif token.startswith("`"):
            parts.append(f"<code>{html.escape(token[1:-1])}</code>")
        else:
            label = re.sub(r"^\[([^\]]+)\]\([^)]+\)$", r"\1", token)
            parts.append(html.escape(label))
        i = match.end()
    parts.append(html.escape(text[i:]))
    return "".join(parts)


def render_table(rows: list[str]) -> str:
    body = []
    for index, row in enumerate(rows):
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if index == 1 and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
            continue
        tag = "th" if index == 0 else "td"
        body.append("<tr>" + "".join(f"<{tag}>{inline(cell)}</{tag}>" for cell in cells) + "</tr>")
    return "<table>" + "".join(body) + "</table>"


def md_to_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close_lists()
            i += 1
            block: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
            continue
        if line.startswith("|"):
            close_lists()
            table: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                table.append(lines[i])
                i += 1
            out.append(render_table(table))
            continue
        if re.fullmatch(r"-{3,}", line.strip()):
            close_lists()
            out.append("<hr>")
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            close_lists()
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        ul = re.match(r"^[-*]\s+(.*)$", line)
        if ul:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(ul.group(1))}</li>")
            i += 1
            continue
        ol = re.match(r"^\d+\.\s+(.*)$", line)
        if ol:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(ol.group(1))}</li>")
            i += 1
            continue
        if not line.strip():
            close_lists()
            i += 1
            continue
        close_lists()
        out.append(f"<p>{inline(line)}</p>")
        i += 1
    close_lists()
    return "\n".join(out)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chapters = []
    for name in CHAPTERS:
        path = DOCS / name
        if not path.exists():
            raise SystemExit(f"Missing {path}")
        chapters.append(
            f'<section class="chapter">\n{md_to_html(path.read_text(encoding="utf-8"))}\n</section>'
        )
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hospital EMR Staff Documentation — v1.0.0-uat</title>
<style>{CSS}</style>
</head>
<body>
<section class="cover">
  <p>Hospital EMR Hospital &amp; Wellness Centre</p>
  <h1>Hospital EMR</h1>
  <p>Staff and operations documentation</p>
  <p>Release <strong>v1.0.0-uat</strong></p>
  <p>Commit <strong>2ea80c40c02cd42aa33fba47a0aa9dc1cc7d9ff6</strong></p>
  <p>This PDF describes the EMR as it exists in this release. It is not a brochure and does not list planned features as if they were available.</p>
  <p class="footer-note">Do not use development passwords on the hospital server. Do not share accounts.</p>
</section>
{"".join(chapters)}
</body>
</html>
"""
    HTML_PATH.write_text(document, encoding="utf-8")
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.exists():
        raise SystemExit(f"Wrote {HTML_PATH} but Google Chrome was not found.")
    subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_PATH}",
            HTML_PATH.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    print(PDF_PATH)
    print(f"bytes={PDF_PATH.stat().st_size}")


if __name__ == "__main__":
    main()
