(function(){
  "use strict";
  // ---- security helpers: all event data is treated as untrusted ----
  // Only absolute http(s) URLs may become links (blocks javascript:, data:, vbscript:, relative tricks).
  function safeUrl(u) {
    if (typeof u !== "string" || u.length > 2000 || /[\u0000-\u001f\u007f-\u009f\s<>"'`]/.test(u)) return null;
    try {
      const p = new URL(u);
      return (p.protocol === "https:" || p.protocol === "http:") && p.hostname && !p.username && !p.password ? p.href : null;
    } catch (_) { return null; }
  }
  function extLink(u, text) {
    const a = document.createElement("a"), su = safeUrl(u);
    if (su) { a.href = su; a.target = "_blank"; a.rel = "noopener noreferrer"; }
    a.textContent = text == null ? "" : String(text);
    return a;
  }
  const T = {
    de: {
      title:"IT & ITSM Event-Kalender", subtitle:"ITSM/ESM · KI · Cloud · Security · Digitale Transformation – Fokus DACH",
      stamp:"Stand", subGoogle:"In Google Kalender abonnieren", subOther:"Abonnieren (Outlook/Apple)",
      dlAll:"Alle (.ics)", dlItsm:"Nur ITSM (.ics)", dlDach:"Nur DACH (.ics)", dlXlsx:"Excel-Liste (.xlsx)",
      fSearch:"Suche", searchPh:"Titel, Ort, Veranstalter …", fTime:"Zeitraum", fRel:"Relevanz", fReg:"Region", fCat:"Thema", fFmt:"Format", fStatus:"Status",
      tUpcoming:"Ab heute", t2026:"Nur 2026", t2027:"Nur 2027", tAll:"Alle (inkl. vergangene)",
      rDefault:"ITSM + verwandte Themen", rCore:"Nur ITSM/ESM", rAll:"Alle (inkl. Randthemen)",
      all:"Alle", regDACH:"DACH", regDE:"Nur Deutschland", regAT:"Nur Österreich", regCH:"Nur Schweiz", regEurope:"Europa (ohne DACH)", regInternational:"International", regOnline:"Online",
      stConfirmed:"Bestätigt", stTentative:"Vorläufig (TBC)",
      count:(n,t)=>`${n} von ${t} Veranstaltungen`, reset:"Filter zurücksetzen",
      lgCore:"ITSM/ESM (Kern)", lgRel:"KI, Cloud, Security, Digital", lgPer:"Randthema", lgTbc:"Termin vorläufig",
      tabList:"Liste", tabCal:"Kalender", empty:"Keine Veranstaltungen für diese Filter.",
      watchTitle:"Beobachtungsliste – noch ohne bestätigten Termin",
      watchText:"Diese Veranstaltungen werden erwartet, haben aber noch kein belastbares Datum. Der Crawler prüft sie bei jedem Lauf.",
      thEvent:"Veranstaltung", thExpected:"Erwartet", thLoc:"Ort",
      dDate:"Datum", dLoc:"Ort", dWeb:"Website", dAdd:"Einzeln in Google Kalender", dClose:"Schließen", tbc:"Termin vorläufig", note:"Hinweis",
      today:"Heute", month:"Monat", list:"Liste", noEvents:"Keine Veranstaltungen im Zeitraum",
      cat:{"ITSM":"ITSM/ESM","AI":"KI","Cloud":"Cloud","Security":"Security","Digital Transformation":"Digitale Transformation","Developer":"Developer"},
      fmt:{conference:"Konferenz/Kongress",tradefair:"Messe",forum:"Forum/Treffen",workshop:"Workshop",meetup:"Meetup/User Group",webinar:"Webinar/Online",training:"Training"},
      footer:["Kuratiert von ", "PAAN-Group Consulting", ". Angaben ohne Gewähr – Termine bitte vor Reiseplanung auf der Veranstalterseite prüfen. Automatische Aktualisierung per Crawler mit manueller Freigabe."],
      locale:"de-DE"
    },
    en: {
      title:"IT & ITSM Event Calendar", subtitle:"ITSM/ESM · AI · Cloud · Security · Digital Transformation – focus on DACH",
      stamp:"Updated", subGoogle:"Subscribe in Google Calendar", subOther:"Subscribe (Outlook/Apple)",
      dlAll:"All (.ics)", dlItsm:"ITSM only (.ics)", dlDach:"DACH only (.ics)", dlXlsx:"Excel list (.xlsx)",
      fSearch:"Search", searchPh:"Title, location, organiser …", fTime:"Period", fRel:"Relevance", fReg:"Region", fCat:"Topic", fFmt:"Format", fStatus:"Status",
      tUpcoming:"From today", t2026:"2026 only", t2027:"2027 only", tAll:"All (incl. past)",
      rDefault:"ITSM + related topics", rCore:"ITSM/ESM only", rAll:"All (incl. peripheral)",
      all:"All", regDACH:"DACH", regDE:"Germany only", regAT:"Austria only", regCH:"Switzerland only", regEurope:"Europe (excl. DACH)", regInternational:"International", regOnline:"Online",
      stConfirmed:"Confirmed", stTentative:"Tentative (TBC)",
      count:(n,t)=>`${n} of ${t} events`, reset:"Reset filters",
      lgCore:"ITSM/ESM (core)", lgRel:"AI, cloud, security, digital", lgPer:"Peripheral topic", lgTbc:"Date tentative",
      tabList:"List", tabCal:"Calendar", empty:"No events match these filters.",
      watchTitle:"Watchlist – no confirmed date yet",
      watchText:"These events are expected but do not have a reliable date yet. The crawler checks them on every run.",
      thEvent:"Event", thExpected:"Expected", thLoc:"Location",
      dDate:"Date", dLoc:"Location", dWeb:"Website", dAdd:"Add to Google Calendar", dClose:"Close", tbc:"Date tentative", note:"Note",
      today:"Today", month:"Month", list:"List", noEvents:"No events in this period",
      cat:{"ITSM":"ITSM/ESM","AI":"AI","Cloud":"Cloud","Security":"Security","Digital Transformation":"Digital transformation","Developer":"Developer"},
      fmt:{conference:"Conference/congress",tradefair:"Trade fair",forum:"Forum/meeting",workshop:"Workshop",meetup:"Meetup/user group",webinar:"Webinar/online",training:"Training"},
      footer:["Curated by ", "PAAN-Group Consulting", ". No liability for accuracy – please verify dates on the organiser's website before making travel plans. Updated automatically by a crawler with manual review."],
      locale:"en-GB"
    }
  };
  const $ = id => document.getElementById(id);
  const store = { get(k){ try{ return localStorage.getItem(k); }catch(_){ return null; } }, set(k,v){ try{ localStorage.setItem(k,v); }catch(_){} } };
  const params = new URLSearchParams(location.search);
  let lang = params.get("lang") || store.get("lang") || ((navigator.language||"de").toLowerCase().startsWith("de") ? "de" : "en");
  if (!T[lang]) lang = "de";
  const t = k => T[lang][k];
  const iso = d => d.toISOString().slice(0,10);
  const TODAY = iso(new Date());
  const addDay = d => { const x = new Date(d+"T00:00:00Z"); x.setUTCDate(x.getUTCDate()+1); return iso(x); };
  const fmtDate = d => new Date(d+"T00:00:00").toLocaleDateString(t("locale"), {day:"2-digit",month:"2-digit",year:"numeric"});
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  let all = [], watch = [], generated = null, cal = null, view = store.get("view") || "list";

  const FILTERS = ["q","time","rel","reg","cat","fmt","st"];
  const DEFAULTS = {q:"", time:"upcoming", rel:"core,related", reg:"", cat:"", fmt:"", st:""};

  function fillSelect(id, opts){
    const sel = $(id), cur = sel.value || store.get("f_"+id) || DEFAULTS[id];
    sel.replaceChildren();
    opts.forEach(([v,label]) => { const o = document.createElement("option"); o.value = v; o.textContent = label; sel.appendChild(o); });
    sel.value = opts.some(o => o[0]===cur) ? cur : DEFAULTS[id];
  }
  function buildSelects(){
    fillSelect("time", [["upcoming",t("tUpcoming")],["2026",t("t2026")],["2027",t("t2027")],["all",t("tAll")]]);
    fillSelect("rel", [["core,related",t("rDefault")],["core",t("rCore")],["core,related,peripheral",t("rAll")]]);
    fillSelect("reg", [["",t("all")],["DACH",t("regDACH")],["DE",t("regDE")],["AT",t("regAT")],["CH",t("regCH")],["Europe",t("regEurope")],["International",t("regInternational")],["Online",t("regOnline")]]);
    fillSelect("cat", [["",t("all")], ...Object.keys(T.de.cat).map(k => [k, t("cat")[k]])]);
    fillSelect("fmt", [["",t("all")], ...Object.keys(T.de.fmt).map(k => [k, t("fmt")[k]])]);
    fillSelect("st", [["",t("all")],["confirmed",t("stConfirmed")],["tentative",t("stTentative")]]);
    $("q").placeholder = t("searchPh");
  }
  function applyLang(){
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
    const [f1, f2, f3] = t("footer");
    $("footer").replaceChildren(document.createTextNode(f1), extLink("https://paan-group.com", f2), document.createTextNode(f3));
    document.querySelectorAll(".lang button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang===lang)));
    buildSelects();
    if (generated) $("stamp").textContent = t("stamp") + ": " + new Date(generated).toLocaleString(t("locale"), {dateStyle:"medium", timeStyle:"short"});
    if (cal) { cal.setOption("locale", lang); cal.setOption("buttonText", {today:t("today"), month:t("month"), list:t("list")}); cal.setOption("noEventsContent", t("noEvents")); }
    renderWatch();
    refresh();
  }

  function filtered(){
    const q = $("q").value.toLowerCase().trim(), time = $("time").value, rel = $("rel").value.split(",");
    const reg = $("reg").value, cat = $("cat").value, fmt = $("fmt").value, st = $("st").value;
    return all.filter(e =>
      (time==="all" || (time==="upcoming" ? e.end >= TODAY : e.start.slice(0,4)===time)) &&
      rel.includes(e.relevance) &&
      (!reg || (["DE","AT","CH"].includes(reg) ? e.country===reg : e.region===reg)) &&
      (!cat || e.categories.includes(cat)) && (!fmt || e.format===fmt) && (!st || e.status===st) &&
      (!q || [e.title, e.location, e.description_de, e.description_en, e.url].join(" ").toLowerCase().includes(q))
    ).sort((a,b) => a.start.localeCompare(b.start) || a.title.localeCompare(b.title));
  }
  const desc = e => (lang==="de" ? (e.description_de || e.description_en) : (e.description_en || e.description_de)) || "";

  function tag(text, cls){ const s = document.createElement("span"); s.className = "tag" + (cls ? " "+cls : ""); s.textContent = text; return s; }

  function renderList(list){
    const box = $("listview"); box.replaceChildren();
    if (!list.length){ const d = document.createElement("div"); d.className = "empty"; d.textContent = t("empty"); box.appendChild(d); return; }
    let cur = "";
    list.forEach(e => {
      const m = e.start.slice(0,7);
      if (m !== cur){
        cur = m;
        const h = document.createElement("div"); h.className = "month";
        h.textContent = new Date(e.start+"T00:00:00").toLocaleDateString(t("locale"), {month:"long", year:"numeric"});
        box.appendChild(h);
      }
      const row = document.createElement("div");
      row.className = "ev " + e.relevance + (e.status==="tentative" ? " tentative" : "");
      row.tabIndex = 0; row.setAttribute("role","button");
      const d = document.createElement("div"); d.className = "d"; d.textContent = e.start===e.end ? fmtDate(e.start) : fmtDate(e.start)+" –\n"+fmtDate(e.end); d.classList.add("pre-line");
      const ti = document.createElement("div"); ti.className = "t"; ti.textContent = e.title;
      const meta = document.createElement("div"); meta.className = "m";
      meta.append(document.createTextNode((e.location || "–") + "  "));
      meta.appendChild(tag(t("fmt")[e.format] || e.format, "fmt"));
      e.categories.forEach(c => meta.appendChild(tag(t("cat")[c] || c)));
      if (e.status==="tentative") meta.appendChild(tag(t("tbc"), "tbc"));
      row.append(d, ti, meta);
      row.addEventListener("click", () => openDlg(e));
      row.addEventListener("keydown", ev => { if (ev.key==="Enter" || ev.key===" ") { ev.preventDefault(); openDlg(e); } });
      box.appendChild(row);
    });
  }
  function toFc(e){
    const color = css("--"+e.relevance);
    return {id:e.id, title:e.title + (e.status==="tentative" ? " (TBC)" : ""), start:e.start, end:addDay(e.end), allDay:true,
      backgroundColor:color, borderColor:e.status==="tentative" ? css("--gold") : color, textColor:e.relevance==="related" ? "#fff" : "#0A3658",
      classNames:e.status==="tentative" ? ["tentative"] : [], extendedProps:e};
  }
  function refresh(){
    const list = filtered();
    $("count").textContent = t("count")(list.length, all.length);
    renderList(list);
    if (cal){ cal.getEventSources().forEach(s => s.remove()); cal.addEventSource(list.map(toFc)); }
  }
  function openDlg(e){
    $("d-title").textContent = e.title;
    $("d-date").textContent = e.start===e.end ? fmtDate(e.start) : fmtDate(e.start)+" – "+fmtDate(e.end);
    $("d-loc").textContent = e.location || "–";
    const du = $("d-url"), su = safeUrl(e.url);
    if (su) { du.href = su; du.textContent = su; } else { du.removeAttribute("href"); du.textContent = "–"; }
    const tags = $("d-tags"); tags.replaceChildren();
    tags.appendChild(tag(t("fmt")[e.format] || e.format, "fmt"));
    e.categories.forEach(c => tags.appendChild(tag(t("cat")[c] || c)));
    tags.appendChild(tag(e.region));
    if (e.status==="tentative") tags.appendChild(tag(t("tbc"), "tbc"));
    $("d-desc").textContent = desc(e);
    $("d-note").textContent = e.note ? t("note")+": "+e.note : "";
    const g = new URL("https://calendar.google.com/calendar/render");
    g.searchParams.set("action","TEMPLATE"); g.searchParams.set("text", e.title);
    g.searchParams.set("dates", e.start.replaceAll("-","")+"/"+addDay(e.end).replaceAll("-",""));
    g.searchParams.set("location", e.location || ""); g.searchParams.set("details", (safeUrl(e.url) || "")+"\n\n"+desc(e));
    $("d-add").href = g.toString();
    $("dlg").showModal();
  }
  function renderWatch(){
    const tb = $("watch"); tb.replaceChildren();
    watch.forEach(x => {
      const tr = document.createElement("tr");
      const td1 = document.createElement("td"); td1.appendChild(safeUrl(x.url) ? extLink(x.url, x.title) : document.createTextNode(x.title || ""));
      const td2 = document.createElement("td"); td2.textContent = (lang==="en" && x.expected_en) ? x.expected_en : x.expected;
      const td3 = document.createElement("td"); td3.textContent = x.location;
      tr.append(td1, td2, td3); tb.appendChild(tr);
    });
  }
  function setView(v){
    view = v; store.set("view", v);
    $("tab-list").setAttribute("aria-selected", String(v==="list"));
    $("tab-cal").setAttribute("aria-selected", String(v==="cal"));
    $("listview").hidden = v!=="list"; $("calview").hidden = v!=="cal";
    if (v==="cal"){ ensureCal(); cal.updateSize(); }
  }
  function ensureCal(){
    if (cal || typeof FullCalendar === "undefined") return;
    cal = new FullCalendar.Calendar($("calendar"), {
      locale:lang, firstDay:1, height:"auto", initialView:"dayGridMonth",
      headerToolbar:{left:"prev,next today", center:"title", right:""},
      buttonText:{today:t("today"), month:t("month"), list:t("list")}, noEventsContent:t("noEvents"),
      dayMaxEvents:4,
      eventClick: info => { info.jsEvent.preventDefault(); openDlg(info.event.extendedProps); },
      eventDidMount: info => { const e = info.event.extendedProps; info.el.title = e.title + (e.location ? " – " + e.location : ""); }
    });
    cal.render();
    cal.addEventSource(filtered().map(toFc));
  }

  // events: 'input' for text, 'change' + 'input' for selects (Safari fires only 'change')
  FILTERS.forEach(id => ["input","change"].forEach(evt => $(id).addEventListener(evt, () => {
    if (id !== "q") store.set("f_"+id, $(id).value);
    refresh();
  })));
  $("reset").addEventListener("click", () => {
    FILTERS.forEach(id => { $(id).value = DEFAULTS[id]; if (id !== "q") store.set("f_"+id, DEFAULTS[id]); });
    refresh();
  });
  document.querySelectorAll(".lang button").forEach(b => b.addEventListener("click", () => {
    lang = b.dataset.lang; store.set("lang", lang);
    const u = new URL(location.href); u.searchParams.set("lang", lang); history.replaceState(null, "", u);
    applyLang();
  }));
  $("tab-list").addEventListener("click", () => setView("list"));
  $("tab-cal").addEventListener("click", () => setView("cal"));
  $("d-close").addEventListener("click", () => $("dlg").close());

  const feed = new URL("events.ics", location.href);
  $("gcal").href = "https://calendar.google.com/calendar/r?cid=" + encodeURIComponent("webcal://" + feed.host + feed.pathname);
  $("webcal").href = "webcal://" + feed.host + feed.pathname;

  applyLang();
  setView(view);
  Promise.all([
    fetch("events.json").then(r => r.json()),
    fetch("watchlist.json").then(r => r.json()).catch(() => [])
  ]).then(([d, w]) => {
    all = d.events; watch = w; generated = d.generated;
    applyLang();
  });
})();
