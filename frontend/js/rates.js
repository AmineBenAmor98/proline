/* The rate card screen.
 *
 * Everything on this page edits a DRAFT held in the browser. Nothing reaches a
 * visitor until Publier, which POSTs a whole card and gets back a new version.
 * The draft survives a refresh (localStorage) so a half-finished change is not
 * lost by a stray reload.
 */
(function () {
  "use strict";

  var A = window.ProlineAdmin;
  var DRAFT_KEY = "proline_rate_draft";

  var SERVICE_LABELS = {
    office_cleaning: "Entretien de bureaux",
    common_areas: "Aires communes",
    post_construction: "Post-construction",
    end_of_lease: "Fin de bail",
    floor_stripping_waxing: "Décapage et cirage",
    carpets: "Tapis"
  };
  /* No EXTRA_LABELS table here. An extra's wording lives on the card, in both
     languages, and this screen is where it is edited. */
  var UNIT_LABELS = {
    flat: "forfait",
    each: "à l'unité",
    per_100sqft: "par 100 pi²"
  };
  var UNIT_NOTE = {
    flat: "Un seul prix, quelle que soit la quantité.",
    each: "Multiplié par le nombre demandé.",
    per_100sqft: "Multiplié par la superficie, arrondie au 100 pi² supérieur."
  };
  var FREQUENCY_LABELS = A.FREQUENCY_LABELS;
  var FIELD_LABELS = {
    hourly_rate_cents: "Taux horaire",
    minimum_visit_cents: "Visite minimum",
    travel_cents: "Déplacement",
    residential_area_allowance_sqft: "Superficie incluse",
    residential_area_cents_per_100sqft: "Supplément par 100 pi²",
    minutes_per_restroom: "Par sanitaire",
    night_access_multiplier: "Majoration de soir"
  };

  var SCENARIOS = [
    { label: "Condo 3 ch. / 2 sdb", audience: "residential", property_type: "condo",
      area_sqft: 1400, bedrooms: 3, bathrooms: 2, frequency: "biweekly",
      extras: { oven: 1, windows: 8 } },
    /* The hard first job, deliberately: this is the scenario that exercises the
       modifiers, so a decimal slip in one of them moves a number here instead of
       reaching a visitor. */
    { label: "Maison 4 ch. / 3 sdb — premier ménage", audience: "residential",
      property_type: "house", area_sqft: 2600, bedrooms: 4, bathrooms: 3,
      frequency: "one_time", extras: {},
      modifiers: { premier_menage: "yes", etat: "tres_sale" } },
    { label: "Bureau 5 000 pi²", audience: "commercial", property_type: "office",
      area_sqft: 5000, restrooms: 4, frequency: "weekly",
      services: ["office_cleaning"], night_access: true }
  ];

  var active = null;   // the published card, as loaded
  var draft = null;    // what the form is editing
  var chosen = 0;      // which scenario the tester is showing
  var previewTimer = null;

  /* The rail. Every entry has a section behind it -- this list and the
     data-section attributes in tarifs.html are the same eight things, and a
     later phase adds a row here plus a box there, nothing else.

     `keys` says which of flatten()'s keys belong to a section, so the rail can
     mark the sections holding unpublished edits -- and name them on hover --
     without a second source of truth about what lives where. */
  var SECTIONS = [
    { group: "Général", id: "gen-minimum", label: "Minimum et déplacement",
      keys: ["minimum_visit_cents", "travel_cents"] },
    { group: "Général", id: "gen-frequency", label: "Rabais de fréquence",
      keys: ["disc:"] },
    { group: "Résidentiel", id: "res-grid", label: "Grille de base",
      keys: ["base:"] },
    { group: "Résidentiel", id: "res-area", label: "Superficie",
      keys: ["residential_area_allowance_sqft", "residential_area_cents_per_100sqft"] },
    { group: "Résidentiel", id: "res-modifiers", label: "Modificateurs",
      keys: ["mod:", "max_residential_multiplier"] },
    { group: "Résidentiel", id: "res-extras", label: "Extras et unités",
      keys: ["extra:", "extraunit:", "extrafr:", "extraen:"] },
    { group: "Commercial", id: "com-rates", label: "Cadences par service",
      keys: ["hourly_rate_cents", "min:", "minutes_per_restroom", "night_access_multiplier"] },
    { group: "Historique", id: "history", label: "Versions publiées", keys: [] }
  ];
  var SECTION_KEY = "proline_rate_section";

  var el = {
    editor: document.getElementById("editor"),
    loading: document.getElementById("loading"),
    pageError: document.getElementById("page-error"),
    draftbar: document.getElementById("draftbar"),
    draftBase: document.getElementById("draft-base"),
    draftTitle: document.getElementById("draft-title"),
    draftCount: document.getElementById("draft-count"),
    publish: document.getElementById("publish-btn"),
    discard: document.getElementById("discard-btn"),
    rail: document.getElementById("rail"),
    matrix: document.getElementById("matrix"),
    warnings: document.getElementById("matrix-warnings"),
    minutes: document.getElementById("minutes-rows"),
    extras: document.getElementById("extras-rows"),
    modifiers: document.getElementById("modifier-rows"),
    discounts: document.getElementById("discount-rows"),
    history: document.getElementById("history"),
    scenarios: document.getElementById("scenarios"),
    result: document.getElementById("tester-result"),
    kill: document.getElementById("kill-switch"),
    killNote: document.getElementById("kill-note"),
    review: document.getElementById("review"),
    reviewIntro: document.getElementById("review-intro"),
    reviewChanges: document.getElementById("review-changes"),
    reviewEffect: document.getElementById("review-effect"),
    reviewError: document.getElementById("review-error")
  };

  /* ---------- draft plumbing ---------- */

  /* `residential_modifiers` is defaulted HERE, once, rather than at each use.
     A card seeded before modifiers existed has no such key at all -- and that is
     precisely the card the "Ajouter les questions habituelles" button exists to
     fix, so the button was reading `undefined[code]` and throwing on the only
     card it was ever meant to be clicked on. Every reader downstream was already
     writing `|| {}`; the one writer was not, which is the argument for
     normalising the shape at the boundary instead of defending at each use. */
  function cardFrom(source) {
    var grid = JSON.parse(JSON.stringify(source.grid || {}));
    if (!grid.residential_modifiers) grid.residential_modifiers = {};
    return {
      hourly_rate_cents: source.hourly_rate_cents,
      minimum_visit_cents: source.minimum_visit_cents,
      travel_cents: source.travel_cents,
      grid: grid
    };
  }

  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ base: active.version, card: draft })); }
    catch (e) { /* private mode: the draft simply does not survive a reload */ }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
  }

  function loadDraft(baseVersion) {
    try {
      var saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      /* A draft built on a card that is no longer active is stale: the grid it was
         based on has been replaced, so its numbers no longer mean what they meant. */
      /* Through cardFrom, not straight out: a draft stored by an older page --
         or built from a card with no modifiers -- gets the same normalised shape
         a fresh one does, so restoring a draft can never reintroduce the missing
         key the loader just fixed. */
      if (saved && saved.base === baseVersion && saved.card) return cardFrom(saved.card);
    } catch (e) { /* ignore */ }
    return null;
  }

  /* ---------- diffing ---------- */

  function flatten(card) {
    var flat = {};
    ["hourly_rate_cents", "minimum_visit_cents", "travel_cents"].forEach(function (key) {
      flat[key] = { value: card[key], kind: "money", label: FIELD_LABELS[key] };
    });
    var g = card.grid || {};
    flat.residential_area_allowance_sqft =
      { value: g.residential_area_allowance_sqft, kind: "int", unit: " pi²", label: FIELD_LABELS.residential_area_allowance_sqft };
    flat.residential_area_cents_per_100sqft =
      { value: g.residential_area_cents_per_100sqft, kind: "money", label: FIELD_LABELS.residential_area_cents_per_100sqft };
    flat.minutes_per_restroom =
      { value: g.minutes_per_restroom, kind: "int", unit: " min", label: FIELD_LABELS.minutes_per_restroom };
    flat.night_access_multiplier =
      { value: g.night_access_multiplier, kind: "decimal", label: FIELD_LABELS.night_access_multiplier };
    Object.keys(g.residential_base_cents || {}).forEach(function (key) {
      flat["base:" + key] = { value: g.residential_base_cents[key], kind: "money", label: cellLabel(key) };
    });
    Object.keys(g.minutes_per_100sqft || {}).forEach(function (key) {
      flat["min:" + key] = { value: g.minutes_per_100sqft[key], kind: "int", unit: " min",
                             label: SERVICE_LABELS[key] || key };
    });
    Object.keys(g.extras || {}).forEach(function (key) {
      var spec = g.extras[key] || {};
      var name = spec.label_fr || key;
      flat["extra:" + key] = { value: spec.cents, kind: "money", label: name };
      /* Unit and wording in one row: they are one decision, and two rows saying
         "à l'unité" and "par fenêtre" separately read like two changes. */
      flat["extraunit:" + key] = {
        value: (UNIT_LABELS[spec.unit] || spec.unit) + (spec.per_fr ? " · " + spec.per_fr : ""),
        kind: "text", label: name + " — facturation"
      };
      flat["extrafr:" + key] = { value: name, kind: "text", label: "Extra " + key + " — nom" };
      flat["extraen:" + key] = { value: spec.label_en || key, kind: "text",
                                 label: "Extra " + key + " — nom (EN)" };
    });
    flat.max_residential_multiplier = {
      value: g.max_residential_multiplier || "2.5", kind: "decimal",
      label: "Plafond des multiplicateurs"
    };
    Object.keys(g.residential_modifiers || {}).forEach(function (code) {
      var mod = g.residential_modifiers[code];
      var name = mod.short_fr || mod.label_fr || code;
      (mod.options || []).forEach(function (option, index) {
        /* Normalised, because this string IS the equality test. Raw, an option
           carrying no multiplier read "undefined/undefined" while the same
           option after one save read "1/0" -- identical in meaning, different as
           text, so the draft would report a change nobody made. */
        var n = modifierNumbers(option);
        flat["mod:" + code + ":" + index] = {
          value: n.mult + "/" + n.cents, kind: "text",
          label: name + " — " + (option.label_fr || "réponse " + (index + 1)),
          shown: modifierShow(option)
        };
      });
    });
    Object.keys(g.frequency_discount_pct || {}).forEach(function (key) {
      flat["disc:" + key] = { value: g.frequency_discount_pct[key], kind: "pct",
                              label: "Rabais — " + (FREQUENCY_LABELS[key] || key) };
    });
    return flat;
  }

  /* A free answer carries NO multiplier key at all -- that is what "free" is on a
     preset -- so `String(option.multiplier) !== "1"` was true for it and the
     publish dialog offered "× undefined" as the thing about to be published, on
     the one screen whose entire job is to be read before committing prices.
     Parsed the way the editor parses it (absent, "", "1" and 1 all mean 1), so
     the two screens describe the same option with the same words. */
  function modifierNumbers(option) {
    return {
      mult: A.parseDecimalStrict(String(option.multiplier)) || 1,
      cents: option.cents || 0
    };
  }

  function modifierShow(option) {
    var n = modifierNumbers(option);
    var bits = [];
    if (n.mult !== 1) bits.push("× " + n.mult);
    if (n.cents) bits.push("+ " + A.moneyExact(n.cents));
    return bits.length ? bits.join(" · ") : "gratuit";
  }

  function show(entry) {
    if (entry === undefined || entry === null || entry.value === undefined || entry.value === null) return "—";
    if (entry.shown) return entry.shown;
    if (entry.kind === "money") return A.moneyExact(entry.value);
    if (entry.kind === "pct") return entry.value + " %";
    if (entry.kind === "decimal") return "× " + entry.value;
    if (entry.kind === "text") return String(entry.value);
    return entry.value + (entry.unit || "");
  }

  /* An extra that appears or disappears is ONE change, not four.
     flatten() gives it a key per field, which is right for "the price moved" and
     wrong for "this extra is new": four rows saying "— → …" bury the two real
     edits made at the same time. */
  function extraSummary(spec) {
    var parts = [A.moneyExact(spec.cents), UNIT_LABELS[spec.unit] || spec.unit];
    if (spec.per_fr) parts.push(spec.per_fr);
    return parts.join(" · ");
  }

  function changes() {
    var before = flatten(cardFrom(active));
    var after = flatten(draft);
    var wasExtras = (cardFrom(active).grid || {}).extras || {};
    var nowExtras = draft.grid.extras || {};
    var out = [];

    Object.keys(nowExtras).sort().forEach(function (code) {
      if (wasExtras[code]) return;
      out.push({ key: "extra:" + code,
                 label: "Nouvel extra — " + (nowExtras[code].label_fr || code),
                 from: "—", to: extraSummary(nowExtras[code]) });
    });
    Object.keys(wasExtras).sort().forEach(function (code) {
      if (nowExtras[code]) return;
      out.push({ key: "extra:" + code,
                 label: "Extra retiré — " + (wasExtras[code].label_fr || code),
                 from: extraSummary(wasExtras[code]), to: "retiré" });
    });

    function isSettled(key) {
      var colon = key.indexOf(":");
      if (colon < 0 || key.slice(0, colon).indexOf("extra") !== 0) return false;
      var code = key.slice(colon + 1);
      return !wasExtras[code] || !nowExtras[code];
    }

    Object.keys(after).forEach(function (key) {
      if (isSettled(key)) return;
      var was = before[key];
      if (!was) {
        out.push({ key: key, label: after[key].label, from: "—", to: show(after[key]) });
        return;
      }
      if (String(was.value) !== String(after[key].value)) {
        out.push({ key: key, label: after[key].label, from: show(was), to: show(after[key]) });
      }
    });
    Object.keys(before).forEach(function (key) {
      if (isSettled(key)) return;
      if (!after[key]) {
        out.push({ key: key, label: before[key].label, from: show(before[key]), to: "retiré" });
      }
    });
    return out;
  }

  function cellLabel(key) {
    var parts = key.split("_");
    return parts[0].replace("br", " ch.") + " / " + parts[1].replace("ba", " sdb");
  }

  /* ---------- rendering ---------- */

  function matrixKey(bed, bath) { return bed + "br_" + bath + "ba"; }

  function renderMatrix() {
    var base = draft.grid.residential_base_cents || {};
    var before = (active.grid || {}).residential_base_cents || {};
    /* Two header rows, so the table says what it is.

       It used to repeat "sdb" across the top and "chambres" down the side, with
       an empty corner and nothing naming either axis -- you had to already know
       the grid was bedrooms by bathrooms, and know that "sdb" is a bathroom.
       Naming each axis once leaves the cells as plain numbers. */
    var head =
      '<thead><tr><td class="corner"></td>' +
      '<th class="axis" colspan="4" scope="colgroup">Salles de bain</th></tr>' +
      '<tr><th class="axis" scope="col">Chambres</th>';
    for (var bath = 1; bath <= 4; bath++) head += '<th scope="col">' + bath + "</th>";
    head += "</tr></thead>";

    var body = "<tbody>";
    for (var bed = 1; bed <= 5; bed++) {
      body += '<tr><th scope="row">' + bed + "</th>";
      for (var b = 1; b <= 4; b++) {
        var key = matrixKey(bed, b);
        if (Object.prototype.hasOwnProperty.call(base, key)) {
          var was = before[key];
          var moved = was !== undefined && was !== base[key];
          body += '<td class="cell' + (moved ? " changed" : "") + '">' +
            '<input data-cell="' + key + '" inputmode="decimal" aria-label="' +
              A.esc("Prix — " + cellLabel(key)) + '" value="' + A.moneyExact(base[key]) + '">' +
            '<button type="button" class="cell-remove" data-remove="' + key + '" title="Retirer" ' +
              'aria-label="' + A.esc("Retirer " + cellLabel(key)) + '">×</button>' +
            (moved ? '<span class="was">était ' + A.moneyExact(was) + "</span>" : "") +
            "</td>";
        } else {
          body += '<td class="cell empty"><button type="button" data-add="' + key +
            '" aria-label="' + A.esc("Ajouter un prix pour " + cellLabel(key)) + '">+ ajouter</button></td>';
        }
      }
      body += "</tr>";
    }
    el.matrix.innerHTML = head + body + "</tbody>";
    renderMatrixWarnings();
  }

  /* Not validation: a nudge when a bigger home costs less than a smaller one, which
     is nearly always a typo and nearly always invisible in a list of numbers. */
  /* Update one cell's "était" label in place. A full re-render on every keystroke
     would take the focus out of the field being typed into. */
  function markCell(node, key) {
    var td = node.closest("td");
    if (!td) return;
    var was = ((active.grid || {}).residential_base_cents || {})[key];
    var moved = was !== undefined && was !== draft.grid.residential_base_cents[key];
    td.classList.toggle("changed", moved);
    var label = td.querySelector(".was");
    if (moved) {
      if (!label) {
        label = document.createElement("span");
        label.className = "was";
        td.appendChild(label);
      }
      label.textContent = "était " + A.moneyExact(was);
    } else if (label) {
      label.remove();
    }
  }

  function renderMatrixWarnings() {
    var base = draft.grid.residential_base_cents || {};
    var notes = [];
    Object.keys(base).forEach(function (key) {
      var bed = parseInt(key, 10);
      var bath = parseInt(key.split("_")[1], 10);
      [[matrixKey(bed + 1, bath), "une chambre de plus"], [matrixKey(bed, bath + 1), "une salle de bain de plus"]]
        .forEach(function (pair) {
          var bigger = base[pair[0]];
          if (bigger !== undefined && bigger < base[key]) {
            notes.push(cellLabel(pair[0]) + " (" + A.moneyExact(bigger) + ") coûte moins que " +
              cellLabel(key) + " (" + A.moneyExact(base[key]) + ") malgré " + pair[1] + ".");
          }
        });
    });
    var min = draft.minimum_visit_cents;
    Object.keys(base).forEach(function (key) {
      if (base[key] < min) {
        notes.push(cellLabel(key) + " (" + A.moneyExact(base[key]) +
          ") est sous la visite minimum (" + A.moneyExact(min) + ") : la publication sera refusée.");
      }
    });
    el.warnings.innerHTML = notes.length
      ? '<div class="warnbox amber">' + notes.map(A.esc).join("<br>") + "</div>"
      : "";
  }

  /* `note` describes the row and sits under its label; `derived` is what the
     value works out to and sits under the field. Two different kinds of sentence,
     so two different columns.

     The unit is appended HERE as well as in `formatFor`. It used to be applied
     only on blur, so a cadence painted as a bare "6" and stayed that way until
     someone happened to click into it and out again -- six what, on a screen where
     the neighbouring rows are dollars and multipliers. */
  function pairRow(id, label, note, value, kind, unit, derived) {
    return '<div class="pair-row">' +
      '<div><label for="' + id + '">' + A.esc(label) + "</label>" +
      (note ? '<p class="note">' + note + "</p>" : "") + "</div>" +
      (derived || "") +
      '<input id="' + id + '" data-key="' + id + '" data-kind="' + kind + '"' +
      (unit ? ' data-unit="' + unit + '"' : "") +
      ' inputmode="decimal" value="' + A.esc(value + (unit || "")) + '">' +
      "</div>";
  }


  /* ---------- extras ----------
     An extra is a price, a unit, and its wording in both languages. The wording
     lives here because the quote form reads it straight off the card: change
     "Vitres intérieures" to "Lavage de vitres" and that is what the next visitor
     sees, with no deploy.

     Every row carries a worked example, because "4,00 $ / à l'unité" and
     "8 fenêtres = 32 $" are not equally easy to check. */

  var EXAMPLE_QTY = 8;
  var EXAMPLE_AREA = 1400;

  function extraExample(spec) {
    var cents = Number(spec.cents) || 0;
    if (spec.unit === "each") {
      return EXAMPLE_QTY + " × " + A.moneyExact(cents) + " = " +
        A.moneyExact(cents * EXAMPLE_QTY);
    }
    if (spec.unit === "per_100sqft") {
      var blocks = Math.ceil(EXAMPLE_AREA / 100);
      return EXAMPLE_AREA + " pi² = " + blocks + " × " + A.moneyExact(cents) +
        " = " + A.moneyExact(cents * blocks);
    }
    return "Toujours " + A.moneyExact(cents);
  }

  function needsAttention(spec) {
    if (!spec.label_en) return true;
    return spec.unit !== "flat" && !(spec.per_fr && spec.per_en);
  }

  function extraRow(code) {
    var spec = draft.grid.extras[code] || {};
    var unit = spec.unit || "flat";
    var options = Object.keys(UNIT_LABELS).map(function (value) {
      return '<option value="' + value + '"' + (value === unit ? " selected" : "") + ">" +
        A.esc(UNIT_LABELS[value]) + "</option>";
    }).join("");

    return '<div class="extra-edit" data-code="' + A.esc(code) + '">' +
      '<div class="extra-edit-main">' +
        '<input class="extra-name-input" data-extra="' + A.esc(code) + '" data-part="label_fr" ' +
          'value="' + A.esc(unnamed[code] ? "" : (spec.label_fr || code)) + '" ' +
          'placeholder="Nom de l\'extra, par exemple : Lavage de murs" ' +
          'aria-label="Nom en français">' +
        '<input data-key="extra:' + A.esc(code) + '" data-kind="money" inputmode="decimal" ' +
          'value="' + A.esc(A.moneyExact(spec.cents)) + '" aria-label="Prix">' +
        '<select class="extra-unit" data-extra="' + A.esc(code) + '" aria-label="Facturation">' +
          options + "</select>" +
        '<button type="button" class="extra-del" data-extra="' + A.esc(code) + '" ' +
          'title="Retirer" aria-label="Retirer ' + A.esc(spec.label_fr || code) + '">&times;</button>' +
      "</div>" +
      /* The English name and the "per" wording are set once and then left alone,
         so they fold away: five extras open at once is twenty boxes to read past.
         A row missing something required opens itself, so the message that blocks
         publishing points at a field that is on screen. */
      '<details class="extra-more"' + (needsAttention(spec) ? " open" : "") + ">" +
        "<summary>" + (unit === "flat" ? "Nom en anglais" : "Nom en anglais et unité") +
        "</summary>" +
        '<div class="extra-edit-more">' +
          '<input data-extra="' + A.esc(code) + '" data-part="label_en" ' +
            'value="' + A.esc(spec.label_en || "") + '" aria-label="Nom en anglais" ' +
            'placeholder="Nom en anglais">' +
          (unit === "flat" ? "" :
            '<input data-extra="' + A.esc(code) + '" data-part="per_fr" ' +
              'value="' + A.esc(spec.per_fr || "") + '" aria-label="Par (français)" ' +
              'placeholder="par fenêtre">' +
            '<input data-extra="' + A.esc(code) + '" data-part="per_en" ' +
              'value="' + A.esc(spec.per_en || "") + '" aria-label="Par (anglais)" ' +
              'placeholder="per window">') +
        "</div>" +
      "</details>" +
      '<p class="note">' + A.esc(UNIT_NOTE[unit] || "") +
        ' <span class="derived">' + A.esc(extraExample(spec)) + "</span></p>" +
    "</div>";
  }

  /* ---------- modifiers ----------
     A question, and what each answer does. Two knobs per answer, because they
     are different things: a multiplier scales the work (a first clean is the
     same rooms taking longer), an amount is added flat afterwards (a pet is a
     pet). Every row carries the worked example, since "× 1,4" is not a number
     anyone can check at a glance. */

  var EXAMPLE_WORK = 22100;   // a 3 ch. / 2 sdb at 1400 pi², roughly

  function modifierEffect(option) {
    var mult = A.parseDecimalStrict(String(option.multiplier)) || 1;
    var bits = [];
    if (mult !== 1) {
      bits.push("221,00 $ → " + A.moneyExact(Math.round(EXAMPLE_WORK * mult)));
    }
    if (option.cents) bits.push("+ " + A.moneyExact(option.cents));
    return bits.length ? bits.join(" · ") : "Gratuit";
  }

  function modifierRow(code) {
    var mod = draft.grid.residential_modifiers[code] || {};
    var options = mod.options || [];
    return '<div class="mod-edit" data-mod="' + A.esc(code) + '">' +
      '<div class="mod-head">' +
        /* `|| code` only when there IS a label to fall back from. A row being
           named right now shows its placeholder, not "question_3". */
        '<input class="mod-name" data-mod="' + A.esc(code) + '" data-part="label_fr" ' +
          'value="' + A.esc(unnamed[code] ? "" : (mod.label_fr || code)) + '" ' +
          'placeholder="Votre question, par exemple : Y a-t-il un sous-sol ?" ' +
          'aria-label="Question en français">' +
        '<button type="button" class="extra-del" data-modrm="' + A.esc(code) + '" ' +
          'aria-label="' + A.esc("Retirer « " + (mod.label_fr || code) + " »") + '">&times;</button>' +
      "</div>" +
      '<div class="mod-opts">' +
        '<div class="mod-opt mod-opt--head"><span>Réponse</span><span>Multiplicateur</span>' +
          "<span>Montant</span><span>Effet</span></div>" +
        options.map(function (option, index) {
          return '<div class="mod-opt" data-index="' + index + '">' +
            '<input data-mod="' + A.esc(code) + '" data-index="' + index + '" data-part="label_fr" ' +
              'value="' + A.esc(option.label_fr || "") + '" aria-label="Réponse">' +
            '<input data-key="modmult:' + A.esc(code) + ':' + index + '" data-kind="decimal" ' +
              'data-prefix="× " inputmode="decimal" value="× ' + A.esc(option.multiplier || "1") +
              '" aria-label="Multiplicateur">' +
            '<input data-key="modcents:' + A.esc(code) + ':' + index + '" data-kind="money" ' +
              'inputmode="decimal" value="' + A.esc(A.moneyExact(option.cents || 0)) +
              '" aria-label="Montant ajouté">' +
            '<span class="derived">' + A.esc(modifierEffect(option)) + "</span>" +
          "</div>";
        }).join("") +
      "</div>" +
      '<details class="extra-more"><summary>Noms anglais</summary><div class="extra-edit-more">' +
        '<input data-mod="' + A.esc(code) + '" data-part="label_en" value="' +
          A.esc(mod.label_en || "") + '" placeholder="Question en anglais" ' +
          'aria-label="Question en anglais">' +
        '<input data-mod="' + A.esc(code) + '" data-part="short_fr" value="' +
          A.esc(mod.short_fr || "") + '" placeholder="Nom sur la soumission" ' +
          'aria-label="Nom sur la soumission">' +
        '<input data-mod="' + A.esc(code) + '" data-part="short_en" value="' +
          A.esc(mod.short_en || "") + '" placeholder="Nom sur la soumission (EN)" ' +
          'aria-label="Nom sur la soumission (EN)">' +
        options.map(function (option, index) {
          return '<input data-mod="' + A.esc(code) + '" data-index="' + index +
            '" data-part="label_en" value="' + A.esc(option.label_en || "") +
            '" placeholder="' + A.esc((option.label_fr || "Réponse") + " en anglais") +
            '" aria-label="' + A.esc((option.label_fr || "Réponse") + " en anglais") + '">';
        }).join("") +
      "</div></details></div>";
  }

  /* Codes of rows added this session and not yet named. A row whose question is
     still blank when the caret leaves it was a misclick, and is removed again --
     but only if it is one of these, so clearing an existing question in order to
     retype it never deletes it. */
  var unnamed = {};

  /* The code is the key in the JSONB map and the value the public form posts
     back; it is never shown. Derived codes ("premier_menage") read better in the
     database, but deriving one from a question that has not been typed yet is
     impossible, and renaming the key afterwards would orphan every quote already
     priced with it. A stable meaningless code is the honest trade. */
  function freeModifierCode() {
    var n = 1;
    while (draft.grid.residential_modifiers["question_" + n]) n += 1;
    return "question_" + n;
  }

  function freeExtraCode() {
    var n = 1;
    while ((draft.grid.extras || {})["extra_" + n]) n += 1;
    return "extra_" + n;
  }

  function orderedModifiers() {
    var all = draft.grid.residential_modifiers || {};
    return Object.keys(all).sort(function (a, b) {
      return ((all[a].sort || 100) - (all[b].sort || 100)) || a.localeCompare(b);
    });
  }

  /* An empty section cannot explain itself. A card seeded before modifiers
     existed has none, so this box was a paragraph of theory, an add button and a
     ceiling on nothing -- there was no way to tell what any of it was for.
     Show one worked example instead, and offer the four standard questions. */
  var MODIFIERS_EMPTY =
    '<div class="empty-state">' +
    "  <p><strong>Aucune question pour l'instant.</strong> Le prix ne dépend donc que" +
    "  de la grille, de la superficie et des extras.</p>" +
    '  <div class="empty-example">' +
    '    <span class="note">Par exemple</span>' +
    "    <p><em>« Est-ce un premier ménage ? »</em> — si le client répond oui, le travail" +
    "    est multiplié par 1,4 : un ménage à 221 $ passe à 309,40 $. S'il répond non," +
    "    rien ne change.</p>" +
    "  </div>" +
    '  <div class="row" style="margin-top:14px">' +
    '    <button type="button" class="btn btn-primary" id="add-standard-modifiers">' +
    "      Ajouter les questions habituelles</button>" +
    '    <button type="button" class="btn btn-ghost" id="add-modifier">' +
    "      Écrire la mienne</button>" +
    "  </div>" +
    "  <p class=\"note\" style=\"margin-top:10px\">Premier ménage, état du logement, animaux," +
    "  logement vide. Rien n'est publié tant que vous ne cliquez pas sur Publier.</p>" +
    "</div>";

  function renderModifiers() {
    if (!el.modifiers) return;
    var codes = orderedModifiers();
    el.modifiers.innerHTML = codes.length
      ? codes.map(modifierRow).join("") +
        '<div class="extra-add"><button type="button" id="add-modifier">' +
        "+ Ajouter une question</button></div>"
      : MODIFIERS_EMPTY;

    /* The ceiling only means something once something multiplies. */
    var row = document.getElementById("maxmult-row");
    if (row) {
      row.hidden = !codes.some(function (code) {
        return (draft.grid.residential_modifiers[code].options || []).some(function (option) {
          return String(option.multiplier) !== "1" && String(option.multiplier) !== "1.0";
        });
      });
    }
  }

  function renderRows() {
    var g = draft.grid;
    el.minutes.innerHTML = Object.keys(SERVICE_LABELS)
      .filter(function (code) { return g.minutes_per_100sqft && code in g.minutes_per_100sqft; })
      .map(function (code) {
        var minutes = g.minutes_per_100sqft[code];
        var perBlock = Math.round(minutes / 60 * draft.hourly_rate_cents);
        return pairRow("min:" + code, SERVICE_LABELS[code], "",
          minutes, "int", " min",
          '<span class="derived">= ' + A.moneyExact(perBlock) + " / 100 pi²</span>");
      }).join("");

    el.extras.innerHTML = Object.keys(g.extras || {}).sort().map(extraRow).join("") +
      '<div class="extra-add"><button type="button" id="add-extra">+ Ajouter un extra</button></div>';

    el.discounts.innerHTML = ["monthly", "biweekly", "weekly"]
      .filter(function (code) { return g.frequency_discount_pct && code in g.frequency_discount_pct; })
      .map(function (code) {
        return pairRow("disc:" + code, "Rabais — " + FREQUENCY_LABELS[code], "",
          g.frequency_discount_pct[code] + " %", "pct");
      }).join("");

    setField("f-hourly", A.moneyExact(draft.hourly_rate_cents));
    setField("f-minimum", A.moneyExact(draft.minimum_visit_cents));
    setField("f-travel", A.moneyExact(draft.travel_cents));
    setField("f-allowance", g.residential_area_allowance_sqft + " pi²");
    setField("f-area", A.moneyExact(g.residential_area_cents_per_100sqft));
    setField("f-restroom", g.minutes_per_restroom + " min");
    setField("f-night", "× " + g.night_access_multiplier);
    setField("f-maxmult", "× " + (g.max_residential_multiplier || "2.5"));
    renderModifiers();
  }

  function setField(id, value) {
    var node = document.getElementById(id);
    if (node && document.activeElement !== node) node.value = value;
  }

  function renderDraftbar() {
    var list = changes();
    renderRail(changesBySection(list));
    el.draftbar.hidden = false;
    el.draftBase.textContent = list.length
      ? "basé sur " + active.version + " · active depuis le " + A.day(active.effective_from)
      : "Carte active " + active.version + " · depuis le " + A.day(active.effective_from);
    el.draftTitle.textContent = list.length ? "Brouillon" : "Aucune modification";
    el.draftCount.hidden = list.length === 0;
    el.draftCount.textContent = list.length + (list.length > 1 ? " modifications" : " modification");
    el.publish.disabled = list.length === 0;
    el.discard.hidden = list.length === 0;
  }

  /* ---------- the rail ---------- */

  var currentSection = null;

  function sectionOf(key) {
    for (var i = 0; i < SECTIONS.length; i++) {
      var section = SECTIONS[i];
      for (var k = 0; k < section.keys.length; k++) {
        var probe = section.keys[k];
        if (probe.slice(-1) === ":" ? key.indexOf(probe) === 0 : key === probe) return section.id;
      }
    }
    return null;
  }

  /* Labels, not a tally. A mark on a menu item raises the question it cannot
     answer -- "why is that one marked?" -- and the tally never answered it
     either: a bigger number is not a better explanation. The names of the things
     that changed are already in `changes()`, so the rail can simply say them. */
  function changesBySection(list) {
    var bySection = {};
    list.forEach(function (change) {
      var id = change.key && sectionOf(change.key);
      if (!id) return;
      (bySection[id] = bySection[id] || []).push(change.label);
    });
    return bySection;
  }

  /* At most four names, then "et N autres": a tooltip is a glance, and the
     publish dialog is where the full list belongs. */
  function editSummary(labels) {
    var shown = labels.slice(0, 4).join(", ");
    return labels.length > 4
      ? shown + ", et " + (labels.length - 4) + " autre" + (labels.length - 4 > 1 ? "s" : "")
      : shown;
  }

  function renderRail(edits) {
    if (!el.rail) return;
    var group = null;
    el.rail.innerHTML = SECTIONS.map(function (section) {
      var head = section.group === group
        ? ""
        : '<span class="rail-group">' + A.esc(section.group) + "</span>";
      group = section.group;
      /* A dot, not the count. The count was of CHANGED LEAF KEYS, which is an
         implementation detail of the diff and not a quantity anyone means: the
         four standard questions carry ten options between them, so adding them
         put a "10" against Modificateurs -- next to a section reading "Aucune
         question pour l'instant" -- while the four extras put a "4" against
         Extras, which read as a count of extras and made the wrong reading look
         right. The rail only has to answer "where are my unpublished edits?",
         and a dot answers exactly that and nothing it cannot back up. The draft
         bar still gives the real number, in words. */
      var labels = (edits || {})[section.id] || [];
      var why = labels.length ? "Non publié : " + editSummary(labels) : "";
      return head +
        '<button type="button" class="rail-item" data-section="' + section.id + '"' +
        (section.id === currentSection ? ' aria-current="true"' : "") +
        (why ? ' title="' + A.esc(why) + '"' : "") + ">" +
        "<span>" + A.esc(section.label) + "</span>" +
        (labels.length
          ? '<span class="rail-dot" role="img" aria-label="' + A.esc(why) + '"></span>'
          : "") +
        "</button>";
    }).join("");
  }

  /* One section at a time. The page was a single scroll through eight boxes and
     only gets longer; with the tester pinned beside it, switching beats
     scrolling past six things to reach the seventh. */
  function showSection(id, options) {
    var known = SECTIONS.some(function (section) { return section.id === id; });
    currentSection = known ? id : SECTIONS[0].id;
    document.querySelectorAll(".rate-box[data-section]").forEach(function (box) {
      box.hidden = box.dataset.section !== currentSection;
    });
    renderRail(changesBySection(changes()));
    try { localStorage.setItem(SECTION_KEY, currentSection); } catch (e) { /* private mode */ }
    if (options && options.focus) {
      var box = document.querySelector('.rate-box[data-section="' + currentSection + '"]');
      var first = box && box.querySelector("input, select, button");
      if (first && first.focus) first.focus();
    }
  }

  if (el.rail) {
    el.rail.addEventListener("click", function (event) {
      var item = event.target.closest(".rail-item");
      if (item) showSection(item.dataset.section, { focus: true });
    });
  }

  function renderKill() {
    var on = active.residential_online_pricing;
    el.kill.setAttribute("aria-checked", String(on));
    el.kill.dataset.on = on ? "1" : "0";
    el.killNote.textContent = on
      ? "Actif. Si vous le coupez, les demandes résidentielles sont chiffrées à la main, comme le commercial."
      : "Coupé. Aucune demande résidentielle ne reçoit de prix en ligne : toutes partent en révision.";
  }

  function renderHistory(items) {
    el.history.innerHTML = items.map(function (card) {
      var span = A.day(card.effective_from) + " → " + (card.effective_to ? A.day(card.effective_to) : "aujourd'hui");
      return '<div class="histrow"><div><strong>' + A.esc(card.version) + "</strong><br>" +
        '<span class="note">' + A.esc(span) + " · " + card.priced_requests +
        (card.priced_requests === 1 ? " demande" : " demandes") + "</span></div>" +
        (card.is_active ? '<span class="chip chip--won">Active</span>' : "") + "</div>";
    }).join("");
  }

  function renderScenarios() {
    el.scenarios.innerHTML = SCENARIOS.map(function (s, index) {
      var codes = Object.keys(s.extras || {});
      var mods = Object.keys(s.modifiers || {}).length;
      var detail = s.audience === "residential"
        ? s.area_sqft + " pi² · " + (s.frequency === "biweekly" ? "aux 2 semaines" : "une seule fois") +
          (codes.length ? " · " + codes.length + (codes.length > 1 ? " extras" : " extra") : "") +
          (mods ? " · " + mods + (mods > 1 ? " modificateurs" : " modificateur") : "")
        : s.restrooms + " sanitaires · hebdo · de soir";
      return '<button type="button" class="scenario' + (index === chosen ? " on" : "") +
        '" data-scenario="' + index + '" aria-pressed="' + (index === chosen) + '">' +
        "<b>" + A.esc(s.label) + "</b><span>" + A.esc(detail) + "</span></button>";
    }).join("");
  }

  /* ---------- reading the form back ---------- */

  function readInput(node) {
    var kind = node.dataset.kind;
    if (kind === "money") return A.parseMoney(node.value);
    if (kind === "int") return A.parseIntStrict(node.value);
    if (kind === "pct" || kind === "decimal") return A.parseDecimalStrict(node.value);
    return null;
  }

  function applyInput(node) {
    var value = readInput(node);
    node.classList.toggle("bad", value === null);
    if (value === null) return false;

    var cell = node.dataset.cell;
    if (cell) {
      draft.grid.residential_base_cents[cell] = value;
      markCell(node, cell);
      return true;
    }

    var key = node.dataset.key || node.id;
    if (key.indexOf("min:") === 0) {
      draft.grid.minutes_per_100sqft[key.slice(4)] = value;
      refreshDerived();
    }
    else if (key.indexOf("extra:") === 0) {
      var extraCode = key.slice(6);
      draft.grid.extras[extraCode].cents = value;
      refreshExtraExample(extraCode);
    }
    else if (key.indexOf("modmult:") === 0 || key.indexOf("modcents:") === 0) {
      var parts = key.split(":");
      var option = draft.grid.residential_modifiers[parts[1]].options[Number(parts[2])];
      if (parts[0] === "modmult") option.multiplier = String(value);
      else option.cents = value;
      refreshModifierEffect(parts[1], Number(parts[2]));
    }
    else if (key === "f-maxmult") draft.grid.max_residential_multiplier = String(value);
    else if (key.indexOf("disc:") === 0) draft.grid.frequency_discount_pct[key.slice(5)] = value;
    else if (key === "f-hourly") draft.hourly_rate_cents = value;
    else if (key === "f-minimum") draft.minimum_visit_cents = value;
    else if (key === "f-travel") draft.travel_cents = value;
    else if (key === "f-allowance") draft.grid.residential_area_allowance_sqft = value;
    else if (key === "f-area") draft.grid.residential_area_cents_per_100sqft = value;
    else if (key === "f-restroom") draft.grid.minutes_per_restroom = value;
    else if (key === "f-night") draft.grid.night_access_multiplier = String(value);
    return true;
  }

  function afterEdit() {
    saveDraft();
    renderDraftbar();
    renderMatrixWarnings();
    schedulePreview();
  }

  /* ---------- preview ---------- */

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(runPreview, 400);
  }

  function runPreview() {
    /* Don't ask the server to price a card it is going to refuse: it answers with
       a validation trace, and the tester would show it where a price goes. */
    var problem = extrasProblem();
    if (problem) {
      el.result.innerHTML = '<div class="warnbox amber">' + A.esc(problem) + "</div>";
      return;
    }
    A.api("/rate-card/preview", {
      method: "POST",
      body: JSON.stringify({ card: draft, scenarios: SCENARIOS })
    })
      .then(function (data) { renderResult(data.results[chosen]); })
      .catch(function (err) {
        if (err === "auth") return;
        el.result.innerHTML = '<div class="warnbox">' + A.esc(A.apiMessage(err)) + "</div>";
      });
  }

  function renderResult(row) {
    if (!row) { el.result.innerHTML = ""; return; }
    if (row.error) {
      el.result.innerHTML = '<div class="warnbox amber">Ce scénario n\'a pas de prix avec ce brouillon : ' +
        A.esc(row.error) + "</div>";
      return;
    }
    var before = row.active_total_cents;
    var after = row.draft_total_cents;
    var html = '<div class="delta"><span>Carte active</span><span style="font-family:var(--font-display);font-weight:700">' +
      (before === null ? "—" : A.moneyExact(before)) + "</span></div>" +
      '<div class="delta"><span><strong>Brouillon</strong></span><b>' + A.moneyExact(after) + "</b></div>";
    if (before !== null && before !== after) {
      var diff = after - before;
      var pct = before ? Math.round(diff / before * 1000) / 10 : 0;
      html += '<div class="delta"><span class="note">Écart</span><span class="' +
        (diff > 0 ? "up" : "down") + '">' + (diff > 0 ? "+ " : "− ") + A.moneyExact(Math.abs(diff)) +
        "  (" + (diff > 0 ? "+" : "−") + Math.abs(pct) + " %)</span></div>";
    }
    /* The panel has to add up. It listed the lines and stopped, so a scenario
       with a recurring discount showed four numbers summing to 285,00 $ under a
       total of 256,50 $, and nothing on screen accounted for the difference --
       in the one place whose whole job is checking a price before publishing. */
    html += '<div style="margin-top:16px"><span class="field-label" style="font-size:0.68rem">Détail du brouillon</span>';
    html += row.draft_lines.map(function (line) {
      /* Same as the client sees: a quantity line says what it is a quantity of. */
      var detail = line.quantity
        ? ' <span class="line-qty">× ' + A.esc(line.quantity) +
          (line.unit_fr ? " " + A.esc(line.unit_fr) : "") + "</span>"
        : "";
      return '<div class="summary-line" style="padding-top:8px"><span>' + A.esc(line.label_fr) +
        detail + "</span><span>" + A.moneyExact(line.amount_cents) + "</span></div>";
    }).join("");

    if (row.draft_discount_cents || row.draft_minimum_adjustment_cents) {
      html += '<div class="summary-line subtotal"><span>Sous-total</span><span>' +
        A.moneyExact(row.draft_subtotal_cents) + "</span></div>";
    }
    if (row.draft_discount_cents) {
      html += '<div class="summary-line" style="padding-top:8px;color:var(--gold-ink)">' +
        "<span>Rabais de fréquence</span><span>− " +
        A.moneyExact(row.draft_discount_cents) + "</span></div>";
    }
    if (row.draft_minimum_adjustment_cents) {
      html += '<div class="summary-line" style="padding-top:8px"><span>Visite minimum</span>' +
        "<span>+ " + A.moneyExact(row.draft_minimum_adjustment_cents) + "</span></div>";
    }
    html += "</div>";
    el.result.innerHTML = html;
  }

  /* ---------- publish ---------- */

  /* Caught here rather than at publish: the server refuses these too, but it
     answers with a validation trace, and the person who has to act on it is
     looking at the field that is wrong. */
  function extrasProblem() {
    var codes = Object.keys(draft.grid.extras || {});
    for (var i = 0; i < codes.length; i++) {
      var spec = draft.grid.extras[codes[i]];
      var name = spec.label_fr || codes[i];
      if (!spec.label_fr || !spec.label_en) {
        return "« " + name + " » a besoin d'un nom en français et en anglais.";
      }
      if (spec.unit !== "flat" && !(spec.per_fr && spec.per_en)) {
        return "« " + name + " » est facturé " + (UNIT_LABELS[spec.unit] || spec.unit) +
          " : indiquez par quoi, en français et en anglais (par exemple « par fenêtre » / « per window »).";
      }
      if (!spec.cents) {
        return "« " + name + " » est à 0 $. Donnez-lui un prix ou retirez-le.";
      }
    }
    return null;
  }

  function openReview() {
    var problem = extrasProblem();
    if (problem) {
      showSection("res-extras");
      el.pageError.textContent = problem;
      el.pageError.hidden = false;
      el.pageError.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    el.pageError.hidden = true;
    var list = changes();
    el.reviewError.hidden = true;
    el.reviewChanges.innerHTML = '<table class="review-table"><tbody>' + list.map(function (c) {
      return "<tr><td>" + A.esc(c.label) + '</td><td class="from">' + A.esc(c.from) +
        '</td><td class="arrow">→</td><td class="to">' + A.esc(c.to) + "</td></tr>";
    }).join("") + "</tbody></table>";

    A.api("/rate-card/preview", {
      method: "POST",
      body: JSON.stringify({ card: draft, scenarios: SCENARIOS })
    }).then(function (data) {
      el.reviewEffect.innerHTML = '<span class="field-label" style="margin-top:18px;display:block">Effet sur les scénarios</span>' +
        '<table class="review-table"><tbody>' + data.results.map(function (row) {
          if (row.error) return "<tr><td>" + A.esc(row.label) + '</td><td colspan="3" class="from">chiffré à la main</td></tr>';
          var diff = row.active_total_cents === null ? null : row.draft_total_cents - row.active_total_cents;
          var big = diff !== null && row.active_total_cents > 0 &&
            Math.abs(diff / row.active_total_cents) > 0.25;
          return "<tr><td>" + A.esc(row.label) + '</td><td class="from">' +
            (row.active_total_cents === null ? "—" : A.moneyExact(row.active_total_cents)) +
            '</td><td class="arrow">→</td><td class="to' + (big ? " big" : "") + '">' +
            A.moneyExact(row.draft_total_cents) +
            (big ? ' <span class="chip chip--quoted">écart important</span>' : "") + "</td></tr>";
        }).join("") + "</tbody></table>";
    }).catch(function () { el.reviewEffect.innerHTML = ""; });

    openModal();
  }

  /* The last gate before a price reaches customers, so it behaves like a dialog:
     focus goes in, Tab stays in, Escape leaves, and focus comes back to the
     button that opened it. Before this it was a div that appeared, with the page
     behind it still tabbable. */
  var returnFocusTo = null;

  function modalCard() {
    return el.review.querySelector(".modal-card");
  }

  function openModal() {
    returnFocusTo = document.activeElement;
    el.review.hidden = false;
    var card = modalCard();
    if (card && card.focus) card.focus();
  }

  function closeModal() {
    el.review.hidden = true;
    if (returnFocusTo && returnFocusTo.focus) returnFocusTo.focus();
    returnFocusTo = null;
  }

  var FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), ' +
    'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  document.addEventListener("keydown", function (event) {
    if (el.review.hidden) return;
    if (event.key === "Escape") { closeModal(); return; }
    if (event.key !== "Tab") return;
    var card = modalCard();
    var stops = card ? card.querySelectorAll(FOCUSABLE) : [];
    if (!stops.length) return;
    var first = stops[0];
    var last = stops[stops.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  });

  function publish() {
    var button = document.getElementById("review-confirm");
    button.disabled = true;
    button.textContent = "Publication…";
    A.api("/rate-card", { method: "POST", body: JSON.stringify(draft) })
      .then(function (card) {
        clearDraft();
        closeModal();
        active = card;
        draft = cardFrom(card);
        renderAll();
        return A.api("/rate-cards").then(function (data) { renderHistory(data.items); });
      })
      .catch(function (err) {
        if (err === "auth") return;
        el.reviewError.textContent = A.apiMessage(err);
        el.reviewError.hidden = false;
      })
      .then(function () {
        button.disabled = false;
        button.textContent = "Publier cette version";
      });
  }

  /* ---------- wiring ---------- */

  function renderAll() {
    var saved = null;
    try { saved = localStorage.getItem(SECTION_KEY); } catch (e) { /* private mode */ }
    showSection(currentSection || saved || SECTIONS[0].id);
    renderMatrix();
    renderRows();
    renderDraftbar();
    renderKill();
    renderScenarios();
    schedulePreview();
  }

  document.addEventListener("input", function (event) {
    var node = event.target;
    if (!node.matches("input[data-kind], input[data-cell]")) return;
    if (node.dataset.cell) node.dataset.kind = "money";
    if (applyInput(node)) afterEdit();
  });

  /* Canonical form on blur -- for THAT field only.
     Re-rendering the matrix here destroyed the input the visitor was moving into:
     blur on cell A fires while the click on cell B is still resolving, B is
     replaced, and everything typed into it is lost. */
  function formatFor(node, value) {
    if (node.dataset.cell || node.dataset.kind === "money") return A.moneyExact(value);
    if (node.dataset.kind === "pct") return value + " %";
    if (node.dataset.kind === "decimal") return (node.dataset.prefix || "") + value;
    return value + (node.dataset.unit || "");
  }

  /* The "= 4,50 $ / 100 pi²" hints depend on the hourly rate, so they move when it
     does. Updated in place for the same reason: a rebuild would steal the focus. */
  function refreshDerived() {
    Object.keys(SERVICE_LABELS).forEach(function (code) {
      var input = document.getElementById("min:" + code);
      if (!input) return;
      var row = input.closest(".pair-row");
      var span = row && row.querySelector(".derived");
      if (!span) return;
      var minutes = draft.grid.minutes_per_100sqft[code];
      span.textContent = "= " + A.moneyExact(Math.round(minutes / 60 * draft.hourly_rate_cents)) +
        " / 100 pi²";
    });
  }

  /* In place, like every other derived hint on this screen: a rebuild would
     take the focus out of the field being typed into. */
  function refreshModifierEffect(code, index) {
    var row = el.modifiers.querySelector(
      '.mod-edit[data-mod="' + CSS.escape(code) + '"] .mod-opt[data-index="' + index + '"]'
    );
    var span = row && row.querySelector(".derived");
    if (span) {
      span.textContent = modifierEffect(draft.grid.residential_modifiers[code].options[index]);
    }
  }

  /* The worked example moves with the price, in place: rebuilding the row would
     take the focus out of the field being typed into. */
  function refreshExtraExample(code) {
    var row = el.extras.querySelector('.extra-edit[data-code="' + CSS.escape(code) + '"]');
    var span = row && row.querySelector(".derived");
    if (span) span.textContent = extraExample(draft.grid.extras[code]);
  }

  /* Replace one extra's row and put the focus back where it was. */
  function redrawExtra(code, focusSelector) {
    var row = el.extras.querySelector('.extra-edit[data-code="' + CSS.escape(code) + '"]');
    if (!row) { renderRows(); return; }
    row.outerHTML = extraRow(code);
    var fresh = el.extras.querySelector('.extra-edit[data-code="' + CSS.escape(code) + '"]');
    var target = fresh && focusSelector && fresh.querySelector(focusSelector);
    if (target && target.focus) target.focus();
  }

  el.modifiers.addEventListener("input", function (event) {
    var node = event.target;
    if (!node.dataset || !node.dataset.mod || !node.dataset.part) return;
    var mod = draft.grid.residential_modifiers[node.dataset.mod];
    if (node.dataset.index === undefined) mod[node.dataset.part] = node.value;
    else mod.options[Number(node.dataset.index)][node.dataset.part] = node.value;
    /* While the row is still being named, the question fills the three other
       wordings too -- the short form used on the quote line, and both English
       fields -- so one typed sentence produces a usable question instead of
       three more empty boxes. All four stay editable under "Noms anglais". */
    if (unnamed[node.dataset.mod] && node.dataset.part === "label_fr") {
      mod.short_fr = node.value;
      mod.label_en = node.value;
      mod.short_en = node.value;
    }
    afterEdit();
  });

  /* Capture, because blur does not bubble. A row added by mistake disappears on
     its own rather than becoming an empty question that blocks publishing. */
  el.modifiers.addEventListener("blur", function (event) {
    var node = event.target;
    if (!node.classList || !node.classList.contains("mod-name")) return;
    var code = node.dataset.mod;
    if (!unnamed[code]) return;
    if (node.value.trim()) { delete unnamed[code]; return; }

    delete draft.grid.residential_modifiers[code];
    delete unnamed[code];
    /* The node is removed rather than the list rebuilt: a rebuild here would
       destroy whichever input the click that caused this blur was landing on. */
    var row = node.closest(".mod-edit");
    if (row) row.remove();
    if (!orderedModifiers().length) renderModifiers();
    afterEdit();
  }, true);

  el.modifiers.addEventListener("click", function (event) {
    var remove = event.target.closest("[data-modrm]");
    if (remove) {
      var code = remove.dataset.modrm;
      var mod = draft.grid.residential_modifiers[code] || {};
      if (!window.confirm("Retirer « " + (mod.label_fr || code) +
          " » ? La question ne sera plus posée.")) return;
      delete draft.grid.residential_modifiers[code];
      renderModifiers();
      afterEdit();
      return;
    }
    if (event.target.id === "add-standard-modifiers") {
      var button = event.target;
      button.disabled = true;
      /* Two arguments to `.then`, not a trailing `.catch`: the rejection handler
         then covers the REQUEST only. With `.catch` it also caught everything the
         success handler threw, so a TypeError in the code below was reported to
         Amine as a failed API call -- an "Erreur" box with no message, since a
         TypeError carries no HTTP status -- while the request had in fact
         returned 200. A bug in this handler now reaches the console as a real
         unhandled rejection, with its stack, instead of being disguised as a
         server problem. */
      A.api("/rate-card/modifier-presets").then(
        function (presets) {
          Object.keys(presets).forEach(function (code) {
            if (!draft.grid.residential_modifiers[code]) {
              draft.grid.residential_modifiers[code] = presets[code];
            }
          });
          if (!draft.grid.max_residential_multiplier) {
            draft.grid.max_residential_multiplier = "2.5";
          }
          renderRows();
          afterEdit();
        },
        function (err) {
          if (err === "auth") return;
          button.disabled = false;
          el.pageError.textContent = A.apiMessage(err);
          el.pageError.hidden = false;
        }
      );
      return;
    }
    /* No `window.prompt`. Every other word on this screen is typed into the field
       that will hold it; asking for the question in a grey browser dialog --
       titled "localhost:8000 says", in the browser's own language, with the page
       frozen behind it -- was the one place that stopped being the product and
       started being the browser. It also asked for the question BEFORE showing
       the row, so you named a thing you could not yet see.

       The row is the form. Add it empty, put the caret in its question field,
       and let the same inputs that edit every other question edit this one. */
    if (event.target.id === "add-modifier") {
      var newCode = freeModifierCode();
      draft.grid.residential_modifiers[newCode] = {
        label_fr: "", label_en: "", short_fr: "", short_en: "",
        sort: (orderedModifiers().length + 1) * 10,
        /* Two answers, the first free: the shape every modifier has to have, so a
           new one is valid the moment it exists and only needs its wording. */
        options: [
          { value: "no", label_fr: "Non", label_en: "No", multiplier: "1", cents: 0 },
          { value: "yes", label_fr: "Oui", label_en: "Yes", multiplier: "1", cents: 0 }
        ]
      };
      /* Tracked out here, not as a field on the modifier: everything inside
         `draft.grid` is posted to the server verbatim on publish, and a flag that
         means something only to this screen has no business in the payload. */
      unnamed[newCode] = true;
      renderModifiers();
      var field = el.modifiers.querySelector(
        '.mod-edit[data-mod="' + CSS.escape(newCode) + '"] .mod-name');
      if (field) {
        field.scrollIntoView({ behavior: "smooth", block: "center" });
        field.focus();
      }
      /* No afterEdit() yet: an empty question is not a change worth marking the
         rail for, and it is dropped again if left blank. */
    }
  });

  el.extras.addEventListener("change", function (event) {
    var node = event.target;
    if (node.classList.contains("extra-unit")) {
      var spec = draft.grid.extras[node.dataset.extra];
      spec.unit = node.value;
      /* A flat extra has nothing to be "per", so those fields go and their values
         with them -- leaving "par fenêtre" on a forfait would print it on a quote. */
      if (spec.unit === "flat") { spec.per_fr = ""; spec.per_en = ""; }
      /* Only this row: rebuilding the whole section destroyed the select the
         admin had just operated and dumped a keyboard user at the top of the
         page. Everywhere else on this screen updates in place for the same
         reason. */
      redrawExtra(node.dataset.extra, ".extra-unit");
      afterEdit();
    }
  });

  el.extras.addEventListener("input", function (event) {
    var node = event.target;
    var part = node.dataset.part;
    if (!part) return;
    draft.grid.extras[node.dataset.extra][part] = node.value;
    if (unnamed[node.dataset.extra] && part === "label_fr") {
      draft.grid.extras[node.dataset.extra].label_en = node.value;
    }
    afterEdit();
  });

  /* The mirror of the modifiers' rule: an extra added by mistake and left
     unnamed removes itself instead of blocking the next publish. */
  el.extras.addEventListener("blur", function (event) {
    var node = event.target;
    if (!node.classList || !node.classList.contains("extra-name-input")) return;
    var code = node.dataset.extra;
    if (!unnamed[code]) return;
    if (node.value.trim()) { delete unnamed[code]; return; }

    delete draft.grid.extras[code];
    delete unnamed[code];
    var row = node.closest(".extra-edit");
    if (row) row.remove();
    afterEdit();
  }, true);

  el.extras.addEventListener("click", function (event) {
    var remove = event.target.closest(".extra-del");
    if (remove) {
      var code = remove.dataset.extra;
      var name = (draft.grid.extras[code] || {}).label_fr || code;
      /* Retiring an extra does not touch the requests that already bought it:
         they keep the wording and the price from the card that quoted them. */
      if (!window.confirm("Retirer « " + name + " » ? Il ne sera plus proposé dans le formulaire.")) return;
      delete draft.grid.extras[code];
      renderRows();
      afterEdit();
      return;
    }
    /* Same as a new question: the row is the form. See the `add-modifier`
       handler for why the browser prompt went. */
    if (event.target.id === "add-extra") {
      var newCode = freeExtraCode();
      draft.grid.extras[newCode] = {
        unit: "flat", cents: 0, label_fr: "", label_en: "", per_fr: "", per_en: ""
      };
      unnamed[newCode] = true;
      renderRows();
      var field = el.extras.querySelector(
        '.extra-edit[data-code="' + CSS.escape(newCode) + '"] .extra-name-input');
      if (field) {
        field.scrollIntoView({ behavior: "smooth", block: "center" });
        field.focus();
      }
    }
  });

  document.addEventListener("blur", function (event) {
    var node = event.target;
    if (!node.matches || !node.matches("input[data-kind], input[data-cell]")) return;
    var value = readInput(node);
    if (value === null) return;
    node.value = formatFor(node, value);
    if (node.id === "f-hourly") refreshDerived();
  }, true);

  el.matrix.addEventListener("click", function (event) {
    var add = event.target.closest("[data-add]");
    if (add) {
      draft.grid.residential_base_cents[add.dataset.add] = draft.minimum_visit_cents;
      renderMatrix(); afterEdit(); return;
    }
    var remove = event.target.closest("[data-remove]");
    if (remove) {
      delete draft.grid.residential_base_cents[remove.dataset.remove];
      renderMatrix(); afterEdit();
    }
  });

  el.scenarios.addEventListener("click", function (event) {
    var card = event.target.closest("[data-scenario]");
    if (!card) return;
    chosen = Number(card.dataset.scenario);
    renderScenarios();
    runPreview();
  });

  el.kill.addEventListener("click", function () {
    var next = el.kill.dataset.on !== "1";
    A.api("/rate-card/online-pricing", { method: "PATCH", body: JSON.stringify({ enabled: next }) })
      .then(function (card) { active.residential_online_pricing = card.residential_online_pricing; renderKill(); })
      .catch(function (err) {
        if (err === "auth") return;
        el.pageError.textContent = A.apiMessage(err);
        el.pageError.hidden = false;
      });
  });

  el.discard.addEventListener("click", function () {
    draft = cardFrom(active);
    clearDraft();
    renderAll();
  });

  el.publish.addEventListener("click", openReview);
  document.getElementById("review-cancel").addEventListener("click", closeModal);
  document.getElementById("review-confirm").addEventListener("click", publish);
  el.review.addEventListener("click", function (event) {
    if (event.target === el.review) closeModal();
  });

  function start() {
    A.api("/rate-card")
      .then(function (card) {
        active = card;
        draft = loadDraft(card.version) || cardFrom(card);
        el.loading.hidden = true;
        el.editor.hidden = false;
        renderAll();
        return A.api("/rate-cards");
      })
      .then(function (data) { if (data) renderHistory(data.items); })
      .catch(function (err) {
        if (err === "auth") return;
        el.loading.hidden = true;
        el.editor.hidden = true;
        /* With no card there is no grid to draw, so the screen is empty apart
           from this. Say what happened and offer the way back, rather than
           leaving a blank page and a reload the person has to think of. */
        el.pageError.innerHTML = A.esc(
          err && err.status === 404
            ? "Aucune carte active. Lancez python -m scripts.seed_rate_card pour en créer une."
            : A.apiMessage(err)
        ) + ' <button type="button" class="linkbtn" id="retry-card">Réessayer</button>';
        el.pageError.hidden = false;
        var retry = document.getElementById("retry-card");
        if (retry) {
          retry.addEventListener("click", function () {
            el.pageError.hidden = true;
            el.loading.hidden = false;
            start();
          });
        }
      });
  }

  A.boot({ onAuthed: start });
})();
