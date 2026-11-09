# Security Review – IT & ITSM Event-Kalender

**Stand:** 09.11.2026 · **Scope:** Website (`docs/`), Datenpipeline (`scripts/`), GitHub Actions (`.github/workflows/`) · **Einsatz:** Einbettung als iFrame in eine Unternehmenswebsite

## 1. Bedrohungsmodell

| Element | Bewertung |
|---|---|
| **Schutzgüter** | Integrität der Website und der einbettenden Seite, Besucher (Browser, Excel, Kalender-Clients), Repository und Secrets, Reputation von PAAN-Group |
| **Haupteintrittspunkt** | **Fremde Inhalte von Event-Websites**: Der Crawler liest JSON-LD, iCal und Seitentext (KI-Extraktion) von über 70 Drittseiten. Jede dieser Seiten kann kompromittiert oder böswillig sein. |
| **Weitere Angriffsflächen** | Einbettung per iFrame (Clickjacking, Zugriff auf die Host-Seite), Drittanbieter-Ressourcen, Lieferkette (GitHub Actions, PyPI), Prompt-Injection gegen die KI-Extraktion |
| **Nicht vorhanden (reduziert das Risiko)** | Kein Login, keine Formulare, keine Cookies, keine personenbezogenen Daten, kein Backend und keine Datenbank (rein statische Seite auf GitHub Pages) |

## 2. Simulierte Angriffe und Befunde

Die Angriffe wurden mit präparierten Daten gegen den **ungepatchten** Stand ausgeführt (Payloads: `tests/attack_payloads.py`).

| # | Angriff | Befund vorher | Schwere | Behebung | Nachher |
|---|---|---|---|---|---|
| 1 | **Gespeichertes XSS über `javascript:`- oder `data:`-URL** in Event-Daten (z. B. per JSON-LD einer Event-Website) | Link wurde unverändert gerendert. **Exploit bestätigt:** Code lief im Kontext der Seite, inklusive Zugriff auf localStorage. | **Hoch** | `safe_url()` im Build (bricht dann ab), im Crawler (verwirft den Kandidaten) und im Browser (`safeUrl()` und `extLink()`); nur absolute http(s)-URLs ohne Zugangsdaten | Blockiert |
| 2 | **HTML-/Skript-Injection** in Titel, Ort, Beschreibung und Watchlist | Bereits sicher (Ausgabe per `textContent`) | – | Zusätzlich: Entfernen von HTML-Tags beim Import, keine `innerHTML`-Nutzung mehr, CSP blockiert Inline-Handler | Blockiert (mehrschichtig) |
| 3 | **Formel-Injection in Excel** (`=HYPERLINK(...)`, `+cmd\|...`) | Titel `=HYPERLINK(...)` wurde von Excel **als Formel ausgeführt**, `javascript:`/`data:`-Hyperlinks wurden übernommen | **Hoch** | `excel_safe()` setzt ein `'` vor gefährliche Präfixe, Zelltyp wird als Text erzwungen, Hyperlinks nur bei http(s) | Blockiert |
| 4 | **ICS-Injection** (CR/LF in Feldern → zusätzliche Properties wie `ATTACH:` oder `VALARM`) | Ein einzelnes CR erzeugte eine **eingeschleuste `ATTACH:`-Zeile**, eine `javascript:`-URL landete im Feed | **Mittel** | Steuerzeichen werden entfernt, RFC-5545-Escaping, URL-Prüfung im Feed | Blockiert |
| 5 | **Unicode-Bidi-Spoofing** (`Normal‮gnp.exe`) | Übernommen | Niedrig | Bidi- und Zero-Width-Zeichen werden entfernt | Blockiert |
| 6 | **Fehlende Content-Security-Policy** | Keine CSP, Inline-Skript und Inline-Styles | **Mittel** | Strikte CSP: `default-src 'none'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'`, JS und CSS ausgelagert, keine Inline-Handler | Aktiv |
| 7 | **Drittanbieter-Ressource Google Fonts** | Bei jedem Seitenaufruf ging die IP-Adresse an Google: **DSGVO-Risiko** (LG München I, 20.01.2022, 3 O 17493/20) und zusätzliche Abhängigkeit in der Lieferkette | **Mittel** (Compliance) | Maven Pro wird selbst gehostet (OFL-1.1), keine externen Requests mehr | 0 externe Requests |
| 8 | **iFrame liest die Host-Seite** (bei gleicher Domain ohne `sandbox`) | Möglich (`hostSecret` auslesbar) | **Mittel** (abhängig von der Einbettung) | Einbettung mit `sandbox` ohne `allow-same-origin` (Abschnitt 4), Seite funktioniert darin vollständig | Blockiert |
| 9 | **Referrer-Leak, Reverse Tabnabbing** | Kein Referrer-Policy | Niedrig | `<meta name="referrer" content="no-referrer">`, `rel="noopener noreferrer"` auf allen externen Links | Behoben |
| 10 | **Prompt-Injection gegen die KI-Extraktion** („Ignore all previous instructions…“) | Seitentext ging ohne Schutzhinweis an das Modell | Mittel | System-Prompt markiert den Seiteninhalt als Daten, Ausgabe nur über ein festes Schema, URL-Prüfung, KI-Funde immer `tentative`, Freigabe per Pull Request | Gemindert |
| 11 | **Lieferkette GitHub Actions / PyPI** | Actions über verschiebbare Tags (`@v4`), Abhängigkeiten mit `>=` | Mittel | Actions auf Commit-SHA gepinnt, exakte Versionen in `requirements.txt`, `persist-credentials: false`, minimale `permissions`, Timeouts | Behoben |
| 12 | **Übergroße oder bösartige Antworten** (DoS gegen den Crawler) | Unbegrenzt | Niedrig | Seiten über 5 MB werden verworfen, Textfelder sind längenbegrenzt | Behoben |

