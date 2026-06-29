const searchQuery = prompt("Enter your Reddit search query:");

if (searchQuery) {
    window.location.href =
        `https://www.reddit.com/search/?q=${encodeURIComponent(searchQuery)}`;
}
