"""Event crawler.

For every source in data/sources.yaml (+ every URL in data/watchlist.yaml):
  1. fetch the page (robots.txt respected, polite delay),
  2. extract events from iCalendar feeds or schema.org/JSON-LD markup,
  3. otherwise - if ANTHROPIC_API_KEY is set - let Claude extract events from the page text,
  4. filter by date window and topic relevance,
  5. de-duplicate against data/events.yaml (fuzzy title match + year),
  6. append new events / update changed dates in data/events.yaml,
  7. write data/crawl_report.md (used as the pull-request body for human review).

Nothing is published without review: the GitHub workflow opens a pull request with the diff.
"""
from __future__ import annotations

import datetime as dt
import difflib
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx
import yaml

from common import DATA, categorise, load_events, region_for, relevance_for, slugify

USER_AGENT = "PGC-ITSM-Event-Calendar-Bot/1.0 (+https://github.com/joropa-pgk/itsm-calendar-via-claude-)"
TODAY = dt.date.today()
HORIZON = dt.date(TODAY.year + 2, 12, 31)
MAX_TEXT_CHARS = 120_000           # page text sent to Claude (logged when exceeded)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
DELAY_S = 2.0
EVENT_TYPES = {"Event", "BusinessEvent", "EducationEvent", "ExhibitionEvent", "SocialEvent",
               "Festival", "CourseInstance", "EventSeries"}

log: list[str] = []


def note(msg: str) -> None:
    print(msg)
    log.append(msg)


# --------------------------------------------------------------------------- fetching

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def allowed(client: httpx.Client, url: str) -> bool:
    base = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = client.get(base + "/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[base] = rp
        except httpx.HTTPError:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def fetch(client: httpx.Client, url: str) -> httpx.Response | None:
    if not allowed(client, url):
        note(f"  robots.txt verbietet Abruf: {url}")
        return None
    try:
        r = client.get(url)
        time.sleep(DELAY_S)
        if r.status_code != 200:
            note(f"  HTTP {r.status_code}: {url}")
            return None
        return r
    except httpx.HTTPError as exc:
        note(f"  Fehler {type(exc).__name__}: {url}")
        return None


# --------------------------------------------------------------------------- extraction

def parse_date(value) -> dt.date | None:
    if not value:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    return dt.date(*map(int, m.groups())) if m else None


def from_ics(text: str, source_url: str) -> list[dict]:
    from icalendar import Calendar
    out = []
    for comp in Calendar.from_ical(text).walk("VEVENT"):
        start = comp.decoded("DTSTART")
        end = comp.decoded("DTEND") if comp.get("DTEND") else start
        if isinstance(start, dt.datetime):
            start, end = start.date(), end.date()
        elif end != start:
            end = end - dt.timedelta(days=1)
        out.append({"title": str(comp.get("SUMMARY", "")).strip(), "start": start, "end": end,
                    "location": str(comp.get("LOCATION", "")), "url": str(comp.get("URL", source_url)),
                    "description_en": str(comp.get("DESCRIPTION", ""))[:300], "_how": "ics"})
    return out


def _walk_jsonld(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk_jsonld(n)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = set(types) if isinstance(types, list) else {types}
        if types & EVENT_TYPES:
            yield node
        for key in ("@graph", "subEvent", "itemListElement", "item", "event", "events"):
            if key in node:
                yield from _walk_jsonld(node[key])


def from_jsonld(page: str, source_url: str) -> list[dict]:
    out = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for ev in _walk_jsonld(data):
            start = parse_date(ev.get("startDate"))
            if not start:
                continue
            loc = ev.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            if isinstance(loc, dict):
                addr = loc.get("address") or {}
                if isinstance(addr, dict):
                    city = addr.get("addressLocality", "")
                    cc = addr.get("addressCountry", "")
                    cc = cc.get("name", "") if isinstance(cc, dict) else cc
                    loc_str = ", ".join(x for x in (city, cc) if x) or loc.get("name", "")
                else:
                    loc_str = str(addr) or loc.get("name", "")
                if loc.get("@type") == "VirtualLocation":
                    loc_str = "Online"
            else:
                loc_str = str(loc)
            out.append({"title": htmllib.unescape(str(ev.get("name", ""))).strip(),
                        "start": start, "end": parse_date(ev.get("endDate")) or start,
                        "location": loc_str, "url": urljoin(source_url, str(ev.get("url") or source_url)),
                        "description_en": htmllib.unescape(str(ev.get("description", "")))[:300],
                        "_how": "json-ld"})
    return out


def page_text(page: str) -> str:
    page = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>", r" [link: \1] ", page, flags=re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", page))
    return re.sub(r"\s+", " ", text).strip()