**Weitere Prüfpunkte ohne Befund:**
- `yaml.safe_load` wird überall verwendet.
- Es gibt kein `eval`, kein `exec` und kein `shell=True`.
- Workflows verwenden kein `pull_request_target` und keine Ausdrucks-Injection über `${{ github.event.* }}`.
- Das Secret `ANTHROPIC_API_KEY` ist nur im Crawl-Schritt sichtbar.

## 3. Verbleibende Risiken und Empfehlungen

| Risiko | Einschätzung | Empfehlung |
|---|---|---|
| **Clickjacking / fremde Einbettung**: GitHub Pages kann keine HTTP-Header setzen, daher fehlt `frame-ancestors` (im `<meta>`-CSP wirkungslos) | Gering: Die Seite hat keine zustandsändernden Aktionen, keine Anmeldung und keine Formulare. Fremdes Einbetten ist möglich, aber ohne Schadenspotenzial für Besucher. | Wer es strikt will, hostet hinter einer eigenen Domain oder einem CDN (z. B. Cloudflare Pages oder Netlify) mit dem Header `Content-Security-Policy: frame-ancestors https://paan-group.com https://www.paan-group.com` sowie `X-Content-Type-Options: nosniff` |
| `style-src 'unsafe-inline'` | Gering: FullCalendar injiziert sein CSS zur Laufzeit. Skripte bleiben strikt `'self'`. | Bei einem späteren FullCalendar-Update prüfen, ob eine Nonce-Variante möglich ist |
| Freigabe der Crawler-PRs | Prozessrisiko: Ein unachtsamer Merge könnte falsche, aber harmlose Termine übernehmen. Technisch gefährliche Inhalte blockieren Build und Tests. | Branch Protection auf `main`: PR-Pflicht mit grünem Workflow „Security tests“ |
| GitHub-Pages-Einstellung | – | Unter **Settings → Pages** die Option „Enforce HTTPS“ aktivieren |
| Aktualität der Abhängigkeiten | – | Dependabot für `github-actions` und `pip` aktivieren, Updates nur per PR mit grünen Tests |

## 4. Sichere Einbettung (iFrame-Code)

```html
<iframe
  src="https://joropa-pgk.github.io/ITSM-Calendar-via-Claude-/?lang=de"
  title="IT &amp; ITSM Event-Kalender"
  loading="lazy"
  referrerpolicy="no-referrer"
  sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads"
  style="width:100%; height:1400px; border:0;">
</iframe>
```

- **Nie** `allow-same-origin` **zusammen mit** `allow-scripts` setzen. Die Kombination hebt die Sandbox auf.
- `allow-popups` und `allow-popups-to-escape-sandbox` sind nötig, damit externe Links und „In Google Kalender abonnieren“ normal in einem neuen Tab öffnen.
- `allow-downloads` ist nötig für die Downloads von `.ics` und `.xlsx`.
- Mit `?lang=en` startet die Seite auf Englisch.

## 5. Tests

| Test | Inhalt | Ausführen |
|---|---|---|
| `tests/test_security.py` (39 Tests) | URL-, Text-, ID- und Enum-Validierung, Build schlägt bei unsicheren Daten fehl, ICS- und Excel-Injection, bösartiges JSON-LD, CSP-Strenge, kein Inline-Code, keine externen Ressourcen, keine gefährlichen DOM-Sinks, generierte Daten sauber | `pip install -r requirements-dev.txt && python -m pytest -q tests` |
| `tests/frontend_security.test.js` (2 Szenarien, je ca. 25 Prüfungen) | Echter Browser mit bösartigen Daten in einem normalen und einem sandboxed iFrame: keine Ausführung, sichere Links, CSP blockiert injizierte Handler, Isolation von der Host-Seite, keine Drittanbieter-Requests, Kalender und Sprachwechsel funktionieren unter CSP | `node tests/frontend_security.test.js` (benötigt `playwright` mit Chromium und `python3`) |
| Workflow `security.yml` | Führt beide Test-Suiten bei jedem Push nach `main` und bei jedem Pull Request aus. Build und Crawl führen zusätzlich die pytest-Suite aus. | automatisch |

**Validierung der Tests:** Gegen den ungepatchten Stand schlagen die Tests fehl: Der Browser-Test meldet 10 Fehler, die pytest-Suite startet nicht, weil die Sicherheitsfunktionen fehlen. Gegen den gepatchten Stand bestehen alle Tests.

## 6. Meldung von Sicherheitsproblemen

Bitte nicht als öffentliches Issue melden, sondern vertraulich über das Kontaktformular auf https://paan-group.com.
