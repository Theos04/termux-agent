(() => {
    const REEL_SELECTOR =
        '.x1qjc9v5.x9f619.x78zum5.xg7h5cd.x1mfogq2.xsfy40s.x1bhewko.xgv127d.xh8yej3.xl56j7k';

    const reels = [...document.querySelectorAll(REEL_SELECTOR)];

    if (!reels.length) {
        return { ok: false, reason: 'no reels' };
    }

    const vh = window.innerHeight;
    const center = vh / 2;

    const active =
        reels.find(r => {
            const b = r.getBoundingClientRect();
            return b.top <= center && b.bottom >= center;
        }) || reels[0];

    // Accept:
    // 1,130
    // 72.9K
    // 1.2M
    // 909
    // 1,234,567
    const isMetric = s =>
        /^(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?[KkMm]?)$/.test(
            s.trim()
        );

    function cleanMetric(s) {
        return s?.trim() || null;
    }

    // Existing Like / Comment reader
    function readMetric(label) {
        const svg = active.querySelector(`svg[aria-label="${label}"]`);

        if (!svg) return null;

        let p = svg;

        for (let i = 0; i < 12 && p; i++) {
            p = p.parentElement;

            if (!p) break;

            const spans = p.querySelectorAll('span');

            for (const span of spans) {
                const text = cleanMetric(span.textContent);

                if (
                    text &&
                    text.length < 20 &&
                    !text.includes(':') &&
                    isMetric(text)
                ) {
                    return text;
                }
            }
        }

        return null;
    }

    /*
     * Repost is structurally different.
     *
     * Repost SVG:
     *
     * <div role="button">
     *     <svg aria-label="Repost">
     * </div>
     *
     * Metric:
     *
     * <div role="button">
     *     ...
     *     <span>1,130</span>
     * </div>
     *
     * Therefore:
     *   1. find Repost SVG
     *   2. find its button
     *   3. find the surrounding action-group
     *   4. inspect sibling buttons
     */
    function readRepost() {
        const svg = active.querySelector(
            'svg[aria-label="Repost"]'
        );

        if (!svg) return null;

        const repostButton = svg.closest('[role="button"]');

        if (!repostButton) return null;

        const parent = repostButton.parentElement;

        if (!parent) return null;

        const buttons = [...parent.querySelectorAll(
            ':scope > [role="button"]'
        )];

        for (const button of buttons) {
            if (button === repostButton) continue;

            const spans = button.querySelectorAll('span');

            for (const span of spans) {
                const text = cleanMetric(span.textContent);

                if (
                    text &&
                    text.length < 20 &&
                    !text.includes(':') &&
                    isMetric(text)
                ) {
                    return text;
                }
            }
        }

        return null;
    }

    /*
     * Username extraction.
     *
     * The first `a[href^="/"][role="link"]` inside a reel is the
     * profile-picture link — it contains only an <img>, so its
     * textContent is empty. The actual handle lives in the second
     * anchor, inside a `<span dir="auto">`.
     *
     * Strategy:
     *   1. Try the span[dir="auto"] inside a profile/reels anchor.
     *   2. Fall back to scanning all anchors for one with real text.
     */
    function readUsername() {
        // Preferred: the span[dir="auto"] that holds the handle text
        const span = active.querySelector(
            'a[href^="/"][role="link"] span[dir="auto"]'
        );

        const fromSpan = span?.textContent.trim();
        if (fromSpan) return fromSpan;

        // Fallback: scan anchors for one whose text looks like a handle
        const anchors = active.querySelectorAll(
            'a[href^="/"][role="link"]'
        );

        for (const a of anchors) {
            const text = a.textContent.trim();

            // A handle has no spaces and is non-empty
            if (text && !text.includes(' ') && text.length < 40) {
                return text;
            }
        }

        // Last resort: derive from the profile link href
        const profileAnchor = active.querySelector(
            'a[href^="/"][role="link"]'
        );

        const href = profileAnchor?.getAttribute('href') || '';
        const match = href.match(/^\/([^/]+)\//);
        if (match) return match[1];

        return 'Unknown';
    }

    const likes =
        readMetric('Like') ||
        readMetric('Unlike') ||
        '0';

    const comments =
        readMetric('Comment') ||
        '0';

    const reposts =
        readRepost() ||
        '0';

    const username = readUsername();

    return {
        ok: true,
        url: location.href,

        mode:
            /^\/reels?\/[A-Za-z0-9_-]+\/?$/.test(location.pathname)
                ? 'isolated'
                : 'feed',

        containers: reels.length,

        username,

        likes,
        comments,
        reposts
    };
})();
