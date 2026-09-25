"""HTML pages. Plain f-strings: every dynamic value goes through `esc` or the renderer."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import quote

from .model import WORD_LIMITS, Doc, Entry, Milestone, Plan, resolve
from .render import Links, inline, render

esc = html.escape
SAFE_SCHEME_RE = re.compile(r"^(https?|mailto):", re.I)
NEEDS = ' <span class="badge b-needs">needs you</span>'


@dataclass
class Site:
    plan: Plan
    repo_url: str | None = None
    stamp: str = ""

    # -- urls ---------------------------------------------------------------
    def doc_url(self, path: str, anchor: str = "") -> str:
        return "/doc/" + quote(path) + (f"#{anchor}" if anchor else "")

    def id_url(self, ident: str) -> str | None:
        for ms in self.plan.milestones:
            if ms.id == ident:
                return self.doc_url(ms.path, ms.anchor)
        doc = self.plan.by_id(ident)
        return self.doc_url(doc.path) if doc else None

    def commit_url(self, sha: str) -> str | None:
        return f"{self.repo_url}/commit/{sha}" if self.repo_url else None

    def issue_url(self, number: str) -> str | None:
        return f"{self.repo_url}/issues/{number}" if self.repo_url else None

    def links(self, doc_path: str) -> Links:
        def href(target: str) -> str | None:
            link = resolve(target, doc_path, self.plan.base)
            if link.path is None:
                if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                    return target if SAFE_SCHEME_RE.match(target) else None
                return f"#{link.anchor}" if target.startswith("#") else None
            if not (self.plan.base / link.path).exists():
                return None
            if link.path.endswith(".md"):
                return self.doc_url(link.path, link.anchor)
            return "/raw/" + quote(link.path)

        return Links(href=href, ident=self.id_url, commit=self.commit_url, issue=self.issue_url)

    def md(self, text: str, doc_path: str) -> str:
        return render(text, self.links(doc_path))

    def md_inline(self, text: str, doc_path: str) -> str:
        return inline(text, self.links(doc_path))


# -- fragments ------------------------------------------------------------------

def pill(status: str, key: str) -> str:
    label = re.sub(r"\s*\(.*", "", status).strip() or "unknown"
    title = f' title="{esc(status)}"' if label != status.strip() else ""
    return f'<span class="pill st-{esc(key)}"{title}>{esc(label)}</span>'


def cells(spec: Doc) -> str:
    if not spec.checks:
        return ""
    parts = "".join(
        f'<span class="cell v-{esc(c.verdict)}" title="C{c.number} {esc(c.verdict)}: {esc(strip_md(c.text))}">{c.number}</span>'
        for c in spec.checks
    )
    passed = sum(c.verdict == "pass" for c in spec.checks)
    return f'<span class="cells" aria-label="{passed} of {len(spec.checks)} checks pass">{parts}</span>'


def bar(done: int, total: int, extra: int = 0, label: str = "") -> str:
    """Progress bar: `done` solid, `extra` (partial/failed) hatched."""
    total = max(total, 1)
    a, b = 100 * done / total, 100 * extra / total
    return (
        f'<span class="bar" title="{esc(label)}"><span class="bar-done" style="width:{a:.1f}%"></span>'
        f'<span class="bar-extra" style="width:{b:.1f}%"></span></span>'
    )


def strip_md(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*`~]", "", text)


def short(text: str, n: int = 160) -> str:
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def adr_chips(site: Site, ids: list[str]) -> str:
    out = []
    for ident in ids:
        adr = site.plan.by_id(ident)
        title = f"{ident}: {adr.title}" if adr else ident
        cls = f" st-{adr.key}" if adr else ""
        url = site.id_url(ident)
        label = ident.replace("ADR-", "ADR ")
        out.append(f'<a class="chip chip-adr{cls}" href="{esc(url or "#")}" title="{esc(title)}">{esc(label)}</a>')
    return f'<span class="chips">{"".join(out)}</span>' if out else ""


def entry_html(site: Site, e: Entry, spec: Doc | None, show_date: bool = True, show_spec: bool = True) -> str:
    text = re.sub(r"^(~~)?\d{4}-\d{2}-\d{2}\s*[—–-]\s*", r"\1", e.text)
    spec_chip = (
        f'<a class="chip chip-spec" href="{esc(site.doc_url(spec.path, "observed"))}" title="{esc(spec.title)}">{esc(e.spec_id)}</a>'
        if show_spec and spec else ""
    )
    date = f'<time>{esc(e.date)}</time>' if show_date else ""
    cls = "entry superseded" if e.superseded else "entry"
    return f'<li class="{cls}">{date}{spec_chip}<span class="etext">{site.md_inline(text, spec.path if spec else "")}</span></li>'


def layout(site: Site, title: str, body: str, active: str = "") -> str:
    plan = site.plan
    n_issues = sum(i.level != "info" for i in plan.issues)
    nav = [("/", "Overview", "overview"), ("/activity", "Activity", "activity"),
           ("/adrs", "ADRs", "adrs"), ("/docs", "Docs", "docs"),
           ("/health", f'Health{f" <b class=count>{n_issues}</b>" if n_issues else ""}', "health")]
    links = "".join(
        f'<a href="{href}"{" class=on" if key == active else ""}>{label}</a>' for href, label, key in nav
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · planview</title>
<link rel="stylesheet" href="/static/app.css">
</head><body data-stamp="{esc(site.stamp)}">
<header class="top"><a class="brand" href="/">planview</a><span class="root">{esc(plan.root)}</span>
<nav>{links}</nav><span id="live" class="live" title="Reloads when planning files change">live</span></header>
<main>{body}</main>
<script src="/static/app.js"></script>
</body></html>"""


