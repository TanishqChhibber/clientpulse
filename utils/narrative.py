"""
ClientPulse Narrative Formatting
================================
Turns the plain text Claude writes for a summary or recommendations into readable
blocks: headings, numbered points and bullets whose key sentence is bold, and
paragraphs. Shared by the dashboard (HTML) and the PDF export. Input is treated
as untrusted text: HTML is escaped, only **bold** markup is honoured.
"""

import html
import re
from typing import List, Tuple

_NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_BULLET = re.compile(r"^\s*[-•*]\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CAPS_LEAD = re.compile(r"^([A-Z][A-Z0-9&/' -]{3,}?)\s*(\(.*\)|:.*)?\s*:?$")
_CELL = re.compile(r"^(.*?\S)\s+([-+]?(?:INR\s?)?[₹$€£]?[\d.,]+%?[A-Za-z]*(?:\s*\([^)]*\))?)$")
_NUMERIC_CELL = re.compile(r"[-+]?(?:INR\s?)?[₹$€£]?[\d.,/%]+[A-Za-z]?")


def _is_heading(line: str) -> bool:
    text = line.strip().rstrip(":")
    if not text or len(text) > 60 or _NUMBERED.match(line) or _BULLET.match(line):
        return False
    letters = [c for c in text if c.isalpha()]
    all_caps = len(letters) >= 3 and all(c.isupper() for c in letters)
    short_label = line.strip().endswith(":") and len(text.split()) <= 6
    return all_caps or short_label or (text.startswith("#"))


def _split_lead(text: str) -> Tuple[str, str]:
    """First sentence (the point) and the rest (the explanation)."""
    if "**" in text:
        return "", text  # the author already chose what to bold
    match = re.search(r"(?<=[.!?:])\s+(?=[A-Z0-9(“\"])", text)
    if match and match.start() <= 140:
        return text[:match.start()].strip(), text[match.end():].strip()
    return (text.strip(), "") if len(text) <= 140 else ("", text)


def _table(rows: List[str]) -> List[Tuple]:
    """
    Pipe-separated lines -> [optional heading, ('table', headers, rows)].
    1. Cells like 'LDAU 57,400' in every row become a column 'LDAU' with the number as the value.
    2. Otherwise a first row without plain numbers is treated as the header row.
    """
    split_rows = [[c.strip() for c in r.split("|")] for r in rows]
    width = max(len(r) for r in split_rows)
    split_rows = [r + [""] * (width - len(r)) for r in split_rows]

    labelled = [[_CELL.match(c) for c in r[1:] if c] for r in split_rows]
    labels = [m.group(1) if m else None for m in labelled[0]]
    if labels and all(labels) and all(
            len(row) == len(labels) and all(m and m.group(1) == labels[i] for i, m in enumerate(row)) for row in labelled):
        body = [[r[0]] + [m.group(2) for m in ms] for r, ms in zip(split_rows, labelled)]
        return [("table", [""] + labels, body)]

    first = split_rows[0]
    if len(split_rows) > 1 and not any(_NUMERIC_CELL.fullmatch(c) for c in first if c):
        out: List[Tuple] = []
        headers = []
        for c in first:
            if "(" in c and ")" not in c:   # "VIDEO BREAKDOWN, OCTOBER (length" -> heading + "length"
                title, _, rest = c.partition("(")
                if title.strip():
                    out.append(("heading", title.strip().rstrip(",")))
                    headers.append("")       # the name column the title was sitting on
                c = rest
            headers.append(c.replace(")", "").replace("(", "").strip())
        while len(headers) > width and headers[-1] == "":
            headers.pop()
        headers += [""] * (width - len(headers))
        return out + [("table", headers, split_rows[1:])]
    return [("table", [], split_rows)]


def parse(text: str) -> List[Tuple]:
    """Blocks: heading | note | item (marker, lead, rest) | table (headers, rows) | para."""
    blocks: List[Tuple] = []
    lines = [l.strip() for l in (text or "").replace("\r\n", "\n").split("\n")]
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            continue
        if line.count("|") >= 2:
            rows = [line]
            while i < len(lines) and lines[i].count("|") >= 2:
                rows.append(lines[i])
                i += 1
            blocks.extend(_table(rows))
            continue
        caps = _CAPS_LEAD.match(line)
        if caps and caps.group(2) and len(caps.group(1)) <= 60:
            blocks.append(("heading", caps.group(1).strip()))
            note = caps.group(2).strip().lstrip(":").strip().strip("()").strip()
            if note:
                blocks.append(("note", note))
            continue
        if _is_heading(line):
            blocks.append(("heading", line.lstrip("#").strip().rstrip(":").strip()))
            continue
        numbered, bullet = _NUMBERED.match(line), _BULLET.match(line)
        if numbered or bullet:
            marker = f"{numbered.group(1)}." if numbered else "•"
            body = numbered.group(2) if numbered else bullet.group(1)
            lead, rest = _split_lead(body)
            blocks.append(("item", marker, lead, rest))
        else:
            blocks.append(("para", line))
    return blocks


_LABEL = re.compile(r"^([^:.!?]{2,40}):\s+(.+)$")


def _inline_html(text: str) -> str:
    return _BOLD.sub(r"<b>\1</b>", html.escape(text))


def _para_html(text: str) -> str:
    """'Label: explanation' paragraphs get a bold label."""
    m = _LABEL.match(text)
    if m and "**" not in text:
        return f"<b>{html.escape(m.group(1))}:</b> {_inline_html(m.group(2))}"
    return _inline_html(text)


def to_html(text: str, empty: str = "Nothing here yet.") -> str:
    blocks = parse(text)
    if not blocks:
        return f'<p class="cp-prose-empty">{html.escape(empty)}</p>'
    parts = []
    for b in blocks:
        if b[0] == "heading":
            parts.append(f'<div class="cp-prose-h">{html.escape(b[1].title() if b[1].isupper() else b[1])}</div>')
        elif b[0] == "item":
            _, marker, lead, rest = b
            lead_html = f"<b>{_inline_html(lead)}</b> " if lead else ""
            parts.append(f'<div class="cp-prose-item"><span class="cp-prose-marker">{html.escape(marker)}</span>'
                         f'<span>{lead_html}{_inline_html(rest)}</span></div>')
        elif b[0] == "note":
            parts.append(f'<p class="cp-prose-note">{_inline_html(b[1])}</p>')
        elif b[0] == "table":
            _, headers, rows = b
            head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
            body = "".join("<tr>" + "".join(f"<td>{'<b>' + html.escape(c) + '</b>' if j == 0 else html.escape(c)}</td>"
                                           for j, c in enumerate(r)) + "</tr>" for r in rows)
            parts.append(f'<div class="cp-table-wrap"><table class="cp-table">'
                         f'{"<thead><tr>" + head + "</tr></thead>" if headers else ""}<tbody>{body}</tbody></table></div>')
        else:
            parts.append(f'<p class="cp-prose-p">{_para_html(b[1])}</p>')
    return "".join(parts)


def to_pdf_markdown(text: str) -> List[Tuple[str, str]]:
    """(kind, fpdf-markdown text) pairs; only ** is used for bold, other markers are neutralised."""
    def safe(s: str) -> str:
        return s.replace("__", "_ _").replace("--", "–")

    out = []
    for b in parse(text):
        if b[0] == "heading":
            out.append(("heading", safe(b[1].title() if b[1].isupper() else b[1])))
        elif b[0] == "item":
            _, marker, lead, rest = b
            out.append(("item", safe(f"{marker} " + (f"**{lead}** " if lead else "") + rest)))
        elif b[0] == "table":
            _, headers, rows = b
            out.append(("table", (headers, rows)))
        elif b[0] == "note":
            out.append(("note", safe(b[1])))
        else:
            m = _LABEL.match(b[1])
            text = f"**{m.group(1)}:** {m.group(2)}" if m and "**" not in b[1] else b[1]
            out.append(("para", safe(text)))
    return out
