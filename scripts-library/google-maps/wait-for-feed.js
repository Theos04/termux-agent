(async () => {
  const args = %%ARGS%%;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const timeoutMs = Number(args.timeout_ms) || 20000;
  const pollMs = Number(args.poll_ms) || 400;
  const start = Date.now();

  const findFeed = () =>
    document.querySelector('div[role="feed"]') ||
    document.querySelector('div[role="main"] div[role="feed"]');

  while (Date.now() - start < timeoutMs) {
    const feed = findFeed();
    if (feed) {
      const articles = feed.querySelectorAll('div[role="article"], .Nv2PK, a.hfpxzc');
      if (articles.length > 0) {
        return {
          ok: true,
          ready: true,
          article_count: articles.length,
          url: location.href,
          title: document.title,
          waited_ms: Date.now() - start
        };
      }
    }
    // consent / empty results still count as "page settled" after half timeout with feed
    if (findFeed() && Date.now() - start > 5000) {
      return {
        ok: true,
        ready: true,
        article_count: 0,
        url: location.href,
        title: document.title,
        waited_ms: Date.now() - start,
        note: "feed present but empty"
      };
    }
    await sleep(pollMs);
  }

  return {
    ok: false,
    ready: false,
    error: "Maps results feed not ready",
    url: location.href,
    title: document.title,
    waited_ms: Date.now() - start
  };
})()
