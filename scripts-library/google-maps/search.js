(async () => {
  const args = %%ARGS%%;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const q = (args.query || "").trim();
  if (!q) return { ok: false, error: "args.query required" };

  const box =
    document.querySelector("#searchboxinput") ||
    document.querySelector('input[name="q"]') ||
    document.querySelector('form[action*="/maps"] input[type="text"]');

  if (!box) {
    // fallback: navigate
    location.href = "https://www.google.com/maps/search/" + encodeURIComponent(q);
    await sleep(Number(args.nav_delay_ms) || 2500);
    return { ok: true, mode: "navigate", query: q, url: location.href };
  }

  box.focus();
  box.value = "";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  box.value = q;
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await sleep(200);

  const form = box.closest("form");
  if (form) {
    form.requestSubmit ? form.requestSubmit() : form.submit();
  } else {
    box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
    box.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
  }

  await sleep(Number(args.search_delay_ms) || 2000);
  return { ok: true, mode: "searchbox", query: q, url: location.href, title: document.title };
})()
