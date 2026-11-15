"""The design system: ONE source of truth for colour, type, spacing and shared components.

Why this module exists
----------------------
Every page shell used to carry its own ``:root`` block and its own hardcoded hex values, which meant
(a) the same "brand orange" existed in several slightly different shades, and (b) there was no way to
add a dark theme without editing fifteen files. This module centralises all of that:

  * ``TOKENS_CSS`` — semantic custom properties (surfaces, text, brand, status, effects), defined
    once for light and redefined for dark.
  * ``BASE_CSS``  — a small reset, type scale and shared component classes.
  * ``THEME_JS``  — the pre-paint theme resolver + the toggle handler.

It is served as a single cacheable stylesheet at ``/theme.css`` (same-origin, so it passes our strict
CSP) and linked from every shell *before* that shell's own ``<style>`` block — so any page-local rule
still wins on a tie. Pages are migrated to reference ``var(--token)`` instead of literal hex; once a
page is fully migrated it is automatically dark-mode correct.

Theming contract (three states, the same one the rest of the web follows)
  * ``:root``                                   -> the complete light palette
  * ``@media (prefers-color-scheme: dark)``     -> dark, guarded by ``:not([data-theme="light"])``
    so an explicit light choice still wins
  * ``:root[data-theme="dark"]``                -> dark, chosen explicitly

Never give a colour its only definition inside a media query: light is always the base.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

# --------------------------------------------------------------------------------------- tokens
# The palette is DATA, not hand-written CSS. Dark has to be declared under two selectors (the OS
# preference and the explicit choice) and keeping two copies in sync by hand is the very duplication
# this module exists to remove — so both are generated from DARK below.
#
# Every value here has been checked for WCAG AA contrast against the surface it is used on; see
# tests/test_contrast.py, which does the real relative-luminance maths and fails the build on a
# regression. If you change a colour, run that test.
#
# NOTE ON THE TWO TERRACOTTAS: the site grew two brand shades — #e8772e (chat/home) and #c1440e
# (nav, admin, landing). Both are kept so this refactor changed nothing visually. To unify them,
# set LIGHT["--brand-strong"] = LIGHT["--brand"] — one line, right here.

LIGHT: dict[str, str] = {
    "color-scheme": "light",
    # surfaces
    "--bg": "#faf8f4", "--bg-2": "#f6f4f1", "--panel": "#fff", "--panel-2": "#f3efe9",
    "--panel-3": "#efe9e1", "--line": "#ece6dd", "--line-2": "#e3ddd3", "--line-3": "#f0ece5",
    # text  (--faint is #8994a8, not the original #98a2b3, which was only 2.58:1 on white)
    "--ink": "#222b33", "--ink-2": "#475467", "--ink-3": "#3a4654", "--muted": "#667085",
    "--faint": "#8994a8",
    # brand (terracotta/orange). --brand is for lines, icons and tints; --brand-fill + --on-brand
    # for anything filled, because white on #e8772e is only 2.95:1 while on #c1440e it is 5.12:1.
    "--brand": "#e77429", "--brand-d": "#cf6212", "--brand-strong": "#c1440e",
    "--brand-strong-d": "#a5380b", "--brand-fill": "#c1440e", "--on-brand": "#fff",
    "--brand-tint": "#fff4ea", "--brand-tint-2": "#ffe7d3", "--brand-ink": "#b4530f",
    # accent (teal) — same fill/line split
    "--accent": "#0f9b8e", "--accent-d": "#0c7e74", "--accent-fill": "#0c7e74",
    "--on-accent": "#fff", "--accent-tint": "#e7f6f4", "--accent-ink": "#0f766e",
    # warm decorative (hero cards, avatars, festival strips)
    "--warm-1": "#ffd9a0", "--warm-2": "#ffb56b", "--warm-tint": "#fff3dc",
    "--warm-line": "#ffd9a0", "--warm-ink": "#8a6a40",
    # status
    "--ok": "#137333", "--ok-tint": "#e7f6ec", "--warn": "#b45309", "--warn-tint": "#fff4e5",
    "--err": "#c5221f", "--err-tint": "#fdecec", "--info": "#1565c0", "--info-tint": "#e8f0fe",
    "--star": "#a36907", "--on-status": "#fff", "--map-ground": "#e8eef2",
    # effects
    "--ring": "#e8772e26", "--ring-accent": "#0f9b8e26",
    "--shadow-1": "0 1px 2px rgba(16,24,40,.04)", "--shadow-2": "0 4px 14px rgba(16,24,40,.05)",
    "--shadow-3": "0 8px 22px rgba(16,24,40,.10)", "--shadow-4": "0 14px 44px rgba(16,24,40,.09)",
    # geometry
    "--r-sm": "8px", "--r-md": "11px", "--r-lg": "14px", "--r-xl": "18px", "--r-2xl": "24px",
    "--r-pill": "999px",
}

DARK: dict[str, str] = {
    "color-scheme": "dark",
    "--bg": "#14110e", "--bg-2": "#181511", "--panel": "#1d1a16", "--panel-2": "#262220",
    "--panel-3": "#2d2825", "--line": "#332e29", "--line-2": "#3b352f", "--line-3": "#2b2622",
    "--ink": "#f1ece5", "--ink-2": "#cbc3b9", "--ink-3": "#d6cfc6", "--muted": "#a39a90",
    "--faint": "#7f776e",
    # on dark the bright hues ARE the fill, paired with dark ink (7.6:1 and 7.8:1)
    "--brand": "#f28c43", "--brand-d": "#e07a32", "--brand-strong": "#ef7e3c",
    "--brand-strong-d": "#d96a2c", "--brand-fill": "#f28c43", "--on-brand": "#1b1106",
    "--brand-tint": "#2e1f14", "--brand-tint-2": "#3b2718", "--brand-ink": "#f3a86a",
    "--accent": "#30c3b3", "--accent-d": "#26a89a", "--accent-fill": "#30c3b3",
    "--on-accent": "#06201d", "--accent-tint": "#12302d", "--accent-ink": "#5fd6c7",
    "--warm-1": "#4a3620", "--warm-2": "#5a3b22", "--warm-tint": "#2b2117",
    "--warm-line": "#453425", "--warm-ink": "#d8b98c",
    "--ok": "#4ade80", "--ok-tint": "#122a1c", "--warn": "#fbbf5c", "--warn-tint": "#2e2314",
    "--err": "#f87171", "--err-tint": "#2f1717", "--info": "#7cb2f5", "--info-tint": "#16233a",
    "--star": "#fbbf24", "--on-status": "#1a1512", "--map-ground": "#2a2f34",
    "--ring": "#f28c4340", "--ring-accent": "#30c3b340",
    "--shadow-1": "0 1px 2px rgba(0,0,0,.5)", "--shadow-2": "0 4px 14px rgba(0,0,0,.45)",
    "--shadow-3": "0 8px 22px rgba(0,0,0,.55)", "--shadow-4": "0 14px 44px rgba(0,0,0,.6)",
    "--r-sm": "8px", "--r-md": "11px", "--r-lg": "14px", "--r-xl": "18px", "--r-2xl": "24px",
    "--r-pill": "999px",
}

# Category identity hues. Each is used as a border, as a tint via color-mix AND as the count text on
# a category card, so every one clears 4.5:1 against its own theme's card surface. The dark values
# are the light hues raised in lightness until they do.
CATEGORY_HUES: dict[str, tuple[str, str]] = {          # category -> (light, dark)
    "restaurants": ("#c1440e", "#e65111"), "temples": ("#996f09", "#d9a00d"),
    "groceries": ("#2e7d32", "#37963c"), "professionals": ("#1565c0", "#2982e8"),
    "salons": ("#ad1457", "#e93e89"), "events": ("#6a1b9a", "#b05de3"),
    "apparel": ("#c2185b", "#e84183"), "sweets": ("#cf4900", "#f06200"),
    "studios": ("#00838f", "#00909e"), "services": ("#37474f", "#428aad"),
    "community": ("#5d4037", "#be6d54"), "legal": ("#3949ab", "#6f7dcf"),
    "education": ("#008577", "#00c9ad"), "realestate": ("#8d6e63", "#c49e8c"),
    "finance": ("#546e7a", "#8badc0"), "movies": ("#7b1fa2", "#b45fe0"),
    "employers": ("#455a64", "#8aa6b8"),
}

for _cat, (_l, _d) in CATEGORY_HUES.items():
    LIGHT[f"--cat-{_cat}"] = _l
    DARK[f"--cat-{_cat}"] = _d


def _decls(palette: dict[str, str], indent: str) -> str:
    """Render a palette as CSS declarations, three per line."""
    items = [f"{k}:{v};" for k, v in palette.items()]
    return "\n".join(indent + " ".join(items[i:i + 3]) for i in range(0, len(items), 3))


# Light is the base, on bare :root — never give a colour its only definition inside a media query.
# Dark is emitted twice from the SAME dict: once for the OS preference (guarded so an explicit light
# choice still wins) and once for the explicit choice (so the toggle wins in both directions).
TOKENS_CSS = f"""
:root{{
{_decls(LIGHT, " ")}
}}

