"""Parse a planning directory into Milestone → Goal → Spec, plus ADRs.

The parser follows the conventions in a planning README (framework v2): each
doc's own header is authoritative for its status, parents list children in
link + status tables, specs carry numbered checks with `[verdict]` markers, an
append-only Observed log and an ordered Open list. Anything that doesn't fit is
kept as a plain reference doc rather than dropped.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Status words the framework defines, longest first so "In progress" wins.
STATUS_WORDS = (
    "not started", "in progress", "proposed", "confirmed", "refuted", "partial",
    "met", "dropped", "done", "active", "revoked", "superseded",
)
CLOSED_SPEC = {"confirmed", "refuted", "partial"}
CLOSED_GOAL = {"met", "dropped"}

# Word limits from the planning README. Spec: text above "## Observed".
WORD_LIMITS = {"milestone": 250, "goal": 150, "spec": 300, "entry": 50, "adr": 300, "reference": 1000}
MAX_OBSERVED = 12

H1_RE = re.compile(r"^#\s+((?:ADR|G|M)-\d+(?:\.\d+)?)\.?\s+(.+?)\s*$", re.M)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
BOLD_FIELD_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
PLAIN_FIELD_RE = re.compile(r"^([A-Z][A-Za-z ]{1,30}):\s+(.*)$")
CHECK_RE = re.compile(r"^(\d+)\.\s+\[([a-z]+)\]\s*(.*)$")
OPEN_RE = re.compile(r"^(\d+)\.\s+(.*)$")
TAG_RE = re.compile(r"\[C(\d+)(?:\s+([a-z]+))?\]")
DATE_RE = re.compile(r"^(?:~~)?(\d{4}-\d{2}-\d{2})")
HEX_RE = re.compile(r"`([0-9a-f]{7,40})`")
PR_RE = re.compile(r"(?<![\w&/])#(\d+)\b")
ADR_ID_RE = re.compile(r"\bADR-(\d{4})\b")
ID_IN_NAME_RE = re.compile(r"^((?:ADR|G|M)-\d{4}(?:\.\d{2})?)")
NEEDS_USER_RE = re.compile(r"needs the user|needs you|user decision|decision pending", re.I)


def status_key(text: str) -> str:
    """Normalise a status cell/header ("Partial (user-approved …)") to a key."""
    low = (text or "").strip().lower().lstrip("*~ ")
    for word in STATUS_WORDS:
        if low.startswith(word):
            return word.replace(" ", "-")
    return "unknown"


def word_count(text: str) -> int:
    """Match `wc -w`: whitespace-separated tokens."""
    return len(text.split())


def slug(text: str) -> str:
    """GitHub-style heading anchor."""
    text = re.sub(r"[`*~]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", text)
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


@dataclass
class Link:
    text: str
    href: str
    path: str | None  # resolved, relative to base; None for external/anchor-only
    anchor: str = ""


@dataclass
class Row:
    """One line of a parent's child table: link + status only."""
    label: str
    path: str | None
    status: str


@dataclass
class Check:
    number: int
    verdict: str
    text: str


@dataclass
class Entry:
    date: str
    text: str
    tags: list[tuple[int, str]]
    commits: list[str]
    prs: list[str]
    adrs: list[str]
    superseded: bool
    words: int
    spec_id: str = ""
    index: int = 0


@dataclass
class OpenItem:
    number: int
    text: str
    needs_user: bool


@dataclass
class Doc:
    kind: str  # milestones | goal | spec | adr | reference | template | guide
    path: str
    title: str
    id: str = ""
    status: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    words: int = 0
    links: list[Link] = field(default_factory=list)
    # spec
    goal_id: str = ""
    adr_ids: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    observed: list[Entry] = field(default_factory=list)
    open_items: list[OpenItem] = field(default_factory=list)
    successor_ids: list[str] = field(default_factory=list)
    revisions: list[str] = field(default_factory=list)
    hypothesis: str = ""
    # goal
    milestone_id: str = ""
    rows: list[Row] = field(default_factory=list)

    @property
    def key(self) -> str:
        return status_key(self.status)

    @property
    def closed(self) -> bool:
        return self.key in (CLOSED_SPEC if self.kind == "spec" else CLOSED_GOAL)


