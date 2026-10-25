(() => {
  const phoneBtn =
    document.querySelector('button[data-item-id^="phone:"]') ||
    document.querySelector('a[data-item-id^="phone:"]') ||
    document.querySelector('button[aria-label*="Phone"]') ||
    document.querySelector('button[aria-label*="phone"]') ||
    document.querySelector('[data-tooltip*="Copy phone"]') ||
    document.querySelector('[data-tooltip*="phone"]');

  const normalize = (raw) => {
    if (!raw) return null;
    const idm = String(raw).match(/phone:([^,\s]+)/i);
    if (idm) {
      const digits = idm[1].replace(/[^\d+]/g, "");
      if (digits.replace(/\D/g, "").length >= 10) return digits;
    }
    const m = String(raw).match(/(?:\+?\d[\d\s\-()]{8,}\d)/);
    if (m) {
      const digits = m[0].replace(/[^\d+]/g, "");
      if (digits.replace(/\D/g, "").length >= 10) return digits;
    }
    return null;
  };

  if (phoneBtn) {
    const raw =
      phoneBtn.getAttribute("data-item-id") ||
      phoneBtn.getAttribute("aria-label") ||
      phoneBtn.innerText ||
      "";
    const fromBtn = normalize(raw);
    if (fromBtn) return { ok: true, phone: fromBtn, source: "button" };
  }

  const main = document.querySelector('[role="main"]');
  const text = (main?.innerText || document.body?.innerText || "").slice(0, 6000);
  const india = text.match(/(?:\+91[\s\-]?)?[6-9]\d{9}/);
  if (india) {
    return { ok: true, phone: india[0].replace(/[^\d+]/g, ""), source: "text" };
  }
  const any = normalize(text);
  if (any) return { ok: true, phone: any, source: "text" };

  const title =
    document.querySelector("h1")?.innerText?.trim() ||
    document.title ||
    null;
  return { ok: true, phone: null, source: null, title };
})()
