(async () => {
  const args = %%ARGS%%;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const maxStable = Number(args.max_stable) || 5;
  const scrollDelay = Number(args.scroll_delay_ms) || 1800;
  const maxScrolls = Number(args.max_scrolls) || 40;
  const maxCards = Number(args.max_cards) || 200;
  const discovered = window.__mapsDiscover || {};
  const nameCss = args.name_css || discovered.name_css || null;
  const phoneCss = args.phone_css || discovered.phone_css || null;

  const feed =
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]');

  if (!feed) {
    return { ok: false, error: "Google Maps results feed not found", data: [], count: 0 };
  }

  const phoneRe = /(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?)?\d{5,10}(?:[\s\-]?\d{3,6})?/g;
  const indiaPhoneRe = /(?:\+91[\s\-]?)?[6-9]\d{9}/g;

  const pickPhone = (text) => {
    if (!text) return null;
    const india = text.match(indiaPhoneRe);
    if (india && india[0]) return india[0].replace(/[^\d+]/g, "");
    const all = text.match(phoneRe) || [];
    for (const p of all) {
      const digits = p.replace(/\D/g, "");
      if (digits.length >= 10 && digits.length <= 13) return p.trim();
    }
    return null;
  };

  const safeQuery = (root, sel) => {
    if (!sel) return null;
    try { return root.querySelector(sel); } catch (_) { return null; }
  };

  const results = new Map();
  let lastCount = 0;
  let stableRounds = 0;
  let scrolls = 0;

  const harvest = () => {
    const cards = feed.querySelectorAll('div[role="article"], .Nv2PK');
    cards.forEach(card => {
      const nameEl =
        safeQuery(card, nameCss) ||
        card.querySelector("a.hfpxzc") ||
        card.querySelector('a[href*="/maps/place"]') ||
        card.querySelector(".qBF1Pd");
      if (!nameEl) return;

      const name =
        (nameEl.getAttribute && nameEl.getAttribute("aria-label")) ||
        card.querySelector(".qBF1Pd")?.innerText?.trim() ||
        (nameEl.innerText || "").trim() ||
        null;
      if (!name || name.length < 2) return;
      if (/^(results|collapse|sponsored|directions)$/i.test(name)) return;

      const mapsUrl = nameEl.href || card.querySelector("a[href*='/maps/place']")?.href || "";
      const key = mapsUrl || name;

      const ratingEl = card.querySelector(".ZkP5Je, span[role='img'][aria-label*='star']");
      const ratingText = ratingEl?.getAttribute("aria-label") || "";
      const ratingMatch = ratingText.match(/([\d.]+)\s*stars?\s*([\d,]*)\s*Reviews?/i);
      let rating = ratingMatch ? Number(ratingMatch[1]) : null;
      let reviews = ratingMatch && ratingMatch[2]
        ? Number(String(ratingMatch[2]).replace(/,/g, ""))
        : null;

      const cardText = (card.innerText || "").trim();
      if (rating == null) {
        const m = cardText.match(/(\d+\.?\d*)\s*\(([\d,]+)\)/);
        if (m) {
          rating = Number(m[1]);
          reviews = Number(m[2].replace(/,/g, ""));
        }
      }

      const blocks = [...card.querySelectorAll(".W4Efsd")]
        .map(x => x.innerText.trim())
        .filter(Boolean);

      let category = null;
      let address = null;
      const info = blocks.find(x => x.includes("·"));
      if (info) {
        const parts = info.split("·").map(x => x.trim()).filter(Boolean);
        category = parts[0] || null;
        address = parts[1] || null;
      }
      if (!address) {
        const lines = cardText.split("\n").map(l => l.trim()).filter(Boolean);
        for (const line of lines.slice(1)) {
          if (line.includes("·") && line.length > 10) {
            const parts = line.split("·").map(x => x.trim()).filter(Boolean);
            address = parts[parts.length - 1] || address;
            category = category || parts[0] || null;
            break;
          }
        }
      }

      const phoneEl = safeQuery(card, phoneCss) || card.querySelector(".UsdlK");
      const phone =
        phoneEl?.innerText?.trim() ||
        pickPhone(cardText) ||
        null;

      const statusEl =
        card.querySelector(".eXlrNe") ||
        [...card.querySelectorAll("span")].find(x =>
          /Open|Closed|Permanently closed|Closes|Opens/i.test(x.innerText || "")
        );
      const status = statusEl?.innerText?.trim() || null;

      const website =
        card.querySelector('a[data-value="Website"]')?.href ||
        card.querySelector('a[aria-label*="Website"]')?.href ||
        null;

      const services = [...card.querySelectorAll(".ah5Ghc")]
        .map(x => x.innerText.trim())
        .filter(Boolean);

      const prev = results.get(key) || {};
      results.set(key, {
        name: name || prev.name,
        category: category || prev.category || null,
        address: address || prev.address || null,
        phone: phone || prev.phone || null,
        rating: rating != null ? rating : (prev.rating ?? null),
        reviews: reviews != null ? reviews : (prev.reviews ?? null),
        status: status || prev.status || null,
        website: website || prev.website || null,
        maps_url: mapsUrl || prev.maps_url || "",
        services: services.length ? services : (prev.services || [])
      });
    });
  };

  while (stableRounds < maxStable && scrolls < maxScrolls && results.size < maxCards) {
    harvest();

    const before = feed.scrollTop;
    feed.scrollTop = feed.scrollHeight;
    feed.dispatchEvent(new Event("scroll", { bubbles: true }));
    await sleep(scrollDelay);
    scrolls += 1;

    const after = feed.scrollTop;
    const currentCount = results.size;
    if (currentCount === lastCount && after === before) {
      stableRounds += 1;
    } else {
      stableRounds = 0;
    }
    lastCount = currentCount;

    if (
      /you've reached the end of the list/i.test(feed.innerText || "") ||
      /end of the list/i.test(feed.innerText || "")
    ) {
      break;
    }
  }

  harvest();
  const data = [...results.values()];
  window.mapsResults = data;

  return {
    ok: true,
    count: data.length,
    scrolls,
    with_phone: data.filter(d => d.phone).length,
    selectors_used: { name_css: nameCss, phone_css: phoneCss },
    data
  };
})()
