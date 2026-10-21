"""Read-only inspection and metadata export. No media download commands."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import requests

from .API import API
from .Album import Album
from .Requests import PhotoError
from .config import load_config
from .pagination import iter_pages
from .exporting import export_metadata


def load_cookies(path):
    data = json.loads(Path(path).read_text("utf-8"))
    if isinstance(data, dict):
        data = [{"name": name, "value": value} for name, value in data.items()]
    jar = requests.cookies.RequestsCookieJar()
    for entry in data:
        domain = entry.get("domain", "photo.baidu.com")
        if domain.lstrip(".") != "baidu.com" and not domain.endswith(".baidu.com"):
            continue
        jar.set(
            entry["name"],
            entry["value"],
            domain=domain,
            path=entry.get("path", "/"),
            secure=entry.get("secure", True),
        )
    if not jar:
        raise ValueError("Cookie file contains no Baidu cookies")
    return jar


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def metadata(item):
    fields = (
        "size",
        "md5",
        "server_md5",
        "category",
        "shoot_time",
        "ctime",
        "mtime",
        "file_cnt",
        "pic_count",
    )
    return {
        "fsid": item.getID(),
        "name": item.getName(),
        **{key: item.info[key] for key in fields if key in item.info},
    }


def source(api, kind, album_id):
    return (
        Album({"album_id": album_id}, api.req).get_sub_1page
        if album_id
        else (lambda cursor=None: api.get_self_1page(kind, cursor=cursor))
    )


def doctor(api):
    report = {"read_only": True, "media_downloaded": 0, "checks": {}}
    first = None
    albums = []
    for kind in ("Item", "Album", "Person", "Location", "Thing"):
        print(f"Checking {kind}", file=sys.stderr, flush=True)
        page = api.get_self_1page(kind)
        report["checks"][kind] = {
            "first_page_count": len(page["items"]),
            "has_more": page["has_more"],
        }
        if kind == "Item":
            first = page["items"][0] if page["items"] else None
            if page["has_more"]:
                second = api.get_self_1page(kind, cursor=page["cursor"])
                if second["cursor"] == page["cursor"] and second["has_more"]:
                    raise PhotoError("Item cursor did not advance")
                report["checks"]["Item"]["second_page_count"] = len(second["items"])
        if kind == "Album":
            albums = page["items"]
    report["checks"]["album_contents"] = []
    for album in albums:
        page = album.get_sub_1page()
        report["checks"]["album_contents"].append(
            {"first_page_count": len(page["items"]), "has_more": page["has_more"]}
        )
    if first:
        link = first.get_download_link()
        report["checks"]["single_download_link"] = {
            "resolved": bool(link),
            "host": urlsplit(link).hostname,
        }
        link = api.get_batchDownloadLink([first], zipname="probe.zip")
        report["checks"]["batch_download_link"] = {
            "resolved": bool(link),
            "host": urlsplit(link).hostname,
        }
    return report


def export_inventory(items, output, scope):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    count = total = 0
    categories = Counter()
    # Exclusive creation prevents accidental replacement of an existing inventory.
    if output.exists():
        raise ValueError("Output already exists; select a new inventory path")
    with partial.open("x", encoding="utf-8") as handle:
        for item in items:
            row = metadata(item)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
            total += int(row.get("size", 0))
            categories[str(row.get("category"))] += 1
            if count % 100 == 0:
                handle.flush()
                print(f"Indexed {count} items", file=sys.stderr, flush=True)
    os.replace(partial, output)
    return {
        "scope": scope,
        "count": count,
        "bytes": total,
        "categories": dict(categories),
        "output": str(output.resolve()),
        "media_downloaded": 0,
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Non-secret JSON configuration")
    parser.add_argument("--cookies", help="Local cookie JSON file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "doctor", help="Test list, pagination, album contents and link resolution"
    )
    listing = sub.add_parser(
        "list", help="List all objects, automatically following all API cursors"
    )
    listing.add_argument(
        "--kind",
        choices=["Item", "Album", "Person", "Location", "Thing"],
        default="Item",
    )
    listing.add_argument(
        "--limit", type=int, help="Return only the first N objects; default: all"
    )
    listing.add_argument(
        "--raw",
        action="store_true",
        help="Return complete API metadata instead of compact fields",
    )
    listing.add_argument("--album-id")
    export = sub.add_parser(
        "export", help="Export complete raw metadata for all objects as JSON Lines"
    )
    export.add_argument(
        "--kind",
        choices=["Item", "Album", "Person", "Location", "Thing"],
        default="Item",
    )
    export.add_argument("--album-id", help="Export all files in this album")
    export.add_argument(
        "--recursive",
        action="store_true",
        help="Also export every file in every selected album/classification",
    )
    export.add_argument("--output", required=True)
    inventory = sub.add_parser(
        "inventory", help="Export all media metadata without downloading media"
    )
    inventory.add_argument("--album-id")
    inventory.add_argument("--output", required=True)
    plan = sub.add_parser(
        "plan",
        help="Prepare a local download plan; does not contact Baidu or download media",
    )
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--destination", required=True)
    plan.add_argument("--name-contains", default="")
    plan.add_argument("--media", choices=["all", "photo", "video"], default="all")
    args = parser.parse_args()
    if getattr(args, "album_id", None) and getattr(args, "kind", "Item") != "Item":
        parser.error("--album-id selects media files and requires --kind Item")
    if args.command == "list" and args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.command == "export" and args.recursive and args.kind == "Item":
        parser.error(
            "--recursive requires Album, Person, Location or Thing; Item already exports all files"
        )
    try:
        if args.command == "plan":
            from .planning import make_plan

            emit(
                make_plan(
                    args.inventory,
                    args.output,
                    args.destination,
                    args.name_contains,
                    args.media,
                )
            )
            return 0
        config = load_config(args.config)
        cookies = load_cookies(args.cookies or config["cookies_file"])
        api = API(cookies, read_only=True, config=config)
        if args.command == "doctor":
            emit(doctor(api))
        elif args.command == "list":
            items = iter_pages(
                source(api, args.kind, args.album_id),
                args.limit,
                delay=config["page_delay_seconds"],
            )
            emit([item.info if args.raw else metadata(item) for item in items])
        elif args.command == "export":
            items = iter_pages(
                source(api, args.kind, args.album_id),
                delay=config["page_delay_seconds"],
            )
            emit(
                export_metadata(
                    items,
                    args.output,
                    kind=args.kind,
                    recursive=args.recursive,
                    delay=config["page_delay_seconds"],
                )
            )
        else:
            items = iter_pages(
                source(api, "Item", args.album_id), delay=config["page_delay_seconds"]
            )
            emit(
                export_inventory(
                    items, args.output, {"album_id": args.album_id, "type": "Item"}
                )
            )
        return 0
    except (PhotoError, ValueError, OSError, RuntimeError) as error:
        # Do not print server payloads, signed URLs, cookies or arbitrary file contents.
        message = (
            str(error)
            if isinstance(error, (PhotoError, RuntimeError))
            else type(error).__name__
        )
        print(
            f"Inspection failed: {message}. Incomplete exports retain .partial.",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
