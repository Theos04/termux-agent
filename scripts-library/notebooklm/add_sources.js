const label = [...document.querySelectorAll("*")].find(e =>
  e.textContent?.trim() === "Add sources"
);

const clickable = label?.closest(
  'button,[role="button"],a,[tabindex],.mdc-button,.mat-mdc-button-base'
);

if (clickable) {
  clickable.click();
  console.log("Clicked:", clickable);
}
