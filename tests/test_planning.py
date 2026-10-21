"""Offline backup plans must not write media or allow path escape."""

import json

import pytest

from pybaiduphoto.planning import make_plan, safe_filename


@pytest.mark.parametrize(
    "name", ["../../escape.jpg", "CON.jpg", "a:b?c.jpg", "C:\\a.jpg", "照片.jpg", "."]
)
def test_safe_filename_stays_inside_destination(name):
    result = safe_filename(name, "123")
    assert result.startswith("123_")
    assert "/" not in result and "\\" not in result and ":" not in result
    assert not result.endswith((" ", "."))


def test_plan_filters_and_deduplicates_without_creating_media_directory(tmp_path):
    source = tmp_path / "inventory.jsonl"
    rows = [
        {"fsid": "1", "name": "旅行.jpg", "size": 12, "category": 3, "dlink": "secret"},
        {"fsid": "1", "name": "旅行.jpg", "size": 12, "category": 3},
        {"fsid": "2", "name": "旅行.mp4", "size": 50, "category": 1},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    output = tmp_path / "plan.jsonl"
    destination = tmp_path / "media"
    report = make_plan(source, output, destination, "旅行", "photo")
    assert report["count"] == 1 and report["bytes"] == 12
    assert "secret" not in output.read_text("utf-8")
    assert not destination.exists()


def test_partial_inventory_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_plan(
            tmp_path / "inventory.jsonl.partial", tmp_path / "plan", tmp_path / "media"
        )