@dataclass
class Milestone:
    id: str
    title: str
    status: str
    anchor: str
    path: str
    fields: dict[str, str]
    rows: list[Row]
    active_spec: str | None  # path
    words: int
    body: str

    @property
    def key(self) -> str:
        return status_key(self.status)


@dataclass
class Section:
    title: str
    anchor: str
    body: str


@dataclass
class Issue:
    level: str  # error | warn | info
    path: str
    message: str


@dataclass
class Plan:
    root: str  # planning dir, relative to base
    base: Path
    milestones: list[Milestone] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    docs: dict[str, Doc] = field(default_factory=dict)  # by path
    issues: list[Issue] = field(default_factory=list)
    backlinks: dict[str, list[str]] = field(default_factory=dict)

    # -- lookups ------------------------------------------------------------
    def by_id(self, ident: str) -> Doc | None:
        for doc in self.docs.values():
            if doc.id == ident:
                return doc
        return None

    def of_kind(self, kind: str) -> list[Doc]:
        return sorted((d for d in self.docs.values() if d.kind == kind), key=lambda d: d.id or d.path)

    def goals_for(self, ms: Milestone) -> list[Doc]:
        return [self.docs[r.path] for r in ms.rows if r.path in self.docs]

    def specs_for(self, goal: Doc) -> list[Doc]:
        return [self.docs[r.path] for r in goal.rows if r.path in self.docs]

    def milestone_of(self, doc: Doc) -> Milestone | None:
        goal = doc if doc.kind == "goal" else self.parent_of(doc)
        if goal is None:
            return None
        for ms in self.milestones:
            if any(r.path == goal.path for r in ms.rows):
                return ms
        return next((m for m in self.milestones if m.id == goal.milestone_id), None)

    def parent_of(self, doc: Doc) -> Doc | None:
        if doc.kind != "spec":
            return None
        for goal in self.of_kind("goal"):
            if any(r.path == doc.path for r in goal.rows):
                return goal
        return self.by_id(doc.goal_id)

    def entries(self) -> list[Entry]:
        """Every Observed entry, newest first (file order breaks date ties)."""
        out = [e for s in self.of_kind("spec") for e in s.observed]
        return sorted(out, key=lambda e: (e.date, e.index), reverse=True)

    def to_json(self) -> dict:
        def doc_json(d: Doc) -> dict:
            data = asdict(d)
            data["status_key"] = d.key
            data.pop("links")
            return data

        return {
            "root": self.root,
            "milestones": [
                {**asdict(m), "status_key": m.key, "body": None} for m in self.milestones
            ],
            "docs": {p: doc_json(d) for p, d in self.docs.items()},
            "issues": [asdict(i) for i in self.issues],
        }


# -- helpers -----------------------------------------------------------------

def find_base(root: Path) -> Path:
    """The repository root (nearest dir with .git) so links like ../README.md resolve."""
    for cand in (root, *root.parents):
        if (cand / ".git").exists():
            return cand
    return root


def resolve(href: str, doc_path: str, base: Path) -> Link:
    """Resolve a markdown href written in `doc_path` against `base`."""
    target, _, anchor = href.partition("#")
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return Link(text="", href=href, path=None, anchor=anchor)
    joined = os.path.normpath(os.path.join(os.path.dirname(doc_path), target))
    if joined.startswith(".."):
        return Link(text="", href=href, path=None, anchor=anchor)
    return Link(text="", href=href, path=Path(joined).as_posix(), anchor=anchor)


def links_in(text: str, doc_path: str, base: Path) -> list[Link]:
    out = []
    for m in LINK_RE.finditer(text):
        link = resolve(m.group(2), doc_path, base)
        link.text = m.group(1)
        out.append(link)
    return out


