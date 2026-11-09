// Browser security tests for the embeddable calendar page.
// Run: node tests/frontend_security.test.js   (requires: playwright + chromium, python3)
//
// Builds an attack copy of docs/ with malicious events.json / watchlist.json, embeds it in host pages
// (plain and sandboxed iframe) and verifies that no attacker-controlled code runs.
"use strict";
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");

const ROOT = path.resolve(__dirname, "..");
const SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads";
let failures = 0;
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };

function buildAttackSite() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cal-sec-"));
  fs.cpSync(path.join(ROOT, "docs"), path.join(dir, "cal"), { recursive: true });
  // malicious data exactly as an attacker would want it to appear (bypassing the build validation,
  // i.e. we test the frontend as the last line of defence)
  const py = `
import json, sys, datetime as dt
sys.path.insert(0, ${JSON.stringify(path.join(ROOT, "tests"))})
import attack_payloads as P
evs = []
for e in P.malicious_events():
    e = {k: (str(v) if isinstance(v, dt.date) else v) for k, v in e.items()}
    e.setdefault("uid", e["id"]); e.setdefault("note", "<img src=x onerror=window.__pwned='note'>")
    evs.append(e)
print(json.dumps({"generated": "2026-11-09T00:00:00+00:00", "events": evs}))`;
  fs.writeFileSync(path.join(dir, "cal/events.json"), execFileSync("python3", ["-I", "-c", py]));
  fs.writeFileSync(path.join(dir, "cal/watchlist.json"), JSON.stringify([
    { title: "Watch <b>x</b>", expected: "<img src=x onerror=window.__pwned='watch'>", location: "X",
      url: "javascript:window.__pwned='watchurl'", categories: ["ITSM"] }]));
  const host = (sb) => `<!doctype html><meta charset="utf-8"><script>window.hostSecret="s3cret"</script>` +
    `<iframe id="f" src="cal/index.html?lang=de" width="1200" height="900"${sb ? ` sandbox="${sb}"` : ""}></iframe>`;
  fs.writeFileSync(path.join(dir, "host.html"), host(""));
  fs.writeFileSync(path.join(dir, "host-sandbox.html"), host(SANDBOX));
  return dir;
}

function startServer(dir, port) {
  const code = `
import http.server, functools
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); super().end_headers()
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", ${port}), functools.partial(H, directory=${JSON.stringify(dir)})).serve_forever()`;
  return spawn("python3", ["-I", "-c", code], { stdio: "ignore" });
}

async function scenario(browser, url, label, sandboxed) {
  const ctx = await browser.newContext(); const page = await ctx.newPage();
  const external = new Set(), dialogs = [], errors = [];
  page.on("request", r => { const u = new URL(r.url()); if (/^https?:$/.test(u.protocol) && !["127.0.0.1", "localhost"].includes(u.hostname)) external.add(u.hostname); });
  page.on("dialog", async d => { dialogs.push(d.message()); await d.dismiss(); });
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(url, { waitUntil: "networkidle" }); await page.waitForTimeout(600);
  const f = page.frame({ url: /cal\/index/ });
  await f.evaluate(() => { window.__csp = []; document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective + " " + e.blockedURI)); });
  await f.selectOption("#time", "all"); await f.selectOption("#rel", "core,related,peripheral");

  ok(await f.locator("#listview .ev").count() === 6, `${label}: page loads data and renders all 6 payload events`);
  ok(!(await f.evaluate(() => !!document.querySelector("#listview img,#listview svg,#listview script,#watch img"))), `${label}: no HTML from data is rendered as markup`);

  // dialogs of every event: link must never be non-http(s)
  const n = await f.locator("#listview .ev").count();
  for (let i = 0; i < n; i++) {
    await f.locator("#listview .ev").nth(i).click(); await page.waitForTimeout(80);
    const href = await f.getAttribute("#d-url", "href");
    ok(href === null || /^https?:\/\//.test(href), `${label}: dialog link ${i} is safe (${href})`);
    const add = await f.getAttribute("#d-add", "href");
    ok(add.startsWith("https://calendar.google.com/"), `${label}: Google-Calendar link ${i} stays on google.com`);
    await f.click("#d-close");
  }
  const hrefs = await f.evaluate(() => [...document.querySelectorAll("a[href]")].map(a => a.getAttribute("href")));
  ok(hrefs.every(h => /^(https?:|webcal:|events|events-|#)/.test(h)), `${label}: all ${hrefs.length} links use safe schemes`);
  ok(await f.evaluate(() => [...document.querySelectorAll('a[target="_blank"]')].every(a => /noopener/.test(a.rel))), `${label}: target=_blank links carry rel=noopener`);

  // exploit attempt: force same-context navigation of every link
  await f.evaluate(() => document.querySelectorAll("a").forEach(a => a.removeAttribute("target")));
  ok(await f.evaluate(() => window.__pwned || null) === null, `${label}: no payload executed (window.__pwned unset)`);

  // CSP defence-in-depth: even if markup were injected, inline handlers must not run
  await f.evaluate(() => { const d = document.createElement("div"); d.innerHTML = '<img src="x:y" onerror="window.__pwned=\'csp\'">'; document.body.appendChild(d); });
  await page.waitForTimeout(300);
  ok(await f.evaluate(() => window.__pwned || null) === null, `${label}: CSP blocks injected inline event handler`);

  // isolation from the embedding page
  const parentAccess = await f.evaluate(() => { try { return window.parent.hostSecret || null; } catch (e) { return "blocked"; } });
  if (sandboxed) ok(parentAccess === "blocked", `${label}: sandboxed iframe cannot read the host page`);
  else console.log(`INFO  ${label}: same-origin iframe without sandbox can read host page -> use the sandbox attribute`);

  // calendar view under CSP, language switch
  await f.click("#tab-cal"); await page.waitForTimeout(400);
  ok(await f.locator(".fc").count() > 0, `${label}: calendar view renders under CSP`);
  await f.click('button[data-lang="en"]'); await page.waitForTimeout(200);
  ok((await f.textContent("h1")).includes("Calendar"), `${label}: language switch works`);

  // ignore the violations caused by our own deliberately injected test payload (<img src="x:y" onerror=...>)
  const csp = (await f.evaluate(() => window.__csp)).filter(v => !/ x(:y)?$/.test(v) && !v.startsWith("script-src-attr"));
  ok(csp.length === 0, `${label}: no unexpected CSP violations (${csp.join(" | ")})`);
  ok(external.size === 0, `${label}: no requests to third parties (${[...external].join(", ")})`);
  ok(dialogs.length === 0, `${label}: no alert/confirm dialogs triggered`);
  ok(errors.length === 0, `${label}: no JavaScript errors (${errors.join(" | ")})`);
  await ctx.close();
}

(async () => {
  const dir = buildAttackSite(); const port = 8800 + Math.floor(Math.random() * 100);
  const srv = startServer(dir, port); await new Promise(r => setTimeout(r, 800));
  const browser = await chromium.launch();
  try {
    await scenario(browser, `http://127.0.0.1:${port}/host.html`, "iframe", false);
    await scenario(browser, `http://127.0.0.1:${port}/host-sandbox.html`, "sandboxed iframe", true);
  } finally { await browser.close(); srv.kill(); fs.rmSync(dir, { recursive: true, force: true }); }
  console.log(failures ? `\n${failures} FAILED` : "\nALL FRONTEND SECURITY TESTS PASSED");
  process.exit(failures ? 1 : 0);
})();
