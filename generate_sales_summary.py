#!/usr/bin/env python3
"""
Monthly Sales Summary Generator
Combines CY YTD and PV YTD reports into a side-by-side comparison with % change.

Usage:
    python generate_sales_summary.py \
        --cy-prev  CY25_YTD.xlsx \
        --cy-curr  CY26_YTD.xlsx \
        --pv-prev  PV25_YTD.xlsx \
        --pv-curr  PV26_YTD.xlsx \
        [--output  Summary.xlsx]

The years are inferred from filenames (e.g. CY25 → 2025, CY26 → 2026).
If --output is omitted the file is saved as:
    Geistlich_CY{prev}CY{curr}_Customer_Sales_{YYYY.MM.DD}.xlsx
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


EXCLUDED_CUSTOMERS = {"- None -", "Total"}
EXCLUDED_CLASS = {"PRIME VENDOR"}


def load_cy(path: Path) -> dict[str, float]:
    """Load a CY file, dropping Prime Vendor rows and the Total/None rows."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    customer_col = header.index("Customer")
    cost_col = header.index("Total Cost")
    class_col = header.index("Class") if "Class" in header else None

    data = {}
    for row in rows[1:]:
        customer = row[customer_col]
        cost = row[cost_col]
        if customer in EXCLUDED_CUSTOMERS or customer is None:
            continue
        if class_col is not None and row[class_col] in EXCLUDED_CLASS:
            continue
        if isinstance(cost, (int, float)):
            data[str(customer)] = float(cost)
    return data


