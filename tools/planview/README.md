# planview

A read-only local web view over a Milestone → Goal → Spec planning directory, the framework described in [`planning/README.md`](../../planning/README.md). It shows the current state and progress, and how each doc relates to the others.

It uses only the Python standard library: one small HTTP server and no build step. It re-parses the docs when they change, and open pages reload themselves.

## Run

```sh
# from this repo
uvx --from ./tools/planview planview planning          # http://localhost:8420/
PYTHONPATH=tools/planview/src python3 -m planview planning --open

# once published / extracted
uvx planview path/to/planning
uvx --from git+https://github.com/<owner>/<repo>#subdirectory=tools/planview planview planning
```

Options: `--port` (default 8420, 0 = any free port), `--host` (default 127.0.0.1), `--allow-host NAME` (answer that Host name too; needed to reach it by a LAN name or IP when binding beyond loopback), `--open`, `--repo-url` (for commit and issue links; defaults to the `origin` remote), `--base` (where relative links resolve; defaults to the enclosing git repo).

For scripts and agents:

- `planview --check planning`: prints rule issues and exits 1 if there are any errors or warnings.
- `planview --json planning`: prints the parsed plan as JSON (also served at `/api/plan.json`).

## Views

- **Overview:** one card per milestone with progress (goals Met, specs closed, checks passing). The **active spec** is shown with its next Open item. Below it, the goal → spec tree, where each spec shows one cell per check (green pass, red fail, outlined open), its ADRs, its Observed count and a "needs you" badge. A sidebar lists Open items waiting on the user and the latest observations.
- **Doc pages:** each markdown file rendered as written, plus a relations panel with the parent, children, checks, ADRs, successor/predecessor, docs linking to it, word count against its limit, and any rule issues for that file. IDs (`G-0001.02`, `ADR-0010`), commit SHAs and `#123` issue refs become links.
- **Activity:** every Observed entry across specs, newest first, with a per-day histogram and a filter by spec.
- **ADRs:** each decision record with its status, dates and the specs that list it.
- **Health:** the framework rules a reader can't easily check by eye. Parent tables must mirror child headers. Children must name the parent that lists them. No orphan docs. A closed spec has no Open items. A Confirmed spec passes every check. A Partial spec names a successor. A Met goal has a Result. Every Observed entry cites a commit or PR. Word limits hold. Relative links resolve.

## What it expects

The parser goes by the framework's conventions, not by paths:

- `milestones.md` in the planning root, with `## M-NNNN: Title` sections, `**Status:**` / `**Active spec:**` fields and a `| [goal](link) | Status |` table. Other `##` sections, such as "Later", appear under the milestones.
- Any `*.md` whose H1 is `# G-NNNN. Title` is a goal (`**Field:**` lines plus a spec table). `# G-NNNN.nn. Title` is a spec (plain `Key: value` header lines, `## Checks` with `N. [verdict] …`, `## Observed` with `- YYYY-MM-DD — …` entries, and a numbered `## Open` list). `# ADR-NNNN. Title` is an ADR, with a `Status: … · Decided: …` line.
- Files named `*template*` are templates. Everything else is a reference doc.

Relationships come from links: a parent's table rows are its children, a spec's `ADRs:` and `Successor:` header links, and backlinks from every other doc. Hidden directories (`.git`, `.local`, …) are never read or served. Requests for any Host name other than loopback, the bind address or an `--allow-host` name are refused, which blocks DNS rebinding. Linked non-markdown files are served as plain text, except raster images, with `nosniff` and a sandboxing CSP. Links render only for `http`, `https` and `mailto`.

## Develop

```sh
cd tools/planview
PYTHONPATH=src python3 -m unittest discover -s tests -t . -q
```

Layout: `model.py` (parse + lint), `render.py` (markdown subset + framework tokens), `views.py` (HTML), `server.py` (HTTP, reload), `cli.py`, `static/` (CSS, live-reload JS).
