"""Convert the user's Excel grid workbook to seed/mega645.csv (date,n1..n6).

Only complete draws are written. Draws that have a draw number but no numbers are listed
on stderr and are never filled in or interpolated.

Usage:  python scripts/xlsx_to_seed_csv.py "Mega 6-45 Vietnam.xlsx" seed/mega645.csv
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.importers.excel_grid import parse_grid  # noqa: E402
from app.validation import GameSpec  # noqa: E402

MEGA = GameSpec(code="vn_mega_645", n=45, k=6)


def main(src: str, dst: str) -> None:
    r = parse_grid(src, MEGA)
    if r.rejected:
        for x in r.rejected:
            print(f"REJECTED row {x.line_no}: {x.reason}", file=sys.stderr)
        raise SystemExit("workbook has rejected rows; fix them before seeding")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "n1", "n2", "n3", "n4", "n5", "n6"])
        for d in r.draws:  # oldest -> newest
            w.writerow([d.draw_date.isoformat(), *d.numbers])
    nos = [d.draw_no for d in r.draws if d.draw_no is not None]
    print(f"wrote {len(r.draws)} draws ({min(nos)}..{max(nos)}) to {dst}")
    have = set(nos)
    gaps = [n for n in range(min(nos), max(nos) + 1) if n not in have]
    print(f"NOT in file: {len(gaps)} draw numbers between {min(nos)} and {max(nos)}", file=sys.stderr)
    print("  " + ", ".join(map(str, gaps)), file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
