"""
Render the final main strategy report in the style of the sample report.

This renderer intentionally writes separate files so the canonical report remains
available for side-by-side comparison.
"""

from __future__ import annotations

import base64
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
REPORT_MD = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.md"
REPORT_HTML = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.html"
REPORT_PDF = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.pdf"


def inline_markdown(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def table_alignments(lines: list[str], max_cols: int) -> list[str]:
    aligns = ["left"] * max_cols
    for line in lines:
        if not is_table_separator(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        for idx, cell in enumerate(cells[:max_cols]):
            if cell.startswith(":") and cell.endswith(":"):
                aligns[idx] = "center"
            elif cell.endswith(":"):
                aligns[idx] = "right"
        break
    return aligns


def render_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        if is_table_separator(line):
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    aligns = table_alignments(lines, max_cols)
    header, body = rows[0], rows[1:]
    parts = ['<div class="table-wrap"><table>']
    parts.append("<thead><tr>")
    for idx, cell in enumerate(header):
        cls = f"align-{aligns[idx]}"
        parts.append(f'<th class="{cls}">{inline_markdown(cell)}</th>')
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        for idx, cell in enumerate(row):
            cls = f"align-{aligns[idx]}"
            parts.append(f'<td class="{cls}">{inline_markdown(cell)}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def image_to_data_uri(path_text: str) -> str | None:
    path = Path(path_text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path_text
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{data}"


def markdown_to_html(markdown_text: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = markdown_text.splitlines()
    body_parts: list[str] = []
    toc_items: list[tuple[int, str, str]] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False
    i = 0

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = " ".join(line.strip() for line in paragraph).strip()
        if text:
            body_parts.append(f"<p>{inline_markdown(text)}</p>")
        paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                body_parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        image_match = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
        if image_match:
            flush_paragraph()
            caption = image_match.group(1).strip()
            data_uri = image_to_data_uri(image_match.group(2).strip())
            if data_uri:
                body_parts.append(
                    f'<figure><img src="{data_uri}" alt="{html.escape(caption)}" />'
                    f"<figcaption>{html.escape(caption)}</figcaption></figure>"
                )
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1
            body_parts.append(render_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", title).strip("-")
            if level in {2, 3}:
                toc_items.append((level, title, slug))
            body_parts.append(f'<h{level} id="{html.escape(slug)}">{inline_markdown(title)}</h{level}>')
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote = stripped.lstrip(">").strip()
            body_parts.append(f"<blockquote>{inline_markdown(quote)}</blockquote>")
            i += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            body_parts.append("<ul>" + "".join(f"<li>{inline_markdown(item)}</li>" for item in items) + "</ul>")
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    return "\n".join(body_parts), toc_items


def render_toc(toc_items: list[tuple[int, str, str]]) -> str:
    parts = ['<section class="toc-page"><h1>目录</h1><div class="toc-list">']
    for level, title, slug in toc_items:
        if level > 3:
            continue
        cls = "toc-l2" if level == 2 else "toc-l3"
        parts.append(
            f'<div class="{cls}"><a href="#{html.escape(slug)}">{inline_markdown(title)}</a>'
            '<span class="dots"></span></div>'
        )
    parts.append("</div></section>")
    return "\n".join(parts)


def build_html(markdown_text: str) -> str:
    body, toc_items = markdown_to_html(markdown_text)
    toc = render_toc(toc_items)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>BETA_MMT_V1 CNE6 风格择时策略报告</title>
  <style>
    @page {{
      size: A4;
      margin: 22mm 23mm 29mm 23mm;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #fff;
      color: #202636;
      font-family: "Microsoft YaHei", "SimSun", "Noto Sans CJK SC", Arial, sans-serif;
      font-size: 12.2px;
      line-height: 1.78;
    }}
    .cover {{
      min-height: 220mm;
      padding: 58mm 18mm 0 18mm;
      page-break-after: always;
      break-after: page;
      position: relative;
    }}
    .cover h1 {{
      color: #1f5b9d;
      font-size: 29px;
      line-height: 1.35;
      margin: 0 0 6px 0;
      font-weight: 700;
    }}
    .cover .subtitle {{
      color: #1f5b9d;
      font-size: 22px;
      line-height: 1.35;
      font-weight: 700;
      padding-bottom: 7px;
      border-bottom: 2px solid #1f5b9d;
      margin-bottom: 8px;
    }}
    .cover .en {{
      font-size: 11px;
      color: #586270;
      font-style: italic;
      margin-bottom: 7px;
    }}
    .cover .meta {{
      margin-top: 4px;
      color: #8a8f99;
      font-size: 13px;
      line-height: 1.8;
    }}
    .cover .meta b {{ color: #202636; }}
    .page-footer {{
      display: none;
    }}
    .toc-page {{
      min-height: 220mm;
      padding-top: 14mm;
      page-break-after: always;
      break-after: page;
    }}
    .toc-page h1 {{
      color: #1f5b9d;
      font-size: 31px;
      font-weight: 500;
      margin: 0 0 16px 0;
    }}
    .toc-list {{ font-size: 12.5px; line-height: 1.55; }}
    .toc-list div {{ display: flex; align-items: baseline; gap: 5px; }}
    .toc-list a {{ color: #30394a; text-decoration: none; white-space: nowrap; }}
    .toc-l3 {{ padding-left: 22px; }}
    .dots {{ border-bottom: 1px dotted #7f8792; flex: 1; transform: translateY(-3px); }}
    main {{ padding-bottom: 24mm; }}
    h2 {{
      color: #1f5b9d;
      font-size: 22px;
      line-height: 1.35;
      margin: 25px 0 8px 0;
      padding-bottom: 5px;
      border-bottom: 2px solid #1f5b9d;
      break-after: avoid;
    }}
    h3 {{
      color: #3e73b5;
      font-size: 16px;
      line-height: 1.35;
      margin: 21px 0 7px 0;
      break-after: avoid;
    }}
    h4 {{
      color: #1f5b9d;
      font-size: 13.5px;
      margin: 16px 0 5px 0;
    }}
    p {{ margin: 5px 0 8px 0; text-align: justify; }}
    strong {{ font-weight: 700; color: #111827; }}
    code {{
      font-family: Consolas, "Courier New", monospace;
      background: transparent;
      color: #111827;
      font-size: 0.95em;
    }}
    ul {{ margin: 4px 0 10px 22px; padding-left: 0; list-style-type: square; }}
    li {{ margin: 2px 0; padding-left: 4px; }}
    blockquote {{
      margin: 10px 0 12px 0;
      padding: 8px 12px;
      border-left: 4px solid #1f5b9d;
      background: #f5f8fc;
      color: #263246;
      font-weight: 600;
    }}
    .table-wrap {{ margin: 10px 0 14px 0; break-inside: avoid; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 10.8px;
      line-height: 1.42;
    }}
    th {{
      background: #dfeaf6;
      color: #1f5b9d;
      font-weight: 700;
      text-align: left;
      padding: 6px 8px;
      border: 1px solid #d2dbe8;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    td {{
      padding: 5px 7px;
      border: 1px solid #d8dee8;
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    tbody tr:nth-child(even) td {{ background: #f5f7fb; }}
    th.align-right, td.align-right {{ text-align: right; font-variant-numeric: tabular-nums; }}
    th.align-center, td.align-center {{ text-align: center; }}
    th.align-left, td.align-left {{ text-align: left; }}
    td code, th code {{ white-space: normal; overflow-wrap: anywhere; }}
    figure {{
      margin: 12px auto 15px auto;
      text-align: center;
      break-inside: avoid;
    }}
    figure img {{
      max-width: 100%;
      max-height: 155mm;
      object-fit: contain;
    }}
    figcaption {{
      margin-top: 5px;
      font-size: 10.5px;
      color: #4b5563;
    }}
    pre {{
      background: #f5f7fb;
      padding: 8px 10px;
      border: 1px solid #d8dee8;
      white-space: pre-wrap;
      font-size: 10.5px;
    }}
    @media print {{
      body {{ background: white; }}
      h2 {{ break-before: auto; }}
    }}
  </style>
</head>
<body>
  <div class="page-footer">BETA_MMT_V1 CNE6 风格择时策略报告</div>
  <section class="cover">
    <h1>BETA_MMT_V1 CNE6 风格择时策略：</h1>
    <div class="subtitle">基于 Barra 风格因子通道择时与成交约束的研究</div>
    <div class="en">A Style Timing Strategy Based on Barra CNE6 Factors, Turnover Control and Execution Constraints</div>
    <div class="meta">
      日期&nbsp;&nbsp;<b>2026-05-12</b><br/>
      标的&nbsp;&nbsp;<b>A 股股票池 / Barra CNE6 风格因子</b><br/>
      数据范围&nbsp;&nbsp;<b>2020-02-17 ~ 2025-12-22</b><br/>
      定稿版本&nbsp;&nbsp;<b>L20 / S5 / B2 / E1 / N100 + tc50_buf2</b>
    </div>
  </section>
  {toc}
  <main>
    {body}
  </main>
</body>
</html>
"""


def find_chrome() -> Path:
    env_path = os.environ.get("CHROME_PATH")
    candidates = [
        Path(env_path) if env_path else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError("Cannot find Chrome or Edge executable.")


def render_pdf() -> None:
    markdown_text = REPORT_MD.read_text(encoding="utf-8")
    html_text = build_html(markdown_text)
    REPORT_HTML.write_text(html_text, encoding="utf-8")

    chrome = find_chrome()
    html_uri = REPORT_HTML.resolve().as_uri()
    with tempfile.TemporaryDirectory(prefix="beta_mmt_sample_style_chrome_") as chrome_profile:
        subprocess.run(
            [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-breakpad",
                "--disable-crash-reporter",
                "--disable-dev-shm-usage",
                f"--user-data-dir={chrome_profile}",
                f"--print-to-pdf={REPORT_PDF.resolve()}",
                "--no-pdf-header-footer",
                html_uri,
            ],
            check=True,
        )
    print(f"HTML: {REPORT_HTML}")
    print(f"PDF:  {REPORT_PDF}")


if __name__ == "__main__":
    render_pdf()
