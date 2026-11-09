"""Shared helpers: event model, categorisation, ICS serialisation."""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

DACH = {"DE", "AT", "CH"}


# --------------------------------------------------------------------------- security
# All event data may originate from untrusted third-party websites (crawler, AI extraction).
# Every field is normalised here before it reaches ICS, Excel, JSON or the website.

MAX_LEN = {"title": 200, "location": 200, "description_en": 1000, "description_de": 1000,
           "note": 500, "source": 300, "expected": 100, "expected_en": 100}
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")                       # C0/C1 control chars incl. CR/LF/TAB
_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")  # bidi overrides / zero-width
_TAGS = re.compile(r"<[^>]{0,500}>")                                   # HTML/XML tags
_URL_OK = re.compile(r"^https://[^\s<>\"'`]+$|^http://[^\s<>\"'`]+$", re.I)


class UnsafeDataError(ValueError):
    """Raised when event data fails security validation (fail closed)."""


def clean_text(value, max_len: int = 1000) -> str:
    """Remove control/bidi characters and HTML tags, collapse whitespace, cap length."""
    if value is None:
        return ""
    text = _CTRL.sub(" ", str(value))
    text = _BIDI.sub("", text)
    text = _TAGS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def safe_url(value) -> str | None:
    """Return the URL only if it is an absolute http(s) URL with a host and no dangerous characters."""
    from urllib.parse import urlsplit
    if not value:
        return None
    url = str(value).strip()
    if _CTRL.search(url) or _BIDI.search(url) or len(url) > 2000 or not _URL_OK.match(url):
        return None
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return None
    return url


def sanitize_event(ev: dict) -> dict:
    """Normalise all free-text fields of an event and enforce a safe URL (raises UnsafeDataError)."""
    out = dict(ev)
    for key, limit in MAX_LEN.items():
        if key in out and out[key] is not None:
            out[key] = clean_text(out[key], limit)
    url = safe_url(out.get("url"))
    if not url:
        raise UnsafeDataError(f"Unsichere oder ungültige URL bei {out.get('id') or out.get('title')!r}: {str(out.get('url'))[:80]!r}")
    out["url"] = url
    if out.get("id") and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", str(out["id"])):
        raise UnsafeDataError(f"Ungültige id: {str(out['id'])[:80]!r}")
    if out.get("country") and not re.fullmatch(r"[A-Z]{2,3}", str(out["country"])):
        out["country"] = None
    if "categories" in out:
        out["categories"] = [clean_text(c, 40) for c in (out.get("categories") or [])][:8]
    return out


EXCEL_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r", "\uff1d", "\uff0b", "\uff0d", "\uff20")


def excel_safe(value):
    """Neutralise spreadsheet formula injection (OWASP CSV/Formula Injection)."""
    if isinstance(value, str) and value.startswith(EXCEL_FORMULA_PREFIX):
        return "'" + value
    return value

# Keyword-based categorisation (lower-case, matched on title + description).
CATEGORY_RULES: dict[str, list[str]] = {
    "ITSM": [
        "itsm", " esm", "service management", "service desk", "servicedesk", "itsmf",
        "servicenow", "serview", "service space", "it support", "afsmi", "itil",
        "freshservice", "jira service", "service-management", "serviceware", "usu ",
        "manageengine", "smfs",
    ],
    "AI": [" ai ", " ai,", " ai/", " ai-", "(ai", "/ai", " ki ", " ki,", " ki-", "-ki", "ki/", "machine learning", "ml ",
           "mlops", "generative", "artificial intelligence", "künstliche intelligenz", "copilot"],
    "Cloud": ["cloud", "kubernetes", "devops", "container", "platform engineering", "finops",
              "data centre", "data center", "infrastructure"],
    "Security": ["security", "cyber", "sicherheit", "infosec", "it-sa", "defense", "grc"],
    "Digital Transformation": ["digital", "transformation", "cio", "it-strategie", "it strategy",
                               "e-government", "verwaltung", "egov", "smart country"],
    "Developer": ["developer", "entwickler", "java", "spring", "open source", "open-source",
                  "software architect", "fosdem", "froscon", "javaland", "w-jax"],
}

PERIPHERAL_HINTS = ["gaming", "gamescom", "broadcast", "marketing", "startup", "venture",
                    "industrietechnologie", "industrial technology", "railway", "eisenbahn"]


def categorise(text: str) -> list[str]:
    t = f" {text.lower()} "
    cats = [c for c, kws in CATEGORY_RULES.items() if any(k in t for k in kws)]
    return cats or ["Digital Transformation"]