def load_pv(path: Path) -> dict[str, float]:
    """Load a PV file, dropping the None/Total rows."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    customer_col = header.index("Customer")
    cost_col = header.index("Total Cost")

    data = {}
    for row in rows[1:]:
        customer = row[customer_col]
        cost = row[cost_col]
        if customer in EXCLUDED_CUSTOMERS or customer is None:
            continue
        if isinstance(cost, (int, float)):
            data[str(customer)] = float(cost)
    return data


def infer_year(path: Path) -> str:
    """Extract 2-digit year from filename, e.g. CY26_YTD.xlsx → '26'."""
    m = re.search(r"(\d{2})_YTD", path.name, re.IGNORECASE)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot infer year from filename: {path.name}")


def pct_change(prev_total: float, curr_total: float) -> float:
    if prev_total == 0 and curr_total > 0:
        return 1.0
    if curr_total == 0 and prev_total > 0:
        return -1.0
    if prev_total == 0 and curr_total == 0:
        return 0.0
    return (curr_total - prev_total) / prev_total


def build_summary(
    cy_prev: dict, cy_curr: dict, pv_prev: dict, pv_curr: dict,
    year_prev: str, year_curr: str,
) -> list[tuple]:
    all_customers = sorted(
        set(cy_prev) | set(cy_curr) | set(pv_prev) | set(pv_curr)
    )

    header = (
        "Customer",
        f"CY20{year_prev} YTD",
        f"CY20{year_prev} PV",
        f"CY20{year_prev} Total",
        f"CY20{year_curr} YTD",
        f"CY20{year_curr} PV",
        f"CY20{year_curr} Total",
        "% Change",
    )

    rows = [header]
    sum_prev = sum_curr = 0.0

    for customer in all_customers:
        ytd_prev = cy_prev.get(customer, 0.0)
        pv_p = pv_prev.get(customer, 0.0)
        total_prev = ytd_prev + pv_p

        ytd_curr = cy_curr.get(customer, 0.0)
        pv_c = pv_curr.get(customer, 0.0)
        total_curr = ytd_curr + pv_c

        pct = pct_change(total_prev, total_curr)

        rows.append((customer, ytd_prev, pv_p, total_prev, ytd_curr, pv_c, total_curr, pct))
        sum_prev += total_prev
        sum_curr += total_curr

    overall_pct = pct_change(sum_prev, sum_curr)
    rows.append(("Total", None, None, sum_prev, None, None, sum_curr, overall_pct))

    return rows


def write_xlsx(rows: list[tuple], output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    FONT_NAME = "Book Antiqua"
    FONT_SIZE = 11
    CURRENCY_FMT = '"$"#,##0.00_);[Red]\\("$"#,##0.00\\)'
    PCT_FMT = "0.00%"
    THIN = Side(border_style="thin")
    THIN_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    # Column B has no left border in original
    B_BORDER = Border(right=THIN, top=THIN, bottom=THIN)
    CENTER = Alignment(horizontal="center")

    def base_font(bold=False):
        return Font(name=FONT_NAME, size=FONT_SIZE, bold=bold)

    for row_idx, row in enumerate(rows, start=1):
        is_header = row_idx == 1
        is_total = row[0] == "Total"

        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)

            if col_idx > 8:
                continue

            cell.alignment = CENTER

            if is_header:
                cell.font = base_font(bold=True)
                cell.border = THIN_BORDER
                cell.number_format = CURRENCY_FMT if col_idx > 1 else "General"
                continue

            # Data and total rows
            # Bold: col A always; cols D, G, H always; col B/C/E/F not bold
            is_bold_col = col_idx in (1, 4, 7, 8)
            cell.font = base_font(bold=is_bold_col)

            # Borders: col B has no left border; total row only has borders on A,D,G,H
            if is_total and col_idx not in (1, 4, 7, 8):
                pass  # no border
            elif col_idx == 2:
                cell.border = B_BORDER
            else:
                cell.border = THIN_BORDER

            # Number formats
            if col_idx in (2, 3, 4, 5, 6, 7):
                cell.number_format = CURRENCY_FMT
            elif col_idx == 8:
                cell.number_format = PCT_FMT

    # Column widths matching original exactly
    col_widths = {
        "A": 28.0, "B": 18.5703125, "C": 16.7109375, "D": 19.0,
        "E": 18.5703125, "F": 16.7109375, "G": 19.0, "H": 15.5703125,
        "I": 10.0,
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width

    ws.row_dimensions[1].height = 15.0
    ws.freeze_panes = "A2"

    wb.save(output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate monthly sales summary.")
    parser.add_argument("--cy-prev", required=True, help="CY previous year YTD xlsx")
    parser.add_argument("--cy-curr", required=True, help="CY current year YTD xlsx")
    parser.add_argument("--pv-prev", required=True, help="PV previous year YTD xlsx")
    parser.add_argument("--pv-curr", required=True, help="PV current year YTD xlsx")
    parser.add_argument("--output", default=None, help="Output xlsx path (optional)")
    args = parser.parse_args()

    cy_prev_path = Path(args.cy_prev)
    cy_curr_path = Path(args.cy_curr)
    pv_prev_path = Path(args.pv_prev)
    pv_curr_path = Path(args.pv_curr)

    for p in (cy_prev_path, cy_curr_path, pv_prev_path, pv_curr_path):
        if not p.exists():
            print(f"ERROR: File not found: {p}", file=sys.stderr)
            sys.exit(1)

    year_prev = infer_year(cy_prev_path)
    year_curr = infer_year(cy_curr_path)

    cy_prev = load_cy(cy_prev_path)
    cy_curr = load_cy(cy_curr_path)
    pv_prev = load_pv(pv_prev_path)
    pv_curr = load_pv(pv_curr_path)

    rows = build_summary(cy_prev, cy_curr, pv_prev, pv_curr, year_prev, year_curr)

    if args.output:
        output_path = Path(args.output)
    else:
        today = date.today().strftime("%-m.%-d.%Y") if sys.platform != "win32" else date.today().strftime("%#m.%#d.%Y")
        output_path = Path(f"Geistlich_CY{year_prev}CY{year_curr}_Customer_Sales_{today}.xlsx")

    write_xlsx(rows, output_path)


if __name__ == "__main__":
    main()
