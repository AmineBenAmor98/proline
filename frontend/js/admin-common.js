/* Shared by every admin screen: the session, the fetch wrapper, the sign-in gate
 * and the formatting helpers. The sign-in markup is injected from here rather than
 * copied into each page, so there is one login screen, not one per screen.
 */
window.ProlineAdmin = (function () {
  "use strict";

  var KEY = "proline_admin_session";

  function session() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }

  function setSession(value) {
    try {
      if (value) localStorage.setItem(KEY, JSON.stringify(value));
      else localStorage.removeItem(KEY);
    } catch (e) { /* private mode */ }
  }

  /* ---------- formatting ---------- */

  function money(cents) {
    if (cents === null || cents === undefined) return "—";
    return new Intl.NumberFormat("fr-CA", {
      style: "currency", currency: "CAD", maximumFractionDigits: 0
    }).format(cents / 100);
  }

  /* Cents in, "195,00 $" out. The rate card needs the cents, the request list does not. */
  function moneyExact(cents) {
    if (cents === null || cents === undefined) return "—";
    return new Intl.NumberFormat("fr-CA", {
      style: "currency", currency: "CAD", minimumFractionDigits: 2, maximumFractionDigits: 2
    }).format(cents / 100);
  }

  /* The cents boundary, in one place. Accepts what fr-CA produces and what a person
     types: "195,00 $", "195.00", "1 950", "1 950,50 $" with any kind of space.
     Returns null for anything else rather than guessing. */
  function parseMoney(text) {
    if (text === null || text === undefined) return null;
    var cleaned = String(text)
      .replace(/[\s   ]/g, "")
      .replace(/\$/g, "")
      .replace(",", ".");
    if (cleaned === "") return null;
    if (!/^-?\d+(\.\d{1,2})?$/.test(cleaned)) return null;
    return Math.round(parseFloat(cleaned) * 100);
  }

  function parseIntStrict(text) {
    if (text === null || text === undefined) return null;
    var cleaned = String(text).replace(/[\s   ]/g, "").replace(/(min|%|×|x|pi²)/gi, "");
    if (cleaned === "") return null;
    if (!/^-?\d+$/.test(cleaned)) return null;
    return parseInt(cleaned, 10);
  }

  function parseDecimalStrict(text) {
    if (text === null || text === undefined) return null;
    var cleaned = String(text)
      .replace(/[\s   ]/g, "").replace(/[×x%]/gi, "").replace(",", ".");
    if (cleaned === "") return null;
    if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
    return parseFloat(cleaned);
  }

  function when(iso) {
    return new Date(iso).toLocaleString("fr-CA", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"
    });
  }

  function day(iso) {
    if (!iso) return "—";
    return new Date(iso + "T12:00:00").toLocaleDateString("fr-CA", {
      day: "numeric", month: "short", year: "numeric"
    });
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /* ---------- the gate ---------- */

  var onAuthed = null;

  var LOGIN_HTML =
    '<div class="login-screen" id="login">' +
    '  <form class="login-card" id="login-form" novalidate>' +
    '    <img src="/img/logo.png" alt="" width="64" height="64">' +
    '    <div class="login-head">' +
    '      <span class="brand-name">PROLINE</span>' +
    '      <span class="brand-sub">Cleaning Solutions</span>' +
    '    </div>' +
    '    <h1>Espace admin</h1>' +
    '    <p class="note">Connectez-vous pour gérer les demandes et les tarifs.</p>' +
    '    <div class="field">' +
    '      <label for="username">Nom d\'utilisateur</label>' +
    '      <input type="text" id="username" name="username" autocomplete="username" required autofocus>' +
    '    </div>' +
    '    <div class="field">' +
    '      <label for="password">Mot de passe</label>' +
    '      <input type="password" id="password" name="password" autocomplete="current-password" required>' +
    '    </div>' +
    '    <div id="login-error" class="alert" hidden role="alert"></div>' +
    '    <button class="btn btn-primary btn-lg" type="submit" id="login-btn" style="width:100%">Se connecter</button>' +
    '    <a class="note" href="/" style="text-align:center">← Retour au site</a>' +
    '  </form>' +
    '</div>';

  function showLogin(message) {
    var login = document.getElementById("login");
    var panel = document.getElementById("panel");
    if (login) login.hidden = false;
    if (panel) panel.hidden = true;
    document.body.classList.add("admin-body");
    var box = document.getElementById("login-error");
    if (box) {
      box.textContent = message || "";
      box.hidden = !message;
    }
  }

  function showPanel() {
    var login = document.getElementById("login");
    var panel = document.getElementById("panel");
    if (login) login.hidden = true;
    if (panel) panel.hidden = false;
    var who = document.getElementById("who");
    var current = session();
    if (who && current) who.textContent = "Connecté : " + current.username;
    if (onAuthed) onAuthed();
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
      if (!res.ok) {
        return res.json().then(
          function (body) { return Promise.reject({ status: res.status, body: body }); },
          function () { return Promise.reject({ status: res.status, body: null }); }
        );
      }
      if (res.status === 204) return null;
      return res.json();
    });
  }

  /* Pydantic reports a list of errors; show the first one in words. */
  function apiMessage(error) {
    if (!error || typeof error !== "object") return "Erreur inattendue.";
    var detail = error.body && error.body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      return String(detail[0].msg || "").replace(/^Value error,\s*/, "");
    }
    return "Erreur " + (error.status || "");
  }

  function boot(options) {
    onAuthed = (options || {}).onAuthed || null;
    document.body.insertAdjacentHTML("afterbegin", LOGIN_HTML);

    document.getElementById("login-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var button = document.getElementById("login-btn");
      var box = document.getElementById("login-error");
      box.hidden = true;
      button.disabled = true;
      button.textContent = "Connexion…";

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
          showPanel();
        })
        .catch(function (err) {
          box.textContent = err === "bad"
            ? "Nom d'utilisateur ou mot de passe incorrect."
            : "Connexion impossible (" + err + ").";
          box.hidden = false;
        })
        .then(function () {
          button.disabled = false;
          button.textContent = "Se connecter";
        });
    });

    var logout = document.getElementById("logout-btn");
    if (logout) {
      logout.addEventListener("click", function () {
        setSession(null);
        showLogin("");
      });
    }

    if (session()) showPanel();
    else showLogin("");
  }

  return {
    boot: boot, api: api, apiMessage: apiMessage,
    session: session, setSession: setSession, showLogin: showLogin,
    money: money, moneyExact: moneyExact, parseMoney: parseMoney,
    parseIntStrict: parseIntStrict, parseDecimalStrict: parseDecimalStrict,
    when: when, day: day, esc: esc
  };
})();