def split_sections(text: str, level: int = 2) -> tuple[str, list[tuple[str, str]]]:
    """Split on `## ` headings, skipping fenced code. Returns (preamble, [(title, body)])."""
    marker = "#" * level + " "
    pre: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith(marker):
            sections.append((line[len(marker):].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            pre.append(line)
    return "\n".join(pre), [(t, "\n".join(b)) for t, b in sections]


def bold_fields(text: str) -> dict[str, str]:
    fields = {}
    for line in text.splitlines():
        m = BOLD_FIELD_RE.match(line.strip())
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def table_rows(text: str, doc_path: str, base: Path) -> list[Row]:
    """Rows of `| [label](target) | status |` tables."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        m = LINK_RE.search(cells[0]) if cells else None
        if not m or len(cells) < 2:
            continue
        link = resolve(m.group(2), doc_path, base)
        rows.append(Row(label=m.group(1), path=link.path, status=cells[-1]))
    return rows


def list_items(body: str, pattern: re.Pattern) -> list[tuple[re.Match, str]]:
    """Top-level list items matching `pattern`, with indented continuation lines joined."""
    items: list[tuple[re.Match, str]] = []
    for line in body.splitlines():
        m = pattern.match(line)
        if m:
            items.append((m, line.strip()))
        elif items and line.startswith((" ", "\t")) and line.strip():
            prev_m, prev = items[-1]
            items[-1] = (pattern.match(prev + " " + line.strip()) or prev_m, prev + " " + line.strip())
    return items


def ids_from_links(links: list[Link], plan_ids: dict[str, str]) -> list[str]:
    return [plan_ids[l.path] for l in links if l.path in plan_ids]


# -- parsing -----------------------------------------------------------------

def parse_entry(line: str) -> Entry:
    text = line[1:].strip() if line.startswith("-") else line
    date = DATE_RE.match(text)
    superseded = text.startswith("~~") or "(superseded" in text
    tail = text.rsplit("·", 1)[1] if "·" in text else ""
    commits = HEX_RE.findall(tail) if tail else [h for h in HEX_RE.findall(text) if re.search("[a-f]", h)]
    prs = PR_RE.findall(tail or text)
    return Entry(
        date=date.group(1) if date else "",
        text=text,
        tags=[(int(n), v or "") for n, v in TAG_RE.findall(text)],
        commits=commits,
        prs=prs,
        adrs=[f"ADR-{n}" for n in dict.fromkeys(ADR_ID_RE.findall(text))],
        superseded=superseded,
        words=word_count(text),
    )


def parse_doc(path: Path, rel: str, base: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    h1 = H1_RE.search(text)
    first = next((l for l in text.splitlines() if l.startswith("# ")), "# " + path.stem)
    title = h1.group(2) if h1 else first[2:].strip()
    ident = h1.group(1) if h1 and "NNNN" not in text[: h1.end()] else ""
    if "template" in path.name.lower():
        kind, ident = "template", ""
    elif ident.startswith("ADR-"):
        kind = "adr"
    elif re.match(r"G-\d{4}\.\d+$", ident):
        kind = "spec"
    elif re.match(r"G-\d{4}$", ident):
        kind = "goal"
    elif path.name.lower() == "readme.md":
        kind = "guide"
    else:
        kind = "reference"

    doc = Doc(kind=kind, path=rel, title=title, id=ident, words=word_count(text))
    doc.links = links_in(text, rel, base)
    pre, sections = split_sections(text)

    if kind == "goal":
        doc.fields = bold_fields(text)
        doc.status = doc.fields.get("Status", "")
        ms = re.search(r"M-\d{4}", doc.fields.get("Milestone", ""))
        doc.milestone_id = ms.group(0) if ms else ""
        doc.rows = table_rows(text, rel, base)
    elif kind == "spec":
        for line in pre.splitlines():
            m = PLAIN_FIELD_RE.match(line.strip())
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "Revision":
                doc.revisions.append(val)
            else:
                doc.fields[key] = val
        doc.status = doc.fields.get("Status", "")
        goal = re.search(r"G-\d{4}(?!\.)", doc.fields.get("Goal", ""))
        doc.goal_id = goal.group(0) if goal else ""
        above = text.split("\n## Observed", 1)[0]
        doc.words = word_count(above)
        for title_, body in sections:
            name = title_.lower()
            if name == "hypothesis":
                doc.hypothesis = body.strip()
            elif name == "checks":
                doc.checks = [Check(int(m.group(1)), m.group(2), m.group(3)) for m, _ in list_items(body, CHECK_RE)]
            elif name == "observed":
                entries = [parse_entry(t) for _, t in list_items(body, re.compile(r"^-\s+"))]
                for i, e in enumerate(entries):
                    e.spec_id, e.index = ident, i
                doc.observed = entries
            elif name == "open":
                doc.open_items = [
                    OpenItem(int(m.group(1)), m.group(2), bool(NEEDS_USER_RE.search(m.group(2))))
                    for m, _ in list_items(body, OPEN_RE)
                ]
    elif kind == "adr":
        status_line = next((l for l in pre.splitlines() if l.startswith("Status:")), "")
        for part in status_line.split(" · "):
            key, _, val = part.partition(":")
            if val:
                doc.fields[key.strip()] = val.strip()
        doc.status = doc.fields.get("Status", "")
    return doc


def parse_milestones(path: Path, rel: str, base: Path) -> tuple[list[Milestone], list[Section], Doc]:
    text = path.read_text(encoding="utf-8")
    first = next((l for l in text.splitlines() if l.startswith("# ")), "# Milestones")
    doc = Doc(kind="milestones", path=rel, title=first[2:].strip(), words=word_count(text))
    doc.links = links_in(text, rel, base)
    _, sections = split_sections(text)
    milestones, extra = [], []
    for heading, body in sections:
        m = re.match(r"^(M-\d+):?\s*(.*)$", heading)
        if not m:
            extra.append(Section(heading, slug(heading), body.strip()))
            continue
        fields = bold_fields(body)
        active = next(
            (l.path for l in links_in(fields.get("Active spec", ""), rel, base) if l.path), None
        )
        milestones.append(Milestone(
            id=m.group(1), title=m.group(2).strip(), status=fields.get("Status", ""),
            anchor=slug(heading), path=rel, fields=fields,
            rows=table_rows(body, rel, base), active_spec=active,
            words=word_count(f"## {heading}\n{body}"), body=body.strip(),
        ))
    return milestones, extra, doc


def load(root: Path, base: Path | None = None) -> Plan:
    root = root.resolve()
    base = (base or find_base(root)).resolve()
    plan = Plan(root=Path(os.path.relpath(root, base)).as_posix(), base=base)
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        rel = Path(os.path.relpath(path, base)).as_posix()
        if path.name == "milestones.md" and path.parent == root:
            plan.milestones, plan.sections, doc = parse_milestones(path, rel, base)
        else:
            doc = parse_doc(path, rel, base)
        plan.docs[rel] = doc

    ids = {p: d.id for p, d in plan.docs.items() if d.id}
    for doc in plan.docs.values():
        if doc.kind == "spec":
            adr_field = links_in(doc.fields.get("ADRs", ""), doc.path, base)
            doc.adr_ids = [i for i in ids_from_links(adr_field, ids) if i.startswith("ADR-")]
            succ = links_in(doc.fields.get("Successor", ""), doc.path, base)
            doc.successor_ids = ids_from_links(succ, ids)
        for link in doc.links:
            if link.path and link.path != doc.path:
                refs = plan.backlinks.setdefault(link.path, [])
                if doc.path not in refs:
                    refs.append(doc.path)
    plan.issues = lint(plan)
    return plan


# -- health ------------------------------------------------------------------

def lint(plan: Plan) -> list[Issue]:
    """Framework rules a reader can't easily eyeball: mirrors, orphans, limits, gaps."""
    issues: list[Issue] = []
    add = lambda level, path, msg: issues.append(Issue(level, path, msg))  # noqa: E731
    listed_goals: dict[str, str] = {}
    listed_specs: dict[str, str] = {}

    for ms in plan.milestones:
        where = f"{ms.path}#{ms.anchor}"
        for row in ms.rows:
            goal = plan.docs.get(row.path or "")
            if goal is None:
                add("error", where, f"{ms.id} lists {row.label!r}, but {row.path} doesn't exist")
                continue
            listed_goals[goal.path] = ms.id
            if status_key(row.status) != goal.key:
                add("warn", where, f"{ms.id} table says {goal.id} is {row.status!r}; its header says {goal.status!r}")
            if goal.milestone_id and goal.milestone_id != ms.id:
                add("warn", goal.path, f"{goal.id} names {goal.milestone_id} as parent but is listed by {ms.id}")
        goals = plan.goals_for(ms)
        if ms.key == "done" and any(g.key != "met" for g in goals):
            add("warn", where, f"{ms.id} is Done but not every goal is Met")
        if ms.active_spec:
            spec = plan.docs.get(ms.active_spec)
            if spec is None:
                add("error", where, f"{ms.id} active spec {ms.active_spec} doesn't exist")
            elif spec.closed:
                add("warn", where, f"{ms.id} active spec {spec.id} is closed ({spec.status})")
        elif ms.key == "in-progress":
            add("info", where, f"{ms.id} has no active spec pointer")
        if ms.words > WORD_LIMITS["milestone"]:
            add("warn", where, f"{ms.id} is {ms.words} words (limit {WORD_LIMITS['milestone']})")

    for goal in plan.of_kind("goal"):
        if goal.path not in listed_goals:
            add("warn", goal.path, f"{goal.id} isn't listed by any milestone")
        for row in goal.rows:
            spec = plan.docs.get(row.path or "")
            if spec is None:
                add("error", goal.path, f"{goal.id} lists {row.label!r}, but {row.path} doesn't exist")
                continue
            listed_specs[spec.path] = goal.id
            if status_key(row.status) != spec.key:
                add("warn", goal.path, f"{goal.id} table says {spec.id} is {row.status!r}; its header says {spec.status!r}")
            if spec.goal_id and spec.goal_id != goal.id:
                add("warn", spec.path, f"{spec.id} names {spec.goal_id} as parent but is listed by {goal.id}")
        specs = plan.specs_for(goal)
        if goal.key == "met" and any(not s.closed for s in specs):
            add("warn", goal.path, f"{goal.id} is Met but has specs still open")
        if goal.closed and not goal.fields.get("Result"):
            add("warn", goal.path, f"{goal.id} is {goal.status} without a Result line")
        if goal.words > WORD_LIMITS["goal"]:
            add("warn", goal.path, f"{goal.id} is {goal.words} words (limit {WORD_LIMITS['goal']})")

    for spec in plan.of_kind("spec"):
        if spec.path not in listed_specs:
            add("warn", spec.path, f"{spec.id} isn't listed by any goal")
        if spec.words > WORD_LIMITS["spec"]:
            add("warn", spec.path, f"{spec.id} is {spec.words} words above Observed (limit {WORD_LIMITS['spec']})")
        if spec.closed and spec.open_items:
            add("warn", spec.path, f"{spec.id} is {spec.key} but still has {len(spec.open_items)} Open item(s)")
        if spec.key == "confirmed" and any(c.verdict != "pass" for c in spec.checks):
            add("warn", spec.path, f"{spec.id} is Confirmed but not every check is [pass]")
        if spec.key == "partial" and not spec.successor_ids:
            add("warn", spec.path, f"{spec.id} is Partial without a Successor link")
        if not spec.closed and not spec.open_items:
            add("info", spec.path, f"{spec.id} is open with an empty Open list")
        live = [e for e in spec.observed if not e.superseded]
        if len(live) > MAX_OBSERVED:
            add("info", spec.path, f"{spec.id} has {len(live)} Observed entries (> {MAX_OBSERVED} often means two hypotheses)")
        for e in spec.observed:
            if not e.commits and not e.prs:
                add("warn", spec.path, f"{spec.id} entry {e.date or '?'} cites no commit or PR")
            if e.words > WORD_LIMITS["entry"]:
                add("warn", spec.path, f"{spec.id} entry {e.date} is {e.words} words (limit {WORD_LIMITS['entry']})")

    for adr in plan.of_kind("adr"):
        if adr.words > WORD_LIMITS["adr"]:
            add("warn", adr.path, f"{adr.id} is {adr.words} words (limit {WORD_LIMITS['adr']})")
    for ref in plan.of_kind("reference"):
        if ref.words > WORD_LIMITS["reference"]:
            add("warn", ref.path, f"{ref.path} is {ref.words} words (limit {WORD_LIMITS['reference']})")

    for doc in plan.docs.values():
        if doc.kind == "template":
            continue
        for link in doc.links:
            if link.path and not (plan.base / link.path).exists():
                add("warn", doc.path, f"broken link to {link.href}")
    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(issues, key=lambda i: (order[i.level], i.path))
