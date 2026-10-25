// Print all list items from accessibility tree
(function() {
    // Method 1: Get all list items from DOM
    const listItems = document.querySelectorAll('li');
    const results = {
        total_li_elements: listItems.length,
        list_items: []
    };
    
    listItems.forEach((item, index) => {
        const text = item.textContent.trim();
        const hasSubList = item.querySelector('ul, ol') !== null;
        const classes = item.className || '';
        const id = item.id || '';
        
        results.list_items.push({
            index: index,
            text: text.substring(0, 200),
            has_sub_list: hasSubList,
            class: classes,
            id: id,
            inner_html: item.innerHTML.substring(0, 200)
        });
        
        // Print each item to console
        console.log(`[${index}] ${text.substring(0, 100)}`);
    });
    
    return results;
})();
