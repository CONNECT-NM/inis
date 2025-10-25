#!/usr/bin/env python3
"""
pdf_3col_to_txt_parity_boxes.py

Esporta testo da un PDF multi-colonna in TXT, ignorando intestazioni/piedi.
Consente di definire box di colonne (x0:x1) diversi per pagine dispari e pari.

Esempi:
  # Tre colonne uguali (default), dalla pagina 6 a fine
  python pdf_3col_to_txt_parity_boxes.py --pdf in.pdf --out out.txt

  # Colonne precise (in punti) per pagine dispari e pari
  python pdf_3col_to_txt_parity_boxes.py \
      --pdf in.pdf --out out.txt --start-page 6 \
      --odd-cols "0:180,180:360,360:540" \
      --even-cols "10:200,210:400,410:590"

  # Colonne in percentuale della larghezza
  python pdf_3col_to_txt_parity_boxes.py \
      --pdf in.pdf --out out.txt \
      --odd-cols "0%:33.3%,33.3%:66.6%,66.6%:100%"
      
Usage with the INIS 2018 pdf file:

python extract.py --start-page 6 --end-page 6 --odd-cols "0%:35.1%,35.1%:63.7%,63.7%:100%" --even-cols "0%:37.9%,37.9%:66.4%,66.4%:100%" --header-ratio 0.14 --footer-ratio 0.06 --pdf ./inis_thesaurus_2018.pdf --out out6.txt

python extract.py --start-page 7 --odd-cols "0%:35.1%,35.1%:63.7%,63.7%:100%" --even-cols "0%:37.9%,37.9%:66.4%,66.4%:100%" --header-ratio 0.08 --footer-ratio 0.06 --pdf ./inis_thesaurus_2018.pdf --out out7-end.txt

then merge the two txt files.

"""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
from typing import List, Tuple, Optional
import pdfplumber


def clean_lines(text: str) -> str:
    """Reduce consecutive blank lines while preserving paragraphs."""
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = []
    last_blank = False
    for ln in lines:
        blank = (ln.strip() == "")
        if blank and last_blank:
            continue
        out.append(ln)
        last_blank = blank
    return "\n".join(out).strip()


def _parse_coord(token: str, width: float) -> float:
    """
    Convert an X coordinate. Valid examples:
      "120" -> 120.0 points
      "33.3%" -> 0.333 * width
    """
    t = token.strip()
    if t.endswith("%"):
        val = float(t[:-1]) / 100.0
        return val * width
    return float(t)


def parse_cols_spec(spec: str, width: float) -> List[Tuple[float, float]]:
    """
    Convert "x0:x1,x2:x3,..." into a list of (x0, x1) boxes.
    Accepts percents or points. Performs basic validations.
    """
    boxes: List[Tuple[float, float]] = []
    if not spec:
        return boxes
    parts = [p for p in spec.split(",") if p.strip()]
    for p in parts:
        if ":" not in p:
            raise ValueError(f"Invalid column spec: '{p}' (missing ':')")
        a, b = p.split(":", 1)
        x0 = _parse_coord(a, width)
        x1 = _parse_coord(b, width)
        if x1 <= x0:
            raise ValueError(f"Box with x1<=x0: '{p}' → ({x0}, {x1})")
        boxes.append((x0, x1))
    # Sanity checks for overlaps and ordering
    boxes_sorted = sorted(boxes, key=lambda t: t[0])
    for i in range(1, len(boxes_sorted)):
        if boxes_sorted[i][0] < boxes_sorted[i-1][1]:
            raise ValueError(
                "Column boxes overlap or are not ordered: "
                f"{boxes_sorted[i-1]} vs {boxes_sorted[i]}"
            )
    return boxes_sorted


def equal_columns(width: float, n: int) -> List[Tuple[float, float]]:
    """Generate n equal-width columns over [0, width]."""
    cols: List[Tuple[float, float]] = []
    step = width / float(n)
    for i in range(n):
        cols.append((i * step, (i + 1) * step))
    return cols


# ---------------------- Bold-aware text reconstruction ---------------------- #

_BOLD_TOKENS = (
    "bold", "bd", "black", "heavy", "semibold", "demi", "mediumbold"
)