def from_claude(text: str, source_url: str) -> list[dict]:
    """KI-Extraktion mit strukturierter Ausgabe (Pydantic-Schema)."""
    import anthropic
    from pydantic import BaseModel

    class ExtractedEvent(BaseModel):
        title: str
        start_date: str           # YYYY-MM-DD
        end_date: str             # YYYY-MM-DD (= start_date for one-day events)
        city: str                 # "" if online
        country_code: str         # ISO-3166 alpha-2, "UK" for United Kingdom, "" if online
        is_online: bool
        url: str                  # most specific event URL found on the page
        description_en: str       # one sentence
        description_de: str       # one sentence
        relevant: bool            # IT / ITSM / ESM / AI / cloud / security / digital transformation

    class Extraction(BaseModel):
        events: list[ExtractedEvent]

    if len(text) > MAX_TEXT_CHARS:
        note(f"  Hinweis: Seitentext gekürzt ({len(text)} > {MAX_TEXT_CHARS} Zeichen): {source_url}")
        text = text[:MAX_TEXT_CHARS]

    client = anthropic.Anthropic()
    prompt = (
        f"Today is {TODAY.isoformat()}. Below is the text of the web page {source_url}.\n"
        "Extract every event (conference, summit, congress, trade fair, forum, meetup, user group, "
        "festival, webinar) that is listed on this page with an explicit calendar date and that takes "
        f"place between {TODAY.isoformat()} and {HORIZON.isoformat()}. "
        "Only use information that is present on the page - never guess dates. Skip events whose date is "
        "given only as a month or 'TBA'. Skip training courses and job postings. "
        "Resolve relative links against the page URL. Mark relevant=true only for events about IT, "
        "IT service management (ITSM/ESM/ITIL/ServiceNow etc.), AI, cloud, cybersecurity, data or "
        "digital transformation.\n\n<page>\n" + text + "\n</page>"
    )
    try:
        resp = client.beta.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
            output_format=Extraction,
        )
    except anthropic.APIError as exc:
        note(f"  Claude-Fehler ({type(exc).__name__}): {source_url}")
        return []
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        note(f"  Claude: keine verwertbare Antwort ({resp.stop_reason}): {source_url}")
        return []

    out = []
    for e in resp.parsed_output.events:
        start, end = parse_date(e.start_date), parse_date(e.end_date)
        if not start or not e.relevant:
            continue
        loc = "Online" if e.is_online else ", ".join(x for x in (e.city, e.country_code.upper()) if x)
        out.append({"title": e.title.strip(), "start": start, "end": end or start, "location": loc,
                    "url": urljoin(source_url, e.url or source_url),
                    "description_en": e.description_en, "description_de": e.description_de,
                    "_how": "claude"})
    return out


# --------------------------------------------------------------------------- matching

