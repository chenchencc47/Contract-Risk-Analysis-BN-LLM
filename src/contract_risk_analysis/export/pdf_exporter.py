"""PDF report exporter — Markdown → PDF via fpdf2 (pure Python, no system deps).

Keeps the original MD export untouched. Supports multi-format export
architecture (md / pdf / html / docx — md+pdf implemented, rest extensible).
"""

from __future__ import annotations

from pathlib import Path


def _md_to_plain_text(md_text: str) -> str:
    """Strip basic Markdown formatting for cleaner PDF text flow.

    Does NOT attempt full Markdown rendering — tables and lists are
    preserved as-is for fpdf2 multi_cell output. Only removes decorators
    that would look ugly in raw PDF text.
    """
    lines: list[str] = []
    for line in md_text.split("\n"):
        # Strip bold/italic markers (keep content)
        line = line.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
        # Strip inline code backticks
        while "`" in line:
            line = line.replace("`", "", 2)
        lines.append(line)
    return "\n".join(lines)


def export_pdf(md_text: str, output_path: str | Path) -> Path:
    """Export Markdown report text to a PDF file via fpdf2.

    Preserves table structure, headings, lists, and code blocks with
    reasonable formatting.

    Args:
        md_text: Full Markdown report content.
        output_path: Destination .pdf file path.

    Returns:
        Path to the generated PDF file.
    """
    from fpdf import FPDF

    output_path = Path(output_path)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Register a CJK-compatible font (use built-in if available, else fallback)
    try:
        pdf.add_font("CJK", "", r"C:\Windows\Fonts\simsun.ttc", uni=True)
        pdf.add_font("CJK", "B", r"C:\Windows\Fonts\simhei.ttf", uni=True)
        font_name = "CJK"
    except Exception:
        font_name = "Helvetica"

    plain = _md_to_plain_text(md_text)

    for line in plain.split("\n"):
        line = line.rstrip()

        # Skip empty lines (fpdf2 handles paragraph spacing)
        if not line.strip():
            pdf.ln(4)
            continue

        # Headings
        if line.startswith("#### "):
            pdf.set_font(font_name, "B", 10)
            pdf.ln(4)
            pdf.multi_cell(0, 6, line[5:])
            pdf.set_font(font_name, "", 9)
            pdf.ln(2)
            continue
        if line.startswith("### "):
            pdf.set_font(font_name, "B", 11)
            pdf.ln(5)
            pdf.multi_cell(0, 7, line[4:])
            pdf.set_font(font_name, "", 9)
            pdf.ln(2)
            continue
        if line.startswith("## "):
            pdf.set_font(font_name, "B", 13)
            pdf.ln(6)
            pdf.multi_cell(0, 8, line[3:])
            # Draw underline
            y = pdf.get_y()
            pdf.set_draw_color(139, 0, 0)
            pdf.line(18, y + 1, pdf.w - 18, y + 1)
            pdf.set_font(font_name, "", 9)
            pdf.ln(4)
            continue
        if line.startswith("# "):
            pdf.set_font(font_name, "B", 16)
            pdf.ln(8)
            pdf.multi_cell(0, 10, line[2:])
            y = pdf.get_y()
            pdf.set_draw_color(139, 0, 0)
            pdf.set_line_width(0.6)
            pdf.line(18, y + 2, pdf.w - 18, y + 2)
            pdf.set_line_width(0.2)
            pdf.set_font(font_name, "", 9)
            pdf.ln(6)
            continue

        # Horizontal rule
        if line.strip() in ("---", "------", "-------", "---"):
            pdf.set_draw_color(200, 200, 200)
            y = pdf.get_y()
            pdf.line(18, y, pdf.w - 18, y)
            pdf.ln(4)
            continue

        # Table rows (detected by | in content)
        if "|" in line and line.strip().startswith("|"):
            pdf.set_font(font_name, "", 7)
            cells = [c.strip() for c in line.split("|")[1:-1]]
            # Skip alignment separator rows (e.g. |---|:---:|---|)
            if all(c.replace("-", "").replace(":", "").strip() == "" for c in cells):
                pdf.ln(1)
                continue
            # Calculate column widths
            n = len(cells)
            if n == 0:
                continue
            usable_w = pdf.w - 2 * pdf.l_margin
            col_w = usable_w / n
            for i, cell in enumerate(cells):
                x = pdf.l_margin + i * col_w
                pdf.set_xy(x, pdf.get_y())
                # Bold for first row after header separator
                pdf.multi_cell(col_w, 5, cell, border=0)
            pdf.ln(2)
            continue

        # Code blocks
        if line.startswith("```"):
            pdf.set_font("Courier", "", 7)
            pdf.set_fill_color(245, 245, 245)
            continue
        if line.startswith("    ") or line.startswith("\t"):
            pdf.set_font("Courier", "", 7)
            pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(0, 4.5, line, fill=True)
            pdf.set_font(font_name, "", 9)
            continue

        # Blockquotes
        if line.startswith("> "):
            pdf.set_font(font_name, "", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(pdf.w - 2 * pdf.l_margin - 6, 5, line[2:])
            pdf.set_text_color(51, 51, 51)
            pdf.set_font(font_name, "", 9)
            continue

        # List items
        if line.strip().startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            pdf.set_font(font_name, "", 9)
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(pdf.w - 2 * pdf.l_margin - 6, 5.5, line.strip())
            continue

        # Normal text
        pdf.set_font(font_name, "", 9)
        # Handle long lines by wrapping
        pdf.multi_cell(0, 5.5, line)

    # Footer: page numbers
    page_count = pdf.page_no()
    for i in range(1, page_count + 1):
        pdf.page = i
        pdf.set_font(font_name, "", 7)
        pdf.set_text_color(150, 150, 150)
        pdf.set_y(-15)
        pdf.cell(0, 10, f"— {i} / {page_count} —", align="C")
        pdf.set_text_color(51, 51, 51)

    pdf.output(str(output_path))
    return output_path


def export_md(md_text: str, output_path: str | Path) -> Path:
    """Export raw Markdown report text to a .md file (passthrough)."""
    output_path = Path(output_path)
    output_path.write_text(md_text, encoding="utf-8")
    return output_path


EXPORTERS = {
    "md": export_md,
    "pdf": export_pdf,
}


def export_report(
    md_text: str,
    output_path: str | Path,
    fmt: str = "pdf",
) -> Path:
    """Unified report export entry point.

    Args:
        md_text: Full Markdown report content.
        output_path: Destination file path.
        fmt: Export format — "md" or "pdf".

    Returns:
        Path to the generated file.
    """
    if fmt not in EXPORTERS:
        raise ValueError(
            f"Unsupported format: {fmt}. Available: {list(EXPORTERS)}"
        )
    output_path = Path(output_path)
    if not output_path.suffix:
        output_path = output_path.with_suffix(f".{fmt}")
    return EXPORTERS[fmt](md_text, output_path)