def relevance_for(categories: list[str], text: str) -> str:
    """core = ITSM; related = AI/Cloud/Security/Digital; peripheral = rest."""
    if "ITSM" in categories:
        return "core"
    t = text.lower()
    if any(h in t for h in PERIPHERAL_HINTS):
        return "peripheral"
    if set(categories) & {"AI", "Cloud", "Security", "Digital Transformation"}:
        return "related"
    return "peripheral"


def region_for(country: str | None) -> str:
    if not country:
        return "Online"
    if country in DACH:
        return "DACH"
    if country == "INT":
        return "International"
    return "Europe"


def slugify(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60]


def load_events() -> list[dict]:
    with open(DATA / "events.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def as_date(value) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def uid_for(ev: dict) -> str:
    if ev.get("uid"):
        return ev["uid"]
    return f"{ev['id']}@itsm-calendar.paan-group.com"


# --------------------------------------------------------------------------- ICS

def _escape(text: str) -> str:
    """RFC 5545 TEXT escaping; bare CR and other control chars are removed (no property injection)."""
    text = _CTRL.sub(lambda m: "\n" if m.group() == "\n" else "", str(text).replace("\r\n", "\n"))
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets (UTF-8 safe)."""
    out, buf, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            out.append(buf)
            buf, size = " " + ch, 1 + n
        else:
            buf += ch
            size += n
    out.append(buf)
    return "\r\n".join(out)


def description_for(ev: dict) -> str:
    parts = [f"URL: {ev['url']}"]
    if ev.get("status") == "tentative":
        parts.append("STATUS: Termin noch nicht final bestätigt / date not yet confirmed")
    if ev.get("description_en"):
        parts.append(f"EN: {ev['description_en']}")
    if ev.get("description_de"):
        parts.append(f"DE: {ev['description_de']}")
    cats = ", ".join(ev.get("categories", []))
    parts.append(f"Kategorie/Category: {cats} | Region: {ev.get('region', '')}")
    return "\n\n".join(parts)


def to_ics(events: list[dict], name: str, stamp: dt.datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//PAAN-Group Consulting//ITSM Event Calendar//DE",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    dtstamp = stamp.strftime("%Y%m%dT%H%M%SZ")
    for ev in sorted(events, key=lambda e: (as_date(e["start"]), e["title"])):
        start = as_date(ev["start"])
        end = as_date(ev.get("end") or ev["start"]) + dt.timedelta(days=1)  # DTEND exclusive
        summary = ev["title"] + (" [TBC]" if ev.get("status") == "tentative" else "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(ev)}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{_escape(summary)}",
            f"URL:{safe_url(ev['url']) or ''}",
            f"DESCRIPTION:{_escape(description_for(ev))}",
            f"LOCATION:{_escape(ev.get('location', ''))}",
            f"CATEGORIES:{','.join(_escape(c) for c in ev.get('categories', []))}",
            "STATUS:" + ("TENTATIVE" if ev.get("status") == "tentative" else "CONFIRMED"),
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def content_hash(ev: dict) -> str:
    key = f"{ev['title']}|{ev['start']}|{ev.get('end')}|{ev.get('location')}|{ev['url']}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]


# --------------------------------------------------------------------------- format

FORMAT_RULES: list[tuple[str, list[str]]] = [
    ("webinar", ["webinar", "online-session", "virtual event", "livestream"]),
    ("workshop", ["workshop", "hands-on", "jam ", "bootcamp", "hackathon"]),
    ("training", ["training", "schulung", "seminar", "zertifizierung", "certification", "foundation"]),
    ("meetup", ["meetup", "user group", "usergroup", "snug", "community day", "stammtisch", "community-"]),
    ("tradefair", ["messe", "expo", "trade fair", "trade show", "fachmesse", " show", "it-sa", "cloudfest",
                   "hannover messe", "dmexco", "gamescom", "learntec", "ccw", "omr"]),
    ("forum", ["forum", "roundtable", "dinner", "gathering", "branchentreff", "anwendertreffen", "circle"]),
    ("conference", ["konferenz", "conference", "kongress", "congress", "summit", "gipfel", "tage", "days",
                    "convention", "festival", "world", "week", "con "]),
]


def infer_format(title: str, description: str = "") -> str:
    t = f" {title.lower()} "
    for fmt, kws in FORMAT_RULES:
        if any(k in t for k in kws):
            return fmt
    d = f" {description.lower()} "
    for fmt, kws in FORMAT_RULES:
        if fmt in ("webinar", "tradefair", "meetup") and any(k in d for k in kws):
            return fmt
    return "conference"
