/* The calculator preview on the home page.
 *
 * WHY THIS IS NOT A NUMBER TYPED INTO THE HTML. It was: `[PRIX] $`, a placeholder
 * that shipped. Filling it in by hand would have been worse than leaving it, on a
 * page whose whole promise is "your price, at the screen, no phone call" -- a
 * figure written into the markup is a price quoted to every visitor that nothing
 * keeps true. Publish a new rate card and the home page keeps advertising the old
 * one until somebody remembers this file exists.
 *
 * So the panel asks the same endpoint the quote form asks, for exactly the home
 * described by the chips beside it. Three outcomes, and only one of them shows a
 * figure:
 *
 *   priced      the real price for that home appears, and the note under it
 *               becomes the firm-price wording
 *   409         the rate card does not price this combination, or online pricing
 *               is switched off -- no figure, the invitation stays
 *   offline     no figure, the invitation stays
 *
 * The invitation is what the panel renders on its own, before any JavaScript, so
 * a visitor with a blocked script or a dead network sees a complete, honest panel
 * rather than an empty box or a spinner. Nothing here can make the page worse; the
 * best it can do is add a real number to it.
 */
(function () {
  "use strict";

  var panel = document.querySelector("[data-demo]");
  if (!panel) return;

  var priceEl = document.getElementById("demo-price");
  var unitEl = document.getElementById("demo-unit");
  var noteEl = document.getElementById("demo-note");
  /* The rule belongs to the number, not to the panel: a divider with nothing
     under it reads as something that failed to load. */
  var ruleEl = document.getElementById("demo-rule");
  if (!priceEl || !unitEl || !noteEl) return;

  var EN = (document.documentElement.lang || "fr").slice(0, 2) === "en";

  /* The chips next to the panel say "3 chambres · 2 salles de bain · 1 100 pi²".
     THESE NUMBERS AND THOSE WORDS HAVE TO AGREE: a panel that quotes 1,100 sq ft
     and prices 1,400 is worse than no panel. Changing one means changing both. */
  var EXAMPLE = {
    audience: "residential",
    property: { property_type: "condo", area_sqft: 1100, bedrooms: 3, bathrooms: 2 },
    services: [],
    frequency: "biweekly",
    extras: {},
    modifiers: {},
    night_access: false
  };

  var PRICED_NOTE = EN
    ? "A firm price for a standard 1,100 sq ft home, every two weeks. Anything unusual is confirmed before the first visit."
    : "Estimation ferme pour un logement standard de 1 100 pi², aux deux semaines. Un cas particulier est confirmé avant la première visite.";

  function money(cents) {
    return new Intl.NumberFormat(EN ? "en-CA" : "fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  fetch("/api/quotes/price", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(EXAMPLE)
  })
    .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
    .then(function (price) {
      if (!price || typeof price.total_cents !== "number") return;
      priceEl.textContent = money(price.total_cents);
      priceEl.hidden = false;
      if (ruleEl) ruleEl.hidden = false;
      unitEl.hidden = false;
      noteEl.textContent = PRICED_NOTE;
    })
    .catch(function () {
      /* Deliberately empty. The panel already reads correctly without a number,
         and an error message here would be telling a visitor about our rate card. */
    });
})();
