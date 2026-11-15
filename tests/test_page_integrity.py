"""Static integrity checks on every rendered page — the class of bug a TestClient normally misses.

Motivation (two real bugs shipped in one afternoon, both invisible to the existing suite):
  * the interactive map's initialiser was emitted at the end of <body> while each map's inline
    `naMap(...)` call sat beside its own markup — so every map threw ReferenceError and rendered
    blank, while every assertion about the markup passed;
  * a `var(--token)` typo renders as nothing at all, silently.

We have no Node and no browser driver (and no budget for a hosted one), so these parse the served
HTML instead: script definition order, inline handler targets, CSS custom-property references,
balanced style blocks, and unresolved template placeholders. Cheap, and they generalise — a new page
added to PAGES gets all of them for free.
"""

import re

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp import db, verticals
from indo_usa_mcp.web import theme
from indo_usa_mcp.web.app import app

_client = TestClient(app)

PAGES = ["/", "/explore", "/browse", "/browse/restaurants", "/about", "/faq", "/privacy", "/terms",
         "/contact", "/find", "/find?q=dosa", "/events", "/festivals", "/today", "/questions",
         "/ask", "/insights", "/for-business", "/for-agents", "/news", "/articles", "/movies",
         "/employers", "/api", "/portal/login", "/portal/register", "/me", "/leaderboard",
         "/submit", "/no-such-page"]

_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


def _get(path: str) -> str:
    return _client.get(path, follow_redirects=True).text


@pytest.fixture(scope="module")
def pages() -> dict[str, str]:
    """Every page fetched once; the checks below are cheap, the HTTP round-trips are not."""
    return {p: _get(p) for p in PAGES}


