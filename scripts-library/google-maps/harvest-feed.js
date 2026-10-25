(() => {
  const args = %%ARGS%%;
  const nameCss = args.name_css || null;
  const feed =
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]');
  if (!feed) {
    return { ok: false, error: "feed not found", data: [], count: 0 };
  }

  const safeQuery = (root, sel) => {
    if (!sel) return null;
    try { return root.querySelector(sel); } catch (_) { return null; }
  };

  const results = new Map();
  const cards = feed.querySelectorAll('div[role="article"], .Nv2PK');
  cards.forEach((card) => {
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
    const cardText = (card.innerText || "").trim();
    const phoneEl = card.querySelector(".UsdlK");
    const india = cardText.match(/(?:\+91[\s\-]?)?[6-9]\d{9}/);
    const phone = phoneEl?.innerText?.trim() || (india ? india[0] : null);

    let rating = null;
    let reviews = null;
    const m = cardText.match(/(\d+\.?\d*)\s*\(([\d,]+)\)/);
    if (m) {
      rating = Number(m[1]);
      reviews = Number(m[2].replace(/,/g, ""));
    }

    let category = null;
    let address = null;
    const blocks = [...card.querySelectorAll(".W4Efsd")]
      .map((x) => x.innerText.trim())
      .filter(Boolean);
    const info = blocks.find((x) => x.includes("·"));
    if (info) {
      const parts = info.split("·").map((x) => x.trim()).filter(Boolean);
      category = parts[0] || null;
      address = parts[1] || null;
    }

    const prev = results.get(key) || {};
    results.set(key, {
      name: name || prev.name,
      category: category || prev.category || null,
      address: address || prev.address || null,
      phone: phone || prev.phone || null,
      rating: rating != null ? rating : (prev.rating ?? null),
      reviews: reviews != null ? reviews : (prev.reviews ?? null),
      maps_url: mapsUrl || prev.maps_url || "",
    });
  });

  const data = [...results.values()];
  window.mapsResults = data;
  return {
    ok: true,
    count: data.length,
    scrollTop: feed.scrollTop,
    scrollHeight: feed.scrollHeight,
    end: /end of the list/i.test(feed.innerText || ""),
    data,
  };
})()
