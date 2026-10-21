"""Bounded HTTP transport with explicit API errors and optional read-only mode."""

import re
from urllib.parse import urlsplit

import requests
from .config import load_config


class PhotoError(RuntimeError):
    """A sanitized error that never includes cookies or signed URLs."""


class Requests:
    def __init__(self, cookies, proxies=None, *, read_only=False, config=None):
        self.config = load_config()
        self.config.update(config or {})
        self.cookies = cookies
        self.proxies = proxies
        self.read_only = read_only
        self.bdstoken = None
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": self.config["user_agent"],
            "Referer": self.config["base_url"] + self.config["home_path"],
        }

    def get_proxies(self):
        return dict(self.proxies or {})

    def _request(self, method, url, *, api=True, **kwargs):
        parts = urlsplit(url)
        origin = urlsplit(self.config["base_url"])
        same_origin = (parts.scheme, parts.netloc) == (origin.scheme, origin.netloc)
        path = parts.path
        if self.read_only and (
            not same_origin
            or path not in self.config["read_paths"]
            or (
                method != "GET"
                and not (method == "POST" and path == "/youai/album/v1/listfile")
            )
        ):
            raise PhotoError("Operation blocked by read-only mode")
        if api and same_origin:
            params = dict(kwargs.pop("params", None) or {})
            params.setdefault("bdstoken", self.get_bdstoken_Cache())
            params.setdefault("clienttype", self.config["clienttype"])
            kwargs["params"] = params
        kwargs.setdefault("timeout", self.config["timeout_seconds"])
        session = self.session if same_origin else requests
        try:
            response = session.request(
                method,
                url,
                headers=self.headers
                if same_origin
                else {"User-Agent": self.headers["User-Agent"]},
                proxies=self.get_proxies(),
                allow_redirects=not same_origin,
                **kwargs,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            status = (
                error.response.status_code if error.response is not None else "unknown"
            )
            raise PhotoError(f"HTTP {status} from {parts.hostname}{path}") from None
        except requests.RequestException:
            raise PhotoError(
                "HTTP request failed; check connectivity and session"
            ) from None
        if response.is_redirect:
            raise PhotoError("Unexpected redirect; refresh your session")
        return response

    @staticmethod
    def parse_bdstoken(text):
        match = re.search(r"['\"]?bdstoken['\"]?\s*:\s*['\"]([^'\"]+)['\"]", text)
        if not match:
            raise PhotoError(
                "Login token missing; refresh cookies from the logged-in photo page"
            )
        return match.group(1)

    def get_bdstoken(self):
        response = self._request(
            "GET", self.config["base_url"] + self.config["home_path"], api=False
        )
        return self.parse_bdstoken(response.text)

    def get_bdstoken_Cache(self):
        if self.bdstoken is None:
            self.bdstoken = self.get_bdstoken()
        return self.bdstoken

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    @staticmethod
    def _json(response):
        try:
            data = response.json()
        except ValueError:
            raise PhotoError("Expected API JSON; refresh your session") from None
        if not isinstance(data, dict) or data.get("errno") != 0:
            errno = data.get("errno") if isinstance(data, dict) else None
            raise PhotoError(f"Baidu Photo API failed (errno={errno})")
        return data

    def getReqJson(self, url, **kwargs):
        return self._json(self.get(url, **kwargs))

    def postReqJson(self, url, **kwargs):
        return self._json(self.post(url, **kwargs))
