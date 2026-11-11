(function () {
  function factor(places) {
    return 10 ** places;
  }

  function parseCents(text, places) {
    const raw = String(text == null ? "" : text).trim();
    if (!raw) return null;
    const negative = raw.startsWith("-");
    const body = negative ? raw.slice(1) : raw;
    if (!/^\d+(\.\d+)?$/.test(body)) return null;
    const parts = body.split(".");
    const whole = Number(parts[0]);
    const frac = parts[1] || "";
    const kept = (frac + "0".repeat(places)).slice(0, places);
    let cents = whole * factor(places) + Number(kept || "0");
    if (frac.length > places && frac.charAt(places) >= "5") cents += 1;
    return negative ? -cents : cents;
  }

  function formatCents(cents, places) {
    const sign = cents < 0 ? "-" : "";
    const abs = Math.abs(cents);
    const scale = factor(places);
    const whole = Math.floor(abs / scale);
    if (!places) return sign + String(whole);
    return sign + whole + "." + String(abs % scale).padStart(places, "0");
  }

  function percentOff(unitCents, percentText) {
    const basis = parseCents(percentText, 2);
    if (basis == null) return 0;
    return Math.floor((unitCents * basis + 5000) / 10000);
  }

  window.J2S = { parseCents, formatCents, percentOff };
})();
