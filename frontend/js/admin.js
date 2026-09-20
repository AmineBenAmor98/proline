/* Proline admin. One screen: the request list, with an editable sent price.
 * Auth is the shared ADMIN_TOKEN, kept in localStorage for this browser only.
 */
(function () {
  "use strict";

  var KEY = "proline_admin_token";
  var login = document.getElementById("login");
  var panel = document.getElementById("panel");
  var tbody = document.querySelector("#requests tbody");
  var stats = document.getElementById("stats");
  var panelError = document.getElementById("panel-error");
  var loginError = document.getElementById("login-error");
  var empty = document.getElementById("empty");
  var logoutBtn = document.getElementById("logout-btn");

  function token() {
    try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; }
  }

  function setToken(value) {
    try { value ? localStorage.setItem(KEY, value) : localStorage.removeItem(KEY); } catch (e) {}
  }

  function money(cents) {
    if (cents === null || cents === undefined) return "—";
    return new Intl.NumberFormat("fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  function when(iso) {
    var d = new Date(iso);
    return d.toLocaleString("fr-CA", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function api(path, options) {
    options = options || {};
    options.headers = Object.assign(
      { "Content-Type": "application/json", Authorization: "Bearer " + token() },
      options.headers || {}
    );
    return fetch("/api/admin" + path, options).then(function (res) {
      if (res.status === 401) { showLogin("Jeton refusé."); return Promise.reject("auth"); }
      if (!res.ok) return Promise.reject(res.status);
      return res.json();
    });
  }

  function showLogin(message) {
    login.hidden = false;
    panel.hidden = true;
    logoutBtn.hidden = true;
    if (message) { loginError.textContent = message; loginError.hidden = false; }
  }

  function currentStatus() {
    var el = document.querySelector('input[name="status"]:checked');
    return el && el.value ? el.value : "";
  }

  function statusChip(status) {
    var labels = { new: "Nouvelle", enriching: "Analyse", priced: "Chiffrée",
                   quoted: "Envoyée", won: "Gagnée", lost: "Perdue" };
    var cls = { new: "chip--new", quoted: "chip--quoted", won: "chip--won", lost: "chip--lost" };
    return '<span class="chip ' + (cls[status] || "") + '">' + (labels[status] || status) + "</span>";
  }

  function propertyCell(row) {
    var parts = [row.property_type];
    if (row.area_sqft) parts.push(row.area_sqft + " pi²");
    if (row.bedrooms) parts.push(row.bedrooms + " ch.");
    if (row.bathrooms) parts.push(row.bathrooms + " sdb");
    if (row.restrooms) parts.push(row.restrooms + " sanit.");
    return escapeHtml(parts.join(" · "));
  }

  function contactCell(row) {
    var lines = ["<strong>" + escapeHtml(row.full_name) + "</strong>"];
    if (row.company) lines.push(escapeHtml(row.company));
    if (row.phone) lines.push('<a href="tel:' + escapeHtml(row.phone) + '">' + escapeHtml(row.phone) + "</a>");
    if (row.email) lines.push('<a href="mailto:' + escapeHtml(row.email) + '">' + escapeHtml(row.email) + "</a>");
    return lines.join("<br>");
  }

  function render(data) {
    stats.innerHTML =
      '<div class="stat"><b>' + data.total + "</b>Total</div>" +
      Object.keys(data.counts_by_status).map(function (key) {
        return '<div class="stat"><b>' + data.counts_by_status[key] + "</b>" + key + "</div>";
      }).join("");

    empty.hidden = data.items.length > 0;
    tbody.innerHTML = data.items.map(function (row) {
      return "<tr data-id=\"" + row.id + "\">" +
        "<td>" + when(row.created_at) + "</td>" +
        "<td>" + contactCell(row) + "</td>" +
        "<td>" + propertyCell(row) + "</td>" +
        "<td>" + escapeHtml(row.audience + " · " + row.frequency) +
          (row.access_notes ? '<br><span class="note">' + escapeHtml(row.access_notes.slice(0, 80)) + "</span>" : "") +
        "</td>" +
        "<td>" + money(row.computed_total_cents) + "</td>" +
        '<td><input type="number" class="quoted" style="min-height:36px;width:110px" value="' +
          (row.quoted_total_cents !== null && row.quoted_total_cents !== undefined ? row.quoted_total_cents / 100 : "") +
          '" placeholder="$"></td>' +
        "<td>" + statusChip(row.status) +
          '<br><select class="status-select" style="min-height:36px;margin-top:6px">' +
          ["new", "priced", "quoted", "won", "lost"].map(function (s) {
            return '<option value="' + s + '"' + (s === row.status ? " selected" : "") + ">" + s + "</option>";
          }).join("") + "</select></td>" +
        "<td>" + escapeHtml(row.utm_campaign || (row.gclid ? "Google Ads" : "direct")) + "</td>" +
        "</tr>";
    }).join("");
  }

  function load() {
    panelError.hidden = true;
    var status = currentStatus();
    api("/requests" + (status ? "?status=" + status : ""))
      .then(function (data) {
        login.hidden = true;
        panel.hidden = false;
        logoutBtn.hidden = false;
        render(data);
      })
      .catch(function (err) {
        if (err === "auth") return;
        panelError.textContent = "Chargement impossible (" + err + ").";
        panelError.hidden = false;
      });
  }

  function patch(id, body) {
    return api("/requests/" + id, { method: "PATCH", body: JSON.stringify(body) })
      .then(load)
      .catch(function (err) {
        if (err === "auth") return;
        panelError.textContent = "Enregistrement impossible (" + err + ").";
        panelError.hidden = false;
      });
  }

  tbody.addEventListener("change", function (event) {
    var row = event.target.closest("tr");
    if (!row) return;
    var id = row.dataset.id;
    if (event.target.classList.contains("quoted")) {
      var dollars = parseFloat(event.target.value);
      if (isNaN(dollars)) return;
      patch(id, { quoted_total_cents: Math.round(dollars * 100) });
    }
    if (event.target.classList.contains("status-select")) {
      patch(id, { status: event.target.value });
    }
  });

  document.querySelectorAll('input[name="status"]').forEach(function (el) {
    el.addEventListener("change", load);
  });

  document.getElementById("login-form").addEventListener("submit", function (event) {
    event.preventDefault();
    loginError.hidden = true;
    setToken(document.getElementById("token").value.trim());
    load();
  });

  document.getElementById("refresh-btn").addEventListener("click", load);
  logoutBtn.addEventListener("click", function () { setToken(""); showLogin(""); });

  if (token()) load();
  else showLogin("");
})();