# -- overview -----------------------------------------------------------------

def milestone_stats(plan: Plan, ms: Milestone) -> dict:
    goals = plan.goals_for(ms)
    specs = [s for g in goals for s in plan.specs_for(g)]
    checks = [c for s in specs for c in s.checks]
    return {
        "goals": goals,
        "met": sum(g.key == "met" for g in goals),
        "specs": specs,
        "closed": sum(s.key in ("confirmed", "refuted") for s in specs),
        "partial": sum(s.key == "partial" for s in specs),
        "checks": len(checks),
        "passed": sum(c.verdict == "pass" for c in checks),
        "failed": sum(c.verdict == "fail" for c in checks),
    }


def spec_node(site: Site, spec: Doc, active: bool) -> str:
    last = max((e.date for e in spec.observed), default="")
    needs = sum(o.needs_user for o in spec.open_items)
    meta = []
    if spec.observed:
        meta.append(f'<a href="{esc(site.doc_url(spec.path, "observed"))}">{len(spec.observed)} observed</a> · last {esc(last)}')
    if spec.open_items:
        meta.append(f'<a href="{esc(site.doc_url(spec.path, "open"))}">{len(spec.open_items)} open</a>')
    if needs:
        meta.append(f'<span class="badge b-needs">needs you ×{needs}</span>')
    if spec.successor_ids:
        meta.append("→ " + ", ".join(
            f'<a class="idref" href="{esc(site.id_url(i) or "#")}">{esc(i)}</a>' for i in spec.successor_ids))
    now = '<span class="badge b-now">active</span>' if active else ""
    return f"""<li class="t-spec{' active' if active else ''}">
<div class="node"><a class="id" href="{esc(site.doc_url(spec.path))}">{esc(spec.id)}</a>
<a class="title" href="{esc(site.doc_url(spec.path))}">{esc(spec.title)}</a>{now}{pill(spec.status, spec.key)}{cells(spec)}</div>
<div class="meta">{" · ".join(meta)}{adr_chips(site, spec.adr_ids)}</div>
</li>"""


def goal_node(site: Site, goal: Doc, active_spec: str | None) -> str:
    specs = site.plan.specs_for(goal)
    closed = sum(s.closed for s in specs)
    outcome = goal.fields.get("Outcome", "")
    result = goal.fields.get("Result", "")
    extra = f'<div class="result"><b>Result</b> {site.md_inline(result, goal.path)}</div>' if result else ""
    items = "".join(spec_node(site, s, s.path == active_spec) for s in specs)
    return f"""<li class="t-goal g-{esc(goal.key)}">
<div class="node"><a class="id" href="{esc(site.doc_url(goal.path))}">{esc(goal.id)}</a>
<a class="title" href="{esc(site.doc_url(goal.path))}">{esc(goal.title)}</a>{pill(goal.status, goal.key)}
<span class="count">{closed}/{len(specs)} specs closed</span></div>
<div class="outcome">{site.md_inline(outcome, goal.path)}</div>{extra}
<ul class="specs">{items}</ul></li>"""


