"""
Generate an SVG calendar heatmap of photos-per-day from the gallery SQLite DB.
Outputs one SVG file per year (yearN.svg) to the specified output directory.
Usage: python heatmap_svg.py [--db path/to/sqlite.db] [--out ./out] [--years 1]
"""

import sqlite3
import argparse
import os
import math
from datetime import date, timedelta
from collections import defaultdict

CELL = 11        # cell size px
GAP = 2          # gap between cells
MONTH_LABEL_H = 16
DAY_LABEL_W = 24
LEGEND_H = 24
PADDING = 8

# GitHub-style green palette (light mode) + matching dark mode
COLORS_LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
COLORS_DARK  = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

WEEKDAYS = ["Mon", "", "Wed", "", "Fri", "", "Sun"]
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def load_counts(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT strftime('%Y-%m-%d', date), COUNT(*) FROM exifdata GROUP BY strftime('%Y-%m-%d', date)")
    counts = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return counts


def color_index(count: int, max_count: int) -> int:
    if count == 0:
        return 0
    if max_count <= 1:
        return 4
    # log scale looks nicer for sparse data
    ratio = math.log(count + 1) / math.log(max_count + 1)
    return min(4, max(1, int(ratio * 4) + 1))


def year_start(year: int) -> date:
    d = date(year, 1, 1)
    # start from the Monday of that week
    return d - timedelta(days=d.weekday())


def build_svg(year: int, counts: dict, max_count: int) -> str:
    start = year_start(year)
    end = date(year, 12, 31)

    # collect weeks
    weeks = []
    cur = start
    while cur <= end + timedelta(days=6):
        week = []
        for _ in range(7):
            week.append(cur)
            cur += timedelta(days=1)
        weeks.append(week)

    n_weeks = len(weeks)
    width  = DAY_LABEL_W + n_weeks * (CELL + GAP) + PADDING * 2
    height = MONTH_LABEL_H + 7 * (CELL + GAP) + LEGEND_H + PADDING * 2

    def cell_x(wi: int) -> int:
        return DAY_LABEL_W + PADDING + wi * (CELL + GAP)

    def cell_y(di: int) -> int:
        return MONTH_LABEL_H + PADDING + di * (CELL + GAP)

    parts = []

    # --- SVG open ---
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )

    # --- style block for dark mode ---
    parts.append("""
<style>
  .hm-bg  { fill: transparent; }
  .hm-txt { fill: #57606a; font: 10px -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  .hm-c0  { fill: #ebedf0; } .hm-c1 { fill: #9be9a8; }
  .hm-c2  { fill: #40c463; } .hm-c3 { fill: #30a14e; }
  .hm-c4  { fill: #216e39; }
  @media (prefers-color-scheme: dark) {
    .hm-txt { fill: #8b949e; }
    .hm-c0  { fill: #161b22; } .hm-c1 { fill: #0e4429; }
    .hm-c2  { fill: #006d32; } .hm-c3 { fill: #26a641; }
    .hm-c4  { fill: #39d353; }
  }
</style>
""")

    # --- background ---
    parts.append(f'<rect class="hm-bg" width="{width}" height="{height}"/>')

    # --- weekday labels ---
    for di, label in enumerate(WEEKDAYS):
        if label:
            y = cell_y(di) + CELL - 2
            parts.append(
                f'<text class="hm-txt" x="{PADDING}" y="{y}" '
                f'text-anchor="start">{label}</text>'
            )

    # --- month labels ---
    last_month = None
    for wi, week in enumerate(weeks):
        first_in_year = next((d for d in week if d.year == year), None)
        if not first_in_year:
            continue
        if first_in_year.month != last_month:
            last_month = first_in_year.month
            x = cell_x(wi)
            parts.append(
                f'<text class="hm-txt" x="{x}" y="{PADDING + MONTH_LABEL_H - 4}" '
                f'text-anchor="start">{MONTHS[first_in_year.month - 1]}</text>'
            )

    # --- cells ---
    for wi, week in enumerate(weeks):
        for di, d in enumerate(week):
            key = d.strftime("%Y-%m-%d")
            cnt = counts.get(key, 0)
            in_year = (d.year == year)
            ci = color_index(cnt, max_count) if in_year else 0
            x = cell_x(wi)
            y = cell_y(di)
            title = f"{cnt} photo{'s' if cnt != 1 else ''} on {d.isoformat()}" if in_year and cnt else d.isoformat()
            parts.append(
                f'<rect class="hm-c{ci}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'rx="2" ry="2"><title>{title}</title></rect>'
            )

    # --- legend ---
    legend_y = cell_y(7) + PADDING
    lx = width - PADDING - 5 * (CELL + GAP)
    parts.append(
        f'<text class="hm-txt" x="{lx - 4}" y="{legend_y + CELL - 1}" '
        f'text-anchor="end">Less</text>'
    )
    for i in range(5):
        parts.append(
            f'<rect class="hm-c{i}" x="{lx + i * (CELL + GAP)}" y="{legend_y}" '
            f'width="{CELL}" height="{CELL}" rx="2" ry="2"/>'
        )
    parts.append(
        f'<text class="hm-txt" x="{lx + 5 * (CELL + GAP)}" y="{legend_y + CELL - 1}" '
        f'text-anchor="start">More</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",    default="./public/sqlite.db")
    parser.add_argument("--out",   default="./heatmap_out")
    parser.add_argument("--years", type=int, default=0,
                        help="Number of most-recent years to generate (0 = all)")
    args = parser.parse_args()

    counts = load_counts(args.db)
    if not counts:
        print("No EXIF date data found in database.")
        return

    all_years = sorted({d[:4] for d in counts})
    max_count = max(counts.values())

    if args.years > 0:
        all_years = all_years[-args.years:]

    os.makedirs(args.out, exist_ok=True)

    for i, year_str in enumerate(reversed(all_years)):
        year = int(year_str)
        svg = build_svg(year, counts, max_count)
        out_path = os.path.join(args.out, f"year{i}.svg")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"Written {out_path}  ({year})")


if __name__ == "__main__":
    main()
