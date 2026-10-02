"""Parse `.bib` files and format citations + a bibliography.

LaTeX-shaped citing, without a LaTeX toolchain: the manifest names one or more
BibTeX files, documents cite with `\\cite{key}`, and a `\\bibliography` marker
renders the reference list. Everything here runs at build time and produces
plain HTML strings, so the published page carries no citation runtime — the
same bargain the math rendering makes.

Deliberately dependency-free. BibTeX is small enough to parse directly, and a
citation formatter that only has to cover the entry types people actually write
is far less code than pulling in a CSL engine.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ── LaTeX → text ────────────────────────────────────────────────────────────

# Accents written either as `\"o` or `{\"o}` / `\"{o}`.
_ACCENTS = {
    '"': {"a": "ä", "e": "ë", "i": "ï", "o": "ö", "u": "ü", "y": "ÿ",
          "A": "Ä", "E": "Ë", "I": "Ï", "O": "Ö", "U": "Ü"},
    "'": {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ý", "c": "ć",
          "n": "ń", "s": "ś", "z": "ź",
          "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú", "C": "Ć"},
    "`": {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù",
          "A": "À", "E": "È", "I": "Ì", "O": "Ò", "U": "Ù"},
    "^": {"a": "â", "e": "ê", "i": "î", "o": "ô", "u": "û",
          "A": "Â", "E": "Ê", "I": "Î", "O": "Ô", "U": "Û"},
    "~": {"a": "ã", "n": "ñ", "o": "õ", "A": "Ã", "N": "Ñ", "O": "Õ"},
    "c": {"c": "ç", "C": "Ç", "s": "ş", "S": "Ş"},
    "v": {"c": "č", "s": "š", "z": "ž", "r": "ř", "e": "ě",
          "C": "Č", "S": "Š", "Z": "Ž", "R": "Ř"},
    "=": {"a": "ā", "e": "ē", "i": "ī", "o": "ō", "u": "ū"},
    ".": {"a": "ȧ", "e": "ė", "z": "ż", "Z": "Ż"},
    "u": {"a": "ă", "e": "ĕ", "g": "ğ", "G": "Ğ"},
    "H": {"o": "ő", "u": "ű", "O": "Ő", "U": "Ű"},
    "k": {"a": "ą", "e": "ę", "A": "Ą", "E": "Ę"},
}

_SPECIALS = {
    r"\ss": "ß", r"\aa": "å", r"\AA": "Å", r"\o": "ø", r"\O": "Ø",
    r"\ae": "æ", r"\AE": "Æ", r"\oe": "œ", r"\OE": "Œ", r"\l": "ł",
    r"\L": "Ł", r"\i": "ı", r"\j": "ȷ", r"\dag": "†", r"\ddag": "‡",
    r"\copyright": "©", r"\pounds": "£", r"\S": "§", r"\P": "¶",
    r"\ldots": "…", r"\dots": "…", r"\textendash": "–", r"\textemdash": "—",
}

# Inline math in a title is common in this domain ("the $\\alpha$ locus",
# "$h^2$"). The bibliography is emitted as raw HTML and never passes through
# the math renderer, so map the small set of symbols that actually show up in
# titles to Unicode rather than letting the generic command-stripper reduce
# `$\\alpha$` to `$$`.
_MATH_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
    "times": "×", "pm": "±", "mp": "∓", "cdot": "·", "leq": "≤", "le": "≤",
    "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈", "sim": "∼",
    "infty": "∞", "rightarrow": "→", "to": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "in": "∈", "subset": "⊂", "cap": "∩", "cup": "∪",
    "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "int": "∫",
    "sqrt": "√", "propto": "∝", "equiv": "≡", "ll": "≪", "gg": "≫",
    "prime": "′", "circ": "∘", "degree": "°", "ldots": "…",
}

_SUPERSCRIPT = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _math_to_text(expr: str) -> str:
    """Best-effort Unicode rendering of a short inline-math span."""
    s = expr
    for name, ch in sorted(_MATH_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(r"\\" + name + r"(?![A-Za-z])", ch, s)
    # h^2 / h^{2} → h², x_i / x_{ij} → xᵢⱼ where the characters exist.
    def sup(m: re.Match[str]) -> str:
        body = m.group(1) or m.group(2)
        return body.translate(_SUPERSCRIPT) if all(
            c in "0123456789+-=()n" for c in body
        ) else f"^{body}"

    def sub(m: re.Match[str]) -> str:
        body = m.group(1) or m.group(2)
        return body.translate(_SUBSCRIPT) if all(
            c in "0123456789+-=()" for c in body
        ) else f"_{body}"

    s = re.sub(r"\^\{([^{}]*)\}|\^(\w)", sup, s)
    s = re.sub(r"_\{([^{}]*)\}|_(\w)", sub, s)
    s = re.sub(r"\\(?:mathrm|mathbf|mathit|mathcal|mathbb|text)\s*\{([^{}]*)\}", r"\1", s)
    s = s.replace("{", "").replace("}", "").replace("\\,", " ").replace("\\ ", " ")
    return s.strip()


# Commands whose sole argument should survive; the wrapper is dropped.
_UNWRAP = (
    "emph", "textit", "textbf", "textrm", "textsc", "texttt", "textsl",
    "mbox", "text", "url", "href", "textnormal", "MakeLowercase",
    "MakeUppercase", "lowercase", "uppercase",
)


def _strip_accents(s: str) -> str:
    # `{\"o}` / `\"{o}` / `\"o`, plus `{\ss}` style specials.
    def accent(m: re.Match[str]) -> str:
        mark, letter = m.group(1), m.group(2)
        return _ACCENTS.get(mark, {}).get(letter, letter)

    pattern = r'\\([\'"`^~=.cvuHk])\s*\{?([A-Za-z])\}?'
    prev = None
    while prev != s:
        prev = s
        s = re.sub(pattern, accent, s)
    for cmd, ch in sorted(_SPECIALS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(re.escape(cmd) + r"(?![A-Za-z])", ch, s)
    return s


def latex_to_text(value: str) -> str:
    """Render a BibTeX field value as plain text.

    Brace groups in BibTeX carry two meanings: grouping, and "do not recase
    this". We only ever preserve the author's capitalisation, so both collapse
    to the same thing — drop the braces, keep the contents.
    """
    s = value
    # Pull inline math out first; the generic command stripper below would
    # otherwise reduce `$\\alpha$` to a bare `$$`.
    s = re.sub(r"\$([^$]+)\$", lambda m: _math_to_text(m.group(1)), s)
    s = _strip_accents(s)
    for cmd in _UNWRAP:
        s = re.sub(r"\\" + cmd + r"\s*\{([^{}]*)\}", r"\1", s)
    # Old-style font switches: {\it foo}, {\bf foo}
    s = re.sub(r"\{\\(?:it|bf|sc|tt|rm|sl|em)\s+([^{}]*)\}", r"\1", s)
    s = s.replace("---", "—").replace("--", "–")
    s = re.sub(r"\\([&%$#_{}])", r"\1", s)
    s = s.replace("~", "\u00a0")
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)      # any command we don't know
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


# ── BibTeX parsing ──────────────────────────────────────────────────────────

class BibError(Exception):
    pass


@dataclass
class Entry:
    key: str
    type: str
    fields: dict[str, str]

    def get(self, *names: str, default: str = "") -> str:
        for n in names:
            v = self.fields.get(n)
            if v:
                return v
        return default


def _skip_ws(src: str, i: int) -> int:
    while i < len(src) and src[i].isspace():
        i += 1
    return i


def _read_braced(src: str, i: int) -> tuple[str, int]:
    """Read a `{...}` group at `i`, returning its contents and the next index."""
    assert src[i] == "{"
    depth, start = 0, i
    while i < len(src):
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1 : i], i + 1
        i += 1
    raise BibError("unbalanced '{' in .bib file")


def _read_quoted(src: str, i: int) -> tuple[str, int]:
    """Read a `"..."` value, honouring brace nesting inside it."""
    assert src[i] == '"'
    depth, i0 = 0, i
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == '"' and depth == 0:
            return src[i0 + 1 : i], i + 1
        i += 1
    raise BibError('unterminated \'"\' in .bib file')


def _read_value(src: str, i: int, macros: dict[str, str]) -> tuple[str, int]:
    """Read one field value, following `#` concatenation."""
    parts: list[str] = []
    while True:
        i = _skip_ws(src, i)
        if i >= len(src):
            break
        c = src[i]
        if c == "{":
            chunk, i = _read_braced(src, i)
            parts.append(chunk)
        elif c == '"':
            chunk, i = _read_quoted(src, i)
            parts.append(chunk)
        else:
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] in "_-.:/"):
                j += 1
            word = src[i:j]
            if not word:
                break
            # A bare word is a @string macro if we know it, else a literal
            # (which is how BibTeX treats numbers).
            parts.append(macros.get(word.lower(), word))
            i = j
        i = _skip_ws(src, i)
        if i < len(src) and src[i] == "#":
            i += 1
            continue
        break
    return "".join(parts), i


def parse_bibtex(text: str, *, origin: str = "<bib>") -> dict[str, Entry]:
    """Parse BibTeX source into `{key: Entry}`.

    Text outside `@...` blocks is ignored, which is what BibTeX itself does and
    what makes stray comments harmless. `@string` macros are expanded,
    `@comment` and `@preamble` are skipped.
    """
    entries: dict[str, Entry] = {}
    macros: dict[str, str] = {}
    i = 0
    while True:
        at = text.find("@", i)
        if at == -1:
            break
        i = at + 1
        i = _skip_ws(text, i)
        j = i
        while j < len(text) and text[j].isalpha():
            j += 1
        etype = text[i:j].lower()
        i = _skip_ws(text, j)
        if i >= len(text) or text[i] not in "{(":
            continue
        opener = text[i]
        if opener == "(":
            # `@type(...)` is legal but rare; normalise by treating the body as
            # running to the matching ')'.
            close = text.find(")", i)
            if close == -1:
                break
            body, i = text[i + 1 : close], close + 1
            body_start = 0
        else:
            body, i = _read_braced(text, i)
            body_start = 0

        if etype in ("comment", "preamble"):
            continue

        if etype == "string":
            m = re.match(r"\s*([A-Za-z][\w.-]*)\s*=", body)
            if m:
                val, _ = _read_value(body, m.end(), macros)
                macros[m.group(1).lower()] = val
            continue

        # Entry: key, then `field = value` pairs.
        k = body_start
        k = _skip_ws(body, k)
        comma = body.find(",", k)
        if comma == -1:
            key, k = body[k:].strip(), len(body)
        else:
            key, k = body[k:comma].strip(), comma + 1
        if not key:
            continue

        fields: dict[str, str] = {}
        while k < len(body):
            k = _skip_ws(body, k)
            m = re.compile(r"([A-Za-z][\w.:-]*)\s*=").match(body, k)
            if not m:
                break
            name = m.group(1).lower()
            value, k = _read_value(body, m.end(), macros)
            fields[name] = value
            k = _skip_ws(body, k)
            if k < len(body) and body[k] == ",":
                k += 1

        if key in entries:
            print(
                f"  warning: duplicate bib key {key!r} in {origin} — keeping the first",
                file=sys.stderr,
            )
            continue
        entries[key] = Entry(key=key, type=etype, fields=fields)
    return entries


# ── Names ───────────────────────────────────────────────────────────────────

@dataclass
class Name:
    family: str
    given: str = ""

    @property
    def initials(self) -> str:
        parts = [p for p in re.split(r"[\s.\-]+", self.given) if p]
        return " ".join(f"{p[0]}." for p in parts)


def _split_authors(value: str) -> list[str]:
    """Split on ` and ` at brace depth zero."""
    out, depth, buf = [], 0, []
    tokens = re.split(r"(\{|\}|\band\b)", value)
    for tok in tokens:
        if tok == "{":
            depth += 1
            buf.append(tok)
        elif tok == "}":
            depth -= 1
            buf.append(tok)
        elif tok == "and" and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(tok)
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def parse_names(value: str) -> list[Name]:
    names: list[Name] = []
    for raw in _split_authors(value):
        raw = latex_to_text(raw)
        if not raw:
            continue
        if raw.lower() in ("others", "et al", "et al."):
            names.append(Name(family="others"))
            continue
        if "," in raw:
            # "von Last, Jr, First"
            bits = [b.strip() for b in raw.split(",")]
            family = bits[0]
            given = bits[-1] if len(bits) > 1 else ""
        else:
            words = raw.split()
            family = words[-1] if words else raw
            given = " ".join(words[:-1])
        names.append(Name(family=family, given=given))
    return names


def _label_names(names: list[Name]) -> str:
    """Author-year style in-text label: Smith / Smith and Doe / Smith et al."""
    real = [n for n in names if n.family != "others"]
    truncated = len(real) != len(names)
    if not real:
        return ""
    if truncated or len(real) > 2:
        return f"{real[0].family} et al."
    if len(real) == 2:
        return f"{real[0].family} and {real[1].family}"
    return real[0].family


# ── Reference formatting ────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _join_sentences(parts: list[str]) -> str:
    """Join reference segments with `. `, without doubling existing periods.

    Author lists and abbreviations already end in a period ("Wray, N. R.",
    "4th edn."), so a naive `". ".join` produces "N. R.. (2008)".
    """
    out = ""
    for part in [p for p in parts if p]:
        if not out:
            out = part
        elif re.search(r"[.!?]\s*(</[a-z]+>)?$", out):
            out += " " + part
        else:
            out += ". " + part
    if out and not re.search(r"[.!?]\s*(</[a-z]+>)?$", out):
        out += "."
    return out


def _author_list(names: list[Name]) -> str:
    """`Smith, J., Doe, A. & Roe, B.` — trailing `others` becomes `et al.`"""
    real = [n for n in names if n.family != "others"]
    etal = len(real) != len(names)
    rendered = [
        f"{n.family}, {n.initials}" if n.initials else n.family for n in real
    ]
    if not rendered:
        return ""
    if etal:
        return rendered[0] + " et al."
    if len(rendered) == 1:
        return rendered[0]
    return ", ".join(rendered[:-1]) + " & " + rendered[-1]


def _year(entry: Entry) -> str:
    y = entry.get("year")
    if not y:
        # biblatex `date = {2020-05-01}`
        m = re.match(r"\s*(\d{4})", entry.get("date"))
        y = m.group(1) if m else ""
    m = re.search(r"\d{4}", y)
    return m.group(0) if m else latex_to_text(y)


def _link(entry: Entry) -> tuple[str, str]:
    """Return (href, label) for the entry's canonical link, or ('', '')."""
    doi = latex_to_text(entry.get("doi")).strip()
    if doi:
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi, flags=re.I)
        return f"https://doi.org/{doi}", f"doi:{doi}"
    url = latex_to_text(entry.get("url", "howpublished")).strip()
    if url.startswith("http"):
        short = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        return url, short[:60] + ("…" if len(short) > 60 else "")
    return "", ""


