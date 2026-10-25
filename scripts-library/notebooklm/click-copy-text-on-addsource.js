// Find all buttons/clickable elements in the dialog
const dialog = document.querySelector('.dialog-container');
if (dialog) {
  const buttons = dialog.querySelectorAll('button, [role="button"], .mat-mdc-button, .mdc-button');
  const results = [];
  buttons.forEach((btn, i) => {
    const text = btn.textContent.trim() || btn.getAttribute('aria-label') || '';
    if (text.toLowerCase().includes('copied') || 
        text.toLowerCase().includes('paste') || 
        text.toLowerCase().includes('text')) {
      results.push(`${i}: ${text} (${btn.className})`);
      btn.click(); // Click the first matching button
    }
  });
  results.length ? `✓ Clicked: ${results.join('\n')}` : 'No matching buttons found';
} else {
  '✗ Dialog not found';
}
