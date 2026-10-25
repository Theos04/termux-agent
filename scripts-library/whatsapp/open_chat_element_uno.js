const element = document.querySelector('#pane-side > div > div > div > div:nth-child(2) > div > div > div > div._ak8l._ap1_');
if (element) {
  ['mousedown', 'mouseup', 'click'].forEach(eventType => {
    element.dispatchEvent(new MouseEvent(eventType, { bubbles: true }));
  });
}
