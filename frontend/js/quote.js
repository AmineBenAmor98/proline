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
    failed: EN ? "Sending failed. Call us at 514 242-4779 and we will take your request by phone."
               : "L'envoi a échoué. Appelez-nous au 514 242-4779 et nous prenons la demande au téléphone.",
    sending: EN ? "Sending…" : "Envoi…",
    submit: EN ? "Send my request" : "Envoyer ma demande",
    thanksFirm: EN ? "Your price is confirmed." : "Votre prix est confirmé.",
    thanksReview: EN ? "Thank you. Your written quote arrives within 24 hours."
                     : "Merci. Votre soumission écrite vous parvient sous 24 h.",
    reference: EN ? "Reference" : "Référence",
    chooseType: EN ? "Pick a type of place and your price appears here."
                   : "Choisissez un type de lieu : le prix apparaît ici.",
    chooseTypeShort: EN ? "Pick a type of place" : "Choisissez un type de lieu",
    typeRequired: EN ? "Choose the type of place." : "Choisissez le type de lieu.",
    consentRequiredShort: EN ? "Tick this so we may answer you."
                             : "Cochez pour que nous puissions vous répondre.",
    areaRequired: EN ? "Give an approximate area, even a rough one."
                     : "Indiquez une superficie approximative, même grossière.",
    areaRange: EN ? "Enter an area between 100 and 1,000,000 sq ft."
                  : "Entrez une superficie entre 100 et 1 000 000 pi².",
    quotedIn24: EN ? "Quoted within 24 h" : "Chiffré sous 24 h",
    /* 409: the grid has no cell for this home, or the admin has switched online
       pricing off. Both mean a person decides the price, which is not an error. */
    byHand: EN ? "We price this one by hand. Send the request and you have it within 24 hours."
               : "Celle-ci est chiffrée à la main. Envoyez la demande : vous l'avez sous 24 h.",
    byHandShort: EN ? "Priced by hand" : "Chiffré à la main"
  };

  /* Price lines arrive in both languages; render the one this page is written in. */
  function lineLabel(line) {
    return (EN ? line.label_en : line.label_fr) || line.label_fr || line.code;
  }

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

  /* The property type IS the branching choice: each tile declares the audience it
     belongs to, so the two can never contradict each other. Null until they pick. */
  function audience() {
    var el = form.querySelector('input[name="property_type"]:checked');
    return el ? el.dataset.audience : null;
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

  /* ---------- inline errors ---------- */

  function fieldError(name, message) {
    var box = document.getElementById("err-" + name);
    if (!box) return;
    box.textContent = message;
    box.hidden = !message;
    var input = form.elements[name];
    if (input && input.setAttribute) {
      if (message) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function clearError(name) { fieldError(name, ""); }

  /* ---------- running price bar (small screens) ---------- */

  var barValue = document.getElementById("pricebar-value");

  function setBar(text, isMoney) {
    if (!barValue) return;
    barValue.textContent = text;
    barValue.classList.toggle("is-text", !isMoney);
  }

  /* ---------- conditional fields ---------- */

  function applyAudience() {
    var current = audience();
    form.querySelectorAll("[data-when]").forEach(function (el) {
      el.hidden = el.dataset.when !== current;
    });
    updatePrice();
  }

  form.querySelectorAll('input[name="property_type"]').forEach(function (el) {
    el.addEventListener("change", function () {
      clearError("property_type");
      applyAudience();
    });
  });

  /* ---------- steps ---------- */

  var furthest = 1;

  /* Painting is separate from navigating so the first paint does not scroll the
     page, and so a pill is disabled from the very first render rather than only
     after the visitor has moved once. */
  function paintSteps(n) {
    form.querySelectorAll(".wizard-step").forEach(function (el) {
      el.hidden = el.dataset.step !== String(n);
    });
    form.querySelectorAll("[data-step-pill]").forEach(function (el) {
      var pill = Number(el.dataset.stepPill);
      if (pill === n) {
        el.setAttribute("aria-current", "step");
        el.dataset.state = "current";
      } else {
        el.removeAttribute("aria-current");
        el.dataset.state = pill < furthest ? "done" : "locked";
      }
      el.disabled = pill > furthest;
    });
  }

  function showStep(step) {
    var n = Number(step);
    if (n > furthest) furthest = n;
    paintSteps(n);
    applyAudience();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* Each step is gated on its own, so nobody reaches "your details" with a
     request we cannot read. Errors land on the field, not in a box at the end. */
  function validateStep(step) {
    var ok = true;
    if (String(step) === "3") {
      if (!value("full_name")) { fieldError("full_name", T.nameRequired); ok = false; }
      else clearError("full_name");

      if (!value("email") && !value("phone")) { fieldError("contact", T.contactRequired); ok = false; }
      else clearError("contact");

      if (!form.querySelector('input[name="consent_given"]:checked')) {
        fieldError("consent_given", T.consentRequiredShort); ok = false;
      } else clearError("consent_given");
    }
    if (String(step) === "1") {
      if (audience() === null) { fieldError("property_type", T.typeRequired); ok = false; }
      else clearError("property_type");

      var area = number("area_sqft");
      if (area === null) { fieldError("area_sqft", T.areaRequired); ok = false; }
      else if (area < 100 || area > 1000000) { fieldError("area_sqft", T.areaRange); ok = false; }
      else clearError("area_sqft");
    }
    return ok;
  }

  function focusFirstError() {
    var bad = form.querySelector('[aria-invalid="true"], .field-error:not([hidden])');
    if (!bad) return;
    var field = bad.closest(".field") || bad;
    field.scrollIntoView({ behavior: "smooth", block: "center" });
    var focusable = field.querySelector("input, select, textarea");
    if (focusable) focusable.focus({ preventScroll: true });
  }

  form.addEventListener("click", function (event) {
    var next = event.target.closest("[data-next]");
    if (next) {
      var from = Number(next.dataset.next) - 1;
      if (!validateStep(from)) { focusFirstError(); return; }
      showStep(next.dataset.next);
      return;
    }
    var prev = event.target.closest("[data-prev]");
    if (prev) { showStep(prev.dataset.prev); return; }

    /* Pills go back to a step already completed. Jumping forward would skip the
       gate, so a step not yet reached is disabled rather than silently ignored. */
    var pill = event.target.closest("[data-goto]");
    if (pill && !pill.disabled) showStep(pill.dataset.goto);
  });

  /* ---------- live price ---------- */

  function draftPayload() {
    /* Only send the fields that belong to this audience. The hidden block keeps its
       values, so a shop would otherwise be filed with three bedrooms. */
    var who = audience();
    var property = { property_type: value("property_type"), area_sqft: number("area_sqft") };
    if (who === "residential") {
      property.bedrooms = number("bedrooms");
      property.bathrooms = number("bathrooms");
    } else if (who === "commercial") {
      property.restrooms = number("restrooms");
      property.floors = number("floors");
    }
    var commercial = who === "commercial";
    return {
      audience: who,
      property: property,
      /* Same reason: services and extras sit in the hidden half of the form and
         stay ticked when someone changes their mind about the type of place. */
      services: commercial ? checkedValues("services") : [],
      frequency: value("frequency") || "one_time",
      extras: commercial ? [] : checkedValues("extras"),
      night_access: commercial && !!form.querySelector('input[name="night_access"]:checked')
    };
  }

  function clearPrice(message, barText) {
    /* No dash pretending to be a price: for commercial there is no number to show. */
    priceTotal.hidden = true;
    priceTotal.textContent = "";
    priceLines.innerHTML = "";
    priceDisclaimer.hidden = true;
    priceNote.textContent = message;
    setBar(barText || (audience() === "commercial" ? T.quotedIn24 : T.chooseTypeShort), false);
  }

  var priceTimer = null;

  function updatePrice() {
    var who = audience();
    /* Drop any request still queued from the previous choice: switching from a
       home to a shop would otherwise fire a residential price call as commercial
       and come back 403. */
    clearTimeout(priceTimer);
    if (who === null) { clearPrice(T.chooseType); return; }
    if (who !== "residential") { clearPrice(T.reviewed); return; }
    priceTimer = setTimeout(function () {
      fetch("/api/quotes/price", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftPayload())
      })
        .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
        .then(function (price) {
          priceTotal.hidden = false;
          priceTotal.textContent = formatMoney(price.total_cents);
          priceNote.textContent = T.perVisit;
          setBar(formatMoney(price.total_cents), true);
          priceLines.innerHTML = price.lines.map(function (line) {
            return '<div class="summary-line"><span>' + lineLabel(line) + "</span><span>" +
              formatMoney(line.amount_cents) + "</span></div>";
          }).join("");
          if (price.discount_cents) {
            priceLines.innerHTML +=
              '<div class="summary-line" style="color:var(--gold-ink);font-weight:600"><span>' +
              (EN ? "Recurring discount" : "Rabais récurrent") + '</span><span>−' +
              formatMoney(price.discount_cents) + "</span></div>";
          }
          priceDisclaimer.hidden = false;
        })
        .catch(function (status) {
          if (status === 409) clearPrice(T.byHand, T.byHandShort);
          else clearPrice(T.fillIn);
        });
    }, 350);
  }

  form.addEventListener("change", updatePrice);
  form.addEventListener("input", function (event) {
    if (event.target.name === "area_sqft") { clearError("area_sqft"); updatePrice(); }
  });

  /* ---------- submit ---------- */

  /* The error box is kept for one thing only: a send that failed on the network.
     Everything the visitor can fix is reported on the field itself. */
  form.addEventListener("input", function (event) {
    var name = event.target.name;
    if (name === "full_name") clearError("full_name");
    if (name === "email" || name === "phone") clearError("contact");
  });
  form.addEventListener("change", function (event) {
    if (event.target.name === "consent_given") clearError("consent_given");
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    /* Re-check every step, not just this one: someone can walk back with the pills,
       empty a field and return here. */
    var bad = [1, 2, 3].filter(function (n) { return !validateStep(n); });
    if (bad.length) {
      showStep(bad[0]);
      focusFirstError();
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

  /* Someone arriving from the commercial page has told us which half they are in,
     but not which kind of building. Lead with their group instead of guessing a
     tile for them: intent respected, choice still theirs. */
  var initial = new URLSearchParams(window.location.search).get("audience");
  var groups = document.getElementById("typegroups");
  if (groups && (initial === "commercial" || initial === "residential")) {
    var wanted = groups.querySelector('[data-group="' + initial + '"]');
    if (wanted) groups.prepend(wanted);
  }
  paintSteps(1);
  applyAudience();
  attribution();
})();
