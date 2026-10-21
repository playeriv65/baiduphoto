"""Export unmodified API object metadata, including optional container membership."""

from collections import Counter
import json
from pathlib import Path
import sys

from .pagination import iter_pages


def records(objects, kind, recursive=False, delay=0):
    for obj in objects:
        yield kind, obj.info, None
        if recursive:
            parent = {"type": kind, "id": str(obj.getID())}
            for child in iter_pages(obj.get_sub_1page, delay=delay):
                yield "Item", child.info, parent


def export_metadata(objects, output, *, kind="Item", recursive=False, delay=0):
    if recursive and kind == "Item":
        raise ValueError("Item has no child objects")
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; select a new export path")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    counts = Counter()
    media = set()
    total = count = 0
    with partial.open("x", encoding="utf-8") as handle:
        for object_kind, info, parent in records(objects, kind, recursive, delay):
            row = {"type": object_kind, "metadata": info} if recursive else info
            if parent is not None:
                row["parent"] = parent
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            counts[object_kind] += 1
            count += 1
            if object_kind == "Item":
                fsid = str(info.get("fsid", info.get("fs_id")))
                if fsid not in media:
                    media.add(fsid)
                    total += int(info.get("size", 0))
            if count % 100 == 0:
                handle.flush()
                print(f"Exported {count} records", file=sys.stderr, flush=True)
    partial.replace(output)
    return {
        "records": count,
        "object_counts": dict(counts),
        "unique_media": len(media),
        "bytes": total,
        "recursive": recursive,
        "format": "jsonl",
        "metadata": "raw",
        "output": str(output.resolve()),
        "media_downloaded": 0,
    }
