(async () => {
    console.log("🔙 Going back...");

    history.back();

    await new Promise(resolve => setTimeout(resolve, 1200));

    console.log("✅ Back navigation requested");

    return {
        action: "back",
        success: true,
        url: location.href
    };
})();