def now_callout(site: Site, ms: Milestone) -> str:
    spec = site.plan.docs.get(ms.active_spec or "")
    if spec is None:
        return ""
    goal = site.plan.parent_of(spec)
    items = spec.open_items
    first = items[0] if items else None
    nxt = (
        f'<div class="next"><span class="lbl">Next up</span><span class="n">{first.number}.</span> '
        f'{site.md_inline(first.text, spec.path)}{NEEDS if first.needs_user else ""}</div>'
        if first else '<div class="next muted">Open list is empty.</div>'
    )
    rest = "".join(
        f'<li value="{o.number}">{site.md_inline(o.text, spec.path)}'
        f'{NEEDS if o.needs_user else ""}</li>'
        for o in items[1:]
    )
    goal_ref = f' <span class="muted">for</span> <a class="idref" href="{esc(site.doc_url(goal.path))}">{esc(goal.id)}</a>' if goal else ""
    return f"""<div class="nowbox">
<div class="now-head"><span class="lbl">Active spec</span>
<a class="id" href="{esc(site.doc_url(spec.path))}">{esc(spec.id)}</a>
<a class="title" href="{esc(site.doc_url(spec.path))}">{esc(spec.title)}</a>{goal_ref}{pill(spec.status, spec.key)}{cells(spec)}</div>
<div class="hyp">{site.md_inline(spec.hypothesis.split(chr(10))[0], spec.path)}</div>
{nxt}{f'<ol class="rest">{rest}</ol>' if rest else ""}
</div>"""


def milestone_card(site: Site, ms: Milestone) -> str:
    s = milestone_stats(site.plan, ms)
    goals = "".join(goal_node(site, g, ms.active_spec) for g in s["goals"])
    missing = [r for r in ms.rows if r.path not in site.plan.docs]
    goals += "".join(f'<li class="t-goal missing"><div class="node">{esc(r.label)} <span class="muted">(missing file)</span></div></li>' for r in missing)
    meta = "".join(
        f"<dt>{esc(k)}</dt><dd>{site.md_inline(v, ms.path)}</dd>"
        for k, v in ms.fields.items() if k not in ("Status", "Active spec") and v
    )
    return f"""<section class="card milestone" id="{esc(ms.anchor)}">
<div class="ms-head"><span class="id">{esc(ms.id)}</span><h2><a href="{esc(site.doc_url(ms.path, ms.anchor))}">{esc(ms.title)}</a></h2>{pill(ms.status, ms.key)}</div>
<div class="stats">
<span class="stat">{bar(s['met'], len(s['goals']), label='goals met')}<b>{s['met']}/{len(s['goals'])}</b> goals met</span>
<span class="stat">{bar(s['closed'], len(s['specs']), s['partial'], label='specs closed (hatched: partial)')}<b>{s['closed'] + s['partial']}/{len(s['specs'])}</b> specs closed</span>
<span class="stat">{bar(s['passed'], s['checks'], s['failed'], label='checks passed (hatched: failed)')}<b>{s['passed']}/{s['checks']}</b> checks pass{f", {s['failed']} fail" if s['failed'] else ""}</span>
</div>
<details class="about"><summary>Scope, deliverable, done-when</summary><dl>{meta}</dl></details>
{now_callout(site, ms)}
<h3 class="sub">Goals → specs</h3>
<ul class="tree">{goals}</ul>
</section>"""


def needs_user(site: Site) -> str:
    rows = []
    for spec in site.plan.of_kind("spec"):
        for o in spec.open_items:
            if o.needs_user:
                rows.append(
                    f'<li><a class="chip chip-spec" href="{esc(site.doc_url(spec.path, "open"))}">{esc(spec.id)}</a>'
                    f'<span class="etext">{site.md_inline(o.text, spec.path)}</span></li>'
                )
    if not rows:
        return ""
    return f'<section class="panel"><h3>Waiting on you</h3><ul class="plain">{"".join(rows)}</ul></section>'