def norm_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\b(19|20)\d{2}\b|\b\d{2}\b", " ", t)          # years like 2027 / '27
    t = re.sub(r"(?<=[a-z])\d{2,4}\b", " ", t)                    # SERVIEW26, ITSM27
    t = re.sub(r"[^a-z0-9äöüß]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def find_match(cand: dict, events: list[dict]) -> dict | None:
    nt = norm_title(cand["title"])
    best, best_score = None, 0.0
    for ev in events:
        if abs(dt.date.fromisoformat(str(ev["start"])).year - cand["start"].year) > 0:
            continue
        score = difflib.SequenceMatcher(None, nt, norm_title(ev["title"])).ratio()
        if score > best_score:
            best, best_score = ev, score
    return best if best_score >= 0.82 else None


def country_from(location: str) -> str | None:
    tail = location.split(",")[-1].strip()
    if re.fullmatch(r"[A-Z]{2}", tail):
        return "UK" if tail == "GB" else tail
    names = {"germany": "DE", "deutschland": "DE", "austria": "AT", "österreich": "AT",
             "switzerland": "CH", "schweiz": "CH", "united kingdom": "UK", "netherlands": "NL"}
    return names.get(tail.lower())


# --------------------------------------------------------------------------- main

def main() -> int:
    sources = yaml.safe_load((DATA / "sources.yaml").read_text(encoding="utf-8")) or []
    watch = yaml.safe_load((DATA / "watchlist.yaml").read_text(encoding="utf-8")) or []
    sources += [{"name": f"Watchlist: {w['title']}", "url": w["url"]} for w in watch]
    use_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
    note(f"Crawl {TODAY.isoformat()} | {len(sources)} Quellen | KI-Extraktion: {'an' if use_claude else 'aus'}")

    events = load_events()
    added, changed = [], []
    seen_urls: set[str] = set()

    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"},
                      timeout=30, follow_redirects=True) as client:
        for src in sources:
            if src["url"] in seen_urls:
                continue
            seen_urls.add(src["url"])
            note(f"- {src['name']}")
            r = fetch(client, src["url"])
            if r is None:
                continue
            ctype = r.headers.get("content-type", "")
            if src.get("type") == "ics" or "text/calendar" in ctype:
                cands = from_ics(r.text, src["url"])
            else:
                cands = from_jsonld(r.text, src["url"])
                if not cands and use_claude:
                    cands = from_claude(page_text(r.text), src["url"])
            note(f"  {len(cands)} Kandidaten")

            for c in cands:
                if not c["title"] or not (TODAY <= c["start"] <= HORIZON):
                    continue
                cats = categorise(f"{c['title']} {c.get('description_en', '')}")
                if src.get("focus") and not set(cats) & set(src["focus"]):
                    continue
                rel = relevance_for(cats, f"{c['title']} {c.get('description_en', '')}")
                if rel == "peripheral" and c["_how"] != "claude":
                    continue
                hit = find_match(c, events)
                if hit:
                    old = (str(hit["start"]), str(hit.get("end")))
                    new = (c["start"].isoformat(), c["end"].isoformat())
                    if old != new and hit.get("status") == "tentative":
                        hit["note"] = f"Datum durch Crawler aktualisiert (alt: {old[0]}–{old[1]}, Quelle: {src['name']})"
                        hit["start"], hit["end"], hit["status"] = c["start"], c["end"], "confirmed"
                        changed.append(f"{hit['title']}: {old[0]}–{old[1]} → {new[0]}–{new[1]}")
                    elif old != new:
                        changed.append(f"PRÜFEN (nicht automatisch geändert, bestätigtes Event): "
                                       f"{hit['title']} – Quelle {src['name']} meldet {new[0]}–{new[1]}")
                    continue
                country = country_from(c["location"])
                ev = {
                    "id": f"{slugify(c['title'])}-{c['start'].year}",
                    "title": c["title"], "start": c["start"], "end": c["end"],
                    "location": c["location"], "country": country, "region": region_for(country),
                    "url": c["url"], "categories": cats, "relevance": rel,
                    "status": "confirmed" if c["_how"] in ("json-ld", "ics") else "tentative",
                    "source": f"crawler:{src['name']} ({c['_how']}, {TODAY.isoformat()})",
                    "description_en": c.get("description_en", ""), "description_de": c.get("description_de", ""),
                }
                if any(e["id"] == ev["id"] for e in events):
                    continue
                events.append(ev)
                added.append(f"{ev['start']} | {ev['title']} | {ev['location']} | {ev['url']}")

    events.sort(key=lambda e: (str(e["start"]), e["title"]))
    header = ("# Kuratierte Event-Liste (Single Source of Truth).\n"
              "# Datumsangaben inklusiv (end = letzter Veranstaltungstag). status: confirmed | tentative\n"
              "# relevance: core (ITSM/ESM) | related (KI, Cloud, Security, Digital) | peripheral\n")
    (DATA / "events.yaml").write_text(
        header + yaml.safe_dump(events, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")

    report = [f"# Crawl-Report {TODAY.isoformat()}", "",
              f"**Neu:** {len(added)} | **Änderungen/Prüfhinweise:** {len(changed)}", "",
              "## Neue Events (bitte prüfen)", *([f"- {a}" for a in added] or ["- keine"]), "",
              "## Geänderte Termine", *([f"- {c}" for c in changed] or ["- keine"]), "",
              "<details><summary>Protokoll</summary>", "", "```", *log, "```", "</details>"]
    (DATA / "crawl_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"\nNeu: {len(added)} | Änderungen: {len(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
