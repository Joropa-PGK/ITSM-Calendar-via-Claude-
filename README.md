# IT & ITSM Event-Kalender (PAAN-Group Consulting)

Kuratierter, automatisch aktualisierter Kalender für **ITSM/ESM-, KI-, Cloud-, Security- und Digital-Transformation-Veranstaltungen**. Der Schwerpunkt liegt auf der DACH-Region, ergänzt um relevante Events aus Europa und einige internationale Flaggschiff-Events.

| Ergebnis | Datei |
|---|---|
| Kalender-Website (GitHub Pages) | `docs/index.html` |
| ICS-Feed, alle Events | `docs/events.ics` |
| ICS-Feed, nur ITSM/ESM | `docs/events-itsm.ics` |
| ICS-Feed, nur DACH | `docs/events-dach.ics` |
| Tabellarische Übersicht | `EVENTS.md` |
| Excel-Liste (Events, Beobachtungsliste, Kennzahlen) | `docs/events.xlsx` |
| Datenbasis (Single Source of Truth) | `data/events.yaml` |
| Events ohne bestätigten Termin | `data/watchlist.yaml` |
| Crawler-Quellen | `data/sources.yaml` |

## Architektur

```
data/sources.yaml ─┐
data/watchlist.yaml┴─► scripts/crawl.py ──► data/events.yaml ──► scripts/build.py ──► docs/*.ics, events.json, EVENTS.md
                       (JSON-LD / ICS /       (kuratiert,           (Validierung,          │
                        KI-Extraktion)         Review per PR)        Feeds, Website-Daten)  ▼
                                                                                    GitHub Pages ──► Google Kalender (Abo)
```

**Governance:** Der Crawler veröffentlicht nichts selbst. Er öffnet wöchentlich einen **Pull Request** mit allen neuen und geänderten Events plus einem Crawl-Report. Erst wenn Sie den PR mergen, landen die Änderungen im Kalender. Bestätigte Termine überschreibt er nie automatisch, sondern meldet Abweichungen nur als Prüfhinweis.

Pro Quelle läuft die Extraktion in drei Stufen:
1. **iCalendar-Feeds** werden direkt gelesen.
2. **schema.org/JSON-LD-Events** werden strukturiert aus dem HTML gelesen.
3. **KI-Extraktion** mit dem Claude API und strukturierter Ausgabe: nur wenn Stufe 1 und 2 nichts liefern und das Secret `ANTHROPIC_API_KEY` gesetzt ist. Events aus dieser Stufe werden als `tentative` markiert, bis Sie sie freigeben. Serverseitige Refusal-Fallbacks sind aktiviert (`fallbacks: "default"`).

## Einrichtung (einmalig)

1. **Branch mergen:** Den Branch `claude/event-calendar-web-crawler-eajf14` nach `main` mergen.
2. **GitHub Pages aktivieren:** Settings → Pages → Source „Deploy from a branch“ → `main` / `/docs`.
3. **Optional, KI-Extraktion:** Settings → Secrets and variables → Actions → `ANTHROPIC_API_KEY` anlegen. Das Modell ist per Umgebungsvariable `CLAUDE_MODEL` überschreibbar.
4. **Actions-Berechtigung:** Settings → Actions → General → „Allow GitHub Actions to create and approve pull requests“ aktivieren.
5. **Google Kalender abonnieren:** Auf der Website „In Google Kalender abonnieren“ klicken, oder in Google Kalender „Weitere Kalender → Per URL“ wählen und die Feed-URL `https://<user>.github.io/<repo>/events.ics` eintragen.
   *Hinweis:* Google aktualisiert abonnierte Kalender nur alle 12–24 Stunden.

> **Sichtbarkeit:** GitHub Pages ist öffentlich, auch bei privaten Repos (außer mit GitHub Enterprise). Die Daten enthalten nur öffentliche Veranstaltungen.

## Pflege

- **Event manuell ergänzen oder korrigieren:** Eintrag in `data/events.yaml` bearbeiten (Felder siehe bestehende Einträge). Nach dem Push nach `main` baut der Workflow `build.yml` die Feeds neu.
- **Neue Quelle:** Eintrag in `data/sources.yaml` hinzufügen.
- **Termin bestätigt:** Event aus `data/watchlist.yaml` nach `data/events.yaml` verschieben.
- **Lokal bauen:** `pip install -r requirements.txt && cd scripts && python build.py`
- **Lokal crawlen:** `cd scripts && python crawl.py` (mit `ANTHROPIC_API_KEY` inklusive KI-Extraktion)
- **Bestehende .ics importieren:** `cd scripts && python import_ics.py <datei.ics>` gibt YAML-Einträge aus.

Stabile UIDs: Events aus der ursprünglichen Datei `EU_IT_Event_Crawl_v5.ics` behalten ihre UIDs. Wer diese Datei bereits in Google importiert hat, bekommt beim Abo deshalb keine Dubletten innerhalb desselben Kalenders. Ein Abo ist allerdings immer ein eigener Kalender. Den alten Import sollten Sie daher löschen, sobald das Abo aktiv ist.

## Datenmodell (`data/events.yaml`)

| Feld | Bedeutung |
|---|---|
| `id` | Stabile ID (Slug), daraus wird die ICS-UID abgeleitet |
| `start` / `end` | Erster und letzter Veranstaltungstag (inklusiv) |
| `status` | `confirmed` oder `tentative` (im Kalender mit „[TBC]“ gekennzeichnet) |
| `relevance` | `core` (ITSM/ESM), `related` (KI/Cloud/Security/Digital), `peripheral` |
| `region` | `DACH`, `Europe`, `International`, `Online` |
| `categories` | ITSM, AI, Cloud, Security, Digital Transformation, Developer |
| `source` / `note` | Herkunft der Daten bzw. Prüfhinweise |