def overview(site: Site) -> str:
    plan = site.plan
    cards = "".join(milestone_card(site, ms) for ms in plan.milestones) or (
        '<section class="card"><p class="muted">No milestones found. Expected <code>milestones.md</code> with '
        '<code>## M-NNNN: Title</code> sections.</p></section>'
    )
    extra = "".join(
        f'<section class="card extra"><h3>{esc(sec.title)}</h3>{site.md(sec.body, plan.milestones[0].path if plan.milestones else "")}</section>'
        for sec in plan.sections
    )
    recent = plan.entries()[:8]
    recent_html = "".join(entry_html(site, e, plan.by_id(e.spec_id)) for e in recent)
    errors = [i for i in plan.issues if i.level != "info"]
    health = (
        f'<a class="health bad" href="/health">{len(errors)} rule issue{"s" if len(errors) != 1 else ""}</a>'
        if errors else '<a class="health ok" href="/health">All planning rules hold</a>'
    )
    refs = "".join(
        f'<li><a href="{esc(site.doc_url(d.path))}">{esc(d.title)}</a></li>'
        for d in plan.of_kind("reference") + plan.of_kind("guide")
    )
    return layout(site, "Overview", f"""<div class="grid">
<div class="col-main">{cards}{extra}</div>
<aside class="col-side">
{health}
{needs_user(site)}
<section class="panel"><h3>Recent observations <a class="more" href="/activity">all</a></h3><ul class="entries compact">{recent_html or '<li class="muted">None yet.</li>'}</ul></section>
<section class="panel"><h3>Reference</h3><ul class="plain">{refs}</ul></section>
</aside></div>""", "overview")


# -- doc page -----------------------------------------------------------------

def breadcrumb(site: Site, doc: Doc) -> str:
    plan = site.plan
    crumbs = []
    if doc.kind in ("spec", "goal"):
        ms = plan.milestone_of(doc)
        if ms:
            crumbs.append(f'<a href="{esc(site.doc_url(ms.path, ms.anchor))}">{esc(ms.id)}</a>')
        goal = doc if doc.kind == "goal" else plan.parent_of(doc)
        if goal and goal is not doc:
            crumbs.append(f'<a href="{esc(site.doc_url(goal.path))}">{esc(goal.id)}</a>')
    elif doc.kind == "adr":
        crumbs.append('<a href="/adrs">ADRs</a>')
    else:
        crumbs.append('<a href="/docs">Docs</a>')
    crumbs.append(f"<span>{esc(doc.id or doc.title)}</span>")
    return '<nav class="crumbs"><a href="/">Overview</a>' + "".join(f"<i>›</i>{c}" for c in crumbs) + "</nav>"


def rel_row(site: Site, doc: Doc, extra: str = "") -> str:
    return (
        f'<li><a class="id" href="{esc(site.doc_url(doc.path))}">{esc(doc.id or doc.title)}</a>'
        f'<span class="t">{esc(doc.title) if doc.id else ""}</span>{pill(doc.status, doc.key) if doc.status else ""}{extra}</li>'
    )


