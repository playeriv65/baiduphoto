"""Streaming pagination that fails on stalled cursors and suppresses duplicates."""

import json
import time


def iter_pages(fetch, limit=None, *, delay=0):
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative or None")
    if limit == 0:
        return
    if delay < 0:
        raise ValueError("delay must be non-negative")
    cursor = None
    cursors = set()
    seen = set()
    count = 0
    while True:
        if cursor is not None and delay:
            time.sleep(delay)
        page = fetch(cursor=cursor)
        for item in page["items"]:
            key = str(item.getID())
            if key in seen:
                continue
            seen.add(key)
            yield item
            count += 1
            if limit is not None and count >= limit:
                return
        if not page["has_more"]:
            return
        cursor = page["cursor"]
        key = json.dumps(cursor, sort_keys=True)
        if cursor in (None, "") or key in cursors:
            raise RuntimeError("Pagination stalled: missing or repeated cursor")
        cursors.add(key)
