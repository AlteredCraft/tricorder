"""A small markdown renderer for the subset planning docs use.

Headings, paragraphs, flat and indented lists, pipe tables, fenced code, HTML
comments, and inline code/bold/italic/strike/links. On top of that it styles
the framework's own tokens: `[pass]`-style verdicts, `[C2 pass]` check tags,
commit SHAs, `#123` issue refs and bare IDs such as G-0001.02 or ADR-0010.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable

from .model import slug

VERDICTS = {"pass", "fail", "open", "inconclusive"}
ID_RE = re.compile(r"\b(ADR-\d{4}|G-\d{4}(?:\.\d{2})?|M-\d{4})\b")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
FIELD_LINE_RE = re.compile(r"^(\*\*[^*]+:\*\*|[A-Z][A-Za-z ]{1,30}:)\s")


@dataclass
class Links:
    """How the renderer turns references into URLs. Every hook may return None."""
    href: Callable[[str], str | None] = lambda href: href  # markdown link target
    ident: Callable[[str], str | None] = lambda ident: None  # G-0001, ADR-0003 …
    commit: Callable[[str], str | None] = lambda sha: None
    issue: Callable[[str], str | None] = lambda number: None
    stash: list[str] = field(default_factory=list)


def _hold(links: Links, fragment: str) -> str:
    links.stash.append(fragment)
    return f"\x00{len(links.stash) - 1}\x00"


PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def _restore(text: str, links: Links) -> str:
    while PLACEHOLDER_RE.search(text):
        text = PLACEHOLDER_RE.sub(lambda m: links.stash[int(m.group(1))], text)
    return text


def inline(text: str, links: Links) -> str:
    text = text.replace("\x00", "")  # NUL marks placeholders; never let input forge one
    def code(m: re.Match) -> str:
        body = m.group(1)
        url = links.commit(body) if SHA_RE.match(body) and re.search("[a-f]", body) else None
        chip = f'<code class="sha">{html.escape(body)}</code>' if url else f"<code>{html.escape(body)}</code>"
        return _hold(links, f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{chip}</a>' if url else chip)

    def link(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        url = links.href(target)
        inner = _inline_marks(html.escape(label), links, autolink=False)
        if url is None:
            return _hold(links, f'<span class="deadlink" title="{html.escape(target)}">{inner}</span>')
        external = re.match(r"^[a-z]+:", url) is not None
        attrs = ' target="_blank" rel="noopener"' if external else ""
        return _hold(links, f'<a href="{html.escape(url)}"{attrs}>{inner}</a>')

    text = re.sub(r"`([^`]+)`", code, text)
    text = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", link, text)
    return _restore(_inline_marks(html.escape(text, quote=False), links), links)


def _inline_marks(text: str, links: Links, autolink: bool = True) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)

    def verdict(m: re.Match) -> str:
        word = m.group(1)
        return _hold(links, f'<span class="verdict v-{word}">{word}</span>') if word in VERDICTS else m.group(0)

    def tag(m: re.Match) -> str:
        n, word = m.group(1), m.group(2) or ""
        cls = f" v-{word}" if word in VERDICTS else ""
        label = f"C{n} {word}".strip()
        return _hold(links, f'<span class="ctag{cls}">{label}</span>')

    text = re.sub(r"\[([a-z]+)\]", verdict, text)
    text = re.sub(r"\[C(\d+)(?:\s+([a-z]+))?\]", tag, text)
    if autolink:
        def ident(m: re.Match) -> str:
            url = links.ident(m.group(1))
            return _hold(links, f'<a class="idref" href="{html.escape(url)}">{m.group(1)}</a>') if url else m.group(0)

        def issue(m: re.Match) -> str:
            url = links.issue(m.group(1))
            return _hold(links, f'<a href="{html.escape(url)}" target="_blank" rel="noopener">#{m.group(1)}</a>') if url else m.group(0)

        text = ID_RE.sub(ident, text)
        text = re.sub(r"(?<![\w&/])#(\d+)\b", issue, text)
    return text


def _table(lines: list[str], links: Links) -> str:
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    head = "".join(f"<th>{inline(c, links)}</th>" for c in cells(lines[0]))
    body = "".join(
        "<tr>" + "".join(f"<td>{inline(c, links)}</td>" for c in cells(line)) + "</tr>"
        for line in lines[2:]
    )
    return f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")


def _list(lines: list[str], links: Links) -> str:
    """Render a list block; deeper indentation nests."""
    items: list[tuple[int, bool, str]] = []  # (indent, ordered, text)
    for line in lines:
        m = LIST_RE.match(line)
        if m:
            items.append((len(m.group(1).expandtabs(4)), m.group(2)[0].isdigit(), m.group(3)))
        elif items:
            indent, ordered, prev = items[-1]
            items[-1] = (indent, ordered, prev + " " + line.strip())

    out: list[str] = []
    stack: list[tuple[int, str]] = []
    for indent, ordered, text in items:
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            tag = "ol" if ordered else "ul"
            if ordered:
                start = re.match(r"\d+", LIST_RE.match(lines[0]).group(2)).group(0) if not stack else "1"
                out.append(f'<ol start="{start}">' if start != "1" else "<ol>")
            else:
                out.append("<ul>")
            stack.append((indent, tag))
        else:
            out.append("</li>")
        out.append(f"<li>{inline(text, links)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def render(md: str, links: Links | None = None) -> str:
    links = links or Links()
    lines = md.splitlines()
    out: list[str] = []
    para: list[str] = []
    i = 0

    def flush() -> None:
        if para:
            # Consecutive `Key: value` header lines (spec/ADR headers) stay one per line.
            fields = len(para) > 1 and all(FIELD_LINE_RE.match(l.strip()) for l in para)
            joined = "<br>".join(inline(l.strip(), links) for l in para) if fields else inline(
                " ".join(l.strip() for l in para), links)
            out.append(f'<p class="fields">{joined}</p>' if fields else f"<p>{joined}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            lang = stripped[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            code = html.escape("\n".join(lines[i + 1 : j]))
            out.append(f'<pre><code class="lang-{html.escape(lang)}">{code}</code></pre>')
            i = j + 1
            continue
        if stripped.startswith("<!--"):
            flush()
            j = i
            while j < len(lines) and "-->" not in lines[j]:
                j += 1
            note = " ".join(l.strip() for l in lines[i : j + 1])
            note = note.removeprefix("<!--").removesuffix("-->").strip()
            out.append(f'<p class="comment">{inline(note, links)}</p>')
            i = j + 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush()
            level, text = len(heading.group(1)), heading.group(2).strip()
            anchor = slug(text)
            out.append(
                f'<h{level} id="{html.escape(anchor)}">{inline(text, links)}'
                f'<a class="anchor" href="#{html.escape(anchor)}">#</a></h{level}>'
            )
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j], links))
            i = j
            continue
        if LIST_RE.match(line) and (not para or not line.startswith((" ", "\t"))):
            flush()
            j = i + 1
            while j < len(lines) and lines[j].strip() and (
                LIST_RE.match(lines[j]) or lines[j].startswith((" ", "\t"))
            ):
                j += 1
            out.append(_list(lines[i:j], links))
            i = j
            continue
        if stripped.startswith(">"):
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith(">"):
                j += 1
            quote = "\n".join(l.strip()[1:].lstrip() for l in lines[i:j])
            out.append(f"<blockquote>{render(quote, links)}</blockquote>")
            i = j
            continue
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if not stripped:
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    return "\n".join(out)
