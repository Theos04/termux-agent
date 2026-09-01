// ============================================================
// SIMPLE NESTED URL TABLE PRINTER
// ============================================================

(function() {
    const urls = [];
    const seen = new Set();
    
    // Extract URLs
    document.querySelectorAll('li a').forEach(link => {
        const href = link.href;
        if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
            const li = link.closest('li');
            let depth = 0;
            let current = li;
            while (current) {
                if (current.tagName.toLowerCase() === 'ul' || current.tagName.toLowerCase() === 'ol') depth++;
                current = current.parentElement;
            }
            
            const key = href + link.textContent;
            if (!seen.has(key)) {
                seen.add(key);
                urls.push({
                    '#': urls.length + 1,
                    Depth: depth,
                    Text: link.textContent.trim().slice(0, 30),
                    URL: href.slice(0, 50),
                    Parent: li ? li.textContent.trim().slice(0, 30) : ''
                });
            }
        }
    });
    
    if (urls.length === 0) {
        console.log('❌ No URLs found in list items');
        return;
    }
    
    // Print table
    console.log('\n🌐 NESTED URLS FROM LIST ITEMS');
    console.log(`📊 Total: ${urls.length} URLs\n`);
    console.table(urls);
    
    // Print tree view
    console.log('\n🌳 TREE VIEW:');
    urls.sort((a, b) => a.Depth - b.Depth).forEach(item => {
        const indent = '  '.repeat(item.Depth);
        console.log(`${indent}${'📎'} ${item.Text}`);
        console.log(`${indent}   → ${item.URL}`);
    });
    
    return urls;
})();
