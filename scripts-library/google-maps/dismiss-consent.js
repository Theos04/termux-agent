(async () => {
  const args = %%ARGS%%;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clicked = [];
  const candidates = [
    ...document.querySelectorAll("button, [role='button'], form[action*='consent'] button")
  ];
  const labels = [/accept all/i, /i agree/i, /^agree$/i, /reject all/i, /got it/i, /^ok$/i];

  for (const el of candidates) {
    const t = (el.innerText || el.getAttribute("aria-label") || "").trim();
    if (!t || t.length > 40) continue;
    if (!labels.some(re => re.test(t))) continue;
    try {
      el.click();
      clicked.push(t);
      await sleep(Number(args.delay_ms) || 600);
    } catch (_) {}
  }

  return { ok: true, clicked, count: clicked.length };
})()
