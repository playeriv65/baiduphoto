"""Regression tests for authentication, read-only boundaries and pagination."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from pybaiduphoto import API
from pybaiduphoto.General import General
from pybaiduphoto.Requests import PhotoError, Requests
from pybaiduphoto.cli import export_inventory, load_cookies
from pybaiduphoto.OnlineItem import OnlineItem
from pybaiduphoto.pagination import iter_pages


def item(identifier):
    return OnlineItem(
        {"fsid": identifier, "path": f"/{identifier}.jpg", "size": 12}, None
    )


@pytest.mark.parametrize(
    "html",
    [
        "var templateData = { bdstoken: 'token=with=equals', uk: 42 };",
        '<script>window.templateData={"uk":42,\n"bdstoken":"token=with=equals"}</script>',
    ],
)
def test_token_parsing_does_not_depend_on_field_order(html):
    assert Requests.parse_bdstoken(html) == "token=with=equals"


def test_missing_token_fails():
    with pytest.raises(PhotoError, match="Login token missing"):
        Requests.parse_bdstoken("<html>Login</html>")


@pytest.mark.parametrize(
    "path,method",
    [
        ("/youai/file/v1/delete", "GET"),
        ("/youai/album/v1/create", "GET"),
        ("/youai/album/v1/delfile", "POST"),
        ("/youai/file/v1/list", "POST"),
        ("/photo/web/home", "DELETE"),
    ],
)
def test_readonly_blocks_before_any_network(path, method):
    transport = Requests({}, read_only=True)
    transport.session.request = Mock(side_effect=AssertionError("network contacted"))
    with pytest.raises(PhotoError, match="blocked"):
        transport._request(method, "https://photo.baidu.com" + path)
    transport.session.request.assert_not_called()


def test_readonly_blocks_media_even_if_same_origin():
    transport = Requests({}, read_only=True)
    with pytest.raises(PhotoError):
        transport.get("https://photo.baidu.com/media.jpg")
    with pytest.raises(PhotoError):
        transport.get("https://cdn.example.test/media.jpg")


def test_list_preserves_params_and_sets_timeout():
    transport = Requests({}, read_only=True)
    transport.bdstoken = "test-token"
    transport.session.request = Mock(
        return_value=SimpleNamespace(raise_for_status=lambda: None, is_redirect=False)
    )
    params = {"cursor": "one"}
    transport.get("https://photo.baidu.com/youai/file/v1/list", params=params)
    assert params == {"cursor": "one"}
    kwargs = transport.session.request.call_args.kwargs
    assert kwargs["timeout"] > 0
    assert kwargs["allow_redirects"] is False
    assert kwargs["params"]["bdstoken"] == "test-token"


def test_http_exception_does_not_leak_signed_url():
    transport = Requests({})
    transport.bdstoken = "test-token"
    transport.session.request = Mock(
        side_effect=requests.ConnectionError("secret-cookie-token")
    )
    with pytest.raises(PhotoError) as error:
        transport.get("https://photo.baidu.com/youai/file/v1/list")
    assert "secret" not in str(error.value)


def test_external_media_request_has_no_api_credentials(monkeypatch):
    transport = Requests({"BDUSS": "private"})
    transport.session.request = Mock(side_effect=AssertionError("API session used"))
    external = Mock(
        return_value=SimpleNamespace(raise_for_status=lambda: None, is_redirect=False)
    )
    monkeypatch.setattr(requests, "request", external)
    transport.get("https://cdn.example.test/file?signature=fake")
    kwargs = external.call_args.kwargs
    assert "cookies" not in kwargs and "params" not in kwargs
    assert "Referer" not in kwargs["headers"]
    assert kwargs["allow_redirects"] is True


def test_api_error_does_not_become_missing_list_key():
    response = SimpleNamespace(json=lambda: {"errno": -6, "data": "secret"})
    with pytest.raises(PhotoError, match="errno=-6") as error:
        Requests._json(response)
    assert "secret" not in str(error.value)


def test_pagination_deduplicates_and_honors_limit():
    fetch = Mock(
        side_effect=[
            {"items": [item(1), item(2)], "has_more": True, "cursor": "next"},
            {"items": [item(2), item(3)], "has_more": True, "cursor": "last"},
        ]
    )
    assert [obj.getID() for obj in iter_pages(fetch, 3)] == ["1", "2", "3"]
    assert fetch.call_count == 2


def test_zero_limit_does_not_fetch():
    fetch = Mock()
    assert list(iter_pages(fetch, 0)) == []
    fetch.assert_not_called()


def test_repeated_cursor_fails_instead_of_looping():
    fetch = Mock(return_value={"items": [], "has_more": True, "cursor": "same"})
    with pytest.raises(RuntimeError, match="Pagination stalled"):
        list(iter_pages(fetch))
    assert fetch.call_count == 2


def test_export_keeps_partial_and_never_labels_failed_export_complete(tmp_path):
    def broken():
        yield item(1)
        raise PhotoError("test failure")

    output = tmp_path / "inventory.jsonl"
    with pytest.raises(PhotoError):
        export_inventory(broken(), output, {})
    assert not output.exists()
    assert output.with_suffix(".jsonl.partial").exists()


def test_inventory_omits_signed_urls_and_never_downloads(tmp_path):
    photo = item(1)
    photo.info["dlink"] = "secret"
    photo.getContent_byRequest = Mock(side_effect=AssertionError("download"))
    output = tmp_path / "inventory.jsonl"
    report = export_inventory([photo], output, {})
    assert report["count"] == 1 and report["bytes"] == 12
    assert "secret" not in output.read_text()
    photo.getContent_byRequest.assert_not_called()


def test_cookie_import_preserves_scope_and_omits_other_sites(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"name": "BDUSS", "value": "fake", "domain": ".baidu.com"},
                {"name": "other", "value": "fake", "domain": "example.test"},
            ]
        )
    )
    cookies = list(load_cookies(path))
    assert len(cookies) == 1 and cookies[0].domain == ".baidu.com"


def test_link_resolution_does_not_fetch_content():
    api = API({}, read_only=True)
    api.req.getReqJson = Mock(
        return_value={"errno": 0, "dlink": "https://cdn.test/file"}
    )
    api.req.get = Mock(side_effect=AssertionError("media transfer"))
    photo = OnlineItem({"fsid": 1}, api.req)
    assert photo.get_download_link() == "https://cdn.test/file"
    api.req.get.assert_not_called()


def test_batch_signature_matches_rc4_vector_and_has_no_newlines():
    assert (
        General.funcS("Key", "Plaintext").encode("latin1").hex() == "bbf316e8d940af0ad3"
    )
    signature = General.get_sign_by_sign1sign2sign3("Plaintext" * 20, "unused", "Key")
    assert "\n" not in signature
