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
    byArea: EN ? "counted from the area" : "calculé selon la superficie",
    howMany: EN ? "How many" : "Combien",
    fewer: EN ? "One fewer" : "Un de moins",
    more: EN ? "One more" : "Un de plus",
    /* 409: the grid has no cell for this home, or the admin has switched online
       pricing off. Both mean a person decides the price, which is not an error. */
    byHand: EN ? "We price this one by hand. Send the request and you have it within 24 hours."
               : "Celle-ci est chiffrée à la main. Envoyez la demande : vous l'avez sous 24 h.",
    byHandShort: EN ? "Priced by hand" : "Chiffré à la main",
    emailInvalid: EN ? "Check this email address — it looks incomplete."
                     : "Vérifiez ce courriel : il semble incomplet.",
    fixFields: EN ? "Some answers need a correction. We have marked them below."
                  : "Certaines réponses demandent une correction. Elles sont indiquées ci-dessous.",
    datePast: EN ? "Pick today or a later date." : "Choisissez aujourd'hui ou une date ultérieure.",
    minimumVisit: EN ? "Minimum visit" : "Visite minimum",
    roomsLimited: EN ? "Some combinations are quoted by a person rather than online."
                     : "Certaines combinaisons sont chiffrées par une personne plutôt qu'en ligne.",
    roomsMoved: EN ? "Adjusted to {n} bathrooms, the nearest one we price online."
                   : "Ajusté à {n} salles de bain, la combinaison la plus proche que nous chiffrons en ligne."
  };

  /* Honour the OS setting: a smooth scroll is motion too. */
  var reduceMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: reduceMotion.matches ? "auto" : "smooth" });
  }

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

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
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

  /* Local date, not UTC: a Montreal evening is already tomorrow in UTC. */
  function todayISO() {
    var d = new Date();
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  }

  function formatMoney(cents) {
    return new Intl.NumberFormat(EN ? "en-CA" : "fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  /* Totals round to the dollar; a unit price must not. At 4,50 $ per window the
     rounded form says "5 $", and six windows then bill 27 $ against a 30 $ the
     visitor did the arithmetic for. Cents show only when there are any. */
  function formatMoneyExact(cents) {
    var digits = cents % 100 === 0 ? 0 : 2;
    return new Intl.NumberFormat(EN ? "en-CA" : "fr-CA", {
      style: "currency", currency: "CAD",
      minimumFractionDigits: digits, maximumFractionDigits: digits
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

  /* ---------- draft persistence ----------
     A refresh, a backgrounded tab or a mis-tap used to wipe every answer and
     drop the visitor back on step 1. Keep the answers, never the consent tick:
     consent has to be an affirmative act each time. */

  var DRAFT_KEY = "proline_quote_draft_" + locale;

  function saveDraft() {
    try {
      var data = { step: currentStep, fields: {}, checks: {} };
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name || el.name === "website" || el.name === "consent_given") return;
        if (el.type === "checkbox" || el.type === "radio") {
          if (el.checked) {
            data.checks[el.name] = data.checks[el.name] || [];
            data.checks[el.name].push(el.value);
          }
        } else if (el.value) {
          data.fields[el.name] = el.value;
        }
      });
      localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
    } catch (e) { /* private mode: the draft is best effort */ }
  }

  /* Kept so the extras, which only exist once the rate card has answered, can be
     restored too -- they are not in the DOM when the draft is first applied. */
  var savedDraft = null;

  function applyDraft(data, only) {
    if (!data) return;
    Object.keys(data.fields || {}).forEach(function (name) {
      if (only && !only.test(name)) return;
      var el = form.elements[name];
      if (el && el.tagName) el.value = data.fields[name];
    });
    Object.keys(data.checks || {}).forEach(function (name) {
      if (only && !only.test(name)) return;
      (data.checks[name] || []).forEach(function (v) {
        var el = form.querySelector('[name="' + name + '"][value="' + CSS.escape(v) + '"]');
        if (el) el.checked = true;
      });
    });
  }

  /* The extras and their quantities: the only part of a draft that cannot be
     restored at load, because the rate card has not answered yet. */
  var EXTRA_FIELDS = /^(extras|qty_|mod_)/;

  function restoreDraft() {
    var raw = null;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return 1; }
    if (!raw) return 1;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return 1; }
    savedDraft = data;
    applyDraft(data);
    var step = Number(data.step) || 1;
    return step < 1 ? 1 : (step > 3 ? 3 : step);
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* nothing to clean */ }
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

  /* Spoken once, for changes the visitor did not make themselves. */
  var lastSaid = "";

  function sayPrice(text) {
    /* Only when the number actually moves. The price call is debounced and fires
       on every keystroke in the area field; announcing each result would talk
       over the typing. */
    if (text === lastSaid) return;
    lastSaid = text;
    say(text);
  }

  function say(message) {
    var region = document.getElementById("announce");
    if (!region) return;
    region.textContent = "";
    setTimeout(function () { region.textContent = message; }, 60);
  }

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
  var currentStep = 1;

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

  /* Paint a step without touching history — shared by showStep and popstate. */
  function renderStep(n) {
    if (n > furthest) furthest = n;
    currentStep = n;
    paintSteps(n);
    applyAudience();
    /* The control that got us here is now hidden, so focus would fall back to
       <body> and a screen reader would announce nothing at all. */
    var panel = form.querySelector('.wizard-step[data-step="' + n + '"]');
    if (panel && panel.focus) panel.focus({ preventScroll: true });
    scrollToTop();
  }

  function showStep(step, replace) {
    var n = Number(step);
    renderStep(n);
    saveDraft();
    /* Back on step 2 used to leave the site entirely. Give each step a history
       entry so Back means "previous question". */
    try {
      var state = { prolineStep: n };
      var hash = "#" + (EN ? "step-" : "etape-") + n;
      if (replace) history.replaceState(state, "", hash);
      else history.pushState(state, "", hash);
    } catch (e) { /* history unavailable: navigation still works */ }
  }

  window.addEventListener("popstate", function (event) {
    var n = event.state && event.state.prolineStep;
    if (n) renderStep(Number(n));
  });

  /* Each step is gated on its own, so nobody reaches "your details" with a
     request we cannot read. Errors land on the field, not in a box at the end. */
  function validateStep(step) {
    var ok = true;
    if (String(step) === "3") {
      if (!value("full_name")) { fieldError("full_name", T.nameRequired); ok = false; }
      else clearError("full_name");

      var email = value("email");
      if (!email && !value("phone")) { fieldError("contact", T.contactRequired); ok = false; }
      else if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
        fieldError("contact", T.emailInvalid); ok = false;
      } else clearError("contact");

      if (!form.querySelector('input[name="consent_given"]:checked')) {
        fieldError("consent_given", T.consentRequiredShort); ok = false;
      } else clearError("consent_given");
    }
    if (String(step) === "2") {
      var start = value("desired_start");
      if (start && start < todayISO()) { fieldError("desired_start", T.datePast); ok = false; }
      else clearError("desired_start");
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
    field.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "center" });
    /* #err-contact sits in a .field of its own with no input in it, so the one
       error most likely to block a send was also the one focus never reached. */
    var focusable = field.querySelector("input, select, textarea") ||
      (bad.id === "err-contact" ? form.elements.email : null);
    if (focusable && focusable.focus) focusable.focus({ preventScroll: true });
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

  /* ---------- extras, from the rate card ----------
     The form used to hard-code three checkboxes. Adding a fourth extra meant
     editing the French page, the English page and the engine, and a checkbox the
     card had no price for was collected and silently ignored. Now the card is the
     list: /api/quotes/form-config says what it can price, and this renders it.

     An extra billed per unit gets a stepper, because "windows: yes" is not a
     price -- four of them and forty are not the same job. */

  var extrasBox = document.getElementById("extras");
  var offers = {};
  var cells = null;   // "3br_2ba" -> true, from the active card

  function extraLabel(offer) {
    return (EN ? offer.label_en : offer.label_fr) || offer.label_fr || offer.code;
  }

  function extraUnit(offer) {
    return (EN ? offer.per_en : offer.per_fr) || "";
  }

  /* applyAudience() owns the `hidden` attribute on every [data-when] block, so a
     field hidden here has to say so another way or it reappears on the next
     change event. */
  function hideExtrasField() {
    if (!extrasBox) return;
    var field = extrasBox.closest(".field");
    if (field) field.dataset.empty = "yes";
  }

  function renderExtras(list) {
    if (!extrasBox) return;
    if (!list.length) { hideExtrasField(); return; }
    var field = extrasBox.closest(".field");
    if (field) delete field.dataset.empty;
    offers = {};

    /* The card hands them over keyed by code, so the visitor would read them in
       English alphabetical order in both languages -- "baseboards" first because
       of a b. Sort by what is actually on screen. */
    var ordered = list.slice().sort(function (a, b) {
      return extraLabel(a).localeCompare(extraLabel(b), EN ? "en-CA" : "fr-CA");
    });
    /* Reserve the quantity column only if something needs it, so a card with no
       per-unit extras does not leave a gap down the side. */
    if (ordered.some(function (o) { return o.unit === "each"; })) {
      extrasBox.dataset.steppers = "yes";
    } else {
      delete extrasBox.dataset.steppers;
    }

    extrasBox.innerHTML = ordered.map(function (offer) {
      offers[offer.code] = offer;
      var id = "extra-" + offer.code;
      var unit = extraUnit(offer);
      var price = formatMoneyExact(offer.cents) + (unit ? " " + esc(unit) : "");
      var html =
        '<div class="extra" data-extra="' + esc(offer.code) + '" data-unit="' + esc(offer.unit) + '">' +
          '<label class="choice" for="' + id + '">' +
            '<input type="checkbox" id="' + id + '" name="extras" value="' + esc(offer.code) + '"> ' +
            '<span class="extra-name">' + esc(extraLabel(offer)) + '</span>' +
            '<span class="extra-price">' + price + '</span>' +
          "</label>";
      if (offer.unit === "each") {
        html +=
          '<div class="stepper" hidden>' +
            '<button type="button" class="stepper-btn" data-delta="-1" aria-label="' +
              esc(T.fewer + " — " + extraLabel(offer)) + '">&minus;</button>' +
            '<input type="number" class="stepper-input" name="qty_' + esc(offer.code) + '" ' +
              'value="1" min="1" max="500" step="1" inputmode="numeric" ' +
              'aria-label="' + esc(T.howMany + " — " + extraLabel(offer)) + '">' +
            '<button type="button" class="stepper-btn" data-delta="1" aria-label="' +
              esc(T.more + " — " + extraLabel(offer)) + '">+</button>' +
          "</div>";
      } else if (offer.unit === "per_100sqft") {
        html += '<p class="extra-note">' + esc(T.byArea) + "</p>";
      }
      return html + "</div>";
    }).join("");
  }

  function extraQuantity(code) {
    var input = form.elements["qty_" + code];
    if (!input) return 1;
    var parsed = parseInt(input.value, 10);
    if (isNaN(parsed) || parsed < 1) return 1;
    return parsed > 500 ? 500 : parsed;
  }

  /* {code: quantity}. A flat extra is sent with 1; the card, not the form,
     decides whether the number means anything. */
  function extrasPayload() {
    var out = {};
    checkedValues("extras").forEach(function (code) {
      out[code] = offers[code] && offers[code].unit === "each" ? extraQuantity(code) : 1;
    });
    return out;
  }

  /* A stepper belongs to its checkbox: no quantity to give until the extra is
     wanted, and ticking one lands you on a sensible 1 rather than an empty box. */
  function syncSteppers() {
    if (!extrasBox) return;
    extrasBox.querySelectorAll(".extra").forEach(function (row) {
      var box = row.querySelector('input[type="checkbox"]');
      var stepper = row.querySelector(".stepper");
      row.dataset.on = box && box.checked ? "yes" : "no";
      if (stepper) stepper.hidden = !(box && box.checked);
    });
  }

  if (extrasBox) {
    extrasBox.addEventListener("click", function (event) {
      var button = event.target.closest(".stepper-btn");
      if (!button) return;
      var input = button.parentNode.querySelector(".stepper-input");
      if (!input) return;
      var next = (parseInt(input.value, 10) || 1) + Number(button.dataset.delta);
      input.value = next < 1 ? 1 : (next > 500 ? 500 : next);
      syncSteppers();
      saveDraft();
      updatePrice();
    });
    extrasBox.addEventListener("input", function (event) {
      if (event.target.classList.contains("stepper-input")) updatePrice();
    });
    /* The buttons clamped to 1..500 but typing did not, so the field could show
       9999 beside a price calculated from 500. Clamp on the way out of the
       field rather than mid-keystroke, which would fight the typing. */
    extrasBox.addEventListener("blur", function (event) {
      if (!event.target.classList || !event.target.classList.contains("stepper-input")) return;
      var clamped = extraQuantity(event.target.name.slice(4));
      if (String(clamped) !== event.target.value) {
        event.target.value = clamped;
        saveDraft();
        updatePrice();
      }
    }, true);
    extrasBox.addEventListener("change", syncSteppers);
  }

  /* ---------- the questions that change the price ----------
     Same rule as the extras: the card decides what is asked. A modifier whose
     every answer is free is not sent by form-config, so it is never rendered --
     asking "premier ménage ?" and charging the same either way wastes the
     visitor's time and teaches them the questions do not matter. */

  var modifiersBox = document.getElementById("modifiers");

  function modLabel(item) { return (EN ? item.label_en : item.label_fr) || item.label_fr; }
  function modHelp(item) { return (EN ? item.help_en : item.help_fr) || ""; }

  function renderModifiers(list) {
    if (!modifiersBox) return;
    modifiersBox.innerHTML = list.map(function (mod) {
      var help = modHelp(mod);
      var name = "mod_" + mod.code;
      return '<div class="field" data-modifier="' + esc(mod.code) + '">' +
        '<span class="field-label" id="lbl-' + esc(name) + '">' + esc(modLabel(mod)) + "</span>" +
        (help ? '<p class="note" id="help-' + esc(name) + '">' + esc(help) + "</p>" : "") +
        '<div class="choice-row" role="radiogroup" aria-labelledby="lbl-' + esc(name) + '"' +
          (help ? ' aria-describedby="help-' + esc(name) + '"' : "") + ">" +
        mod.options.map(function (option, index) {
          return '<label class="choice"><input type="radio" name="' + esc(name) + '" value="' +
            esc(option.value) + '"' + (index === 0 ? " checked" : "") + "> " +
            esc(modLabel(option)) + "</label>";
        }).join("") +
        "</div></div>";
    }).join("");
  }

  /* code -> the chosen option's value. The first option is pre-selected and is
     always the free one, so an untouched form prices as if nothing applied. */
  function modifiersPayload() {
    var out = {};
    if (!modifiersBox) return out;
    modifiersBox.querySelectorAll(".field[data-modifier]").forEach(function (row) {
      var chosen = row.querySelector("input:checked");
      if (chosen) out[row.dataset.modifier] = chosen.value;
    });
    return out;
  }

  /* ---------- the rooms the card can price ----------
     The grid is deliberately sparse: Amine prices the configurations he has
     actually cleaned and adds the rest later. Offering all twenty and sending
     the unpriced ones into "a person will call you" wastes the visitor's time
     after promising them a number, so the combinations with no price are shown
     as unavailable instead. */

  var bedroomsField = form.elements.bedrooms;
  var bathroomsField = form.elements.bathrooms;
  var roomsNote = document.getElementById("rooms-note");

  function cellKey(bedrooms, bathrooms) {
    return Math.min(bedrooms, 5) + "br_" + Math.min(bathrooms, 4) + "ba";
  }

  function optionValue(option) {
    return parseInt(option.value || option.text, 10);
  }

  function pricedBathrooms(bedrooms) {
    return Array.prototype.filter.call(bathroomsField.options, function (option) {
      return !!cells[cellKey(bedrooms, optionValue(option))];
    });
  }

  function applyCells() {
    if (!cells || !bedroomsField || !bathroomsField) return;

    /* Bedrooms first. Disabling only the bathrooms meant a bedroom count with no
       row at all left every bathroom option disabled and the visitor stuck in a
       select they could not change, with nothing on screen saying why. */
    Array.prototype.forEach.call(bedroomsField.options, function (option) {
      option.disabled = pricedBathrooms(optionValue(option)).length === 0;
    });
    var chosenBedrooms = bedroomsField.selectedOptions[0];
    if (chosenBedrooms && chosenBedrooms.disabled) {
      bedroomsField.value = nearest(bedroomsField, optionValue(chosenBedrooms));
    }

    var bedrooms = parseInt(bedroomsField.value, 10);
    var priced = pricedBathrooms(bedrooms);
    Array.prototype.forEach.call(bathroomsField.options, function (option) {
      option.disabled = priced.indexOf(option) === -1;
    });

    var chosen = bathroomsField.selectedOptions[0];
    if (priced.length && chosen && chosen.disabled) {
      var was = optionValue(chosen);
      bathroomsField.value = nearest(bathroomsField, was);
      /* Their answer just changed under them and the price with it. Say so: a
         number that moves on its own is the kind of thing that costs trust. */
      say(T.roomsMoved.replace("{n}", bathroomsField.value));
    }
    if (roomsNote) {
      var missing = bathroomsField.options.length - priced.length;
      roomsNote.textContent = missing ? T.roomsLimited : "";
      roomsNote.hidden = !missing;
    }
  }

  function nearest(field, want) {
    var options = Array.prototype.filter.call(field.options, function (o) { return !o.disabled; });
    options.sort(function (a, b) {
      return Math.abs(optionValue(a) - want) - Math.abs(optionValue(b) - want);
    });
    return options[0].value || options[0].text;
  }

  if (bedroomsField && bedroomsField.addEventListener) {
    bedroomsField.addEventListener("change", applyCells);
  }

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
      extras: commercial ? {} : extrasPayload(),
      modifiers: commercial ? {} : modifiersPayload(),
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
    sayPrice(message);
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
          sayPrice(formatMoney(price.total_cents) + " " + T.perVisit);
          priceLines.innerHTML = price.lines.map(function (line) {
            /* "Vitres intérieures × 6 par fenêtre", so a 24 $ line explains itself
               and nobody has to trust the total on faith. */
            var unit = (EN ? line.unit_en : line.unit_fr) || line.unit_fr;
            var detail = line.quantity
              ? ' <span class="line-qty">× ' + esc(line.quantity) +
                (unit ? " " + esc(unit) : "") + "</span>"
              : "";
            return '<div class="summary-line"><span>' + esc(lineLabel(line)) + detail +
              "</span><span>" + formatMoney(line.amount_cents) + "</span></div>";
          }).join("");
          if (price.discount_cents) {
            priceLines.innerHTML +=
              '<div class="summary-line" style="color:var(--gold-ink);font-weight:600"><span>' +
              (EN ? "Recurring discount" : "Rabais récurrent") + '</span><span>−' +
              formatMoney(price.discount_cents) + "</span></div>";
          }
          /* The floor almost never bites, but when it does the lines have to
             explain the total rather than quietly fail to add up to it. */
          if (price.minimum_adjustment_cents) {
            priceLines.innerHTML +=
              '<div class="summary-line"><span>' + T.minimumVisit + "</span><span>+" +
              formatMoney(price.minimum_adjustment_cents) + "</span></div>";
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
      modifiers: draft.modifiers,
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
      .then(function (res) {
        if (res.ok) return res.json();
        /* A rejected field is not an outage. Read the 422 so the visitor is told
           which answer to fix, instead of being sent to the phone. */
        if (res.status === 422) {
          return res.json().then(function (body) {
            return Promise.reject({ status: 422, body: body });
          }, function () { return Promise.reject({ status: 422 }); });
        }
        return Promise.reject({ status: res.status });
      })
      .then(function (result) {
        clearDraft();
        form.hidden = true;
        document.getElementById("summary").hidden = true;
        var bar = document.getElementById("pricebar");
        if (bar) bar.hidden = true;
        var done = document.getElementById("done");
        document.getElementById("done-title").textContent =
          EN ? result.message_en : result.message_fr;
        if (result.price) {
          var el = document.getElementById("done-price");
          el.textContent = formatMoney(result.price.total_cents);
          el.hidden = false;
        }
        document.getElementById("done-ref").textContent =
          T.reference + (EN ? ": " : " : ") + result.id.slice(0, 8);
        done.hidden = false;
        if (done.focus) done.focus({ preventScroll: true });
        if (window.gtag) window.gtag("event", "generate_lead", { value: 1 });
        scrollToTop();
      })
      .catch(function (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = T.submit;
        if (err && err.status === 422) {
          if (applyServerErrors(err.body)) {
            errorBox.textContent = T.fixFields;
            errorBox.hidden = false;
            showStep(3);
            focusFirstError();
            return;
          }
        }
        errorBox.textContent = T.failed;
        errorBox.hidden = false;
      });
  });

  /* FastAPI reports {detail: [{loc: ["body", "contact", "email"], msg: ...}]}.
     Only the contact fields are reachable by a visitor, so map those and treat
     anything else as a genuine failure. */
  function applyServerErrors(body) {
    var detail = body && body.detail;
    if (!Array.isArray(detail)) return false;
    var handled = false;
    detail.forEach(function (item) {
      var loc = item && item.loc;
      if (!Array.isArray(loc)) return;
      var field = loc[loc.length - 1];
      if (field === "email") { fieldError("contact", T.emailInvalid); handled = true; }
      else if (field === "full_name") { fieldError("full_name", T.nameRequired); handled = true; }
      else if (field === "phone") { fieldError("contact", T.contactRequired); handled = true; }
    });
    return handled;
  }

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
  var startStep = restoreDraft();
  var startInput = form.querySelector('input[name="desired_start"]');
  if (startInput && !startInput.min) startInput.min = todayISO();

  form.addEventListener("input", saveDraft);
  form.addEventListener("change", saveDraft);

  furthest = startStep;
  showStep(startStep, true);
  updatePrice();
  attribution();

  /* The card decides what the form may ask. If this call fails the form still
     works -- the visitor simply gets no extras, which is honest: we could not
     have priced them anyway. */
  fetch("/api/quotes/form-config")
    .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
    .then(function (config) {
      renderModifiers(config.modifiers || []);
      renderExtras(config.extras || []);
      cells = {};
      (config.residential_cells || []).forEach(function (key) { cells[key] = true; });
      applyDraft(savedDraft, EXTRA_FIELDS);
      syncSteppers();
      applyCells();
      updatePrice();
    })
    .catch(hideExtrasField);
})();
