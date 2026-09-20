/* Proline quote wizard.
 * Three steps, conditional fields by audience, and a live price for residential.
 * The rate grid stays on the server: every price comes from /api/quotes/price.
 */
(function () {
  "use strict";

  var form = document.getElementById("quote-form");
  if (!form) return;

  var locale = document.body.dataset.locale || "fr";
  var EN = locale === "en";
  var priceTotal = document.getElementById("price-total");
  var priceNote = document.getElementById("price-note");
  var priceLines = document.getElementById("price-lines");
  var priceDisclaimer = document.getElementById("price-disclaimer");
  var errorBox = document.getElementById("form-error");
  var submitBtn = document.getElementById("submit-btn");

  var T = {
    fillIn: EN ? "Fill in the property and frequency: your price appears here."
               : "Remplissez la propriété et la fréquence : le prix apparaît ici.",
    reviewed: EN ? "Commercial requests are quoted by a person, within 24 hours."
                 : "Les demandes commerciales sont chiffrées par une personne, sous 24 h.",
    perVisit: EN ? "per visit" : "par visite",
    nameRequired: EN ? "Your name is required." : "Votre nom est requis.",
    contactRequired: EN ? "Add an email address or a phone number."
                        : "Ajoutez un courriel ou un téléphone.",
    consentRequired: EN ? "Your consent is required so we can answer."
                        : "Votre accord est requis pour vous répondre.",
    failed: EN ? "Sending failed. Call us at 514 242-4779 and we will take your request by phone."
               : "L'envoi a échoué. Appelez-nous au 514 242-4779 et nous prenons la demande au téléphone.",
    sending: EN ? "Sending…" : "Envoi…",
    submit: EN ? "Send my request" : "Envoyer ma demande",
    thanksFirm: EN ? "Your price is confirmed." : "Votre prix est confirmé.",
    thanksReview: EN ? "Thank you. Your written quote arrives within 24 hours."
                     : "Merci. Votre soumission écrite vous parvient sous 24 h.",
    reference: EN ? "Reference" : "Référence"
  };

  /* ---------- helpers ---------- */

  function value(name) {
    var el = form.elements[name];
    if (!el) return null;
    if (el instanceof RadioNodeList) return el.value || null;
    return el.value || null;
  }

  function checkedValues(name) {
    return Array.prototype.slice
      .call(form.querySelectorAll('input[name="' + name + '"]:checked'))
      .map(function (el) { return el.value; });
  }

  function number(name) {
    var raw = value(name);
    if (raw === null || raw === "") return null;
    var parsed = parseInt(raw, 10);
    return isNaN(parsed) ? null : parsed;
  }

  function audience() {
    var el = form.querySelector('input[name="audience"]:checked');
    return el ? el.value : "residential";
  }

  function formatMoney(cents) {
    return new Intl.NumberFormat(EN ? "en-CA" : "fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  function attribution() {
    var params = new URLSearchParams(window.location.search);
    var out = { landing_path: window.location.pathname };
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "gclid"].forEach(function (key) {
      var v = params.get(key);
      if (v) out[key] = v;
    });
    // Keep attribution across pages within the visit.
    try {
      var stored = sessionStorage.getItem("proline_attr");
      if (stored) out = Object.assign(JSON.parse(stored), out);
      sessionStorage.setItem("proline_attr", JSON.stringify(out));
    } catch (e) { /* private mode: attribution is best effort */ }
    return out;
  }

  /* ---------- conditional fields ---------- */

  function applyAudience() {
    var current = audience();
    form.querySelectorAll("[data-when]").forEach(function (el) {
      el.hidden = el.dataset.when !== current;
    });
    updatePrice();
  }

  form.querySelectorAll('input[name="audience"]').forEach(function (el) {
    el.addEventListener("change", applyAudience);
  });

  /* ---------- steps ---------- */

  function showStep(step) {
    form.querySelectorAll(".wizard-step").forEach(function (el) {
      el.hidden = el.dataset.step !== String(step);
    });
    form.querySelectorAll("[data-step-pill]").forEach(function (el) {
      if (el.dataset.stepPill === String(step)) el.setAttribute("aria-current", "step");
      else el.removeAttribute("aria-current");
    });
    applyAudience();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  form.addEventListener("click", function (event) {
    var next = event.target.closest("[data-next]");
    if (next) { showStep(next.dataset.next); return; }
    var prev = event.target.closest("[data-prev]");
    if (prev) showStep(prev.dataset.prev);
  });

  /* ---------- live price ---------- */

  function draftPayload() {
    return {
      audience: audience(),
      property: {
        property_type: value("property_type") || "house",
        area_sqft: number("area_sqft"),
        bedrooms: number("bedrooms"),
        bathrooms: number("bathrooms"),
        restrooms: number("restrooms"),
        floors: number("floors")
      },
      services: checkedValues("services"),
      frequency: value("frequency") || "one_time",
      extras: checkedValues("extras"),
      night_access: !!form.querySelector('input[name="night_access"]:checked')
    };
  }

  function clearPrice(message) {
    priceTotal.textContent = "—";
    priceLines.innerHTML = "";
    priceDisclaimer.hidden = true;
    priceNote.textContent = message;
  }

  var priceTimer = null;

  function updatePrice() {
    if (audience() !== "residential") {
      clearPrice(T.reviewed);
      return;
    }
    clearTimeout(priceTimer);
    priceTimer = setTimeout(function () {
      fetch("/api/quotes/price", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftPayload())
      })
        .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
        .then(function (price) {
          priceTotal.textContent = formatMoney(price.total_cents);
          priceNote.textContent = T.perVisit;
          priceLines.innerHTML = price.lines.map(function (line) {
            return '<div class="summary-line"><span>' + line.label_fr + "</span><span>" +
              formatMoney(line.amount_cents) + "</span></div>";
          }).join("");
          if (price.discount_cents) {
            priceLines.innerHTML +=
              '<div class="summary-line" style="color:var(--gold-ink);font-weight:600"><span>Rabais récurrent</span><span>−' +
              formatMoney(price.discount_cents) + "</span></div>";
          }
          priceDisclaimer.hidden = false;
        })
        .catch(function () { clearPrice(T.fillIn); });
    }, 350);
  }

  form.addEventListener("change", updatePrice);
  form.addEventListener("input", function (event) {
    if (event.target.name === "area_sqft") updatePrice();
  });

  /* ---------- submit ---------- */

  function validate() {
    if (!value("full_name")) return T.nameRequired;
    if (!value("email") && !value("phone")) return T.contactRequired;
    if (!form.querySelector('input[name="consent_given"]:checked')) return T.consentRequired;
    return null;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var problem = validate();
    if (problem) {
      errorBox.textContent = problem;
      errorBox.hidden = false;
      return;
    }
    errorBox.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = T.sending;

    var draft = draftPayload();
    var payload = {
      audience: draft.audience,
      property: draft.property,
      services: draft.services,
      frequency: draft.frequency,
      extras: draft.extras,
      night_access: draft.night_access,
      desired_start: value("desired_start"),
      access_notes: value("access_notes"),
      contact: {
        full_name: value("full_name"),
        email: value("email"),
        phone: value("phone"),
        company: value("company"),
        locale: locale,
        consent_given: true
      },
      attribution: attribution(),
      website: value("website")
    };

    fetch("/api/quotes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
      .then(function (result) {
        form.hidden = true;
        document.getElementById("summary").hidden = true;
        var done = document.getElementById("done");
        document.getElementById("done-title").textContent =
          EN ? result.message_en : result.message_fr;
        if (result.price) {
          var el = document.getElementById("done-price");
          el.textContent = formatMoney(result.price.total_cents);
          el.hidden = false;
        }
        document.getElementById("done-ref").textContent =
          T.reference + " : " + result.id.slice(0, 8);
        done.hidden = false;
        if (window.gtag) window.gtag("event", "generate_lead", { value: 1 });
        window.scrollTo({ top: 0, behavior: "smooth" });
      })
      .catch(function () {
        errorBox.textContent = T.failed;
        errorBox.hidden = false;
        submitBtn.disabled = false;
        submitBtn.textContent = T.submit;
      });
  });

  /* ---------- start ---------- */

  var initial = new URLSearchParams(window.location.search).get("audience");
  if (initial === "commercial") {
    var radio = form.querySelector('input[name="audience"][value="commercial"]');
    if (radio) radio.checked = true;
    var type = form.elements["property_type"];
    if (type) type.value = "office";
  }
  applyAudience();
  attribution();
})();
