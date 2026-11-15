"""Post-deploy smoke check over plain HTTPS — run it from anywhere, no DB access needed.

    python scripts/check_deploy.py                        # checks https://namasteamerica.us
    python scripts/check_deploy.py http://127.0.0.1:8080  # or a local dev server

Unlike scripts/verify_live.py (which queries the database and therefore only works on the VPS),
this only speaks HTTP, so it can confirm a deploy from a laptop. Exits non-zero if anything fails,
so it also works as a one-liner in a deploy script.

It checks the things that actually broke during the UI platform work: a page shell that forgot the
design system, the map client loading after the markup that calls it, an unsubstituted template
placeholder, a missing security header.
"""
from __future__ import annotations

import json
import re
import sys

import httpx          # already a project dependency; ships certifi, so TLS verification stays on

DEFAULT = "https://namasteamerica.us"
TIMEOUT = 20

_OK, _FAIL, _WARN = "  ok  ", " FAIL ", " warn "
_results: list[tuple[str, str, str]] = []


_HEADERS = {"User-Agent": "namaste-deploy-check/1"}


def _get(base: str, path: str) -> tuple[int, str, dict]:
    """(status, body, headers). Status 0 means the request never completed (DNS/TLS/timeout)."""
    try:
        r = httpx.get(base + path, headers=_HEADERS, timeout=TIMEOUT, follow_redirects=True)
        return r.status_code, r.text, dict(r.headers)
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}


def _post(base: str, path: str, payload: dict) -> tuple[int, str]:
    try:
        r = httpx.post(base + path, json=payload, headers=_HEADERS, timeout=TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def check(name: str, passed: bool, detail: str = "", *, warn_only: bool = False) -> bool:
    """Record a check. `detail` explains a FAILURE, so it is dropped when the check passes."""
    _results.append((name, _OK if passed else (_WARN if warn_only else _FAIL),
                     "" if passed else detail))
    return passed


def main(base: str) -> int:
    base = base.rstrip("/")
    print(f"checking {base}\n")

    # ---------------------------------------------------------------- reachable + healthy
    code, body, _ = _get(base, "/healthz")
    if not check("health endpoint", code == 200, body[:60] if code != 200 else ""):
        print("\n".join(f"{mark} {n}" + (f"  — {d}" if d else "")
                        for n, mark, d in _results))
        print("\nsite is not reachable — stopping here")
        return 1

    # ---------------------------------------------------------------- shared resources
    code, theme, _ = _get(base, "/theme.css")
    check("/theme.css served", code == 200, f"HTTP {code}")
    check("palette has light + dark",
          "--brand:" in theme and ':root[data-theme="dark"]' in theme
          and "prefers-color-scheme: dark" in theme)
    check("contrast-safe fill token exists", "--brand-fill:" in theme)

    code, mapjs, _ = _get(base, "/map.js")
    has_map_client = code == 200
    check("/map.js served", has_map_client, f"HTTP {code} (expected until the map commit is deployed)",
          warn_only=not has_map_client)
    if has_map_client:
        check("map client defines naMap", "window.naMap=window.naMap||" in mapjs)
        code, mapcss, _ = _get(base, "/map.css")
        check("/map.css served", code == 200 and ".imap-box{" in mapcss)

    # ---------------------------------------------------------------- page shells
    pages = ["/", "/browse", "/about", "/events", "/today", "/find", "/explore", "/for-business"]
    missing_theme, leaked = [], []
    for p in pages:
        code, html, _ = _get(base, p)
        if code != 200:
            check(f"{p} responds", False, f"HTTP {code}")
            continue
        if '<link rel="stylesheet" href="/theme.css">' not in html:
            missing_theme.append(p)
        if re.findall(r"__[A-Z][A-Z0-9_]{2,}__", html):
            leaked.append(p)
    check("every shell links the design system", not missing_theme, ", ".join(missing_theme))
    check("no unsubstituted placeholders", not leaked, ", ".join(leaked))

    code, home, _ = _get(base, "/")
    check("theme toggle present", "naToggleTheme" in home)
    check("mobile tab bar present", "tabbar" in home)
    check("skip link present", "skip-link" in home)

    # ---------------------------------------------------------------- maps on a real city page
    # /browse/<vertical> lists states, and the city links live one level below that -- so walk
    # down rather than guessing a URL. Without this the map check quietly skipped itself.
    def _find_city_page() -> str | None:
        _, vpage, _ = _get(base, "/browse/restaurants")
        city = re.search(r"/browse/restaurants/([a-z]{2})/([a-z0-9-]+)", vpage or "")
        if city:
            return city.group(0)
        for st in dict.fromkeys(re.findall(r"/browse/restaurants/([a-z]{2})\b", vpage or "")):
            _, spage, _ = _get(base, f"/browse/restaurants/{st}")
            city = re.search(rf"/browse/restaurants/{st}/([a-z0-9-]+)", spage or "")
            if city:
                return city.group(0)
        return None

    city_path = _find_city_page()
    if not check("found a city page to test the map on", bool(city_path),
                 "no city links under /browse/restaurants"):
        pass
    else:
        _, city, _ = _get(base, city_path)
        call = city.find("naMap('m")
        if check(f"map renders on {city_path}", call != -1, "no map in the page"):
            # the client must be in place before the inline call that uses it, however it is loaded
            loader = max(city.find('<script src="/map.js">'),
                         city.find("window.naMap=window.naMap||"))
            check("map client loads before it is called", loader != -1 and loader < call,
                  f"loader={loader} call={call}")
            check("map starts collapsed (OSM tile politeness)",
                  "<details class='imap' >" in city or "<details class='imap'>" in city)
            check("map attribution present", "openstreetmap.org/copyright" in city)

    # ---------------------------------------------------------------- the assistant
    code, raw = _post(base, "/chat/api",
                      {"messages": [{"role": "user", "content": "indian restaurants"}],
                       "filters": {}})
    if check("chat API answers", code == 200, f"HTTP {code}"):
        try:
            d = json.loads(raw)
        except Exception:
            d = {}
        check("chat returns a reply", bool(d.get("reply")))
        if has_map_client:                       # generative UI ships with the map commit
            check("chat returns follow-ups", isinstance(d.get("followups"), list))
            if d.get("cards"):
                check("chat cards carry coordinates",
                      any(c.get("lat") is not None for c in d["cards"]), warn_only=True)

    # ---------------------------------------------------------------- hardening
    _, _, h = _get(base, "/")
    csp = h.get("content-security-policy", "")
    check("CSP present", bool(csp))
    check("CSP keeps scripts same-origin", "script-src" in csp and "https://cdn" not in csp)
    check("nosniff header", h.get("x-content-type-options") == "nosniff")
    if base.startswith("https://"):
        check("HSTS header", "max-age" in h.get("strict-transport-security", ""), warn_only=True)

    # ---------------------------------------------------------------- report
    print("\n".join(f"{mark} {name}" + (f"  — {d}" if d else "") for name, mark, d in _results))
    failed = [n for n, mark, _ in _results if mark == _FAIL]
    warned = [n for n, mark, _ in _results if mark == _WARN]
    print(f"\n{len(_results) - len(failed) - len(warned)} ok, {len(warned)} warn, {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT))
