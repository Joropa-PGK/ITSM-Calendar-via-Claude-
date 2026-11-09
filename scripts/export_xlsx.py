"""Excel export of all events (docs/events.xlsx). Called from build.py."""
from __future__ import annotations

import datetime as dt

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from common import as_date, excel_safe, safe_url

NAVY, CYAN, LIGHT, CREAM = "0A3658", "1AB7EA", "D1F1FB", "FDF3D4"
FONT = "Calibri"
REL = {"core": "ITSM (Kern)", "related": "Verwandt", "peripheral": "Randthema"}
CAT = {"ITSM": "ITSM/ESM", "AI": "KI", "Cloud": "Cloud", "Security": "Security",
       "Digital Transformation": "Digitale Transformation", "Developer": "Developer"}
STATUS = {"confirmed": "Bestätigt", "tentative": "Vorläufig (TBC)"}
FORMAT = {"conference": "Konferenz/Kongress", "tradefair": "Messe", "forum": "Forum/Treffen", "workshop": "Workshop",
          "meetup": "Meetup/User Group", "webinar": "Webinar/Online", "training": "Training"}
REGION = {"DACH": "DACH", "Europe": "Europa", "International": "International", "Online": "Online"}

HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
THIN = Border(bottom=Side(style="thin", color="DBE4EA"))
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")


def _header(ws, columns: list[tuple[str, int]]) -> None:
    for i, (name, width) in enumerate(columns, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font, c.fill = HEAD_FONT, HEAD_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def write_xlsx(events: list[dict], watch: list[dict], path, stamp: dt.datetime) -> None:
    wb = Workbook()

    # --- Sheet 1: Events -------------------------------------------------------
    ws = wb.active
    ws.title = "Events"
    cols = [("Start", 12), ("Ende", 12), ("Tage", 6), ("Veranstaltung", 42), ("Ort", 30), ("Land", 7),
            ("Region", 12), ("Relevanz", 13), ("Themen", 28), ("Format", 18), ("Status", 15), ("Website", 40),
            ("Beschreibung (DE)", 60), ("Description (EN)", 60), ("Hinweis", 35), ("Quelle", 26)]
    _header(ws, cols)
    rows = sorted(events, key=lambda e: (as_date(e["start"]), e["title"]))
    for r, e in enumerate(rows, 2):
        s, en = as_date(e["start"]), as_date(e.get("end") or e["start"])
        vals = [s, en, None, e["title"], e.get("location", ""), e.get("country") or "",
                REGION.get(e["region"], e["region"]), REL[e["relevance"]],
                ", ".join(CAT.get(c, c) for c in e["categories"]), FORMAT.get(e.get("format", ""), ""),
                STATUS[e["status"]], e["url"],
                e.get("description_de", ""), e.get("description_en", ""), e.get("note", ""), e.get("source", "")]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=excel_safe(v))
            if isinstance(v, str):
                cell.data_type = "s"  # never let data become a formula (formula injection)
            cell.font = Font(name=FONT)
            cell.alignment = WRAP if c in (4, 5, 9, 13, 14, 15) else TOP
            cell.border = THIN
        ws.cell(row=r, column=3, value=f"=B{r}-A{r}+1")
        for c in (1, 2):
            ws.cell(row=r, column=c).number_format = "DD.MM.YYYY"
        link = ws.cell(row=r, column=12)
        if safe_url(e["url"]):
            link.hyperlink = e["url"]
        link.font = Font(name=FONT, color="0563C1", underline="single")
        if e["relevance"] == "core":
            ws.cell(row=r, column=4).font = Font(name=FONT, bold=True)
            ws.cell(row=r, column=8).fill = PatternFill("solid", fgColor=LIGHT)
        if e["status"] == "tentative":
            ws.cell(row=r, column=11).fill = PatternFill("solid", fgColor=CREAM)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"

    # --- Sheet 2: Beobachtungsliste -------------------------------------------
    wl = wb.create_sheet("Beobachtungsliste")
    _header(wl, [("Veranstaltung", 50), ("Erwarteter Termin", 24), ("Ort", 40), ("Themen", 26), ("Website", 45)])
    for r, w in enumerate(watch, 2):
        vals = [w["title"], w.get("expected", ""), w.get("location", ""),
                ", ".join(CAT.get(c, c) for c in w.get("categories", [])), w["url"]]
        for c, v in enumerate(vals, 1):
            cell = wl.cell(row=r, column=c, value=excel_safe(v))
            if isinstance(v, str):
                cell.data_type = "s"
            cell.font, cell.alignment, cell.border = Font(name=FONT), WRAP, THIN
        if safe_url(w["url"]):
            wl.cell(row=r, column=5).hyperlink = w["url"]
        wl.cell(row=r, column=5).font = Font(name=FONT, color="0563C1", underline="single")
    wl.auto_filter.ref = f"A1:E{len(watch) + 1}"

    # --- Sheet 3: Übersicht (live formulas) -----------------------------------
    ov = wb.create_sheet("Übersicht")
    ov.column_dimensions["A"].width = 34
    ov.column_dimensions["B"].width = 14
    ov["A1"] = "IT & ITSM Event-Kalender – Übersicht"
    ov["A1"].font = Font(name=FONT, bold=True, size=14, color=NAVY)
    ov["A2"] = f"Stand: {stamp:%d.%m.%Y %H:%M} UTC · Quelle: data/events.yaml"
    ov["A2"].font = Font(name=FONT, italic=True, color="5B6B78")
    n = len(rows) + 1
    stats = [
        ("Events gesamt", f"=COUNTA(Events!D2:D{n})"),
        ("ITSM-Kernevents", f'=COUNTIF(Events!H2:H{n},"ITSM (Kern)")'),
        ("DACH", f'=COUNTIF(Events!G2:G{n},"DACH")'),
        ("Termin vorläufig (TBC)", f'=COUNTIF(Events!K2:K{n},"Vorläufig (TBC)")'),
        ("Events 2026", f'=SUMPRODUCT((YEAR(Events!A2:A{n})=2026)*1)'),
        ("Events 2027", f'=SUMPRODUCT((YEAR(Events!A2:A{n})=2027)*1)'),
        ("Kommende Events (ab heute)", f'=COUNTIF(Events!B2:B{n},">="&TODAY())'),
        ("Beobachtungsliste (ohne Datum)", f"=COUNTA(Beobachtungsliste!A2:A{len(watch) + 1})"),
    ]
    for i, (label, formula) in enumerate(stats, 4):
        ov.cell(row=i, column=1, value=label).font = Font(name=FONT)
        c = ov.cell(row=i, column=2, value=formula)
        c.font = Font(name=FONT, bold=True, color=NAVY)
    legend_row = 4 + len(stats) + 1
    ov.cell(row=legend_row, column=1, value="Legende").font = Font(name=FONT, bold=True)
    ov.cell(row=legend_row + 1, column=1, value="Relevanz hellblau = ITSM-Kernthema").fill = PatternFill("solid", fgColor=LIGHT)
    ov.cell(row=legend_row + 2, column=1, value="Status cremefarben = Termin vorläufig").fill = PatternFill("solid", fgColor=CREAM)
    ov.cell(row=legend_row + 3, column=1,
            value="Angaben ohne Gewähr – Termine vor Reiseplanung beim Veranstalter prüfen.").font = Font(name=FONT, italic=True, color="5B6B78")

    wb.move_sheet("Übersicht", offset=-2)
    wb.active = 1
    wb.save(path)
