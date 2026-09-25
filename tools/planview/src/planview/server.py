"""Standard-library HTTP server. Re-parses the planning dir whenever a file changes."""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import views
from .model import Plan, find_base, load

MAX_RAW_BYTES = 2_000_000


def repo_url(root: Path) -> str | None:
    """https URL of the `origin` remote, for commit and issue links."""
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if url.startswith("git@"):
        host, _, path = url[4:].partition(":")
        url = f"https://{host}/{path}"
    if not url.startswith("https://"):
        return None
    # Drop embedded credentials or proxy prefixes; keep host/owner/repo.
    url = url.removesuffix(".git").split("@")[-1] if "@" in url else url.removesuffix(".git")
    if not url.startswith("https://"):
        url = "https://" + url
    return url


def stamp(root: Path) -> str:
    """Changes whenever a markdown file under root is added, removed or edited."""
    files = [p for p in root.rglob("*.md") if not any(s.startswith(".") for s in p.relative_to(root).parts)]
    latest = max((p.stat().st_mtime_ns for p in files), default=0)
    return f"{len(files)}-{latest}"


class State:
    def __init__(self, root: Path, base: Path | None, repo: str | None):
        self.root = root.resolve()
        self.base = (base or find_base(self.root)).resolve()
        self.repo = repo
        self._lock = threading.Lock()
        self._stamp = ""
        self._plan: Plan | None = None

    def site(self) -> views.Site:
        current = stamp(self.root)
        with self._lock:
            if self._plan is None or current != self._stamp:
                self._plan, self._stamp = load(self.root, self.base), current
            return views.Site(plan=self._plan, repo_url=self.repo, stamp=self._stamp)


class Handler(BaseHTTPRequestHandler):
    state: State  # set by make_server
    quiet = True

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        if not self.quiet:
            super().log_message(fmt, *args)

    def send(self, body: str | bytes, ctype: str = "text/html; charset=utf-8", status: int = 200) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        path, query = unquote(url.path), parse_qs(url.query)
        try:
            if path == "/api/stamp":
                return self.send(stamp(self.state.root), "text/plain; charset=utf-8")
            if path.startswith("/static/"):
                return self.static(path.removeprefix("/static/"))
            site = self.state.site()
            if path == "/":
                return self.send(views.overview(site))
            if path == "/activity":
                return self.send(views.activity(site, query.get("spec", [""])[0]))
            if path == "/adrs":
                return self.send(views.adrs(site))
            if path == "/docs":
                return self.send(views.docs_index(site))
            if path == "/health":
                return self.send(views.health(site))
            if path == "/api/plan.json":
                return self.send(json.dumps(site.plan.to_json(), indent=2), "application/json")
            if path.startswith("/doc/"):
                rel = self.safe(path.removeprefix("/doc/"))
                page = views.doc_page(site, rel) if rel else None
                if page:
                    return self.send(page)
            if path.startswith("/raw/"):
                return self.raw(path.removeprefix("/raw/"))
            self.send(views.not_found(site, path), status=HTTPStatus.NOT_FOUND)
        except BrokenPipeError:
            pass

    def safe(self, rel: str) -> str | None:
        """A path under base with no dot-directories (keeps .git and private runs out)."""
        parts = Path(rel).parts
        if not parts or any(p.startswith(".") for p in parts):
            return None
        target = (self.state.base / rel).resolve()
        if not target.is_relative_to(self.state.base):
            return None
        return Path(rel).as_posix()

    def raw(self, rel: str) -> None:
        clean = self.safe(rel)
        target = self.state.base / clean if clean else None
        if not target or not target.is_file() or target.stat().st_size > MAX_RAW_BYTES:
            return self.send("not found", "text/plain", HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(target.name)[0] or "text/plain"
        if ctype.startswith("text/") or ctype in ("application/json",):
            ctype = "text/plain; charset=utf-8"
        self.send(target.read_bytes(), ctype)

    def static(self, name: str) -> None:
        if name not in ("app.css", "app.js"):
            return self.send("not found", "text/plain", HTTPStatus.NOT_FOUND)
        data = resources.files("planview").joinpath("static", name).read_bytes()
        ctype = "text/css" if name.endswith(".css") else "text/javascript"
        self.send(data, ctype + "; charset=utf-8")


def make_server(root: Path, host: str, port: int, base: Path | None = None, repo: str | None = None,
                verbose: bool = False) -> ThreadingHTTPServer:
    state = State(root, base, repo)
    handler = type("PlanHandler", (Handler,), {"state": state, "quiet": not verbose})
    return ThreadingHTTPServer((host, port), handler)