def _looks_bold(fontname: str) -> bool:
    """
    Heuristic to decide whether a font name indicates a bold weight.
    """
    if not fontname:
        return False
    fn = fontname.lower()
    return any(tok in fn for tok in _BOLD_TOKENS)


def _group_chars_into_lines(chars: List[dict], line_tol: float) -> List[List[dict]]:
    """
    Group chars into lines using the 'top' coordinate with a tolerance.
    Returns a list of lines; each line is a list of char dicts.
    """
    if not chars:
        return []

    # Sort by vertical position then by x
    chars_sorted = sorted(chars, key=lambda c: (round(c.get("top", 0.0), 3), c.get("x0", 0.0)))
    lines: List[List[dict]] = []
    current_line: List[dict] = []
    current_top: Optional[float] = None

    for ch in chars_sorted:
        ch_top = ch.get("top", 0.0)
        if current_line and current_top is not None:
            # New line if vertical distance exceeds tolerance
            if abs(ch_top - current_top) > line_tol:
                # finalize previous
                lines.append(sorted(current_line, key=lambda c: c.get("x0", 0.0)))
                current_line = [ch]
                current_top = ch_top
            else:
                current_line.append(ch)
        else:
            current_line = [ch]
            current_top = ch_top

    if current_line:
        lines.append(sorted(current_line, key=lambda c: c.get("x0", 0.0)))

    return lines


def _reconstruct_line_with_bold(line_chars: List[dict], gap_ratio: float = 0.5) -> str:
    """
    Reconstruct a single text line from ordered chars, inserting spaces when the
    x-gap suggests a word boundary, and wrapping bold runs in <bold>…</bold>.
    """
    if not line_chars:
        return ""

    out: List[str] = []
    in_bold = False
    prev_x1 = None
    prev_w = None

    for ch in line_chars:
        txt = ch.get("text", "")
        if not txt:
            continue

        x0 = ch.get("x0", None)
        x1 = ch.get("x1", None)
        w = None
        if x0 is not None and x1 is not None:
            w = max(0.0, x1 - x0)

        # Space heuristic: if there is a noticeable gap, insert a space
        if prev_x1 is not None and x0 is not None:
            avg_char_w = prev_w if prev_w is not None and prev_w > 0 else 3.0
            if (x0 - prev_x1) > gap_ratio * avg_char_w:
                out.append(" ")

        # Bold state management
        is_bold = _looks_bold(ch.get("fontname", ""))

        if is_bold and not in_bold:
            out.append("<bold>")
            in_bold = True
        elif not is_bold and in_bold:
            out.append("</bold>")
            in_bold = False

        out.append(txt)

        prev_x1 = x1
        prev_w = w

    # Close tag if line ended in bold
    if in_bold:
        out.append("</bold>")

    return "".join(out)


def extract_text_with_bold(
    page: "pdfplumber.page.Page",
    bbox: Tuple[float, float, float, float],
    line_tol: float,
) -> str:
    """
    Extract text within bbox using per-char reconstruction and bold tagging.
    """
    cp = page.crop(bbox)
    chars = cp.chars or []
    # Group into lines by 'top'
    lines = _group_chars_into_lines(chars, line_tol=line_tol)

    # Build line strings
    s_lines = []
    for line_chars in lines:
        s_lines.append(_reconstruct_line_with_bold(line_chars))

    # Join with newlines, then light cleanup
    return clean_lines("\n".join(s_lines))


# --------------------------- Column-wise extraction ------------------------- #

def extract_page_columns(
    page: "pdfplumber.page.Page",
    col_boxes: List[Tuple[float, float]],
    header_ratio: float,
    footer_ratio: float,
    x_tolerance: float,  # kept for interface parity (not used directly)
    y_tolerance: float,
) -> str:
    """
    Extract text for each column box left→right using bold-aware reconstruction.
    """
    W, H = page.width, page.height
    y0 = H * header_ratio
    y1 = H * (1.0 - footer_ratio)
    if y1 <= y0:
        y0, y1 = 0, H

    col_texts: List[str] = []
    for (x0, x1) in col_boxes:
        # Clamp prudentially
        xx0 = max(0.0, min(W, x0))
        xx1 = max(0.0, min(W, x1))
        if xx1 <= xx0:
            continue

        t = extract_text_with_bold(
            page=page,
            bbox=(xx0, y0, xx1, y1),
            line_tol=max(1.0, y_tolerance),
        )
        if t:
            col_texts.append(clean_lines(t))
    return "\n\n".join([t for t in col_texts if t])