def relations(site: Site, doc: Doc) -> str:
    plan = site.plan
    blocks = []

    def block(title: str, inner: str) -> None:
        if inner:
            blocks.append(f'<section class="rel"><h4>{title}</h4>{inner}</section>')

    if doc.status:
        limit = WORD_LIMITS.get(doc.kind)
        words = f'<span class="muted">{doc.words} words{f" / {limit}" if limit else ""}</span>' if limit else ""
        block("Status", f'<div class="st-row">{pill(doc.status, doc.key)}{cells(doc) if doc.kind == "spec" else ""}</div>{words}')
    if doc.kind == "spec":
        goal = plan.parent_of(doc)
        ms = plan.milestone_of(doc)
        parents = (rel_row(site, goal) if goal else "") + (
            f'<li><a class="id" href="{esc(site.doc_url(ms.path, ms.anchor))}">{esc(ms.id)}</a><span class="t">{esc(ms.title)}</span>{pill(ms.status, ms.key)}</li>'
            if ms else "")
        block("Parent", f'<ul class="rels">{parents}</ul>' if parents else "")
        checks = "".join(
            f'<li><span class="verdict v-{esc(c.verdict)}">C{c.number}</span>{esc(short(strip_md(c.text), 110))}</li>'
            for c in doc.checks)
        block("Checks", f'<ul class="checks">{checks}</ul>' if checks else "")
        preds = [s for s in plan.of_kind("spec") if doc.id in s.successor_ids]
        block("Successor", '<ul class="rels">' + "".join(rel_row(site, plan.by_id(i)) for i in doc.successor_ids if plan.by_id(i)) + "</ul>" if doc.successor_ids else "")
        block("Carries work from", '<ul class="rels">' + "".join(rel_row(site, s) for s in preds) + "</ul>" if preds else "")
        block("ADRs", '<ul class="rels">' + "".join(rel_row(site, plan.by_id(i)) for i in doc.adr_ids if plan.by_id(i)) + "</ul>" if doc.adr_ids else "")
    elif doc.kind == "goal":
        ms = plan.milestone_of(doc)
        if ms:
            block("Parent", f'<ul class="rels"><li><a class="id" href="{esc(site.doc_url(ms.path, ms.anchor))}">{esc(ms.id)}</a><span class="t">{esc(ms.title)}</span>{pill(ms.status, ms.key)}</li></ul>')
        specs = plan.specs_for(doc)
        block("Specs", '<ul class="rels">' + "".join(rel_row(site, s, cells(s)) for s in specs) + "</ul>" if specs else "")
        adrs = list(dict.fromkeys(i for s in specs for i in s.adr_ids))
        block("ADRs via specs", adr_chips(site, adrs))
    elif doc.kind == "adr":
        meta = "".join(f"<dt>{esc(k)}</dt><dd>{site.md_inline(v, doc.path)}</dd>" for k, v in doc.fields.items() if k not in ("Status", "Evidence"))
        block("Decision", f"<dl>{meta}</dl>" if meta else "")
        users = [s for s in plan.of_kind("spec") if doc.id in s.adr_ids]
        block("Specs honoring it", '<ul class="rels">' + "".join(rel_row(site, s) for s in users) + "</ul>" if users else "")

    shown = {doc.path} | {m.path for m in plan.milestones}
    if doc.kind == "spec":
        shown |= {d.path for d in (plan.parent_of(doc), *map(plan.by_id, doc.adr_ids + doc.successor_ids)) if d}
        shown |= {s.path for s in plan.of_kind("spec") if doc.id in s.successor_ids}
    elif doc.kind == "goal":
        shown |= {s.path for s in plan.specs_for(doc)}
    elif doc.kind == "adr":
        shown |= {s.path for s in plan.of_kind("spec") if doc.id in s.adr_ids}
    back = [plan.docs[p] for p in plan.backlinks.get(doc.path, []) if p in plan.docs and p not in shown]
    block("Linked from", '<ul class="rels">' + "".join(rel_row(site, d) for d in sorted(back, key=lambda d: d.id or d.path)) + "</ul>" if back else "")
    issues = [i for i in plan.issues if i.path.split("#")[0] == doc.path]
    block("Rule issues", '<ul class="issues">' + "".join(f'<li class="lvl-{i.level}">{esc(i.message)}</li>' for i in issues) + "</ul>" if issues else "")
    src = f'<a href="{esc(site.repo_url)}/blob/HEAD/{esc(doc.path)}" target="_blank" rel="noopener">{esc(doc.path)}</a>' if site.repo_url else esc(doc.path)
    block("File", f'<div class="path">{src}</div>')
    return "".join(blocks)


def milestones_relations(site: Site) -> str:
    out = []
    for ms in site.plan.milestones:
        goals = "".join(rel_row(site, g) for g in site.plan.goals_for(ms))
        out.append(f'<section class="rel"><h4><a href="#{esc(ms.anchor)}">{esc(ms.id)}</a> {pill(ms.status, ms.key)}</h4><ul class="rels">{goals}</ul></section>')
    return "".join(out)


def doc_page(site: Site, path: str) -> str | None:
    plan = site.plan
    doc = plan.docs.get(path)
    file = plan.base / path
    if doc is None:
        # Markdown outside the planning dir (README, TODO …): render plainly.
        if not path.endswith(".md") or not file.is_file():
            return None
        body = site.md(file.read_text(encoding="utf-8"), path)
        return layout(site, path, f'<nav class="crumbs"><a href="/">Overview</a><i>›</i><span>{esc(path)}</span></nav><div class="docgrid"><article class="md">{body}</article></div>')
    body = site.md(file.read_text(encoding="utf-8"), path)
    aside = milestones_relations(site) if doc.kind == "milestones" else relations(site, doc)
    return layout(site, doc.id or doc.title, f"""{breadcrumb(site, doc)}
<div class="docgrid kind-{esc(doc.kind)}"><article class="md">{body}</article><aside class="relations">{aside}</aside></div>""")


# -- other pages ---------------------------------------------------------------

