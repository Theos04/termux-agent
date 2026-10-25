(() => {
    const target = "https://www.instagram.com/reels/";

    console.log("➡️ Navigating to:", target);

    location.href = target;

    return {
        action: "navigate",
        success: true,
        target
    };
})();
