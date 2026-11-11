(function () {
  const form = document.getElementById("close-form");
  const live = document.getElementById("counted-live");
  if (!form || !live || !window.J2S) return;
  const places = Number(form.dataset.places || "2");
  const symbol = form.dataset.symbol || "$";

  function refresh() {
    let total = 0;
    form.querySelectorAll("[data-denom]").forEach((input) => {
      const denom = window.J2S.parseCents(input.dataset.denom, places);
      const count = Number(input.value || "0");
      if (denom != null && count > 0) total += denom * count;
    });
    live.textContent = symbol + window.J2S.formatCents(total, places);
  }

  form.addEventListener("input", refresh);
  refresh();
})();
