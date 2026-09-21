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
  var EXTRA_LABELS = {
    fridge: "Intérieur du réfrigérateur",
    oven: "Intérieur du four",
    windows: "Vitres intérieures",
    garage: "Garage",
    carpets: "Shampooing de tapis"
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
      area_sqft: 1400, bedrooms: 3, bathrooms: 2, frequency: "biweekly", extras: ["oven"] },
    { label: "Maison 4 ch. / 3 sdb", audience: "residential", property_type: "house",
      area_sqft: 2600, bedrooms: 4, bathrooms: 3, frequency: "one_time", extras: [] },
    { label: "Bureau 5 000 pi²", audience: "commercial", property_type: "office",
      area_sqft: 5000, restrooms: 4, frequency: "weekly",
      services: ["office_cleaning"], night_access: true }
  ];

  var active = null;   // the published card, as loaded
  var draft = null;    // what the form is editing
  var chosen = 0;      // which scenario the tester is showing
  var previewTimer = null;

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
    matrix: document.getElementById("matrix"),
    warnings: document.getElementById("matrix-warnings"),
    minutes: document.getElementById("minutes-rows"),
    extras: document.getElementById("extras-rows"),
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

  function cardFrom(source) {
    return {
      hourly_rate_cents: source.hourly_rate_cents,
      minimum_visit_cents: source.minimum_visit_cents,
      travel_cents: source.travel_cents,
      grid: JSON.parse(JSON.stringify(source.grid || {}))
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
      if (saved && saved.base === baseVersion) return saved.card;
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
    Object.keys(g.extras_cents || {}).forEach(function (key) {
      flat["extra:" + key] = { value: g.extras_cents[key], kind: "money", label: EXTRA_LABELS[key] || key };
    });
    Object.keys(g.frequency_discount_pct || {}).forEach(function (key) {
      flat["disc:" + key] = { value: g.frequency_discount_pct[key], kind: "pct",
                              label: "Rabais — " + (FREQUENCY_LABELS[key] || key) };
    });
    return flat;
  }

  function show(entry) {
    if (entry === undefined || entry === null || entry.value === undefined || entry.value === null) return "—";
    if (entry.kind === "money") return A.moneyExact(entry.value);
    if (entry.kind === "pct") return entry.value + " %";
    if (entry.kind === "decimal") return "× " + entry.value;
    return entry.value + (entry.unit || "");
  }

  function changes() {
    var before = flatten(cardFrom(active));
    var after = flatten(draft);
    var out = [];
    Object.keys(after).forEach(function (key) {
      var was = before[key];
      if (!was) { out.push({ label: after[key].label, from: "—", to: show(after[key]) }); return; }
      if (String(was.value) !== String(after[key].value)) {
        out.push({ label: after[key].label, from: show(was), to: show(after[key]) });
      }
    });
    Object.keys(before).forEach(function (key) {
      if (!after[key]) out.push({ label: before[key].label, from: show(before[key]), to: "retiré" });
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
    var head = '<thead><tr><th>&nbsp;</th>';
    for (var bath = 1; bath <= 4; bath++) head += "<th>" + bath + " sdb</th>";
    head += "</tr></thead>";

    var body = "<tbody>";
    for (var bed = 1; bed <= 5; bed++) {
      body += "<tr><td>" + bed + (bed > 1 ? " chambres" : " chambre") + "</td>";
      for (var b = 1; b <= 4; b++) {
        var key = matrixKey(bed, b);
        if (Object.prototype.hasOwnProperty.call(base, key)) {
          var was = before[key];
          var moved = was !== undefined && was !== base[key];
          body += '<td class="cell' + (moved ? " changed" : "") + '">' +
            '<input data-cell="' + key + '" inputmode="decimal" value="' + A.moneyExact(base[key]) + '">' +
            '<button type="button" class="cell-remove" data-remove="' + key + '" title="Retirer">×</button>' +
            (moved ? '<span class="was">était ' + A.moneyExact(was) + "</span>" : "") +
            "</td>";
        } else {
          body += '<td class="cell empty"><button type="button" data-add="' + key + '">+ ajouter</button></td>';
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

  function pairRow(id, label, note, value, kind, unit) {
    return '<div class="pair-row">' +
      '<div><label for="' + id + '">' + A.esc(label) + "</label>" +
      (note ? '<p class="note">' + note + "</p>" : "") + "</div>" +
      '<input id="' + id + '" data-key="' + id + '" data-kind="' + kind + '"' +
      (unit ? ' data-unit="' + unit + '"' : "") +
      ' inputmode="decimal" value="' + A.esc(value) + '"></div>';
  }

  function renderRows() {
    var g = draft.grid;
    el.minutes.innerHTML = Object.keys(SERVICE_LABELS)
      .filter(function (code) { return g.minutes_per_100sqft && code in g.minutes_per_100sqft; })
      .map(function (code) {
        var minutes = g.minutes_per_100sqft[code];
        var perBlock = Math.round(minutes / 60 * draft.hourly_rate_cents);
        return pairRow("min:" + code, SERVICE_LABELS[code],
          '<span class="derived">= ' + A.moneyExact(perBlock) + " / 100 pi²</span>",
          minutes, "int", " min");
      }).join("");

    el.extras.innerHTML = Object.keys(g.extras_cents || {}).map(function (code) {
      return pairRow("extra:" + code, EXTRA_LABELS[code] || code, "", A.moneyExact(g.extras_cents[code]), "money");
    }).join("");

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
  }

  function setField(id, value) {
    var node = document.getElementById(id);
    if (node && document.activeElement !== node) node.value = value;
  }

  function renderDraftbar() {
    var list = changes();
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
      var detail = s.audience === "residential"
        ? s.area_sqft + " pi² · " + (s.frequency === "biweekly" ? "aux 2 semaines" : "une seule fois") +
          (s.extras.length ? " · four" : "")
        : s.restrooms + " sanitaires · hebdo · de soir";
      return '<div class="scenario' + (index === chosen ? " on" : "") + '" data-scenario="' + index + '">' +
        "<b>" + A.esc(s.label) + "</b><span>" + A.esc(detail) + "</span></div>";
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
    else if (key.indexOf("extra:") === 0) draft.grid.extras_cents[key.slice(6)] = value;
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
    html += '<div style="margin-top:16px"><span class="field-label" style="font-size:0.68rem">Détail du brouillon</span>';
    html += row.draft_lines.map(function (line) {
      return '<div class="summary-line" style="padding-top:8px"><span>' + A.esc(line.label_fr) +
        "</span><span>" + A.moneyExact(line.amount_cents) + "</span></div>";
    }).join("") + "</div>";
    el.result.innerHTML = html;
  }

  /* ---------- publish ---------- */

  function openReview() {
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

    el.review.hidden = false;
  }

  function publish() {
    var button = document.getElementById("review-confirm");
    button.disabled = true;
    button.textContent = "Publication…";
    A.api("/rate-card", { method: "POST", body: JSON.stringify(draft) })
      .then(function (card) {
        clearDraft();
        el.review.hidden = true;
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
  document.getElementById("review-cancel").addEventListener("click", function () { el.review.hidden = true; });
  document.getElementById("review-confirm").addEventListener("click", publish);
  el.review.addEventListener("click", function (event) {
    if (event.target === el.review) el.review.hidden = true;
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
        el.pageError.textContent = err && err.status === 404
          ? "Aucune carte active. Lancez python -m scripts.seed_rate_card pour en créer une."
          : A.apiMessage(err);
        el.pageError.hidden = false;
      });
  }

  A.boot({ onAuthed: start });
})();
