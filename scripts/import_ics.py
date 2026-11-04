"""One-off/occasional: import an existing .ics into data/events.yaml format (stdout)."""
from __future__ import annotations

import datetime as dt
import sys

import yaml
from icalendar import Calendar

from common import categorise, region_for, relevance_for, slugify


def parse(path: str) -> list[dict]:
    cal = Calendar.from_ical(open(path, "rb").read())
    out = []
    for comp in cal.walk("VEVENT"):
        title = str(comp.get("SUMMARY"))
        start = comp.decoded("DTSTART")
        end = comp.decoded("DTEND") - dt.timedelta(days=1)  # back to inclusive
        loc = str(comp.get("LOCATION", ""))
        desc = str(comp.get("DESCRIPTION", ""))
        en = de = ""
        for block in desc.split("\n\n"):
            if block.startswith("EN: "):
                en = block[4:].strip()
            elif block.startswith("DE: "):
                de = block[4:].strip()
        country = None
        if loc.lower() != "online":
            tail = loc.split(",")[-1].strip().split(" ")[0]
            country = tail if len(tail) == 2 and tail.isupper() else None
        cats = categorise(f"{title} {en}")
        out.append({
            "id": f"{slugify(title)}-{start.year}",
            "uid": str(comp.get("UID")),
            "title": title,
            "start": start,
            "end": end,
            "location": loc,
            "country": country,
            "region": region_for(country),
            "url": str(comp.get("URL")),
            "categories": cats,
            "relevance": relevance_for(cats, f"{title} {en} {de}"),
            "status": "confirmed",
            "source": "EU_IT_Event_Crawl_v5.ics",
            "description_en": en,
            "description_de": de,
        })
    return out


if __name__ == "__main__":
    yaml.safe_dump(parse(sys.argv[1]), sys.stdout, allow_unicode=True, sort_keys=False, width=200)