# --------------------------------------------------------------------------- script definition order
_STRINGS = re.compile(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`""")


def _toplevel_calls(script_body: str) -> dict[str, int]:
    """Identifiers invoked at brace depth 0, i.e. executed while the page is parsed.

    A call nested inside a function body runs later, by which time a definition further down the
    document exists — so only depth-0 calls can raise ReferenceError at parse time. String literals
    are blanked first so a brace inside one cannot shift the depth.
    """
    body = _STRINGS.sub(lambda m: " " * len(m.group(0)), script_body)
    depth, out = 0, {}
    for m in re.finditer(r"\{|\}|(\b[A-Za-z_$][\w$]*)\s*\(", body):
        tok = m.group(0)
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and m.group(1):
            out.setdefault(m.group(1), m.start())
    return out


def test_globals_are_defined_before_they_are_called(pages):
    """Our shared helpers are declared as `window.foo = window.foo || function…`. A top-level call
    to one must come after its definition in document order, or the page throws while parsing.

    This is the exact bug that made every interactive map render blank: the initialiser was emitted
    at the end of <body>, while each map's inline naMap(...) call sat beside its own markup.
    """
    for path, t in pages.items():
        defined = {m.group(1): m.start()
                   for m in re.finditer(r"window\.(\w+)\s*=\s*window\.\1\s*\|\|", t)}
        if not defined:
            continue
        for m in _SCRIPT.finditer(t):
            offset = m.start(1)
            for name, pos in _toplevel_calls(m.group(1)).items():
                if name in defined:
                    assert defined[name] < offset + pos, (
                        f"{path}: {name}() runs at byte {offset + pos} but is only defined at "
                        f"{defined[name]} -> ReferenceError while the page parses")


def test_inline_handlers_point_at_functions_that_exist(pages):
    """onclick='naSheet(true)' is a silent no-op if naSheet was never shipped on that page."""
    for path, t in pages.items():
        handlers = set(re.findall(r"on(?:click|change|submit|input)\s*=\s*['\"]\s*(\w+)\(", t))
        for fn in handlers:
            # `onclick="if(x)…"` and friends are statements, not calls to a function of ours
            if fn in {"return", "this", "event", "if", "for", "while", "switch", "typeof",
                      "alert", "confirm"}:
                continue
            defined = (f"function {fn}(" in t or f"window.{fn}=" in t
                       or re.search(rf"\b(?:var|let|const)\s+{fn}\s*=", t) is not None)
            assert defined, f"{path}: inline handler calls {fn}() which is not defined on the page"


def test_no_script_block_is_unbalanced(pages):
    """An unclosed brace in one inline block kills every statement after it in that block."""
    for path, t in pages.items():
        for i, body in enumerate(_SCRIPT.findall(t)):
            # strings and regex literals would confuse a naive count; only flag a big mismatch
            opens, closes = body.count("{"), body.count("}")
            assert abs(opens - closes) <= 2, (
                f"{path}: inline script #{i} has {opens} '{{' vs {closes} '}}'")


# --------------------------------------------------------------------------- CSS integrity
# Custom properties a COMPONENT sets on its own elements rather than on :root. The stylesheet that
# reads them ships on every page, but the declaration only exists where the component is rendered —
# so a page without any category cards legitimately has `var(--c)` with no page-level declaration.
_ELEMENT_LOCAL = {"--c"}


def _declared(text: str) -> set[str]:
    """Custom properties declared anywhere in `text`, including inline style='--c:…'."""
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", text))


def test_every_custom_property_used_is_declared(pages):
    """A var(--typo) renders as nothing — no error, no warning, just a missing colour."""
    palette = _declared(theme.THEME_CSS)
    for path, t in pages.items():
        available = palette | _declared(t) | _ELEMENT_LOCAL
        used = set(re.findall(r"var\((--[a-z0-9-]+)", t))
        missing = sorted(used - available)
        assert not missing, f"{path} uses undeclared custom properties: {missing}"


def test_the_design_system_does_not_reference_its_own_typos():
    """The stylesheet is served as a separate resource, so it never appears in any page's HTML — a
    var(--typo) *inside* /theme.css is invisible to the per-page check above. It gets its own."""
    css = _client.get("/theme.css").text
    declared = _declared(css) | _ELEMENT_LOCAL
    missing = sorted(set(re.findall(r"var\((--[a-z0-9-]+)", css)) - declared)
    assert not missing, f"/theme.css uses undeclared custom properties: {missing}"


def test_style_blocks_are_balanced(pages):
    for path, t in pages.items():
        for i, css in enumerate(_STYLE.findall(t)):
            assert css.count("{") == css.count("}"), f"{path}: <style> #{i} has unbalanced braces"


def test_no_page_redeclares_the_palette(pages):
    """A page-level `:root` copy of the palette is the pattern the design system replaced; it drifts
    and it breaks dark mode. One deliberate alias is fine, a whole palette is not."""
    for path, t in pages.items():
        for block in re.findall(r":root\s*\{([^}]*)\}", t):
            n = len(re.findall(r"--[a-z0-9-]+\s*:", block))
            assert n <= 3, f"{path} redeclares {n} tokens in a page-level :root block"


# --------------------------------------------------------------------------- template hygiene
def test_no_unresolved_placeholders(pages):
    """__LIKE_THIS__ placeholders are substituted by .replace(); a renamed key leaks the raw token."""
    for path, t in pages.items():
        leaked = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]{2,}__", t)))
        assert not leaked, f"{path} leaked unsubstituted placeholders: {leaked}"


def test_no_python_repr_leaked_into_html(pages):
    """A dict or None reaching the template usually means a formatting bug, not a design choice."""
    for path, t in pages.items():
        # `{'` and `'}` appear in ordinary JS object literals, so they are not signals.
        for bad in ("None</", ">None<", "dict_keys(", "<built-in", " object at 0x"):
            assert bad not in t, f"{path} contains a leaked Python value: {bad!r}"


def test_every_page_declares_a_viewport_and_charset(pages):
    for path, t in pages.items():
        assert 'name="viewport"' in t, f"{path} has no viewport meta (mobile layout breaks)"
        assert "charset=" in t, f"{path} has no charset"


# --------------------------------------------------------------------------- data-dependent pages
# The city and listing templates only render once there are rows, so the module-level `pages`
# fixture cannot reach them. They get the identical checks against a throwaway record — reusing the
# same helpers, so there is one definition of each rule rather than a drifting copy.
_DATA_CHECKS = (
    test_globals_are_defined_before_they_are_called,
    test_inline_handlers_point_at_functions_that_exist,
    test_no_script_block_is_unbalanced,
    test_every_custom_property_used_is_declared,
    test_style_blocks_are_balanced,
    test_no_page_redeclares_the_palette,
    test_no_unresolved_placeholders,
    test_no_python_repr_leaked_into_html,
    test_every_page_declares_a_viewport_and_charset,
)


def test_city_and_listing_pages_pass_every_check():
    """Covers the two templates that need data — including the interactive map, which only appears
    on pages with geocoded rows and was exactly where the definition-order bug hid."""
    rid = verticals.create_record(
        "restaurants",
        {"name": "ZZTEST Integrity Cafe", "city": "Zzintegrity", "state": "TX",
         "lat": 33.0, "lng": -96.7}, source="test")["id"]
    try:
        rendered = {p: _get(p) for p in ("/browse/restaurants/tx/zzintegrity",
                                        f"/listing/restaurants/{rid}")}
        assert "naMap(" in rendered[f"/listing/restaurants/{rid}"], "expected a map to check"
        for check in _DATA_CHECKS:
            check(rendered)
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
