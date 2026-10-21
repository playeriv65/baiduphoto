"""CLI callers consume full datasets without knowing server cursors."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pybaiduphoto import cli
from pybaiduphoto.Album import Album
from pybaiduphoto.OnlineItem import OnlineItem
from pybaiduphoto.Requests import PhotoError, Requests
from pybaiduphoto.exporting import export_metadata
from pybaiduphoto.pagination import iter_pages


def photo(identifier):
    return OnlineItem(
        {
            "fsid": identifier,
            "path": f"/{identifier}.jpg",
            "size": 7,
            "location": {"unknown_nested_field": [1, 2]},
            "extra": "original",
        },
        None,
    )


def test_album_content_requests_use_configured_batch_size():
    req = SimpleNamespace(
        config={"page_size": 100},
        postReqJson=Mock(
            return_value={"list": [photo(1).info], "has_more": 0, "cursor": None}
        ),
    )
    result = Album({"album_id": "123"}, req).get_sub_1page()
    assert len(result["items"]) == 1
    assert req.postReqJson.call_args.kwargs["data"]["limit"] == 100


def test_cli_media_source_uses_creation_time_listing():
    req = Requests({}, read_only=True)
    req.getReqJson = Mock(
        return_value={"list": [photo(1).info], "has_more": 0, "cursor": None}
    )
    OnlineItem.get_self_1page(req, stable=True)
    call = req.getReqJson.call_args.kwargs
    assert call["url"].endswith("/youai/file/v1/listrecent")
    assert call["params"]["sort_field"] == "ctime"
    assert "/youai/file/v1/listrecent" in req.config["read_paths"]
    OnlineItem.get_self_1page(req)
    call = req.getReqJson.call_args.kwargs
    assert call["url"].endswith("/youai/file/v1/list")
    assert "sort_field" not in call["params"]


def setup_cli(monkeypatch, argv, fetch):
    monkeypatch.setattr("sys.argv", ["baiduphoto", *argv])
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda path: {"cookies_file": "unused", "page_delay_seconds": 0},
    )
    monkeypatch.setattr(cli, "load_cookies", lambda path: {})
    api = SimpleNamespace(get_self_1page=fetch)
    monkeypatch.setattr(cli, "API", lambda *args, **kwargs: api)


def media_pages(kind, cursor=None, *, stable=False):
    pages = {
        None: {
            "items": [photo(i) for i in range(1, 101)],
            "has_more": True,
            "cursor": "second",
        },
        "second": {
            "items": [photo(i) for i in range(100, 201)],
            "has_more": True,
            "cursor": "third",
        },
        "third": {
            "items": [photo(i) for i in range(201, 251)],
            "has_more": False,
            "cursor": "end",
        },
    }
    return pages[cursor]


def test_list_defaults_to_all_pages(monkeypatch, capsys):
    fetch = Mock(side_effect=media_pages)
    setup_cli(monkeypatch, ["list"], fetch)
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result) == 250
    assert result[-1]["fsid"] == "250"
    assert fetch.call_count == 3
    assert all(call.kwargs["stable"] is True for call in fetch.call_args_list)


def test_list_limit_is_an_explicit_preview(monkeypatch, capsys):
    fetch = Mock(side_effect=media_pages)
    setup_cli(monkeypatch, ["list", "--limit", "5", "--raw"], fetch)
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result) == 5 and result[0] == photo(1).info
    assert fetch.call_count == 1


def test_export_fetches_all_pages_and_preserves_raw_metadata(
    monkeypatch, capsys, tmp_path
):
    fetch = Mock(side_effect=media_pages)
    path = tmp_path / "raw.jsonl"
    setup_cli(monkeypatch, ["export", "--output", str(path)], fetch)
    assert cli.main() == 0
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 250 and rows[0] == photo(1).info
    report = json.loads(capsys.readouterr().out)
    assert report["unique_media"] == 250 and report["bytes"] == 1750
    assert report["media_downloaded"] == 0
    assert fetch.call_count == 3


def test_recursive_export_follows_parent_and_child_pages(tmp_path):
    children = Mock(
        side_effect=[
            {"items": [photo(1)], "has_more": True, "cursor": "next"},
            {"items": [photo(2)], "has_more": False, "cursor": None},
        ]
    )
    album1 = SimpleNamespace(
        info={"album_id": "a", "title": "one"},
        getID=lambda: "a",
        get_sub_1page=children,
    )
    album2 = SimpleNamespace(
        info={"album_id": "b", "title": "two"},
        getID=lambda: "b",
        get_sub_1page=lambda cursor=None: {
            "items": [photo(1)],
            "has_more": False,
            "cursor": None,
        },
    )
    roots = Mock(
        side_effect=[
            {"items": [album1], "has_more": True, "cursor": "more"},
            {"items": [album2], "has_more": False, "cursor": None},
        ]
    )
    output = tmp_path / "recursive.jsonl"
    report = export_metadata(iter_pages(roots), output, kind="Album", recursive=True)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 5
    assert rows[0] == {"type": "Album", "metadata": album1.info}
    assert rows[1]["parent"] == {"type": "Album", "id": "a"}
    assert rows[-1]["parent"] == {"type": "Album", "id": "b"}
    assert report["object_counts"] == {"Album": 2, "Item": 3}
    assert report["unique_media"] == 2 and report["bytes"] == 14
    assert roots.call_count == children.call_count == 2


def test_recursive_failure_keeps_export_partial(tmp_path):
    album = SimpleNamespace(
        info={"album_id": "a"},
        getID=lambda: "a",
        get_sub_1page=Mock(side_effect=PhotoError("failure")),
    )
    path = tmp_path / "recursive.jsonl"
    with pytest.raises(PhotoError):
        export_metadata([album], path, kind="Album", recursive=True)
    assert not path.exists()
    assert path.with_suffix(".jsonl.partial").exists()


def test_existing_export_does_not_fetch_or_overwrite(tmp_path):
    output = tmp_path / "raw.jsonl"
    output.write_text("existing")
    fetch = Mock()
    with pytest.raises(ValueError):
        export_metadata(iter_pages(fetch), output)
    assert output.read_text() == "existing"
    fetch.assert_not_called()


@pytest.mark.parametrize(
    "argv",
    [
        ["list", "--kind", "Album", "--album-id", "123"],
        ["list", "--limit", "-1"],
        ["export", "--recursive", "--output", "unused"],
    ],
)
def test_invalid_scope_fails_before_session_loading(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["baiduphoto", *argv])
    cookies = Mock(side_effect=AssertionError("session loaded"))
    monkeypatch.setattr(cli, "load_cookies", cookies)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    cookies.assert_not_called()
