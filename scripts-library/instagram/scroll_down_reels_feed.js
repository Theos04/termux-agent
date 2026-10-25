(() => {
    try {
        const buttons = [...document.querySelectorAll(
            '[aria-label="Navigate to next Reel"]'
        )];

        if (buttons.length === 0) {
            return {
                success: false,
                error: "NEXT_REEL_NOT_FOUND"
            };
        }

        const el = buttons.find(e => {
            const r = e.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        });

        if (!el) {
            return {
                success: false,
                error: "NEXT_REEL_FOUND_BUT_NOT_VISIBLE",
                count: buttons.length
            };
        }

        const r = el.getBoundingClientRect();

        el.dispatchEvent(new MouseEvent("mousedown", {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: r.left + r.width / 2,
            clientY: r.top + r.height / 2,
            button: 0
        }));

        el.dispatchEvent(new MouseEvent("mouseup", {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: r.left + r.width / 2,
            clientY: r.top + r.height / 2,
            button: 0
        }));

        el.dispatchEvent(new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: r.left + r.width / 2,
            clientY: r.top + r.height / 2,
            button: 0
        }));

        return {
            success: true,
            action: "next_reel",
            tag: el.tagName,
            role: el.getAttribute("role"),
            aria: el.getAttribute("aria-label"),
            x: r.left,
            y: r.top,
            width: r.width,
            height: r.height
        };

    } catch (err) {
        return {
            success: false,
            error: String(err),
            stack: err && err.stack ? String(err.stack) : null
        };
    }
})()
