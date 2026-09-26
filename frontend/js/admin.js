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

  var STATUS_LABELS = A.STATUS_LABELS;
  var STATUS_ORDER = A.STATUS_ORDER;
  var FREQUENCY_LABELS = A.FREQUENCY_LABELS;
  var PROPERTY_LABELS = A.PROPERTY_LABELS;
  var SERVICE_LABELS = A.SERVICE_LABELS;

  function currentStatus() {
    var el = document.querySelector('input[name="status"]:checked');
    return el && el.value ? el.value : "";
  }

  /* The status IS the control: a select styled as the chip it used to sit under.
     Two elements showing the same value, one of them read-only, was noise in the
     narrowest column on the screen. */
  function statusPicker(row) {
    return '<select class="statuspick" data-status="' + A.esc(row.status) + '" aria-label="' +
      A.esc("Statut — " + row.full_name) + '">' +
      STATUS_ORDER.map(function (code) {
        return '<option value="' + code + '"' + (code === row.status ? " selected" : "") + ">" +
          A.esc(STATUS_LABELS[code]) + "</option>";
      }).join("") + "</select>";
  }

  function propertyCell(row) {
    var parts = [PROPERTY_LABELS[row.property_type] || row.property_type];
    if (row.area_sqft) parts.push(row.area_sqft + " pi²");
    if (row.bedrooms) parts.push(row.bedrooms + " ch.");
    if (row.bathrooms) parts.push(row.bathrooms + " sdb");
    if (row.restrooms) parts.push(row.restrooms + " sanit.");
    /* Nothing prices the number of floors, but three storeys is a different job
       and whoever writes the quote has to know. It was being collected and shown
       to no one. */
    if (row.floors > 1) parts.push(row.floors + " étages");

    var where = [row.address_line, row.borough || row.city, row.postal_code]
      .filter(Boolean).join(", ");
    return A.esc(parts.join(" · ")) +
      (where ? '<br><span class="note">' + A.esc(where) + "</span>" : "");
  }

  /* What was asked for, not just what it came to. A total of 600 $ tells nobody
     that the job includes forty windows and the baseboards. */
  function needCell(row) {
    var head = (row.audience === "residential" ? "Résidentiel" : "Commercial") + " · " +
      (FREQUENCY_LABELS[row.frequency] || row.frequency);
    var out = "<strong>" + A.esc(head) + "</strong>";

    var services = (row.services || []).map(function (code) {
      return SERVICE_LABELS[code] || code;
    });
    if (row.night_access) services.push("accès de nuit");
    if (services.length) out += '<br><span class="note">' + A.esc(services.join(" · ")) + "</span>";

    /* The answers that changed the price first -- they describe the job, and a
       459 $ quote next to a 221 $ one is otherwise unexplained -- then the
       extras, which are things added to it. */
    if ((row.modifiers || []).length) {
      out += '<br><span class="need-tags">' + row.modifiers.map(function (item) {
        return '<span class="need-tag need-tag--mod">' + A.esc(item.label) + "</span>";
      }).join("") + "</span>";
    }
    if ((row.extras || []).length) {
      out += '<br><span class="need-tags">' + row.extras.map(function (item) {
        var qty = item.quantity ? " × " + item.quantity + (item.unit ? " " + item.unit : "") : "";
        return '<span class="need-tag">' + A.esc(item.label + qty) + "</span>";
      }).join("") + "</span>";
    }
    var when = [];
    if (row.desired_start) when.push("dès le " + A.day(row.desired_start));
    if (row.preferred_contact) {
      when.push(row.preferred_contact === "phone" ? "préfère le téléphone" : "préfère le courriel");
    }
    if (when.length) out += '<br><span class="note">' + A.esc(when.join(" · ")) + "</span>";

    if (row.access_notes) {
      out += '<br><span class="note">' + A.esc(row.access_notes.slice(0, 70)) +
        (row.access_notes.length > 70 ? "…" : "") + "</span>";
    }
    return out;
  }

  function contactCell(row) {
    /* The name is the way into the full request -- photos, access notes and the
       rest of what does not fit in a table row. Linking the name rather than
       adding a "view" column keeps the table the width it already is. */
    var lines = [
      '<a class="rowlink" href="/admin/demande?id=' + A.esc(row.id) + '">' +
        "<strong>" + A.esc(row.full_name) + "</strong></a>"
    ];
    if (row.company) lines.push(A.esc(row.company));
    if (row.phone) lines.push('<a href="tel:' + A.esc(row.phone) + '">' + A.esc(row.phone) + "</a>");
    if (row.email) lines.push('<a href="mailto:' + A.esc(row.email) + '">' + A.esc(row.email) + "</a>");
    return lines.join("<br>");
  }

  function renderStats(data) {
    var counts = data.counts_by_status || {};
    var tiles = [{ label: "Total", value: data.total, code: "" }];
    STATUS_ORDER.forEach(function (code) {
      tiles.push({ label: STATUS_LABELS[code], value: counts[code] || 0, code: code });
    });
    stats.innerHTML = tiles.map(function (t) {
      return '<div class="stat" data-status="' + A.esc(t.code) + '"><b>' + t.value +
        "</b><span>" + A.esc(t.label) + "</span></div>";
    }).join("");
  }

  var lastRows = [];

  function render(data) {
    lastRows = data.items;
    renderStats(data);
    empty.hidden = data.items.length > 0;
    tbody.innerHTML = data.items.map(function (row) {
      var quoted = row.quoted_total_cents;
      return '<tr data-id="' + row.id + '">' +
        "<td>" + A.when(row.created_at) + "</td>" +
        "<td>" + contactCell(row) + "</td>" +
        "<td>" + propertyCell(row) + "</td>" +
        "<td>" + needCell(row) + "</td>" +
        /* No computed price is a queue, not a blank. Say so where the number
           would be, since that is where the eye already is. */
        "<td>" + (row.computed_total_cents === null || row.computed_total_cents === undefined
          ? '<span class="todo">à chiffrer</span>'
          : A.money(row.computed_total_cents)) + "</td>" +
        '<td><input type="text" inputmode="decimal" class="quoted" style="width:118px" ' +
          'placeholder="$" aria-label="' + A.esc("Prix envoyé — " + row.full_name) + '" value="' +
          (quoted !== null && quoted !== undefined ? A.moneyExact(quoted) : "") + '"></td>' +
        "<td>" + statusPicker(row) + "</td>" +
        /* Disabled without an address rather than hidden: a row with no email is
           a phone call, and the greyed button with its reason says that, where a
           missing button would just look like a bug. */
        '<td><a class="btn btn-ghost btn-sm" href="/admin/demande?id=' + A.esc(row.id) +
          /* Always a link, even with no email: the page carries the photos and
             the phone number, which is how an emailless request gets quoted. */
          (row.email ? '">Ouvrir' : '" title="Pas de courriel — à rappeler">Ouvrir') +
          "</a></td>" +
        "<td>" + A.esc(row.utm_campaign || (row.gclid ? "Google Ads" : "direct")) + "</td>" +
        "</tr>";
    }).join("");
  }


  /* THE OFFER COMPOSER USED TO LIVE HERE, as a dialog over this table.

     It moved to /admin/demande, and not for tidiness. Quoting well now means
     looking at the customer's photos first -- that is the entire reason they
     are collected -- and a composer that opens straight from the inbox is a
     way to send a price without ever having seen them. The Offre column links
     to that page now, so the photos are always on the path to the send button
     rather than somewhere off to one side.

     `git log -p -- frontend/js/admin.js` has the dialog if it is ever wanted. */

  function load() {
    panelError.hidden = true;
    var status = currentStatus();
    A.api("/requests" + (status ? "?status=" + status : ""))
      .then(render)
      .catch(function (err) {
        if (err === "auth") return;
        /* The table stays empty behind this, so the message has to carry both
           what happened and the way back. */
        panelError.innerHTML = A.esc(A.apiMessage(err)) +
          ' <button type="button" class="linkbtn" id="retry-list">Réessayer</button>';
        panelError.hidden = false;
        var retry = document.getElementById("retry-list");
        if (retry) retry.addEventListener("click", load);
      });
  }

  /* Saving one row used to reload the whole table, and the change event that
     triggers the save fires on blur -- by which time focus has already landed in
     the NEXT row's price field. That field was then replaced mid-keystroke and
     everything typed into it was lost. /admin/tarifs learned this the hard way
     and updates in place; this screen never did.

     So: patch, then update only the row that changed. A full reload is still
     what the filters and the refresh button do, deliberately. */
  function patch(row, body) {
    var id = row.dataset.id;
    return A.api("/requests/" + id, { method: "PATCH", body: JSON.stringify(body) })
      .then(function (updated) {
        row.classList.add("saved");
        setTimeout(function () { row.classList.remove("saved"); }, 900);
        var quoted = row.querySelector(".quoted");
        if (quoted && document.activeElement !== quoted &&
            updated && updated.quoted_total_cents !== null &&
            updated.quoted_total_cents !== undefined) {
          quoted.value = A.moneyExact(updated.quoted_total_cents);
        }
        var select = row.querySelector(".statuspick");
        if (select && updated && updated.status) {
          select.dataset.status = updated.status;
          if (document.activeElement !== select) select.value = updated.status;
        }
        refreshCounts();
      })
      .catch(function (err) {
        if (err === "auth") return;
        panelError.textContent = "Enregistrement impossible : " + A.apiMessage(err);
        panelError.hidden = false;
      });
  }

  /* The tallies at the top move when a status does. Fetched on its own so the
     table -- and whatever the user is typing into it -- is left alone. */
  function refreshCounts() {
    A.api("/requests?limit=1").then(function (data) {
      renderStats(data);
    }).catch(function () { /* the tallies are not worth an error message */ });
  }

  tbody.addEventListener("change", function (event) {
    var row = event.target.closest("tr");
    if (!row) return;
    if (event.target.classList.contains("quoted")) {
      var cents = A.parseMoney(event.target.value);
      event.target.classList.toggle("bad", cents === null && event.target.value !== "");
      if (cents === null) return;
      patch(row, { quoted_total_cents: cents });
    }
    if (event.target.classList.contains("statuspick")) {
      patch(row, { status: event.target.value });
    }
  });

  document.querySelectorAll('input[name="status"]').forEach(function (el) {
    el.addEventListener("change", load);
  });
  document.getElementById("refresh-btn").addEventListener("click", load);

  A.boot({ onAuthed: load });
})();
