const insertButton = [...document.querySelectorAll("button")]
  .find(btn => btn.textContent.trim().toLowerCase() === "insert");

if (insertButton) {
  insertButton.click();
  console.log("✅ Insert button clicked");
} else {
  console.log("❌ Insert button not found");
}