/* Dark — follows the OS, unless the visitor explicitly chose light. */
@media (prefers-color-scheme: dark){{
 :root:not([data-theme="light"]){{
{_decls(DARK, "  ")}
 }}
}}

/* Dark — chosen explicitly, so the toggle wins in both directions. */
:root[data-theme="dark"]{{
{_decls(DARK, " ")}
}}
"""

# ------------------------------------------------------------------------------------- base css
# Deliberately small: a reset, sane defaults that read from the tokens, and the handful of
# primitives every page needs. Page-local <style> blocks load AFTER this file and still win, so
# adding to this file cannot restyle an un-migrated page out from under us.
BASE_CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink)}
img,svg,video{max-width:100%}
:where(a){color:var(--brand-strong)}
::selection{background:var(--ring);color:var(--ink)}
:where(a,button,input,select,textarea,summary,[tabindex]):focus-visible{
 outline:2px solid var(--brand);outline-offset:2px;border-radius:4px}
hr{border:0;border-top:1px solid var(--line);margin:18px 0}

/* Skip link — first tabbable element on every page. */
.skip-link{position:absolute;left:-9999px;top:0;z-index:999;background:var(--panel);color:var(--ink);
 border:1px solid var(--line);border-radius:0 0 var(--r-md) 0;padding:10px 16px;font-weight:600}
.skip-link:focus{left:0}

/* Theme toggle (sun/moon). Shown in the site header + admin header. */
.theme-toggle{background:var(--panel);border:1px solid var(--line);color:var(--ink);cursor:pointer;
 border-radius:var(--r-md);padding:7px 10px;font-size:15px;line-height:1;flex:0 0 auto}
.theme-toggle:hover{border-color:var(--brand)}
.theme-toggle .ti-dark{display:none}
:root[data-theme="dark"] .theme-toggle .ti-dark{display:inline}
:root[data-theme="dark"] .theme-toggle .ti-light{display:none}
@media (prefers-color-scheme: dark){
 :root:not([data-theme="light"]) .theme-toggle .ti-dark{display:inline}
 :root:not([data-theme="light"]) .theme-toggle .ti-light{display:none}
}

/* ------------------------------------------------------------------ touch: bottom tab bar
   70%+ of local search is on a phone, and the top nav is an eleven-item horizontal scroll strip
   whose later items are effectively invisible. On narrow screens the five primary destinations move
   into a fixed bar inside the thumb arc, the rest live behind "More", and the strip is hidden. On
   desktop none of this applies and the header is unchanged. */
.tabbar{display:none}
.navsheet{display:none}
@media (max-width:760px){
 .site-nav{display:none}                      /* its items are in the tab bar + More sheet */
 body{padding-bottom:calc(58px + env(safe-area-inset-bottom))}
 .tabbar{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:60;
  background:var(--panel);border-top:1px solid var(--line);
  padding-bottom:env(safe-area-inset-bottom);box-shadow:0 -2px 12px rgba(0,0,0,.06)}
 /* On the chat page the composer already owns the bottom edge, so the bar joins the flex column
    as a normal child instead of floating over it. */
 .tabbar.is-static{position:static;box-shadow:none;flex:0 0 auto}
 .tabbar a{flex:1 1 0;min-width:0;min-height:52px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:2px;text-decoration:none;color:var(--muted);
  font-size:10.5px;font-weight:600;padding:6px 2px 4px;-webkit-tap-highlight-color:transparent}
 .tabbar a .tb-ic{font-size:19px;line-height:1}
 .tabbar a .tb-lb{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
 .tabbar a.on{color:var(--brand-strong)}
 .tabbar a.on .tb-ic{transform:translateY(-1px)}
 .tabbar a:active{background:var(--panel-2)}

 /* "More" sheet: everything the bar has no room for, so nothing is unreachable. */
 .navsheet{display:block;position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.45)}
 .navsheet[hidden]{display:none!important}
 .navsheet-panel{position:absolute;left:0;right:0;bottom:0;background:var(--panel);
  border-radius:var(--r-xl) var(--r-xl) 0 0;padding:10px 14px calc(16px + env(safe-area-inset-bottom));
  max-height:78vh;overflow-y:auto}
 .navsheet-grip{width:40px;height:4px;border-radius:2px;background:var(--line-2);margin:4px auto 12px}
 .navsheet-panel a{display:flex;align-items:center;min-height:48px;padding:6px 10px;
  border-radius:var(--r-md);color:var(--ink);text-decoration:none;font-weight:600;font-size:15px}
 .navsheet-panel a:active{background:var(--panel-2)}
 .navsheet-close{width:100%;min-height:48px;margin-top:8px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink-2);border-radius:var(--r-md);font-size:15px;
  font-weight:600;cursor:pointer}

 /* Thumb reach: full-width primary actions, and no sub-44px tap target anywhere. */
 .cta,.addcta,.btn-primary{min-height:46px;display:inline-flex;align-items:center;justify-content:center}
 button,.btn,input[type=submit],select{min-height:44px}
 .fchip,.chip{min-height:40px;display:inline-flex;align-items:center}
}

/* ------------------------------------------------------------------ skeletons
   Shown while an answer is in flight so the page has shape before it has content. */
.sk{background:linear-gradient(90deg,var(--panel-2) 25%,var(--panel-3) 37%,var(--panel-2) 63%);
 background-size:400% 100%;animation:sk-shimmer 1.3s ease-in-out infinite;border-radius:var(--r-sm)}
@keyframes sk-shimmer{0%{background-position:100% 0}100%{background-position:0 0}}
.sk-card{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--line-2);
 border-radius:var(--r-lg);padding:15px 17px;margin-top:12px}
.sk-line{height:12px;margin:9px 0}
.sk-w70{width:70%}.sk-w45{width:45%}.sk-w90{width:90%}.sk-w30{width:30%}

/* Respect the visitor's motion preference — we ship pulsing mic/typing animations. */
@media (prefers-reduced-motion: reduce){
 *,*::before,*::after{animation-duration:.001ms !important;animation-iteration-count:1 !important;
  transition-duration:.001ms !important;scroll-behavior:auto !important}
}
"""

