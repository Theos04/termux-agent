(function() {
    'use strict';

    const quickApplyBtn = document.querySelector('#un-register-btn');

    if (quickApplyBtn) {
        quickApplyBtn.click();
        return '✅ Quick Apply clicked successfully!';
    } else {
        return '❌ Quick Apply button not found on the page.';
    }
})();
