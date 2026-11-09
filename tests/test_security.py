"""Security tests for the event calendar (run: python -m pytest -q tests)."""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import attack_payloads as P  # noqa: E402
import build  # noqa: E402
from common import (UnsafeDataError, clean_text, excel_safe, load_events, safe_url,  # noqa: E402
                    sanitize_event, to_ics)
from crawl import from_jsonld  # noqa: E402
from export_xlsx import write_xlsx  # noqa: E402

DOCS = ROOT / "docs"
STAMP = dt.datetime(2026, 11, 9, tzinfo=dt.timezone.utc)


# ----------------------------------------------------------------- input sanitising

@pytest.mark.parametrize("url", P.UNSAFE_URLS)
def test_safe_url_rejects_dangerous_urls(url):
    assert safe_url(url) is None


@pytest.mark.parametrize("url", ["https://www.itsmf.de/veranstaltung/x/", "http://example.org/a?b=c&d=e#f"])
def test_safe_url_accepts_normal_urls(url):
    assert safe_url(url) == url


def test_clean_text_strips_html_control_and_bidi():
    assert clean_text('<img src=x onerror=alert(1)>A\r\nB\x00‮C') == "A B C"
    assert len(clean_text("x" * 5000, 200)) == 200


@pytest.mark.parametrize("ev_id", ["js-url", "data-url"])
def test_build_rejects_unsafe_url_fail_closed(ev_id):
    ev = next(e for e in P.malicious_events() if e["id"] == ev_id)
    with pytest.raises(UnsafeDataError):
        build.validate([dict(ev)])


def test_build_rejects_unknown_enum_values():
    ev = dict(P.malicious_events()[0], status="<script>")
    with pytest.raises(UnsafeDataError):
        build.validate([ev])


def test_build_rejects_malicious_id():
    ev = dict(P.malicious_events()[0], id="../../etc/passwd")
    with pytest.raises(UnsafeDataError):
        sanitize_event(ev)


def test_build_sanitises_text_fields():
    safe = [e for e in P.malicious_events() if e["id"] not in ("js-url", "data-url")]
    out = build.validate([dict(e) for e in safe])
    for e in out:
        for field in ("title", "location", "description_de", "description_en"):
            assert "<" not in e[field] and "\r" not in e[field] and "‮" not in e[field]


def test_real_dataset_passes_validation():
    events = build.validate(load_events())
    assert len(events) > 100
    assert all(safe_url(e["url"]) for e in events)


# ----------------------------------------------------------------- ICS injection

def test_ics_has_no_injected_properties():
    events = [sanitize_event(e) for e in P.malicious_events() if e["id"] not in ("js-url", "data-url")]
    # also feed raw (unsanitised) data to prove the serialiser itself is safe
    raw = [e for e in P.malicious_events() if e["id"] == "ics-inject"]
    ics = to_ics(events + raw, "t", STAMP)
    unfolded = ics.replace("\r\n ", "")
    lines = unfolded.split("\r\n")
    assert not [l for l in lines if l.startswith(("ATTACH", "X-INJ", "BEGIN:VALARM", "TRIGGER", "ACTION"))]
    assert all("\r" not in l and "\n" not in l for l in lines)
    assert "javascript:" not in ics.lower()


def test_ics_drops_unsafe_url_even_without_validation():
    ev = next(e for e in P.malicious_events() if e["id"] == "js-url")
    assert "URL:javascript" not in to_ics([ev], "t", STAMP)


# ----------------------------------------------------------------- Excel formula injection

def test_xlsx_has_no_formula_injection(tmp_path):
    events = [e for e in P.malicious_events()]
    path = tmp_path / "x.xlsx"
    write_xlsx(events, [{"title": "=1+1", "expected": "@x", "location": "-y", "url": "javascript:x", "categories": []}],
               path, STAMP)
    wb = openpyxl.load_workbook(path)
    for name in ("Events", "Beobachtungsliste"):
        ws = wb[name]
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if name == "Events" and c.column == 3:
                    continue  # our own "Tage" formula
                assert c.data_type != "f", f"{name}!{c.coordinate} executes as formula: {c.value!r}"
                if c.hyperlink:
                    assert safe_url(c.hyperlink.target), f"unsafe hyperlink {c.hyperlink.target!r}"