def format_reference(entry: Entry, *, link: bool = True) -> tuple[str, str]:
    """Render one bibliography entry. Returns (html, plain_text)."""
    names = parse_names(entry.get("author", "editor"))
    authors = _author_list(names)
    year = _year(entry)
    title = latex_to_text(entry.get("title"))
    et = entry.type

    bits_html: list[str] = []
    bits_text: list[str] = []

    def add(html: str, text: str | None = None) -> None:
        if html:
            bits_html.append(html)
            bits_text.append(text if text is not None else re.sub(r"<[^>]+>", "", html))

    add(_esc(authors), authors)
    if year:
        add(f"({_esc(year)})", f"({year})")
    add(_esc(title), title)

    if et in ("article",):
        journal = latex_to_text(entry.get("journal", "journaltitle"))
        vol = latex_to_text(entry.get("volume"))
        num = latex_to_text(entry.get("number", "issue"))
        pages = latex_to_text(entry.get("pages")).replace("--", "–")
        where = f"<em>{_esc(journal)}</em>" if journal else ""
        where_text = journal
        if vol:
            where += f" <strong>{_esc(vol)}</strong>"
            where_text += f" {vol}"
            if num:
                where += f"({_esc(num)})"
                where_text += f"({num})"
        if pages:
            where += f", {_esc(pages)}" if vol else f" {_esc(pages)}"
            where_text += f", {pages}"
        add(where, where_text)
    elif et in ("inproceedings", "conference", "incollection"):
        book = latex_to_text(entry.get("booktitle"))
        pages = latex_to_text(entry.get("pages")).replace("--", "–")
        if book:
            add(f"In <em>{_esc(book)}</em>", f"In {book}")
        if pages:
            add(f"pp. {_esc(pages)}", f"pp. {pages}")
        add(_esc(latex_to_text(entry.get("publisher"))))
    elif et == "book":
        ed = latex_to_text(entry.get("edition"))
        if ed:
            add(f"{_esc(ed)} edn.", f"{ed} edn.")
        add(_esc(latex_to_text(entry.get("publisher"))))
    elif et in ("phdthesis", "mastersthesis"):
        kind = "PhD thesis" if et == "phdthesis" else "Master's thesis"
        add(kind)
        add(_esc(latex_to_text(entry.get("school", "institution"))))
    elif et in ("techreport", "report"):
        add("Technical report")
        add(_esc(latex_to_text(entry.get("institution", "school"))))
    else:
        add(_esc(latex_to_text(entry.get("journal", "booktitle", "publisher",
                                         "institution", "school", "note"))))

    href, label = _link(entry) if link else ("", "")
    html = _join_sentences(bits_html)
    text = _join_sentences(bits_text)
    if href:
        html += (
            f' <a class="ref-link" href="{_esc(href)}"'
            f' target="_blank" rel="noreferrer">{_esc(label)}</a>'
        )
        text += f" {label}"
    return html, text


