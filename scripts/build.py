"""Build ICS feeds + JSON for the website from data/events.yaml.

Outputs (docs/ is served via GitHub Pages):
  docs/events.ics        all events
  docs/events-itsm.ics   relevance == core (ITSM/ESM)
  docs/events-dach.ics   region == DACH
  docs/events.json       data for the calendar website
  docs/watchlist.json    announced-but-undated events
  docs/events.xlsx       Excel export (all events + watchlist)
"""
from __future__ import annotations

import datetime as dt
import json

import yaml

from export_xlsx import write_xlsx
from common import DATA, DOCS, as_date, categorise, infer_format, load_events, region_for, relevance_for, to_ics, uid_for

REQUIRED = ("id", "title", "start", "url")


def validate(events: list[dict]) -> list[dict]:
    seen, out = set(), []
    for ev in events:
        missing = [k for k in REQUIRED if not ev.get(k)]
        if missing:
            raise ValueError(f"Event {ev.get('title')!r} fehlt: {missing}")
        if ev["id"] in seen:
            raise ValueError(f"Doppelte id: {ev['id']}")
        seen.add(ev["id"])
        if as_date(ev.get("end") or ev["start"]) < as_date(ev["start"]):
            raise ValueError(f"end < start: {ev['id']}")
        ev.setdefault("categories", categorise(ev["title"] + " " + ev.get("description_en", "")))
        ev.setdefault("region", region_for(ev.get("country")))
        ev.setdefault("relevance", relevance_for(ev["categories"], ev["title"]))
        ev.setdefault("status", "confirmed")
        ev.setdefault("format", infer_format(ev["title"], ev.get("description_en", "")))
        out.append(ev)
    return out


def translate_expected(text: str) -> str:
    """German month/term wording of watchlist dates -> English."""
    repl = {"vorauss.": "expected", "offen": "TBA", "Januar": "January", "Februar": "February", "März": "March",
            "Mai": "May", "Juni": "June", "Juli": "July", "Okt": "Oct", "Dez": "Dec", "eine Quelle nennt": "one source says",
            "Herbst": "Autumn"}
    for de, en in repl.items():
        text = text.replace(de, en)
    return text


def write_markdown(events: list[dict]) -> None:
    """Human-readable overview (EVENTS.md) grouped by year and month."""
    months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
              "September", "Oktober", "November", "Dezember"]
    rel = {"core": "ITSM", "related": "verwandt", "peripheral": "Rand"}
    lines = ["# Event-Übersicht", "",
             "Automatisch erzeugt aus `data/events.yaml` – nicht manuell bearbeiten.", "",
             "Legende Relevanz: **ITSM** = Kernthema, verwandt = KI/Cloud/Security/Digital, Rand = Randthema; "
             "(TBC) = Termin vorläufig.", ""]
    cur = None
    for e in sorted(events, key=lambda x: (as_date(x["start"]), x["title"])):
        s, en = as_date(e["start"]), as_date(e.get("end") or e["start"])
        key = (s.year, s.month)
        if key != cur:
            if cur is None or cur[0] != s.year:
                lines += ["", f"## {s.year}"]
            lines += ["", f"### {months[s.month - 1]} {s.year}", "",
                      "| Datum | Veranstaltung | Ort | Relevanz |", "|---|---|---|---|"]
            cur = key
        date = f"{s:%d.%m.}" if s == en else f"{s:%d.%m.}–{en:%d.%m.}"
        title = e["title"].replace("|", "/") + (" (TBC)" if e.get("status") == "tentative" else "")
        lines.append(f"| {date}{s.year} | [{title}]({e['url']}) | {e.get('location', '')} | {rel[e['relevance']]} |")
    (DATA.parent / "EVENTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    events = validate(load_events())
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    DOCS.mkdir(exist_ok=True)

    feeds = {
        "events.ics": ("PGC – IT/ITSM/AI Events", events),
        "events-itsm.ics": ("PGC – ITSM/ESM Events", [e for e in events if e["relevance"] == "core"]),
        "events-dach.ics": ("PGC – IT-Events DACH", [e for e in events if e["region"] == "DACH"]),
    }
    for fname, (name, evs) in feeds.items():
        (DOCS / fname).write_text(to_ics(evs, name, stamp), encoding="utf-8", newline="")
        print(f"{fname}: {len(evs)} Events")

    payload = []
    for e in events:
        payload.append({
            "id": e["id"], "uid": uid_for(e), "title": e["title"],
            "start": str(as_date(e["start"])), "end": str(as_date(e.get("end") or e["start"])),
            "location": e.get("location", ""), "country": e.get("country"), "region": e["region"],
            "url": e["url"], "categories": e["categories"], "relevance": e["relevance"],
            "status": e["status"], "format": e["format"], "note": e.get("note", ""),
            "description_en": e.get("description_en", ""), "description_de": e.get("description_de", ""),
        })
    (DOCS / "events.json").write_text(
        json.dumps({"generated": stamp.isoformat(), "events": payload}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    write_markdown(events)
    watch = yaml.safe_load((DATA / "watchlist.yaml").read_text(encoding="utf-8")) or []
    for w in watch:
        w.setdefault("expected_en", translate_expected(str(w.get("expected", ""))))
    (DOCS / "watchlist.json").write_text(json.dumps(watch, ensure_ascii=False, indent=1), encoding="utf-8")
    write_xlsx(events, watch, DOCS / "events.xlsx", stamp)
    print(f"events.json: {len(payload)} | watchlist.json: {len(watch)}")


if __name__ == "__main__":
    main()
