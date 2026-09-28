/* Shared by every admin screen: the session, the fetch wrapper, the sign-in gate
 * and the formatting helpers. The sign-in markup is injected from here rather than
 * copied into each page, so there is one login screen, not one per screen.
 */
window.ProlineAdmin = (function () {
  "use strict";

  var KEY = "proline_admin_session";

  /* Shared vocabulary. Defined once here because both admin screens render the
     same words, and two copies drifted apart the first time they existed. */
  /* Four states, in workflow order. `priced` and `enriching` are gone: the first
     restated "the calculator produced a number", which the Prix calculé column
     already shows, and nothing ever set the second. */
  var STATUS_ORDER = ["new", "quoted", "won", "lost"];
  var STATUS_LABELS = {
    new: "Nouvelle", quoted: "Envoyée", won: "Gagnée", lost: "Perdue"
  };
  var FREQUENCY_LABELS = {
    one_time: "Une seule fois", weekly: "Chaque semaine", biweekly: "Aux 2 semaines",
    monthly: "Mensuel", to_discuss: "À déterminer"
  };
  /* Explicit, like STATUS_ORDER: a dropdown reads least-often to most-often, and
     that is an editorial decision rather than whatever order the keys happen to
     have been typed in. */
  var FREQUENCY_ORDER = ["one_time", "weekly", "biweekly", "monthly", "to_discuss"];
  var PROPERTY_LABELS = {
    house: "Maison", condo: "Condo", apartment: "Appartement", office: "Bureau",
    retail: "Commerce", building: "Immeuble", industrial: "Industriel",
    construction: "Chantier"
  };

  /* Which property types belong to which half of the business. Mirrors
     AUDIENCE_BY_PROPERTY_TYPE on the server, which is the authority -- the edit
     form offers only the types matching the request's own audience, because
     turning a condo into a shop is a different request and the API refuses it.
     A test reads this table and compares it to the enum, so the copy cannot
     quietly drift from the original. */
  var PROPERTY_TYPES_BY_AUDIENCE = {
    residential: ["house", "condo", "apartment"],
    commercial: ["office", "retail", "building", "industrial", "construction"]
  };

  var LOCALE_LABELS = { fr: "Français", en: "Anglais" };

  /* Commercial services. Extras are NOT listed here on purpose: they live on the
     rate card, which carries their wording, and a second copy would drift. */
  /* Every ServiceCode, and only those. This table had `disinfection`, which the
     enum does not have, and was missing `garage` and `waste_management`, which it
     does -- so a request asking for either showed the operator a raw code, and the
     edit form would have offered no tick box for them at all. A test compares this
     table to the enum for exactly that reason. */
  var SERVICE_LABELS = {
    residential_cleaning: "Ménage résidentiel", office_cleaning: "Bureaux",
    common_areas: "Aires communes", post_construction: "Post-construction",
    end_of_lease: "Fin de bail", floor_stripping_waxing: "Décapage et cirage",
    carpets: "Tapis", windows: "Vitres", garage: "Garage",
    waste_management: "Gestion des déchets"
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
    var box = document.getElementById("login-error");
    if (box) {
      box.textContent = message || "";
      box.hidden = !message;
    }
    /* A session can expire mid-action: the panel vanishes and this form takes
       its place. Without moving the focus, a screen-reader user is left reading
       a page that silently changed under them. (`autofocus` does not fire here:
       the markup is injected after load.) */
    var field = document.getElementById("username");
    if (field && field.focus) field.focus();
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
    }, function () {
      /* fetch rejects only when the request never got an answer: the server is
         not running, or the network went away. Without this it arrived in the
         catch as a TypeError and every screen said "Erreur inattendue." */
      return Promise.reject({ status: 0, body: null });
    });
  }

  /* An authenticated GET that yields an object URL instead of JSON.
   *
   * Customer photos are served behind the admin token, so `<img src="/api/...">`
   * cannot fetch them -- a plain image request carries no Authorization header
   * and comes back 401, which renders as a broken-image icon and no explanation
   * whatsoever. Fetching the bytes here and handing back a blob: URL is what
   * makes an authenticated image displayable at all.
   *
   * The caller owns the URL it gets and must revokeObjectURL when done with it,
   * or a long session leaks every photo it ever looked at.
   */
  function apiBlobUrl(path) {
    var current = session();
    return fetch("/api/admin" + path, {
      headers: current ? { Authorization: "Bearer " + current.token } : {}
    }).then(function (res) {
      if (res.status === 401) {
        setSession(null);
        showLogin("Session expirée. Reconnectez-vous.");
        return Promise.reject("auth");
      }
      if (!res.ok) return Promise.reject({ status: res.status, body: null });
      return res.blob();
    }, function () {
      return Promise.reject({ status: 0, body: null });
    }).then(function (blob) { return URL.createObjectURL(blob); });
  }

  /* What went wrong, in French, and what to do about it.

     This used to pass FastAPI's `detail` straight through, so a dead database
     put "Internal Server Error" on a French admin page and the screen it was
     driving came up blank. A person reading that learns nothing; the thing they
     need to know is that the server is not answering.

     Then it over-corrected, and that was worse. The status map below ran FIRST
     and won every time, so a 502 always read "Le serveur ne répond pas" -- even
     when the server had answered perfectly and said exactly what was wrong. A
     real case: SES refused an offer email because the recipient was not verified
     in its sandbox, the API replied 502 with "Le fournisseur a refusé l'envoi :
     (554, Email address is not verified...)", and the admin was told to check
     the server was running. It was running. Nothing about the message pointed
     anywhere near the actual problem.

     So: a deliberate message from our own API wins, and the status map is the
     fallback for when there is nothing better. The only details worth ignoring
     are the generic ones a framework or a proxy invents when it knows nothing,
     which is what GENERIC_DETAILS is for. */
  var GENERIC_DETAILS = {
    "internal server error": 1,
    "bad gateway": 1,
    "service unavailable": 1,
    "gateway timeout": 1,
    "not found": 1,
    "unprocessable entity": 1
  };

  /* The useful part of a response body, or null if there is nothing worth
     showing. Pydantic reports a list of field errors; the first one names the
     field that is wrong, which is exactly what the person needs. */
  function usefulDetail(body) {
    var detail = body && body.detail;
    if (typeof detail === "string") {
      var text = detail.trim();
      if (!text || GENERIC_DETAILS[text.toLowerCase()]) return null;
      return text;
    }
    if (Array.isArray(detail) && detail.length) {
      return String(detail[0].msg || "").replace(/^Value error,\s*/, "") || null;
    }
    return null;
  }

  var STATUS_MESSAGES = {
    0: "Le serveur ne répond pas. Vérifiez qu'il est démarré, puis rafraîchissez.",
    500: "Le serveur a répondu par une erreur. La base de données est-elle démarrée ?",
    502: "Le serveur ne répond pas. Vérifiez qu'il est démarré, puis rafraîchissez.",
    503: "Le serveur ne répond pas. Vérifiez qu'il est démarré, puis rafraîchissez.",
    504: "Le serveur a mis trop de temps à répondre. Réessayez."
  };

  function apiMessage(error) {
    if (!error || typeof error !== "object") return "Erreur inattendue.";
    /* A thrown Error is not a failed request. This used to fall all the way to
       the bottom and come back as "Erreur " -- the word, a space, and an empty
       status -- which told Amine nothing except that something had gone wrong
       somewhere. A bug in the page is worth naming as such, and worth logging
       with its stack, because the screen it is about to break is not the one
       that failed. */
    if (error instanceof Error) {
      if (window.console && console.error) console.error(error);
      return "Erreur dans la page, pas sur le serveur. Rafraîchissez ; " +
        "si cela recommence, la console du navigateur en a le détail.";
    }
    /* Before the status map, not after. The server knows WHY; a status code only
       knows the category. A status 0 never reaches here with a body -- there was
       no answer to have one -- so it still falls through to the map below. */
    var detail = usefulDetail(error.body);
    if (detail) return detail;

    if (STATUS_MESSAGES[error.status]) return STATUS_MESSAGES[error.status];

    /* Never "Erreur " with nothing after it: without a status there is no status
       to show, and the number alone was never the useful part anyway. */
    return error.status
      ? "Le serveur a refusé la demande (erreur " + error.status + ")."
      : "Erreur inattendue. Rafraîchissez et réessayez.";
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
    STATUS_LABELS: STATUS_LABELS, STATUS_ORDER: STATUS_ORDER, FREQUENCY_LABELS: FREQUENCY_LABELS,
    FREQUENCY_ORDER: FREQUENCY_ORDER,
    PROPERTY_LABELS: PROPERTY_LABELS, SERVICE_LABELS: SERVICE_LABELS,
    PROPERTY_TYPES_BY_AUDIENCE: PROPERTY_TYPES_BY_AUDIENCE,
    LOCALE_LABELS: LOCALE_LABELS,
    boot: boot, api: api, apiBlobUrl: apiBlobUrl, apiMessage: apiMessage,
    money: money, moneyExact: moneyExact, parseMoney: parseMoney,
    parseIntStrict: parseIntStrict, parseDecimalStrict: parseDecimalStrict,
    when: when, day: day, esc: esc
  };
})();
