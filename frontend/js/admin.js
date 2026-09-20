/* Proline admin.
 * Sign in with username and password, then one screen: the request list, with an
 * editable sent price. The token from /api/admin/login is kept in localStorage
 * and expires after 12 hours.
 */
(function () {
  "use strict";

  var KEY = "proline_admin_session";
  var login = document.getElementById("login");
  var panel = document.getElementById("panel");
  var loginForm = document.getElementById("login-form");
  var loginBtn = document.getElementById("login-btn");
  var loginError = document.getElementById("login-error");
  var panelError = document.getElementById("panel-error");
  var tbody = document.querySelector("#requests tbody");
  var stats = document.getElementById("stats");
  var empty = document.getElementById("empty");
  var who = document.getElementById("who");

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

  function session() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }
  function setSession(value) {
    try {
      if (value) localStorage.setItem(KEY, JSON.stringify(value));
      else localStorage.removeItem(KEY);
    } catch (e) { /* private mode */ }
  }

  function money(cents) {
    if (cents === null || cents === undefined) return "—";
    return new Intl.NumberFormat("fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  function when(iso) {
    return new Date(iso).toLocaleString("fr-CA", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"
    });
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function api(path, options) {
    var current = session();
    options = options || {};
    options.headers = Object.assign(
      { "Content-Type": "application/json" },
      current ? { Authorization: "Bearer " + current.token } : {},
      options.headers || {}
    );
    return fetch("/api/admin" + path, options).then(function (res) {
      if (res.status === 401) {
        setSession(null);
        showLogin("Session expirée. Reconnectez-vous.");
        return Promise.reject("auth");
      }
      if (!res.ok) return Promise.reject(res.status);
      return res.json();
    });
  }

  function showLogin(message) {
    login.hidden = false;
    panel.hidden = true;
    document.body.classList.add("admin-body");
    if (message) { loginError.textContent = message; loginError.hidden = false; }
    else loginError.hidden = true;
  }

  function showPanel(username) {
    login.hidden = true;
    panel.hidden = false;
    document.body.classList.remove("admin-body");
    who.textContent = username ? "Connecté : " + username : "";
  }

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
    return esc(parts.join(" · ")) + (city ? '<br><span class="note">' + esc(city) + "</span>" : "");
  }

  function contactCell(row) {
    var lines = ["<strong>" + esc(row.full_name) + "</strong>"];
    if (row.company) lines.push(esc(row.company));
    if (row.phone) lines.push('<a href="tel:' + esc(row.phone) + '">' + esc(row.phone) + "</a>");
    if (row.email) lines.push('<a href="mailto:' + esc(row.email) + '">' + esc(row.email) + "</a>");
    return lines.join("<br>");
  }

  function render(data) {
    var counts = data.counts_by_status || {};
    var tiles = [{ label: "Total", value: data.total }];
    Object.keys(counts).forEach(function (key) {
      tiles.push({ label: STATUS_LABELS[key] || key, value: counts[key] });
    });
    stats.innerHTML = tiles.map(function (t) {
      return '<div class="stat"><b>' + t.value + "</b><span>" + esc(t.label) + "</span></div>";
    }).join("");

    empty.hidden = data.items.length > 0;
    tbody.innerHTML = data.items.map(function (row) {
      var quoted = row.quoted_total_cents;
      return '<tr data-id="' + row.id + '">' +
        "<td>" + when(row.created_at) + "</td>" +
        "<td>" + contactCell(row) + "</td>" +
        "<td>" + propertyCell(row) + "</td>" +
        "<td>" + esc((row.audience === "residential" ? "Résidentiel" : "Commercial") + " · " +
          (FREQUENCY_LABELS[row.frequency] || row.frequency)) +
          (row.access_notes ? '<br><span class="note">' + esc(row.access_notes.slice(0, 70)) + "</span>" : "") +
        "</td>" +
        "<td>" + money(row.computed_total_cents) + "</td>" +
        '<td><input type="number" class="quoted" style="width:118px" placeholder="$" value="' +
          (quoted !== null && quoted !== undefined ? quoted / 100 : "") + '"></td>' +
        "<td>" + statusChip(row.status) +
          '<br><select class="status-select" style="margin-top:8px;width:128px">' +
          ["new", "priced", "quoted", "won", "lost"].map(function (s) {
            return '<option value="' + s + '"' + (s === row.status ? " selected" : "") + ">" +
              STATUS_LABELS[s] + "</option>";
          }).join("") + "</select></td>" +
        "<td>" + esc(row.utm_campaign || (row.gclid ? "Google Ads" : "direct")) + "</td>" +
        "</tr>";
    }).join("");
  }

  function load() {
    panelError.hidden = true;
    var status = currentStatus();
    api("/requests" + (status ? "?status=" + status : ""))
      .then(function (data) {
        var current = session();
        showPanel(current && current.username);
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

  loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    loginError.hidden = true;
    loginBtn.disabled = true;
    loginBtn.textContent = "Connexion…";

    fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value,
        password: document.getElementById("password").value
      })
    })
      .then(function (res) {
        if (res.status === 401) return Promise.reject("bad");
        if (!res.ok) return Promise.reject(res.status);
        return res.json();
      })
      .then(function (data) {
        setSession({ token: data.token, username: data.username });
        document.getElementById("password").value = "";
        load();
      })
      .catch(function (err) {
        loginError.textContent = err === "bad"
          ? "Nom d'utilisateur ou mot de passe incorrect."
          : "Connexion impossible (" + err + ").";
        loginError.hidden = false;
      })
      .then(function () {
        loginBtn.disabled = false;
        loginBtn.textContent = "Se connecter";
      });
  });

  document.getElementById("refresh-btn").addEventListener("click", load);
  document.getElementById("logout-btn").addEventListener("click", function () {
    setSession(null);
    showLogin("");
  });

  if (session()) load();
  else showLogin("");
})();
