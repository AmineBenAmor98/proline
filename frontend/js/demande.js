/* One request, in full: photos, what was asked for, who asked, and the offer.
 *
 * The inbox table answers "what came in today". This page answers "should I
 * quote this, and at what price" -- which needs the photos at a size you can
 * actually judge dirt from, and the access notes that decide how long the job
 * takes. Those do not fit in a table row, which is why this page exists.
 *
 * The price field and the send button sit at the TOP of the side column, not
 * the bottom: they are the reason anybody opened the page, and an action parked
 * under three reference cards reads as an afterthought.
 */
(function () {
  "use strict";

  /* `ProlineAdmin` is the global admin-common.js actually exports; `A` is just
     the short name every screen aliases it to. Getting this wrong cost a blank
     page: the whole file is one IIFE, so `A.boot` threw at the bottom, nothing
     ran, and #panel stayed hidden with no login screen and no visible error.
     Hence the guard below -- a missing helper should say so, not show cream. */
  var A = window.ProlineAdmin;
  if (!A) {
    document.documentElement.innerHTML =
      '<pre style="padding:24px;font:14px/1.5 monospace">' +
      "admin-common.js n'a pas été chargé — la page ne peut pas démarrer." +
      "</pre>";
    return;
  }
  var detail = null;
  var objectUrls = [];

  function el(id) { return document.getElementById(id); }

  function param(name) {
    return new URLSearchParams(window.location.search).get(name) || "";
  }

  /* A <dt>/<dd> pair, skipped entirely when there is nothing to say. An empty
     field printed as "—" is noise; six of them hide the two that matter. */
  function fact(list, label, value) {
    if (value === null || value === undefined || value === "") return;
    /* The pair goes in a wrapper, so the grid moves a fact rather than a <dt> and
       a <dd> independently. Without it a three-column grid laid "TYPE | Commerce |
       SUPERFICIE" on one row and "2112 pi² | TOILETTES | 88" on the next -- every
       label against somebody else's value. (A <div> between <dl> and <dt>/<dd> is
       valid HTML5 and keeps the list semantics intact.) */
    var wrap = document.createElement("div");
    wrap.className = "fact";
    var dt = document.createElement("dt");
    dt.textContent = label;
    var dd = document.createElement("dd");
    dd.textContent = String(value);
    wrap.appendChild(dt);
    wrap.appendChild(dd);
    list.appendChild(wrap);
  }

  function line(label, cents, tone) {
    var row = document.createElement("div");
    row.className = "breakdown-row";
    var name = document.createElement("span");
    name.textContent = label;
    var dots = document.createElement("span");
    dots.className = "breakdown-dots";
    var amount = document.createElement("span");
    amount.className = "breakdown-amount" + (tone ? " is-" + tone : "");
    amount.textContent = A.moneyExact(cents);
    row.appendChild(name);
    row.appendChild(dots);
    row.appendChild(amount);
    return row;
  }

  /* ---------- rendering ---------- */

  function renderHead(d) {
    /* The API sends the raw `property_type`; the label table is client-side.
       (There is no `property_type_label` field -- an earlier version reached for
       one and got away with it only because the fallback covered for it.) */
    var where = [A.PROPERTY_LABELS[d.property_type] || d.property_type,
                 d.borough || d.city].filter(Boolean).join(", ");
    el("d-title").textContent = d.full_name + (where ? " — " + where : "");
    el("d-meta").textContent = [
      "Reçue le " + A.when(d.created_at),
      d.id.slice(0, 8),
      d.audience === "commercial" ? "Commercial" : "Résidentiel"
    ].join(" · ");

    var chip = el("d-status");
    chip.textContent = A.STATUS_LABELS[d.status] || d.status;
    chip.setAttribute("data-status", d.status);
  }

  function renderPhotos(d) {
    var photos = d.photos || [];
    if (!photos.length) return;
    el("photos-card").hidden = false;
    el("d-photo-count").textContent = photos.length;

    var grid = el("d-photos");
    grid.innerHTML = "";
    photos.forEach(function (photo) {
      var tile = document.createElement("div");
      tile.className = "admin-photo";

      var button = document.createElement("button");
      button.type = "button";
      button.className = "admin-photo-btn";
      button.setAttribute("aria-label", "Agrandir : " + photo.zone_label_fr);

      var img = document.createElement("img");
      img.alt = photo.zone_label_fr;
      img.loading = "lazy";
      button.appendChild(img);

      /* Behind the admin token, so the bytes are fetched rather than linked.
         A failure leaves the tile visibly empty instead of silently blank. */
      A.apiBlobUrl("/photos/" + photo.id).then(function (url) {
        objectUrls.push(url);
        img.src = url;
      }, function () {
        tile.setAttribute("data-state", "gone");
        button.setAttribute("aria-label", "Photo indisponible");
      });

      button.addEventListener("click", function () {
        if (img.src) openLightbox(img.src, photo.zone_label_fr);
      });

      var caption = document.createElement("div");
      caption.className = "admin-photo-cap";
      var zone = document.createElement("span");
      zone.className = "admin-photo-zone";
      zone.textContent = photo.zone_label_fr;
      /* A room the customer named themselves is marked as theirs. Without this,
         a typed-in "Salle de lavage" reads exactly like one of our categories,
         and the two are not the same thing: ours are a fixed list you can count
         across requests, theirs is whatever they wrote. */
      if (photo.customer_named) {
        zone.classList.add("is-custom");
        zone.title = "Nom donné par le client";
      }
      caption.appendChild(zone);
      if (photo.bytes_size) {
        var size = document.createElement("span");
        size.className = "admin-photo-size";
        size.textContent = Math.round(photo.bytes_size / 1024) + " Ko";
        caption.appendChild(size);
      }

      tile.appendChild(button);
      tile.appendChild(caption);
      grid.appendChild(tile);
    });
  }

  function renderRequest(d) {
    var list = el("d-request");
    list.innerHTML = "";
    fact(list, "Services", (d.services || []).map(function (code) {
      return A.SERVICE_LABELS[code] || code;
    }).join(", "));
    fact(list, "Fréquence", A.FREQUENCY_LABELS[d.frequency] || d.frequency);
    fact(list, "Début souhaité", d.desired_start ? A.day(d.desired_start) : "");
    /* `label` on a RequestedItem is already the whole phrase the visitor was
       quoted -- "Vitres intérieures × 10 par fenêtre", "État : Encombré" -- so
       it is printed as-is rather than taken apart into a key and a value. The
       inbox chips render exactly the same string. */
    fact(list, "Extras", (d.extras || []).map(function (x) {
      return x.label || x.code;
    }).join(", "));
    fact(list, "Précisions", (d.modifiers || []).map(function (m) {
      return m.label || m.code;
    }).join(", "));
    fact(list, "Accès de nuit", d.night_access ? "Oui" : "Non");
    fact(list, "Carte tarifaire", d.rate_card_version);

    if (d.access_notes) {
      el("d-notes-wrap").hidden = false;
      el("d-notes").textContent = d.access_notes;
    }
  }

  function renderBreakdown(d) {
    var host = el("d-breakdown");
    host.innerHTML = "";
    var breakdown = d.computed_breakdown || {};
    var lines = breakdown.lines || [];

    if (!lines.length && d.computed_total_cents == null) {
      var none = document.createElement("p");
      none.className = "note";
      none.textContent = "Pas de prix calculé — cette demande est chiffrée à la main.";
      host.appendChild(none);
      return;
    }

    /* The stored breakdown uses `label_fr` and `amount_cents`. Guessing `label`
       and `cents` here is what printed three rows of raw codes against em
       dashes -- moneyExact(undefined) returns "—", so it looked like a styling
       problem rather than the wrong field name. The quantity and unit are on
       the line too, and they are the difference between "24 $" and an
       explained "24 $". */
    lines.forEach(function (item) {
      var label = item.label_fr || item.code;
      if (item.quantity) {
        label += " × " + item.quantity + (item.unit_fr ? " " + item.unit_fr : "");
      }
      host.appendChild(line(label, item.amount_cents,
                            item.amount_cents < 0 ? "credit" : ""));
    });

    var total = document.createElement("div");
    total.className = "breakdown-row breakdown-total";
    var label = document.createElement("span");
    label.textContent = "Total";
    var spacer = document.createElement("span");
    spacer.className = "breakdown-dots";
    var amount = document.createElement("span");
    amount.className = "breakdown-amount";
    amount.textContent = A.moneyExact(d.computed_total_cents);
    total.appendChild(label);
    total.appendChild(spacer);
    total.appendChild(amount);
    host.appendChild(total);
  }

  function renderContact(d) {
    var host = el("d-contact");
    host.innerHTML = "";

    function row(text, href) {
      if (!text) return;
      var div = document.createElement("div");
      div.className = "contact-row";
      if (href) {
        var link = document.createElement("a");
        link.href = href;
        link.textContent = text;
        div.appendChild(link);
      } else {
        div.textContent = text;
      }
      host.appendChild(div);
    }

    row(d.full_name);
    row(d.company);
    row(d.email, d.email ? "mailto:" + d.email : null);
    row(d.phone, d.phone ? "tel:" + d.phone.replace(/[^\d+]/g, "") : null);
    row([d.address_line, d.city, d.postal_code].filter(Boolean).join(", "));

    var facts = el("d-contact-facts");
    facts.innerHTML = "";
    fact(facts, "Contact préféré", d.preferred_contact);
    fact(facts, "Langue", d.locale === "en" ? "Anglais" : "Français");
    fact(facts, "Quartier", d.borough);
    fact(facts, "Consentement", d.consent_given ? "Accordé" : "Absent");
  }

  /* The type of place is in the page heading and the postal code is in the address
     above -- both were repeated here, and a card that mostly restates its
     neighbours is a card you stop reading. What is left is only what this card
     alone says: the numbers that decide how long the job takes. */
  function renderProperty(d) {
    var list = el("d-property");
    list.innerHTML = "";
    fact(list, "Superficie", d.area_sqft ? d.area_sqft + " pi²" : "");
    fact(list, "Chambres", d.bedrooms);
    fact(list, "Salles de bain", d.bathrooms);
    fact(list, "Toilettes", d.restrooms);
    fact(list, "Étages", d.floors);
  }

  /* Only when there is attribution worth reading.
     `landing_path` is recorded on every single request, so counting it as
     content meant this card appeared on every direct lead saying nothing but
     "/soumission" -- a whole card telling you the page they were already on.
     The card now belongs to paid traffic, where knowing which campaign produced
     a lead is the point, and is simply absent otherwise. */
  function renderSource(d) {
    var list = el("d-source");
    list.innerHTML = "";
    if (!d.utm_source && !d.utm_campaign && !d.gclid) {
      el("source-card").hidden = true;
      return;
    }
    fact(list, "Source", [d.utm_source, d.utm_medium].filter(Boolean).join(" / "));
    fact(list, "Campagne", d.utm_campaign);
    fact(list, "Google Ads", d.gclid ? "oui" : "");
    fact(list, "Page d'arrivée", d.landing_path);
    el("source-card").hidden = false;
  }

  function renderAction(d) {
    var price = el("offer-price");
    price.value = A.moneyExact(
      d.quoted_total_cents != null ? d.quoted_total_cents : (d.computed_total_cents || 0)
    );
    el("d-computed-hint").textContent = d.computed_total_cents != null
      ? "Calculé : " + A.moneyExact(d.computed_total_cents) + " — modifiable avant l'envoi"
      : "Aucun prix calculé — entrez le vôtre.";

    var sent = (d.offers || []).filter(function (o) { return o.status === "sent"; });
    el("d-offer-state").textContent = sent.length
      ? sent.length + (sent.length > 1 ? " offres envoyées" : " offre envoyée")
      : "Aucune offre envoyée";

    var pick = el("d-status-pick");
    pick.innerHTML = "";
    A.STATUS_ORDER.forEach(function (value) {
      var option = document.createElement("option");
      option.value = value;
      option.textContent = A.STATUS_LABELS[value] || value;
      if (value === d.status) option.selected = true;
      pick.appendChild(option);
    });
  }

  /* ---------- lightbox ---------- */

  var lastFocus = null;

  function openLightbox(src, caption) {
    lastFocus = document.activeElement;
    el("lightbox-img").src = src;
    el("lightbox-caption").textContent = caption || "";
    el("lightbox").hidden = false;
    el("lightbox-card").focus();
  }

  function closeLightbox() {
    el("lightbox").hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  /* ---------- the offer ---------- */

  function previewOffer() {
    var cents = A.parseMoney(el("offer-price").value);
    var message = el("offer-message").value.trim();
    var send = el("offer-send");
    send.disabled = true;
    if (cents === null || !message) {
      el("offer-preview").textContent =
        cents === null ? "Entrez un prix valide." : "Écrivez un message.";
      return;
    }
    A.api("/requests/" + detail.id + "/offer/preview", {
      method: "POST",
      body: JSON.stringify({ message: message, total_cents: cents })
    }).then(function (data) {
      el("offer-preview").textContent = "Objet : " + data.subject + "\n\n" + data.text;
      send.disabled = false;
    }, function (err) {
      if (err === "auth") return;
      el("offer-preview").textContent = A.apiMessage(err);
    });
  }

  /* ---------- correcting what the customer told us ----------
   *
   * A quote form is a first draft. Somebody types 1200 for a 2100 pi² condo, drops
   * a digit out of their phone number, or leaves the address blank and gives it on
   * the call. All of that used to be frozen the moment they pressed send, and
   * fixing a typo in an email address meant opening psql.
   *
   * ONE CARD AT A TIME, editing in place. Not a modal: the point of the correction
   * is usually the photo or the note sitting beside it, and a dialog over the page
   * hides exactly what you are looking at. Not one big form either -- three small
   * ones mean a save touches three fields, not thirty, and a mistake in one card
   * cannot blank another.
   *
   * The field bounds below are the API's, repeated in the markup so the browser
   * catches a slip before it costs a round trip. The API still enforces them: this
   * is a courtesy, not the check.
   */

  var PREFERRED = [
    { value: "", label: "—" },
    { value: "email", label: "Courriel" },
    { value: "phone", label: "Téléphone" }
  ];

  var EDITORS = {
    contact: {
      title: "Coordonnées",
      fields: [
        { name: "full_name", label: "Nom", type: "text", attrs: { required: "", maxlength: "160" } },
        { name: "company", label: "Entreprise", type: "text", attrs: { maxlength: "160" } },
        { name: "email", label: "Courriel", type: "email", attrs: { maxlength: "255" } },
        { name: "phone", label: "Téléphone", type: "tel", attrs: { maxlength: "40" } },
        { name: "preferred_contact", label: "Contact préféré", type: "select", options: PREFERRED },
        { name: "address_line", label: "Adresse", type: "text", attrs: { maxlength: "255" }, wide: true },
        { name: "city", label: "Ville", type: "text", attrs: { maxlength: "120" } },
        { name: "borough", label: "Quartier", type: "text", attrs: { maxlength: "120" } },
        { name: "postal_code", label: "Code postal", type: "text", attrs: { maxlength: "12" } }
      ]
    },
    property: {
      title: "La propriété",
      /* `when` keeps the other audience's questions off the screen -- a shop has no
         bedrooms, and a field that is not shown is not sent, so the value the
         customer never gave stays untouched. */
      fields: [
        { name: "area_sqft", label: "Superficie (pi²)", type: "number",
          attrs: { min: "100", max: "1000000", inputmode: "numeric" } },
        { name: "bedrooms", label: "Chambres", type: "number",
          attrs: { min: "0", max: "20", inputmode: "numeric" }, when: "residential" },
        { name: "bathrooms", label: "Salles de bain", type: "number",
          attrs: { min: "0", max: "20", inputmode: "numeric" }, when: "residential" },
        { name: "restrooms", label: "Sanitaires", type: "number",
          attrs: { min: "0", max: "200", inputmode: "numeric" }, when: "commercial" },
        { name: "floors", label: "Étages", type: "number",
          attrs: { min: "1", max: "100", inputmode: "numeric" }, when: "commercial" }
      ],
      note: "Le type de lieu n'est pas modifiable : il décide de la grille de prix. " +
            "Le prix calculé plus haut reste celui affiché au client lors de l'envoi."
    },
    request: {
      title: "La demande",
      fields: [
        { name: "desired_start", label: "Début souhaité", type: "date" },
        { name: "access_notes", label: "Notes d'accès", type: "textarea",
          attrs: { rows: "4", maxlength: "2000" }, wide: true }
      ]
    }
  };

  /* Which field each rejection belongs to, so a 422 lands on the input that caused
     it rather than in a box at the bottom saying something went wrong. */
  var FIELD_MESSAGES = {
    full_name: "Le nom est requis (au moins deux caractères).",
    email: "Ce courriel n'est pas valide.",
    phone: "Ce numéro est trop long.",
    preferred_contact: "Choisissez courriel ou téléphone.",
    area_sqft: "Entrez une superficie entre 100 et 1 000 000 pi².",
    bedrooms: "Entre 0 et 20.",
    bathrooms: "Entre 0 et 20.",
    restrooms: "Entre 0 et 200.",
    floors: "Entre 1 et 100.",
    desired_start: "Date invalide.",
    access_notes: "Ces notes sont trop longues (2000 caractères maximum)."
  };

  function fieldValue(name) {
    var raw = detail[name];
    return raw === null || raw === undefined ? "" : String(raw);
  }

  function buildEditor(key) {
    var spec = EDITORS[key];
    var form = document.querySelector('[data-form="' + key + '"]');
    form.innerHTML = "";

    var grid = document.createElement("div");
    grid.className = "editgrid";

    spec.fields.forEach(function (f) {
      if (f.when && f.when !== detail.audience) return;

      var wrap = document.createElement("div");
      wrap.className = "editfield" + (f.wide ? " is-wide" : "");
      var id = "edit-" + key + "-" + f.name;

      var label = document.createElement("label");
      label.setAttribute("for", id);
      label.textContent = f.label;
      wrap.appendChild(label);

      var control;
      if (f.type === "select") {
        control = document.createElement("select");
        f.options.forEach(function (o) {
          var option = document.createElement("option");
          option.value = o.value;
          option.textContent = o.label;
          control.appendChild(option);
        });
      } else if (f.type === "textarea") {
        control = document.createElement("textarea");
      } else {
        control = document.createElement("input");
        control.type = f.type;
      }
      control.id = id;
      control.name = f.name;
      Object.keys(f.attrs || {}).forEach(function (k) { control.setAttribute(k, f.attrs[k]); });
      control.value = fieldValue(f.name);
      /* aria-describedby is set even though the box starts empty: adding it only
         when an error appears means a screen reader that has already read the
         field never hears about it. */
      control.setAttribute("aria-describedby", id + "-err");
      wrap.appendChild(control);

      var err = document.createElement("p");
      err.className = "field-error";
      err.id = id + "-err";
      err.hidden = true;
      err.setAttribute("role", "alert");
      wrap.appendChild(err);

      grid.appendChild(wrap);
    });
    form.appendChild(grid);

    if (spec.note) {
      var note = document.createElement("p");
      note.className = "note";
      note.textContent = spec.note;
      form.appendChild(note);
    }

    var box = document.createElement("div");
    box.className = "alert";
    box.setAttribute("role", "alert");
    box.hidden = true;
    box.dataset.role = "formerror";
    form.appendChild(box);

    var foot = document.createElement("div");
    foot.className = "row editfoot";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn-ghost";
    cancel.textContent = "Annuler";
    cancel.dataset.cancel = key;
    var save = document.createElement("button");
    save.type = "submit";
    save.className = "btn btn-primary";
    save.textContent = "Enregistrer";
    save.dataset.save = key;
    foot.appendChild(cancel);
    foot.appendChild(save);
    form.appendChild(foot);

    return form;
  }

  function openEditor(key) {
    if (!detail) return;
    closeEditors();
    var form = buildEditor(key);
    document.querySelector('[data-view="' + key + '"]').hidden = true;
    form.hidden = false;
    var button = document.querySelector('[data-edit="' + key + '"]');
    if (button) button.hidden = true;
    var first = form.querySelector("input, select, textarea");
    if (first && first.focus) first.focus();
  }

  function closeEditors() {
    Object.keys(EDITORS).forEach(function (key) {
      var form = document.querySelector('[data-form="' + key + '"]');
      var view = document.querySelector('[data-view="' + key + '"]');
      var button = document.querySelector('[data-edit="' + key + '"]');
      if (form) { form.hidden = true; form.innerHTML = ""; }
      if (view) view.hidden = false;
      if (button) button.hidden = false;
    });
  }

  function showFieldErrors(form, body) {
    var detailBody = body && body.detail;
    var box = form.querySelector('[data-role="formerror"]');
    form.querySelectorAll(".field-error").forEach(function (p) {
      p.hidden = true; p.textContent = "";
    });
    form.querySelectorAll("[aria-invalid]").forEach(function (c) {
      c.removeAttribute("aria-invalid");
    });

    /* A string detail is one we raised on purpose -- the refusal to leave a request
       with no email and no phone. It is written for Amine, so show it as it is. */
    if (typeof detailBody === "string") {
      box.textContent = detailBody;
      box.hidden = false;
      return true;
    }
    if (!Array.isArray(detailBody)) return false;

    var marked = 0;
    detailBody.forEach(function (item) {
      var loc = item && item.loc;
      if (!Array.isArray(loc)) return;
      var name = loc[loc.length - 1];
      var control = form.querySelector('[name="' + name + '"]');
      if (!control) return;
      var err = form.querySelector("#" + control.id + "-err");
      if (!err) return;
      err.textContent = FIELD_MESSAGES[name] || (item.msg || "Valeur refusée.");
      err.hidden = false;
      control.setAttribute("aria-invalid", "true");
      marked++;
    });
    if (marked) {
      box.textContent = "Corrigez les champs indiqués.";
      box.hidden = false;
      var bad = form.querySelector('[aria-invalid="true"]');
      if (bad && bad.focus) bad.focus();
      return true;
    }
    return false;
  }

  function saveEditor(key, form) {
    var spec = EDITORS[key];
    var payload = {};
    /* Only the fields this card put on screen. An absent key means "leave it
       alone" on the server, which is how one card's save cannot blank another's
       fields -- and why an emptied box (sent as "") clears just that one. */
    spec.fields.forEach(function (f) {
      var control = form.querySelector('[name="' + f.name + '"]');
      if (control) payload[f.name] = control.value;
    });

    var save = form.querySelector("[data-save]");
    save.disabled = true;
    save.textContent = "Enregistrement…";

    A.api("/requests/" + encodeURIComponent(detail.id) + "/customer", {
      method: "PATCH", body: JSON.stringify(payload)
    }).then(function (updated) {
      closeEditors();
      renderAll(updated);
      var card = el(key + "-card");
      if (card) {
        card.classList.add("saved");
        setTimeout(function () { card.classList.remove("saved"); }, 900);
      }
    }, function (err) {
      save.disabled = false;
      save.textContent = "Enregistrer";
      if (err === "auth") return;
      if (err && err.status === 422 && showFieldErrors(form, err.body)) return;
      var box = form.querySelector('[data-role="formerror"]');
      box.textContent = A.apiMessage(err);
      box.hidden = false;
    });
  }

  document.addEventListener("click", function (event) {
    var open = event.target.closest("[data-edit]");
    if (open) { openEditor(open.dataset.edit); return; }
    var cancel = event.target.closest("[data-cancel]");
    if (cancel) { closeEditors(); return; }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-form]");
    if (!form) return;
    event.preventDefault();
    saveEditor(form.dataset.form, form);
  });

  /* Escape closes whichever card is open, the same as Annuler. The offer dialog
     has its own handler and stops here, so this cannot close both at once. */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!el("offer").hidden || !el("lightbox").hidden) return;
    if (document.querySelector("[data-form]:not([hidden])")) closeEditors();
  });

  function renderAll(data) {
    detail = data;
    renderHead(data);
    renderPhotos(data);
    renderRequest(data);
    renderBreakdown(data);
    renderContact(data);
    renderProperty(data);
    renderSource(data);
    renderAction(data);
  }

  function load() {
    var id = param("id");
    if (!id) {
      el("loading").hidden = true;
      el("panel-error").textContent = "Aucune demande indiquée.";
      el("panel-error").hidden = false;
      return;
    }
    objectUrls.forEach(URL.revokeObjectURL);
    objectUrls = [];

    A.api("/requests/" + encodeURIComponent(id)).then(function (data) {
      el("loading").hidden = true;
      el("panel-error").hidden = true;
      el("detail").hidden = false;
      closeEditors();
      renderAll(data);
    }, function (err) {
      if (err === "auth") return;
      el("loading").hidden = true;
      el("detail").hidden = true;
      el("panel-error").textContent = A.apiMessage(err);
      el("panel-error").hidden = false;
    });
  }

  /* ---------- wiring ---------- */

  el("offer-open").addEventListener("click", function () {
    if (!detail) return;
    el("offer-to").textContent = "À : " + detail.full_name + " <" + (detail.email || "") + ">";
    el("offer-message").value =
      "Merci pour votre demande. Voici notre offre pour l'entretien de votre " +
      "propriété. Nous pouvons commencer dès la semaine prochaine — dites-nous " +
      "le moment qui vous convient.";
    el("offer-error").hidden = true;
    el("offer-preview").textContent = "…";
    el("offer").hidden = false;
    el("offer-card").focus();
    previewOffer();
  });

  el("offer-cancel").addEventListener("click", function () { el("offer").hidden = true; });

  var previewTimer = null;
  el("offer-message").addEventListener("input", function () {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(previewOffer, 350);
  });
  el("offer-price").addEventListener("input", function () {
    if (!el("offer").hidden) { clearTimeout(previewTimer); previewTimer = setTimeout(previewOffer, 350); }
  });

  el("offer-send").addEventListener("click", function () {
    var cents = A.parseMoney(el("offer-price").value);
    if (cents === null) return;
    var button = el("offer-send");
    button.disabled = true;
    A.api("/requests/" + detail.id + "/offer", {
      method: "POST",
      body: JSON.stringify({
        message: el("offer-message").value.trim(),
        total_cents: cents
      })
    }).then(function () {
      el("offer").hidden = true;
      load();
    }, function (err) {
      if (err === "auth") return;
      button.disabled = false;
      el("offer-error").textContent = A.apiMessage(err);
      el("offer-error").hidden = false;
    });
  });

  /* The quoted price saves on blur, the same as in the inbox table, so the two
     screens behave identically for the same field. */
  el("offer-price").addEventListener("change", function () {
    var cents = A.parseMoney(el("offer-price").value);
    el("offer-price").classList.toggle("bad", cents === null && el("offer-price").value !== "");
    if (cents === null || !detail) return;
    A.api("/requests/" + detail.id, {
      method: "PATCH",
      body: JSON.stringify({ quoted_total_cents: cents })
    }).then(function () {}, function () {});
  });

  el("d-status-pick").addEventListener("change", function () {
    if (!detail) return;
    A.api("/requests/" + detail.id, {
      method: "PATCH",
      body: JSON.stringify({ status: el("d-status-pick").value })
    }).then(load, function () {});
  });

  el("lightbox-close").addEventListener("click", closeLightbox);
  el("lightbox").addEventListener("click", function (event) {
    if (event.target === el("lightbox")) closeLightbox();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!el("lightbox").hidden) closeLightbox();
    else if (!el("offer").hidden) el("offer").hidden = true;
  });

  el("refresh-btn").addEventListener("click", load);

  A.boot({ onAuthed: load });
})();