def test_excel_safe_prefixes_formula_triggers():
    for v in ("=1", "+1", "-1", "@1", "\t=1", "＝1"):
        assert excel_safe(v).startswith("'")
    assert excel_safe("Normal") == "Normal"


# ----------------------------------------------------------------- crawler (untrusted input)

def test_crawler_drops_malicious_jsonld():
    assert from_jsonld(P.MAL_JSONLD_PAGE, "https://evil.example/events") == []


def test_crawler_keeps_benign_jsonld_but_strips_markup():
    c = from_jsonld(P.BENIGN_JSONLD_PAGE, "https://servicespace.acp-gruppe.com/x")
    assert len(c) == 1
    assert c[0]["title"] == "Service Space 2027"
    assert c[0]["url"] == "https://servicespace.acp-gruppe.com/en/"


def test_ai_extraction_prompt_marks_page_as_untrusted():
    src = (ROOT / "scripts" / "crawl.py").read_text(encoding="utf-8")
    assert "never instructions" in src and "<page>" in src


def test_yaml_is_loaded_safely():
    for f in (ROOT / "scripts").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"yaml\.load\(", src), f"unsafe yaml.load in {f.name}"
        assert "eval(" not in src and "exec(" not in src and "shell=True" not in src


# ----------------------------------------------------------------- website (static analysis)

def _html():
    return (DOCS / "index.html").read_text(encoding="utf-8")


def test_csp_is_strict():
    m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', _html())
    assert m, "CSP meta tag missing"
    csp = m.group(1)
    for directive in ("default-src 'none'", "script-src 'self'", "base-uri 'none'", "form-action 'none'",
                      "connect-src 'self'", "font-src 'self'"):
        assert directive in csp
    assert "unsafe-eval" not in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_no_inline_scripts_handlers_or_styles():
    html = _html()
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> found"
    assert not re.search(r"\son[a-z]+\s*=", html, re.I), "inline event handler found"
    assert "style=" not in html, "inline style attribute found"


def test_no_external_resources_loaded():
    html = _html()
    for m in re.finditer(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="([^"]+)"', html):
        assert not m.group(1).startswith(("http:", "https:", "//")), f"external resource: {m.group(1)}"
    css = "".join(p.read_text(encoding="utf-8") for p in DOCS.rglob("*.css"))
    assert "fonts.googleapis" not in css and "@import" not in css
    assert not re.search(r"url\((['\"]?)(https?:)?//", css)


def test_frontend_js_has_no_dangerous_sinks():
    js = (DOCS / "assets" / "app.js").read_text(encoding="utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in js, f"dangerous sink {sink}"
    # every href assignment goes through safeUrl / extLink or a constant
    for m in re.finditer(r"\.href\s*=\s*([^;]+);", js):
        rhs = m.group(1)
        assert ("safeUrl" in rhs or rhs.strip().startswith(("su", '"https://', '"webcal://')) or "g.toString()" in rhs), rhs


def test_external_links_have_noopener():
    for m in re.finditer(r'<a [^>]*target="_blank"[^>]*>', _html()):
        assert 'rel="noopener noreferrer"' in m.group(0)


def test_generated_data_is_clean():
    import json
    data = json.loads((DOCS / "events.json").read_text(encoding="utf-8"))["events"]
    for e in data:
        assert safe_url(e["url"]), e["id"]
        assert "<" not in e["title"] and "<" not in e["location"]
    for w in json.loads((DOCS / "watchlist.json").read_text(encoding="utf-8")):
        assert safe_url(w["url"]), w["title"]
