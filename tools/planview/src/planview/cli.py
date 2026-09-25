"""planview [PLANNING_DIR] — serve the view; --check / --json for scripts and agents."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .model import find_base, load
from .server import make_server, repo_url


def default_root() -> Path:
    return Path("planning") if Path("planning", "milestones.md").exists() else Path(".")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planview", description=__doc__)
    ap.add_argument("root", nargs="?", type=Path, help="planning directory (default: ./planning if present, else .)")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8420, help="port (default 8420; 0 picks a free one)")
    ap.add_argument("--base", type=Path, help="directory links resolve against (default: enclosing git repo)")
    ap.add_argument("--repo-url", help="https URL for commit/issue links (default: git remote origin)")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    ap.add_argument("--check", action="store_true", help="print rule issues and exit 1 if any error or warning")
    ap.add_argument("--json", action="store_true", help="print the parsed plan as JSON and exit")
    ap.add_argument("-v", "--verbose", action="store_true", help="log requests")
    ap.add_argument("--version", action="version", version=f"planview {__version__}")
    args = ap.parse_args(argv)

    root = (args.root or default_root()).resolve()
    if not root.is_dir():
        ap.error(f"{root} is not a directory")
    if not (root / "milestones.md").exists():
        print(f"planview: note: no milestones.md in {root}", file=sys.stderr)

    if args.check or args.json:
        plan = load(root, args.base)
        if args.json:
            json.dump(plan.to_json(), sys.stdout, indent=2)
            print()
            return 0
        for issue in plan.issues:
            print(f"{issue.level:5}  {issue.path}  {issue.message}")
        bad = [i for i in plan.issues if i.level != "info"]
        print(f"{len(bad)} issue(s), {len(plan.issues) - len(bad)} note(s)", file=sys.stderr)
        return 1 if bad else 0

    base = args.base or find_base(root)
    server = make_server(root, args.host, args.port, args.base, args.repo_url or repo_url(base), args.verbose)
    host, port = server.server_address[:2]
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    print(f"planview: serving {root} at {url} (Ctrl-C to stop)", file=sys.stderr)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
