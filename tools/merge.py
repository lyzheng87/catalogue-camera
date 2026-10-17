"""Merge a Catalogue Camera JSON export into a master file and build an HTML catalogue.

Usage: uv run tools/merge.py <export.json> [--master PATH]
"""

import argparse
import html
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MASTER = Path(__file__).resolve().parent.parent / "Catalogue" / "master.json"
VIEW_LABELS = ["First View", "Second View", "Third View"]
UNGROUPED = "Ungrouped"

Item = dict[str, Any]


def load_items(path: Path) -> list[Item]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("items"), list):
        raise SystemExit(f"Invalid backup file: {path}")
    return payload["items"]


def modified_at(item: Item) -> int:
    return item.get("updatedAt") or item.get("createdAt") or 0


def merge(master: list[Item], incoming: list[Item]) -> tuple[list[Item], int, int]:
    by_id = {item["id"]: item for item in master}
    added = updated = 0
    for item in incoming:
        existing = by_id.get(item["id"])
        if existing is None:
            added += 1
        elif modified_at(item) > modified_at(existing):
            updated += 1
        else:
            continue
        by_id[item["id"]] = item
    return list(by_id.values()), added, updated


def duplicate_part_numbers(items: list[Item]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item["partNo"].strip().upper()] += 1
    return sorted(part_no for part_no, count in counts.items() if count > 1)


def natural_key(text: str) -> list[int | str]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", text)]


def group_items(items: list[Item]) -> list[tuple[str, list[Item]]]:
    groups: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        groups[(item.get("group") or "").strip() or UNGROUPED].append(item)
    return [
        (name, sorted(group, key=lambda item: natural_key(item["partNo"])))
        for name, group in sorted(groups.items(), key=lambda entry: entry[0].lower())
    ]


def photo_cell(photo: str | None) -> str:
    if not photo:
        return "<td class=\"img\">—</td>"
    return f'<td class="img"><a href="{photo}" target="_blank"><img src="{photo}" alt=""></a></td>'


def build_html(items: list[Item]) -> str:
    esc = lambda value: html.escape(value or "")
    header = "".join(f"<th>{label}</th>" for label in VIEW_LABELS)
    sections = []
    for group_name, group in group_items(items):
        rows = "\n".join(
            f"<tr><td><b>{esc(item['partNo'])}</b></td><td>{esc(item.get('name'))}</td>"
            f"<td>{esc(item.get('brand'))}</td>"
            + "".join(photo_cell(photo) for photo in (item.get("photos") or [])[: len(VIEW_LABELS)])
            + "</tr>"
            for item in group
        )
        sections.append(
            f"<h2>{esc(group_name)} <small>({len(group)})</small></h2>\n<table>\n"
            f"<thead><tr><th>Part No.</th><th>Name</th><th>Brand</th>{header}</tr></thead>\n"
            f"<tbody>\n{rows}\n</tbody>\n</table>"
        )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalogue {generated[:10]}</title>
<style>
body{{font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;color:#1c1c1e}}
h1{{margin:0 0 4px}}h2{{margin:28px 0 8px;border-bottom:2px solid #007aff;padding-bottom:4px}}
h2 small{{color:#8e8e93;font-weight:400}}
table{{width:100%;border-collapse:collapse;page-break-inside:auto}}
tr{{page-break-inside:avoid}}
th,td{{border:1px solid #d1d1d6;padding:6px;text-align:left;vertical-align:middle}}
th{{background:#f2f2f7}}
td.img{{width:130px;text-align:center}}
td.img img{{width:120px;height:120px;object-fit:cover;border-radius:6px;display:block;margin:auto}}
</style></head><body>
<h1>Catalogue</h1><p style="color:#8e8e93">Master · generated {generated} · {len(items)} items</p>
{chr(10).join(sections)}
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path, help="JSON backup exported from the iPhone app")
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER, help=f"default: {DEFAULT_MASTER}")
    args = parser.parse_args()

    master_path: Path = args.master.expanduser()
    master_path.parent.mkdir(parents=True, exist_ok=True)
    master = load_items(master_path) if master_path.exists() else []
    if master_path.exists():
        shutil.copy2(master_path, master_path.with_suffix(".backup.json"))

    merged, added, updated = merge(master, load_items(args.export.expanduser()))
    payload = {"app": "catalogue-camera", "version": 1, "exportedAt": datetime.now().astimezone().isoformat(), "items": merged}
    master_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    html_path = master_path.with_name("catalogue.html")
    html_path.write_text(build_html(merged), encoding="utf-8")

    print(f"Added {added}, updated {updated}, total {len(merged)} items")
    print(f"Master: {master_path}")
    print(f"HTML:   {html_path}")
    duplicates = duplicate_part_numbers(merged)
    if duplicates:
        print(f"⚠️  Duplicate Part No. (different entries): {', '.join(duplicates)}")


if __name__ == "__main__":
    main()
