(async () => {
  const args = %%ARGS%%;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const maxPlaces = Number(args.max_places) || 25;
  const openDelay = Number(args.open_delay_ms) || 1200;
  const onlyMissing = args.only_missing !== false;

  const seed = Array.isArray(window.mapsResults) ? window.mapsResults.slice() : [];
  const feed =
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]');

  if (!feed) {
    return { ok: false, error: "feed not found", data: seed, enriched: 0 };
  }

  const links = [...feed.querySelectorAll("a.hfpxzc, a[href*='/maps/place']")];
  const seen = new Set();
  let enriched = 0;

  const readPanelPhone = () => {
    const phoneBtn =
      document.querySelector('button[data-item-id^="phone:"]') ||
      document.querySelector('a[data-item-id^="phone:"]') ||
      document.querySelector('button[aria-label*="Phone"]') ||
      document.querySelector('[data-tooltip*="Copy phone"]');
    if (phoneBtn) {
      const raw =
        phoneBtn.getAttribute("data-item-id") ||
        phoneBtn.getAttribute("aria-label") ||
        phoneBtn.innerText ||
        "";
      const m = raw.match(/(?:\+?\d[\d\s\-]{8,}\d)/);
      if (m) return m[0].replace(/[^\d+]/g, "");
      const idm = raw.match(/phone:([^,]+)/i);
      if (idm) return idm[1].replace(/[^\d+]/g, "");
    }
    const text = (document.querySelector('[role="main"]')?.innerText || "").slice(0, 4000);
    const india = text.match(/(?:\+91[\s\-]?)?[6-9]\d{9}/);
    return india ? india[0].replace(/[^\d+]/g, "") : null;
  };

  const upsert = (name, mapsUrl, phone) => {
    let row = seed.find(r => (mapsUrl && r.maps_url === mapsUrl) || (name && r.name === name));
    if (!row) {
      row = { name, maps_url: mapsUrl || "", phone: null };
      seed.push(row);
    }
    if (phone && (!row.phone || row.phone !== phone)) {
      row.phone = phone;
      enriched += 1;
    }
  };

  for (const a of links) {
    if (enriched >= maxPlaces && onlyMissing) {
      // still allow filling remaining missing only
    }
    const name = a.getAttribute("aria-label") || a.innerText?.trim() || "";
    const mapsUrl = a.href || "";
    const key = mapsUrl || name;
    if (!key || seen.has(key)) continue;
    seen.add(key);

    const existing = seed.find(r => r.maps_url === mapsUrl || r.name === name);
    if (onlyMissing && existing && existing.phone) continue;
    if (seen.size > maxPlaces) break;

    try {
      a.click();
      await sleep(openDelay);
      const phone = readPanelPhone();
      upsert(name, mapsUrl, phone);
    } catch (_) {}
  }

  window.mapsResults = seed;
  return {
    ok: true,
    count: seed.length,
    enriched,
    with_phone: seed.filter(r => r.phone).length,
    data: seed
  };
})()