def pdf_to_txt_parity_boxes(
    pdf_path: Path,
    out_path: Path,
    start_page: int = 6,
    end_page: Optional[int] = None,
    default_cols: int = 3,
    header_ratio: float = 0.08,
    footer_ratio: float = 0.06,
    x_tolerance: float = 1.0,
    y_tolerance: float = 2.0,
    odd_cols_spec: Optional[str] = None,
    even_cols_spec: Optional[str] = None,
) -> None:
    """
    Extract text for the page range using:
      - boxes defined by odd_cols_spec for odd pages,
      - boxes defined by even_cols_spec for even pages,
      - otherwise 'default_cols' equal columns.
    Pages are 1-based for the user.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        sp = max(1, start_page)
        ep = end_page if end_page is not None else total
        ep = max(sp, min(ep, total))

        all_text: List[str] = []
        for idx0 in range(sp - 1, ep):  # idx0 is 0-based
            page = pdf.pages[idx0]
            page_num = idx0 + 1  # 1-based
            W = page.width

            # Choose boxes: odd vs even
            if (page_num % 2) == 1 and odd_cols_spec:
                col_boxes = parse_cols_spec(odd_cols_spec, W)
            elif (page_num % 2) == 0 and even_cols_spec:
                col_boxes = parse_cols_spec(even_cols_spec, W)
            else:
                col_boxes = equal_columns(W, default_cols)

            page_text = extract_page_columns(
                page=page,
                col_boxes=col_boxes,
                header_ratio=header_ratio,
                footer_ratio=footer_ratio,
                x_tolerance=x_tolerance,
                y_tolerance=y_tolerance,
            )
            if page_text:
                all_text.append(page_text)

    out_path.write_text("\n\n".join(all_text), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Export a columnar PDF to TXT with odd/even page-specific X boxes. Marks bold as <bold>…</bold>."
    )
    ap.add_argument("--pdf", required=True, type=Path, help="Input PDF")
    ap.add_argument("--out", required=True, type=Path, help="Output TXT")
    ap.add_argument("--start-page", type=int, default=6, help="Start page (1-based). Default: 6")
    ap.add_argument("--end-page", type=int, default=None, help="End page inclusive (1-based). Default: end of PDF")
    ap.add_argument("--default-cols", type=int, default=3, help="Number of columns if no spec is provided. Default: 3")
    ap.add_argument("--header-ratio", type=float, default=0.08, help="Top crop ratio [0..1]. Default: 0.08")
    ap.add_argument("--footer-ratio", type=float, default=0.06, help="Bottom crop ratio [0..1]. Default: 0.06")
    ap.add_argument("--x-tolerance", type=float, default=1.0, help="Kept for interface parity. Default: 1.0")
    ap.add_argument("--y-tolerance", type=float, default=2.0, help="Line grouping tolerance. Default: 2.0")
    ap.add_argument(
        "--odd-cols",
        type=str,
        default=None,
        help='Column spec for ODD pages, e.g. "0:180,180:360,360:540" or "0%:33.3%,33.3%:66.6%,66.6%:100%"',
    )
    ap.add_argument(
        "--even-cols",
        type=str,
        default=None,
        help='Column spec for EVEN pages, e.g. "10:200,210:400,410:590" or "0%:32%,34%:66%,68%:100%"',
    )

    args = ap.parse_args(argv)

    try:
        pdf_to_txt_parity_boxes(
            pdf_path=args.pdf,
            out_path=args.out,
            start_page=args.start_page,
            end_page=args.end_page,
            default_cols=args.default_cols,
            header_ratio=args.header_ratio,
            footer_ratio=args.footer_ratio,
            x_tolerance=args.x_tolerance,
            y_tolerance=args.y_tolerance,
            odd_cols_spec=args.odd_cols,
            even_cols_spec=args.even_cols,
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

