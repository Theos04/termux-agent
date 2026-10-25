(async () => {
  const CONFIG = {
    scrollDelay: 2500,
    scrollStep: 0.75,
    maxIdleRounds: 15,
    maxScrolls: 500,
    postPathRegex: /^\/(p|reel|tv)\/([A-Za-z0-9_-]+)\/?/,
    outputFile: "instagram_liked_posts.json",
    maxAltPreview: 150,
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /** @type {Map<string, {url:string, shortcode:string, alt:string, image_urls:string[], collected_at:string}>} */
  const posts = new Map();

  /**
   * Extracts post metadata from a single anchor element.
   * Returns null if the anchor isn't a valid post link.
   */
  function extractPostData(anchor) {
    const href = anchor.getAttribute("href");
    if (!href) return null;

    const match = CONFIG.postPathRegex.exec(href);
    if (!match) return null;

    const [, , shortcode] = match;
    const url = new URL(href, location.origin).href;

    const altTexts = [];
    const imageURLs = [];

    for (const img of anchor.querySelectorAll("img")) {
      const alt = img.getAttribute("alt");
      if (alt) altTexts.push(alt);

      const src = img.currentSrc || img.src;
      if (src) imageURLs.push(src);
    }

    return {
      url,
      shortcode,
      alt: altTexts.join(" | "),
      image_urls: imageURLs,
      collected_at: new Date().toISOString(),
    };
  }

  /**
   * Merges a new post record into the map, updating metadata
   * if a previous pass captured the link without images/alt text.
   * Returns true if a new URL was added.
   */
  function mergePost(data) {
    const existing = posts.get(data.url);
    if (!existing) {
      posts.set(data.url, data);
      return true;
    }

    if (!existing.alt && data.alt) existing.alt = data.alt;
    if (existing.image_urls.length === 0 && data.image_urls.length) {
      existing.image_urls = data.image_urls;
    }
    return false;
  }

  /** Scans the DOM for post links. Returns the count of new URLs added. */
  function collectPosts() {
    let added = 0;
    const anchors = document.querySelectorAll('a[href^="/p/"], a[href^="/reel/"], a[href^="/tv/"]');

    for (const anchor of anchors) {
      const data = extractPostData(anchor);
      if (data && mergePost(data)) added++;
    }

    return added;
  }

  function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();

    URL.revokeObjectURL(url);
  }

  // --- Main loop ---------------------------------------------------------

  console.log("🚀 Collecting Instagram post URLs + image alt metadata");
  collectPosts();

  let idleRounds = 0;
  let scrolls = 0;

  while (idleRounds < CONFIG.maxIdleRounds && scrolls < CONFIG.maxScrolls) {
    window.scrollBy({
      top: Math.floor(window.innerHeight * CONFIG.scrollStep),
      behavior: "smooth",
    });

    await sleep(CONFIG.scrollDelay);

    const added = collectPosts();

    if (added > 0) {
      idleRounds = 0;
      console.log(`📥 Scroll ${scrolls + 1}: +${added} | Total: ${posts.size}`);
    } else {
      idleRounds++;
      console.log(`⏳ No new links: ${idleRounds}/${CONFIG.maxIdleRounds}`);
    }

    scrolls++;
  }

  // Final pass to catch anything rendered after the last scroll
  collectPosts();

  // --- Results -----------------------------------------------------------

  const results = [...posts.values()];
  const withAlt = results.filter((p) => p.alt).length;

  console.log("✅ Finished");
  console.log(`Total posts: ${results.length} | With alt text: ${withAlt}`);

  console.table(
    results.map(({ url, alt }) => ({
      URL: url,
      ALT: alt.slice(0, CONFIG.maxAltPreview),
    }))
  );

  window.igLikedPosts = results; // accessible in DevTools
  downloadJSON(results, CONFIG.outputFile);
  console.log(`💾 Saved: ${CONFIG.outputFile}`);

  return results;
})();
