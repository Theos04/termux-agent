(() => {
  const feed =
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]');
  if (!feed) return { ok: false, error: "feed not found" };
  const before = feed.scrollTop;
  feed.scrollTop = feed.scrollHeight;
  feed.dispatchEvent(new Event("scroll", { bubbles: true }));
  return {
    ok: true,
    before,
    after: feed.scrollTop,
    height: feed.scrollHeight,
    moved: feed.scrollTop !== before,
    end: /end of the list/i.test(feed.innerText || ""),
  };
})()
