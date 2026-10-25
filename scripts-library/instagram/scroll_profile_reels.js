(() => {
  const svg = document.querySelector('svg[aria-label="Next"]');
  if (!svg) return 'no-next-svg';
  const btn = svg.closest('button') || svg.closest('[role="button"]');
  if (!btn) return 'no-button-wrapper';
  btn.click();
  return 'clicked';
})()