THEME_CSS = TOKENS_CSS + BASE_CSS

# ---------------------------------------------------------------------------------------- script
# Runs in <head> BEFORE first paint, so an explicitly-chosen theme never flashes the other palette.
# Kept to one line-ish and dependency-free; mirrors the three-state contract above.
# Each page ships its own light <meta name="theme-color"> (the shells differ), so the toggle
# remembers whatever was there at load and restores it, rather than hardcoding one brand shade.
THEME_JS = (
    "(function(){try{var t=localStorage.getItem('na_theme');"
    "if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();"
    "window.naToggleTheme=function(){var r=document.documentElement,c=r.getAttribute('data-theme');"
    "if(!c){c=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}"
    "var n=c==='dark'?'light':'dark';r.setAttribute('data-theme',n);"
    "try{localStorage.setItem('na_theme',n);}catch(e){}"
    "var m=document.querySelector('meta[name=\"theme-color\"]:not([media])')"
    "||document.querySelector('meta[name=\"theme-color\"]');"
    "if(m){if(!m.dataset.light)m.dataset.light=m.getAttribute('content')||'';"
    "m.setAttribute('content',n==='dark'?'" + DARK["--bg"] + "':m.dataset.light);}};"
)


def head_tags() -> str:
    """Everything a page shell needs in <head> to join the design system.

    Put this BEFORE the shell's own <style> block so page-local rules keep winning ties.
    """
    return (f'<link rel="stylesheet" href="/theme.css">'
            f'<script>{THEME_JS}</script>')


def theme_toggle() -> str:
    """The light/dark toggle button. Labelled for screen readers; icon swaps via CSS, not JS."""
    return ("<button type='button' class='theme-toggle' onclick='naToggleTheme()' "
            "title='Switch between light and dark' aria-label='Switch between light and dark'>"
            "<span class='ti-light' aria-hidden='true'>☽</span>"
            "<span class='ti-dark' aria-hidden='true'>☀</span></button>")


def skip_link(target: str = "#main") -> str:
    """A keyboard skip-link; pair with id='main' on the page's <main>/content wrapper."""
    return f"<a class='skip-link' href='{target}'>Skip to content</a>"


# ----------------------------------------------------------------------------------------- route
_MAX_AGE = 3600  # the stylesheet changes only on deploy; an hour is plenty and keeps dev sane


def theme_css(request: Request) -> Response:
    return Response(THEME_CSS, media_type="text/css",
                    headers={"Cache-Control": f"public, max-age={_MAX_AGE}"})


routes = [Route("/theme.css", theme_css, methods=["GET"])]