def activity(site: Site, spec_filter: str = "") -> str:
    plan = site.plan
    entries = [e for e in plan.entries() if not spec_filter or e.spec_id == spec_filter]
    specs_with = Counter(e.spec_id for e in plan.entries())
    chips = f'<a class="chip{"" if spec_filter else " on"}" href="/activity">All</a>' + "".join(
        f'<a class="chip chip-spec{" on" if s == spec_filter else ""}" href="/activity?spec={quote(s)}">{esc(s)} <small>{n}</small></a>'
        for s, n in sorted(specs_with.items())
    )
    per_day = Counter(e.date for e in entries)
    peak = max(per_day.values(), default=1)
    days = "".join(
        f'<a class="day" href="#d-{d}" title="{d}: {n} entries"><span style="height:{max(8, 100 * n / peak):.0f}%"></span><small>{d[5:]}</small></a>'
        for d, n in sorted(per_day.items())
    )
    groups, current = [], None
    for e in entries:
        if e.date != current:
            if current is not None:
                groups.append("</ul>")
            current = e.date
            groups.append(f'<h3 class="date" id="d-{esc(e.date)}">{esc(e.date or "undated")}</h3><ul class="entries">')
        groups.append(entry_html(site, e, plan.by_id(e.spec_id), show_date=False, show_spec=not spec_filter))
    if current is not None:
        groups.append("</ul>")
    title = f"Activity · {spec_filter}" if spec_filter else "Activity"
    spec = plan.by_id(spec_filter) if spec_filter else None
    sub = f'<p class="muted"><a href="{esc(site.doc_url(spec.path))}">{esc(spec.id)} {esc(spec.title)}</a></p>' if spec else ""
    return layout(site, title, f"""<section class="card">
<h2>Observed log</h2>{sub}<p class="muted">Every Observed entry across specs, newest first. {len(entries)} entries.</p>
<div class="days">{days}</div>
<div class="chips filter">{chips}</div>
{''.join(groups) or '<p class="muted">No entries.</p>'}
</section>""", "activity")


def adrs(site: Site) -> str:
    rows = []
    for adr in site.plan.of_kind("adr"):
        users = [s for s in site.plan.of_kind("spec") if adr.id in s.adr_ids]
        used = "".join(f'<a class="chip chip-spec" href="{esc(site.doc_url(s.path))}" title="{esc(s.title)}">{esc(s.id)}</a>' for s in users)
        rows.append(f"""<tr><td><a class="id" href="{esc(site.doc_url(adr.path))}">{esc(adr.id)}</a></td>
<td><a href="{esc(site.doc_url(adr.path))}">{esc(adr.title)}</a></td><td>{pill(adr.status, adr.key)}</td>
<td class="nowrap">{esc(adr.fields.get('Decided', ''))}</td><td>{esc(adr.fields.get('Revised', ''))}</td>
<td><span class="chips">{used}</span></td></tr>""")
    return layout(site, "ADRs", f"""<section class="card"><h2>Decision records</h2>
<p class="muted">Durable decisions, and the specs that list them.</p>
<div class="tablewrap"><table class="list"><thead><tr><th>ID</th><th>Decision</th><th>Status</th><th>Decided</th><th>Revised</th><th>Specs</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>""", "adrs")


def docs_index(site: Site) -> str:
    groups = [("Milestones", "milestones"), ("Goals", "goal"), ("Specs", "spec"), ("ADRs", "adr"),
              ("Reference", "reference"), ("Guide", "guide"), ("Templates", "template")]
    out = []
    for title, kind in groups:
        docs = site.plan.of_kind(kind)
        if docs:
            out.append(f'<h3>{title}</h3><ul class="rels wide">{"".join(rel_row(site, d) for d in docs)}</ul>')
    return layout(site, "Docs", f'<section class="card"><h2>All planning docs</h2>{"".join(out)}</section>', "docs")


def health(site: Site) -> str:
    issues = site.plan.issues
    names = {"error": "Errors", "warn": "Warnings", "info": "Notes"}
    out = []
    for level, name in names.items():
        items = [i for i in issues if i.level == level]
        if not items:
            continue
        rows = "".join(
            f'<li class="lvl-{level}"><a href="{esc(site.doc_url(*i.path.split("#", 1)))}">{esc(i.path)}</a> {esc(i.message)}</li>'
            for i in items
        )
        out.append(f'<h3>{name} <small class="muted">{len(items)}</small></h3><ul class="issues">{rows}</ul>')
    body = "".join(out) or '<p class="health ok">Every rule checked holds.</p>'
    return layout(site, "Health", f"""<section class="card"><h2>Planning rules</h2>
<p class="muted">Checked: parent tables mirror child headers; children name the parent that lists them; no orphans;
closed specs have no Open items; Confirmed means every check passes; Partial names a successor; Met goals have a Result;
Observed entries cite a commit or PR; word limits; relative links resolve.</p>{body}</section>""", "health")


def not_found(site: Site, path: str) -> str:
    return layout(site, "Not found", f'<section class="card"><h2>Not found</h2><p><code>{esc(path)}</code></p></section>')
