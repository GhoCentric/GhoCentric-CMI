(() => {
  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy") || "";
      const prior = button.textContent;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "COPIED";
      } catch (_) {
        button.textContent = "SELECT";
      }
      setTimeout(() => { button.textContent = prior; }, 1200);
    });
  }
})();
