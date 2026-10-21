"""Build portable, collision-resistant backup paths from metadata only."""

import json
from pathlib import Path
import re


def safe_filename(name, fsid):
    if not re.fullmatch(r"[0-9]{1,20}", str(fsid)):
        raise ValueError("Expected a numeric file identifier")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    path = Path(name or "unnamed")
    suffix = path.suffix[:20]
    stem = path.stem[:80].rstrip(" .") or "unnamed"
    # Prefixing avoids reserved DOS device names; fsid prevents filename collisions.
    return f"{fsid}_{stem}{suffix}"


def make_plan(inventory, output, destination, name_contains="", media="all"):
    inventory, output = Path(inventory), Path(output)
    if inventory.name.endswith(".partial"):
        raise ValueError("Use a completed inventory, not a partial export")
    if media not in ("all", "photo", "video"):
        raise ValueError("Unknown media filter")
    if output.exists():
        raise ValueError("Output already exists")
    destination = Path(destination).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    count = total = 0
    seen = set()
    with (
        inventory.open(encoding="utf-8") as source,
        partial.open("x", encoding="utf-8") as target,
    ):
        for line in source:
            row = json.loads(line)
            if name_contains.casefold() not in row["name"].casefold():
                continue
            if (
                media != "all"
                and row.get("category") != {"photo": 3, "video": 1}[media]
            ):
                continue
            fsid = str(row["fsid"])
            if fsid in seen:
                continue
            seen.add(fsid)
            row["destination"] = str(destination / safe_filename(row["name"], fsid))
            # Only selected inventory fields are propagated, never dlinks/cookies.
            row = {
                key: row[key]
                for key in (
                    "fsid",
                    "name",
                    "size",
                    "md5",
                    "server_md5",
                    "category",
                    "shoot_time",
                    "ctime",
                    "mtime",
                    "destination",
                )
                if key in row
            }
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
            total += int(row.get("size", 0))
    partial.replace(output)
    return {
        "count": count,
        "bytes": total,
        "media_downloaded": 0,
        "destination": str(destination),
        "output": str(output.resolve()),
    }
