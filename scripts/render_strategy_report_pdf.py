"""
Render the editable Markdown strategy report into a polished HTML/PDF report.

The PDF is generated through headless Chrome so Chinese text, tables, and images
are handled by the browser's layout engine instead of a low-level PDF canvas.
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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
REPORT_MD = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告.md"
REPORT_HTML = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告_图文版.html"
REPORT_PDF = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf"
REPORT_PDF_CANONICAL = DOCS_DIR / "BETA_MMT_V1_CNE6风格择时策略报告.pdf"


FIGURES_BY_SECTION = {
    "4. 回测表现": [
        ("策略累计收益与基准对比", PROJECT_ROOT / "output/cne6/factor_timing_l20_s5_b2_e1_n100.png"),
    ],
    "5. 风格收益归因": [
        ("全样本 CNE6 风格因子收益归因", PROJECT_ROOT / "output/cne6/images/style_factor_attribution_summary_l20_s5_b2_e1_n100.png"),
    ],
    "6. 分时段归因": [
        ("分时段风格收益归因与净值曲线联动", PROJECT_ROOT / "output/cne6/images/style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.png"),
    ],
    "7. 风格择时有效性与持仓兑现": [
        ("风格择时有效性表", PROJECT_ROOT / "output/cne6/images/style_timing_effectiveness_table_l20_s5_b2_e1_n100.png"),
        ("持仓内部风格暴露质量表", PROJECT_ROOT / "output/cne6/images/style_holding_exposure_quality_table_l20_s5_b2_e1_n100.png"),
    ],
    "8. 交易成本压力测试": [
        ("交易成本压力测试", PROJECT_ROOT / "output/cne6/images/transaction_cost_stress_l20_s5_b2_e1_n100.png"),
    ],
    "9. 因子剔除/降权实验": [
        ("因子剔除/降权实验", PROJECT_ROOT / "output/cne6/images/factor_weight_experiment_l20_s5_b2_e1_n100.png"),
    ],
    "10. Residual 归因": [
        ("Residual 归因总览", PROJECT_ROOT / "output/cne6/images/residual_attribution_l20_s5_b2_e1_n100.png"),
    ],
}


def inline_markdown(text: str) -> str:
    """Convert the small inline Markdown subset used by the report."""
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<span class="file-ref">\1</span>', text)
    return text


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def render_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        if is_table_separator(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    header = rows[0]
    body = rows[1:]

    parts = ['<div class="table-wrap"><table>']
    parts.append("<thead><tr>")
    for cell in header:
        parts.append(f"<th>{inline_markdown(cell)}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body:
        parts.append("<tr>")
        for cell in row:
            cls = "num" if re.search(r"^-?\+?\d|%$|bp$", cell.strip()) else ""
            parts.append(f'<td class="{cls}">{inline_markdown(cell)}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def image_to_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{data}"


def render_figures(section_title: str) -> str:
    figures = FIGURES_BY_SECTION.get(section_title, [])
    parts = []
    for caption, path in figures:
        data_uri = image_to_data_uri(path)
        if not data_uri:
            continue
        parts.append(
            f"""
            <figure class="report-figure">
              <img src="{data_uri}" alt="{html.escape(caption)}" />
              <figcaption>{html.escape(caption)}</figcaption>
            </figure>
            """
        )
    return "\n".join(parts)


def markdown_to_html(markdown_text: str) -> tuple[str, str]:
    """Render report Markdown to HTML body and collect a simple table of contents."""
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
            if level in {1, 2}:
                toc_items.append((level, title, slug))
            body_parts.append(f'<h{level} id="{html.escape(slug)}">{inline_markdown(title)}</h{level}>')
            if level == 2:
                body_parts.append(render_figures(title))
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

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            body_parts.append("<ol>" + "".join(f"<li>{inline_markdown(item)}</li>" for item in items) + "</ol>")
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()

    toc_parts = ['<nav class="toc"><h2>目录</h2><ol>']
    for level, title, slug in toc_items:
        cls = "toc-h1" if level == 1 else "toc-h2"
        toc_parts.append(f'<li class="{cls}"><a href="#{html.escape(slug)}">{inline_markdown(title)}</a></li>')
    toc_parts.append("</ol></nav>")
    return "\n".join(body_parts), "\n".join(toc_parts)


def build_html(markdown_text: str) -> str:
    body, toc = markdown_to_html(markdown_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>BETA_MMT_V1 CNE6 风格择时策略报告</title>
  <style>
    @page {{
      size: A4;
      margin: 15mm 13mm 16mm 13mm;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: #1f2933;
      font-family: "Microsoft YaHei", "DengXian", "SimHei", "PingFang SC", sans-serif;
      font-size: 14px;
      line-height: 1.72;
      background: #f4f6f8;
    }}
    .page {{
      width: 100%;
      max-width: 980px;
      margin: 0 auto;
      background: #fff;
      padding: 0 0 28px 0;
    }}
    .cover {{
      min-height: 245mm;
      padding: 42mm 18mm 20mm 18mm;
      color: white;
      background: linear-gradient(135deg, #19324d 0%, #315d6f 55%, #4f7b61 100%);
      break-after: page;
      position: relative;
    }}
    .cover::after {{
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 22mm;
      background: rgba(255,255,255,0.12);
    }}
    .eyebrow {{
      font-size: 13px;
      letter-spacing: .12em;
      opacity: .86;
      margin-bottom: 22px;
    }}
    .cover h1 {{
      font-size: 34px;
      line-height: 1.25;
      margin: 0 0 18px 0;
      font-weight: 800;
      color: #fff;
    }}
    .cover .subtitle {{
      font-size: 17px;
      opacity: .92;
      max-width: 650px;
      margin-bottom: 44px;
    }}
    .cover-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      max-width: 680px;
    }}
    .cover-card {{
      padding: 13px 15px;
      background: rgba(255,255,255,0.14);
      border: 1px solid rgba(255,255,255,0.22);
      border-radius: 6px;
    }}
    .cover-card b {{ display: block; font-size: 21px; margin-bottom: 3px; }}
    .cover-card span {{ font-size: 12px; opacity: .84; }}
    .cover-meta {{
      position: absolute;
      left: 18mm;
      bottom: 20mm;
      font-size: 13px;
      opacity: .86;
      z-index: 2;
    }}
    main {{
      padding: 0 8mm;
    }}
    h1, h2, h3, h4 {{
      color: #24384d;
      line-height: 1.35;
      break-after: avoid;
    }}
    main > h1 {{
      font-size: 26px;
      margin: 24px 0 14px;
      padding-bottom: 8px;
      border-bottom: 2px solid #d8e0e7;
    }}
    h2 {{
      font-size: 21px;
      margin: 26px 0 12px;
      padding-left: 10px;
      border-left: 5px solid #3a6f7f;
    }}
    h3 {{
      font-size: 17px;
      margin: 20px 0 8px;
    }}
    h4 {{ font-size: 15px; margin: 16px 0 6px; }}
    p {{ margin: 7px 0; }}
    a {{ color: #2c6f91; text-decoration: none; }}
    blockquote {{
      margin: 12px 0;
      padding: 10px 14px;
      border-left: 4px solid #7fa58e;
      background: #f5f8f5;
      color: #405044;
      border-radius: 0 5px 5px 0;
    }}
    code {{
      font-family: Consolas, "Microsoft YaHei", monospace;
      background: #eef2f5;
      border-radius: 4px;
      padding: 1px 5px;
      color: #374151;
      font-size: .92em;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      padding: 12px 14px;
      background: #17212b;
      color: #e5edf4;
      border-radius: 6px;
      overflow: hidden;
      font-size: 12px;
      line-height: 1.55;
      break-inside: avoid;
    }}
    pre code {{ background: transparent; color: inherit; padding: 0; }}
    ul, ol {{ margin: 7px 0 10px 20px; padding: 0; }}
    li {{ margin: 3px 0; }}
    .toc {{
      break-after: page;
      padding: 10mm 8mm 8mm;
    }}
    .toc h2 {{
      border: none;
      padding: 0;
      margin-top: 0;
    }}
    .toc ol {{ list-style: none; margin: 0; padding: 0; column-count: 2; column-gap: 22px; }}
    .toc li {{ break-inside: avoid; margin: 4px 0; }}
    .toc .toc-h1 {{ font-weight: 700; }}
    .toc .toc-h2 {{ padding-left: 12px; color: #52606d; font-size: 13px; }}
    .table-wrap {{
      width: 100%;
      overflow: hidden;
      margin: 10px 0 15px;
      break-inside: avoid;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 11.2px;
      line-height: 1.38;
    }}
    th {{
      background: #2e4057;
      color: white;
      font-weight: 700;
      padding: 7px 6px;
      border: 1px solid #cbd5df;
      text-align: center;
    }}
    td {{
      padding: 6px 6px;
      border: 1px solid #d8dee6;
      vertical-align: middle;
      word-break: break-word;
    }}
    tbody tr:nth-child(even) td {{ background: #f8fafc; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .report-figure {{
      margin: 18px 0 20px;
      padding: 10px;
      background: #f8fafc;
      border: 1px solid #d9e1e8;
      border-radius: 6px;
      break-inside: avoid;
    }}
    .report-figure img {{
      display: block;
      width: 100%;
      max-height: 205mm;
      object-fit: contain;
      background: white;
      border-radius: 3px;
    }}
    figcaption {{
      margin-top: 8px;
      color: #52606d;
      font-size: 12px;
      text-align: center;
    }}
    .file-ref {{ color: #516070; }}
    strong {{ color: #19324d; }}
    @media print {{
      body {{ background: white; }}
      .page {{ max-width: none; }}
      h2 {{ break-before: auto; }}
    }}
  </style>
</head>
<body>
  <section class="cover">
    <div class="eyebrow">BETA_MMT_V1 / Barra CNE6 / Strategy Research</div>
    <h1>CNE6 风格因子择时策略报告</h1>
    <div class="subtitle">基于项目架构、周度回测、风格归因、交易成本压力测试、因子剔除实验与 residual 归因的综合研究版。</div>
    <div class="cover-grid">
      <div class="cover-card"><b>8.01</b><span>期末净值</span></div>
      <div class="cover-card"><b>42.7%</b><span>样本内年化收益</span></div>
      <div class="cover-card"><b>-18.0%</b><span>最大回撤</span></div>
      <div class="cover-card"><b>76.9%</b><span>平均单边换手</span></div>
    </div>
    <div class="cover-meta">报告日期：2026-04-30<br/>数据区间：2020-02-17 至 2025-12-22</div>
  </section>
  <div class="page">
    {toc}
    <main>
      {body}
    </main>
  </div>
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
    with tempfile.TemporaryDirectory(prefix="beta_mmt_report_chrome_") as chrome_profile:
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
                "--print-to-pdf-no-header",
                html_uri,
            ],
            check=True,
        )
    REPORT_PDF_CANONICAL.write_bytes(REPORT_PDF.read_bytes())
    print(f"HTML: {REPORT_HTML}")
    print(f"PDF:  {REPORT_PDF}")
    print(f"PDF:  {REPORT_PDF_CANONICAL}")


if __name__ == "__main__":
    render_pdf()