@dataclass
class Bibliography:
    """Everything the renderer needs, in a JSON-serialisable shape."""

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    style: str = "numeric"
    sort: str = "appearance"
    title: str = "References"
    heading: str = "h2"

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "sort": self.sort,
            "title": self.title,
            "heading": self.heading,
            "entries": self.entries,
        }


def load_bibliography(
    root: Path,
    sources: Iterable[str],
    *,
    style: str = "numeric",
    sort: str = "appearance",
    title: str = "References",
    heading: str = "h2",
    link: bool = True,
) -> Bibliography:
    """Read every `.bib` source and pre-render each entry.

    Formatting happens here, once, rather than per citation in the renderer:
    the markdown-it side only has to choose labels and order.
    """
    merged: dict[str, Entry] = {}
    for src in sources:
        path = root / src
        if not path.is_file():
            print(f"  warning: bibliography source {src} not found", file=sys.stderr)
            continue
        for key, entry in parse_bibtex(path.read_text(), origin=src).items():
            if key in merged:
                print(
                    f"  warning: duplicate bib key {key!r} across sources — "
                    "keeping the first",
                    file=sys.stderr,
                )
                continue
            merged[key] = entry

    out: dict[str, dict[str, Any]] = {}
    for key, entry in merged.items():
        names = parse_names(entry.get("author", "editor"))
        year = _year(entry)
        html, text = format_reference(entry, link=link)
        label = _label_names(names)
        out[key] = {
            "html": html,
            "text": text,
            # In-text forms for author-year style.
            "label": f"{label}, {year}" if label and year else (label or key),
            "labelBare": label or key,
            "year": year,
            # Sort keys, precomputed so the JS side never has to know about
            # name parsing or locale collation.
            "sortAuthor": (
                f"{names[0].family.lower()} {year}" if names else key.lower()
            ),
            "sortYear": f"{year or '9999'} {names[0].family.lower() if names else key}",
        }

    return Bibliography(
        entries=out, style=style, sort=sort, title=title, heading=heading
    )
