/* The requests screen: one list, with an editable sent price and a status.
 * Session, sign-in and formatting live in admin-common.js, shared with /admin/tarifs.
 */
(function () {
  "use strict";

  var A = window.ProlineAdmin;
  var panelError = document.getElementById("panel-error");
  var tbody = document.querySelector("#requests tbody");
  var stats = document.getElementById("stats");
  var empty = document.getElementById("empty");

  var STATUS_LABELS = {
    new: "Nouvelle", enriching: "Analyse", priced: "Chiffrée",
    quoted: "Envoyée", won: "Gagnée", lost: "Perdue"
  };

  var FREQUENCY_LABELS = {
    one_time: "Une seule fois", weekly: "Chaque semaine", biweekly: "Aux 2 semaines",
    monthly: "Mensuel", to_discuss: "À déterminer"
  };

  var PROPERTY_LABELS = {
    house: "Maison", condo: "Condo", apartment: "Appartement", office: "Bureau",
    retail: "Commerce", building: "Immeuble", industrial: "Industriel",
    construction: "Chantier"
  };

  function currentStatus() {
    var el = document.querySelector('input[name="status"]:checked');
    return el && el.value ? el.value : "";
  }

  function statusChip(status) {
    var cls = { new: "chip--new", quoted: "chip--quoted", won: "chip--won", lost: "chip--lost" };
    return '<span class="chip ' + (cls[status] || "") + '">' +
      (STATUS_LABELS[status] || status) + "</span>";
  }

  function propertyCell(row) {
    var parts = [PROPERTY_LABELS[row.property_type] || row.property_type];
    if (row.area_sqft) parts.push(row.area_sqft + " pi²");
    if (row.bedrooms) parts.push(row.bedrooms + " ch.");
    if (row.bathrooms) parts.push(row.bathrooms + " sdb");
    if (row.restrooms) parts.push(row.restrooms + " sanit.");
    var city = row.borough || row.city;
    return A.esc(parts.join(" · ")) + (city ? '<br><span class="note">' + A.esc(city) + "</span>" : "");
  }

  function contactCell(row) {
    var lines = ["<strong>" + A.esc(row.full_name) + "</strong>"];
    if (row.company) lines.push(A.esc(row.company));
    if (row.phone) lines.push('<a href="tel:' + A.esc(row.phone) + '">' + A.esc(row.phone) + "</a>");
    if (row.email) lines.push('<a href="mailto:' + A.esc(row.email) + '">' + A.esc(row.email) + "</a>");
    return lines.join("<br>");
  }

  function render(data) {
    var counts = data.counts_by_status || {};
    var tiles = [{ label: "Total", value: data.total }];
    Object.keys(counts).forEach(function (key) {
      tiles.push({ label: STATUS_LABELS[key] || key, value: counts[key] });
    });
    stats.innerHTML = tiles.map(function (t) {
      return '<div class="stat"><b>' + t.value + "</b><span>" + A.esc(t.label) + "</span></div>";
    }).join("");

    empty.hidden = data.items.length > 0;
    tbody.innerHTML = data.items.map(function (row) {
      var quoted = row.quoted_total_cents;
      return '<tr data-id="' + row.id + '">' +
        "<td>" + A.when(row.created_at) + "</td>" +
        "<td>" + contactCell(row) + "</td>" +
        "<td>" + propertyCell(row) + "</td>" +
        "<td>" + A.esc((row.audience === "residential" ? "Résidentiel" : "Commercial") + " · " +
          (FREQUENCY_LABELS[row.frequency] || row.frequency)) +
          (row.access_notes ? '<br><span class="note">' + A.esc(row.access_notes.slice(0, 70)) + "</span>" : "") +
        "</td>" +
        "<td>" + A.money(row.computed_total_cents) + "</td>" +
        '<td><input type="number" class="quoted" style="width:118px" placeholder="$" value="' +
          (quoted !== null && quoted !== undefined ? quoted / 100 : "") + '"></td>' +
        "<td>" + statusChip(row.status) +
          '<br><select class="status-select" style="margin-top:8px;width:128px">' +
          ["new", "priced", "quoted", "won", "lost"].map(function (s) {
            return '<option value="' + s + '"' + (s === row.status ? " selected" : "") + ">" +
              STATUS_LABELS[s] + "</option>";
          }).join("") + "</select></td>" +
        "<td>" + A.esc(row.utm_campaign || (row.gclid ? "Google Ads" : "direct")) + "</td>" +
        "</tr>";
    }).join("");
  }

  function load() {
    panelError.hidden = true;
    var status = currentStatus();
    A.api("/requests" + (status ? "?status=" + status : ""))
      .then(render)
      .catch(function (err) {
        if (err === "auth") return;
        panelError.textContent = "Chargement impossible : " + A.apiMessage(err);
        panelError.hidden = false;
      });
  }

  function patch(id, body) {
    return A.api("/requests/" + id, { method: "PATCH", body: JSON.stringify(body) })
      .then(load)
      .catch(function (err) {
        if (err === "auth") return;
        panelError.textContent = "Enregistrement impossible : " + A.apiMessage(err);
        panelError.hidden = false;
      });
  }

  tbody.addEventListener("change", function (event) {
    var row = event.target.closest("tr");
    if (!row) return;
    if (event.target.classList.contains("quoted")) {
      var dollars = parseFloat(event.target.value);
      if (isNaN(dollars)) return;
      patch(row.dataset.id, { quoted_total_cents: Math.round(dollars * 100) });
    }
    if (event.target.classList.contains("status-select")) {
      patch(row.dataset.id, { status: event.target.value });
    }
  });

  document.querySelectorAll('input[name="status"]').forEach(function (el) {
    el.addEventListener("change", load);
  });
  document.getElementById("refresh-btn").addEventListener("click", load);

  A.boot({ onAuthed: load });
})();
