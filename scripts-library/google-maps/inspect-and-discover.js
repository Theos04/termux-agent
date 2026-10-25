(async () => {
  const args = %%ARGS%%;
  const sampleLimit = Number(args.sample_limit) || 8;

  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 6) {
      let part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) {
        const cls = [...cur.classList]
          .filter(c => c && !/^\d/.test(c) && c.length < 40)
          .slice(0, 2)
          .map(c => `.${CSS.escape(c)}`)
          .join("");
        if (cls) part += cls;
      }
      const parent = cur.parentElement;
      if (parent) {
        const sibs = [...parent.children].filter(x => x.tagName === cur.tagName);
        if (sibs.length > 1) {
          const idx = sibs.indexOf(cur) + 1;
          part += `:nth-of-type(${idx})`;
        }
      }
      parts.unshift(part);
      if (cur.getAttribute && cur.getAttribute("role") === "feed") break;
      cur = parent;
      if (cur === document.body || cur === document.documentElement) break;
    }
    return parts.join(" > ");
  };

  const xpathOf = (el) => {
    if (!el || el.nodeType !== 1) return "";
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 8) {
      let ix = 1;
      let sib = cur.previousElementSibling;
      while (sib) {
        if (sib.tagName === cur.tagName) ix += 1;
        sib = sib.previousElementSibling;
      }
      parts.unshift(`${cur.tagName.toLowerCase()}[${ix}]`);
      if (cur.getAttribute && cur.getAttribute("role") === "feed") break;
      cur = cur.parentElement;
      if (!cur || cur === document.body) break;
    }
    return "//" + parts.join("/");
  };

  const feed =
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]') ||
    document.querySelector('[role="main"]');

  const page = {
    url: location.href,
    title: document.title,
    has_feed: !!document.querySelector('div[role="feed"]'),
    body_len: (document.body && document.body.innerText || "").length,
    consent_like: /before you continue|consent|accept all/i.test(document.body?.innerText || ""),
    end_of_list: /you've reached the end of the list|end of the list/i.test(feed?.innerText || "")
  };

  if (!feed) {
    return {
      ok: false,
      error: "no feed/main container to inspect",
      page,
      selectors: {},
      samples: []
    };
  }

  const phoneRe = /(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?)?\d{5,10}(?:[\s\-]?\d{3,6})?/g;
  const indiaPhoneRe = /(?:\+91[\s\-]?)?[6-9]\d{9}/g;

  // Candidate name anchors (Maps result cards)
  const nameCandidates = [
    ...feed.querySelectorAll("a.hfpxzc"),
    ...feed.querySelectorAll('a[href*="/maps/place"]'),
    ...feed.querySelectorAll(".qBF1Pd"),
    ...feed.querySelectorAll('div[role="article"] a[aria-label]')
  ];

  const phoneCandidates = [
    ...feed.querySelectorAll(".UsdlK"),
    ...feed.querySelectorAll('button[data-item-id^="phone:"]'),
    ...feed.querySelectorAll('a[data-item-id^="phone:"]'),
    ...feed.querySelectorAll('[aria-label*="Phone"]'),
    ...feed.querySelectorAll('span, div, a, button')
  ].filter(el => {
    const t = (el.innerText || el.getAttribute("aria-label") || "").trim();
    if (!t || t.length > 40) return false;
    return indiaPhoneRe.test(t) || (t.match(phoneRe) || []).some(p => p.replace(/\D/g, "").length >= 10);
  });

  const scoreSelector = (sel, root) => {
    if (!sel) return 0;
    try {
      return root.querySelectorAll(sel).length;
    } catch (_) {
      return 0;
    }
  };

  // Prefer short stable class/attr selectors over deep paths
  const preferNameCss = [
    "a.hfpxzc",
    'a[href*="/maps/place"]',
    ".qBF1Pd",
    'div[role="article"] a[aria-label]',
    'div[role="article"] .qBF1Pd'
  ];
  const preferPhoneCss = [
    ".UsdlK",
    'button[data-item-id^="phone:"]',
    'a[data-item-id^="phone:"]',
    'button[aria-label*="Phone"]',
    '[data-tooltip*="Copy phone"]'
  ];

  let name_css = preferNameCss.find(s => scoreSelector(s, feed) > 0) || null;
  let phone_css = preferPhoneCss.find(s => scoreSelector(s, feed) > 0) || null;

  let name_xpath = null;
  let phone_xpath = null;
  if (nameCandidates[0]) {
    if (!name_css) name_css = cssPath(nameCandidates[0]);
    name_xpath = xpathOf(nameCandidates[0]);
  }
  if (phoneCandidates[0]) {
    if (!phone_css) phone_css = cssPath(phoneCandidates[0]);
    phone_xpath = xpathOf(phoneCandidates[0]);
  }

  const nameHits = name_css ? scoreSelector(name_css, feed) : 0;
  const phoneHits = phone_css ? scoreSelector(phone_css, feed) : 0;

  const samples = [];
  const cards = feed.querySelectorAll('div[role="article"], .Nv2PK');
  for (const card of [...cards].slice(0, sampleLimit)) {
    const nameEl =
      (name_css && card.querySelector(name_css)) ||
      card.querySelector("a.hfpxzc") ||
      card.querySelector(".qBF1Pd");
    const phoneEl =
      (phone_css && card.querySelector(phone_css)) ||
      card.querySelector(".UsdlK");
    const name =
      nameEl?.getAttribute?.("aria-label") ||
      nameEl?.innerText?.trim() ||
      null;
    const phone = phoneEl?.innerText?.trim() || null;
    const snippet = (card.innerText || "").split("\n").map(s => s.trim()).filter(Boolean).slice(0, 4);
    if (name || snippet.length) {
      samples.push({ name, phone, snippet, maps_url: nameEl?.href || null });
    }
  }

  // Also store for downstream scroll script
  window.__mapsDiscover = {
    name_css,
    phone_css,
    name_xpath,
    phone_xpath,
    name_hits: nameHits,
    phone_hits: phoneHits
  };

  const meaningful_samples = samples.filter(
    s => s.name && s.name.length >= 2 && !/^(results|collapse|sponsored|directions)$/i.test(s.name)
  );

  return {
    ok: true,
    page,
    selectors: {
      name_css,
      phone_css,
      name_xpath,
      phone_xpath,
      name_hits: nameHits,
      phone_hits: phoneHits,
      card_css: 'div[role="article"], .Nv2PK',
      feed_css: 'div[role="feed"]'
    },
    samples: meaningful_samples,
    sample_count: meaningful_samples.length,
    extractable: meaningful_samples.length > 0 && nameHits > 0,
    diagnostics: {
      raw_name_candidates: nameCandidates.length,
      raw_phone_candidates: phoneCandidates.length,
      article_count: cards.length,
      feed_text_preview: (feed.innerText || "").slice(0, 280)
    }
  };
})()
