/* The optional photo picker on the quote form, and the upload that follows.
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE: photos never travel with the request
 * that creates the lead. The form posts the answers, the lead is saved, the
 * visitor sees their confirmation -- and only THEN do the images start moving.
 * A customer on a bad connection whose upload dies has still submitted their
 * request, which is the entire point. Bundling the two would mean a 30-second
 * spinner on 4G and a lead lost every time someone gives up on it.
 *
 * Images are resized here, in the browser, before anything is sent. A phone
 * photo is 3-5 MB and useless at that size for judging how dirty a kitchen is;
 * 1600px of it is about 200 KB and just as informative. That one step is what
 * keeps uploads quick on mobile data and keeps the server's disk -- shared with
 * Postgres -- from filling.
 */
(function (window, document) {
  "use strict";

  var MAX_EDGE = 1600;
  var JPEG_QUALITY = 0.82;

  var T = {
    fr: {
      add: "Ajouter",
      choose: "Choisir des photos",
      drop: "ou glissez-les ici",
      max: function (n) { return n + " max"; },
      zone: "Pièce",
      nameIt: "Quelle pièce ?",
      nameItHint: "ex. salle de lavage",
      remove: "Retirer cette photo",
      resized: "Redimensionnées dans votre navigateur — l'envoi ne retarde pas votre demande.",
      selected: function (n) { return n + (n > 1 ? " sélectionnées" : " sélectionnée"); },
      tooMany: function (n) { return "Maximum " + n + " photos."; },
      notImage: "Choisissez des images (JPEG, PNG ou WebP).",
      sending: "Envoi des photos",
      ofCount: function (a, b) { return a + " sur " + b; },
      done: "Photos envoyées.",
      failed: "Certaines photos ne sont pas parties. Répondez au courriel de confirmation avec vos photos.",
      closeOk: "Vous pouvez fermer cette page — votre demande est déjà enregistrée."
    },
    en: {
      add: "Add",
      choose: "Choose photos",
      drop: "or drag them here",
      max: function (n) { return n + " max"; },
      zone: "Room",
      nameIt: "Which room?",
      nameItHint: "e.g. laundry room",
      remove: "Remove this photo",
      resized: "Resized in your browser — this will not delay your request.",
      selected: function (n) { return n + " selected"; },
      tooMany: function (n) { return "Maximum " + n + " photos."; },
      notImage: "Please choose images (JPEG, PNG or WebP).",
      sending: "Uploading photos",
      ofCount: function (a, b) { return a + " of " + b; },
      done: "Photos uploaded.",
      failed: "Some photos did not upload. Reply to the confirmation email with them.",
      closeOk: "You can close this page — your request is already saved."
    }
  };

  /* Draw the image onto a canvas at a bounded size and re-encode as JPEG.
   *
   * `imageOrientation: "from-image"` is load-bearing on phones: a photo taken
   * in portrait carries its rotation in EXIF, and a canvas that ignores that
   * hands you a sideways kitchen. Every one of them, every time.
   */
  function shrink(file) {
    if (!window.createImageBitmap || !window.HTMLCanvasElement) {
      return Promise.resolve(file); // ancient browser: send it as it is
    }
    return window.createImageBitmap(file, { imageOrientation: "from-image" })
      .then(function (bitmap) {
        var scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
        var width = Math.round(bitmap.width * scale);
        var height = Math.round(bitmap.height * scale);
        var canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
        if (bitmap.close) bitmap.close();
        return new Promise(function (resolve) {
          canvas.toBlob(function (blob) {
            /* Only keep the resized copy if it is actually smaller. A tiny
               screenshot re-encoded as JPEG can come out bigger, and sending
               the larger of the two would be a strange way to save bandwidth. */
            resolve(blob && blob.size < file.size ? blob : file);
          }, "image/jpeg", JPEG_QUALITY);
        });
      })
      .catch(function () { return file; }); // a file the decoder refused: let
      // the server have the last word on it rather than dropping it silently
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "class") node.className = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    if (text != null) node.textContent = text;
    return node;
  }

  /* One picker, bound to a container already in the page. */
  function Picker(root, options) {
    this.root = root;
    this.locale = options.locale === "en" ? "en" : "fr";
    this.t = T[this.locale];
    this.maxCount = options.maxCount || 10;
    this.zones = options.zones || [];
    this.items = [];
    this._build();
  }

  Picker.prototype._build = function () {
    var self = this;
    this.root.innerHTML = "";

    this.input = el("input", {
      type: "file", accept: "image/jpeg,image/png,image/webp", multiple: "multiple",
      id: "photo-input", class: "photo-input"
    });
    this.label = el("label", { for: "photo-input", class: "photo-drop" });
    this.label.appendChild(el("span", { class: "photo-drop-main" }, this.t.choose));
    this.label.appendChild(el("span", { class: "photo-drop-sub" },
      this.t.drop + " · " + this.t.max(this.maxCount)));

    this.grid = el("div", { class: "photo-grid" });
    this.note = el("p", { class: "photo-note" }, this.t.resized);
    this.note.hidden = true;
    this.error = el("p", { class: "field-error", role: "alert" });
    this.error.hidden = true;

    this.root.appendChild(this.input);
    this.root.appendChild(this.label);
    this.root.appendChild(this.grid);
    this.root.appendChild(this.note);
    this.root.appendChild(this.error);

    this.input.addEventListener("change", function () {
      self.accept(self.input.value ? self.input.files : []);
      /* Cleared so choosing the same file twice in a row still fires `change`
         -- otherwise removing a photo and re-picking it does nothing at all. */
      self.input.value = "";
    });

    ["dragover", "dragenter"].forEach(function (name) {
      self.label.addEventListener(name, function (event) {
        event.preventDefault();
        self.label.classList.add("is-over");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      self.label.addEventListener(name, function () { self.label.classList.remove("is-over"); });
    });
    this.label.addEventListener("drop", function (event) {
      event.preventDefault();
      self.accept(event.dataTransfer && event.dataTransfer.files);
    });
  };

  Picker.prototype.accept = function (fileList) {
    var self = this;
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;

    var images = incoming.filter(function (f) { return /^image\//.test(f.type); });
    this.error.hidden = images.length === incoming.length;
    if (images.length !== incoming.length) this.error.textContent = this.t.notImage;

    var room = this.maxCount - this.items.length;
    if (images.length > room) {
      this.error.textContent = this.t.tooMany(this.maxCount);
      this.error.hidden = false;
      images = images.slice(0, Math.max(0, room));
    }

    images.forEach(function (file) {
      var item = { file: file, zone: self.zones.length ? self.zones[0].value : "other" };
      self.items.push(item);
      self._tile(item);
    });
    this._sync();
  };

  Picker.prototype._tile = function (item) {
    var self = this;
    var tile = el("div", { class: "photo-tile" });
    var frame = el("div", { class: "photo-thumb" });

    var img = el("img", { alt: "" });
    item.url = URL.createObjectURL(item.file);
    img.src = item.url;
    frame.appendChild(img);

    var remove = el("button", { type: "button", class: "photo-remove",
                                "aria-label": this.t.remove });
    remove.innerHTML =
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
      ' stroke-width="2.6" stroke-linecap="round" aria-hidden="true">' +
      '<path d="M18 6 6 18M6 6l12 12"/></svg>';
    remove.addEventListener("click", function () {
      URL.revokeObjectURL(item.url);
      self.items.splice(self.items.indexOf(item), 1);
      tile.parentNode.removeChild(tile);
      self._sync();
    });
    frame.appendChild(remove);
    tile.appendChild(frame);

    if (this.zones.length) {
      var id = "zone-" + Math.random().toString(36).slice(2, 9);
      tile.appendChild(el("label", { for: id, class: "photo-zone-label" }, this.t.zone));
      item.select = el("select", { id: id, class: "photo-zone" });
      tile.appendChild(item.select);

      /* "AUTRE" ON ITS OWN SAYS NOTHING. The list cannot name every room in
         Montreal -- a laundry room, a solarium, a dépanneur's back store -- and a
         photo filed under "Autre" leaves whoever writes the quote looking at a
         picture they have no word for. So picking it opens a box to type the word
         in. Shown only then: an extra field on every tile for the nine cases the
         list already covers is nine chances to fill in something redundant. */
      item.nameBox = el("input", {
        type: "text", class: "photo-zone-name", maxlength: "60",
        placeholder: this.t.nameItHint, "aria-label": this.t.nameIt
      });
      item.nameBox.hidden = true;
      tile.appendChild(item.nameBox);

      item.select.addEventListener("change", function () {
        item.zone = item.select.value;
        self._syncName(item);
        if (!item.nameBox.hidden) item.nameBox.focus();
      });
      item.nameBox.addEventListener("input", function () {
        item.zoneLabel = item.nameBox.value;
      });
      this._fillZones(item);
    }

    item.tile = tile;
    this.grid.appendChild(tile);
  };

  /* Put the current zone list in one tile's select, keeping the chosen room if the
     new list still has it. */
  Picker.prototype._fillZones = function (item) {
    var self = this;
    var want = item.zone;
    item.select.innerHTML = "";
    this.zones.forEach(function (zone) {
      item.select.appendChild(el("option", { value: zone.value },
        self.locale === "en" ? zone.label_en : zone.label_fr));
    });
    var kept = this.zones.some(function (z) { return z.value === want; });
    item.select.value = kept ? want : this.zones[0].value;
    item.zone = item.select.value;
    this._syncName(item);
  };

  Picker.prototype._syncName = function (item) {
    if (!item.nameBox) return;
    var isOther = item.zone === "other";
    item.nameBox.hidden = !isOther;
    /* Cleared on the way out, so a name typed under "Autre" and then changed to
       "Cuisine" does not travel with it. The server drops it in that case too --
       this just keeps the screen honest about what will be sent. */
    if (!isOther) { item.nameBox.value = ""; item.zoneLabel = ""; }
  };

  /* THE ROOM LIST BELONGS TO THE AUDIENCE, and the audience is chosen after this
     picker is built -- the form asks for photos on step 1 and the type of place is
     the first question on it. Mounting once at load meant a shop was offered
     bedrooms and basements, which is the list for the other kind of customer.
     So the form calls this whenever the choice changes. Photos already picked are
     kept; a room that does not exist in the new list falls back to the first one. */
  Picker.prototype.setZones = function (zones) {
    if (!zones || !zones.length) return;
    var same = zones.length === this.zones.length && zones.every(function (z, i) {
      return z.value === this.zones[i].value;
    }, this);
    if (same) return;
    this.zones = zones;
    var self = this;
    this.items.forEach(function (item) { if (item.select) self._fillZones(item); });
  };

  Picker.prototype._sync = function () {
    var full = this.items.length >= this.maxCount;
    this.label.hidden = full;
    this.note.hidden = this.items.length === 0;
    this.label.querySelector(".photo-drop-main").textContent =
      this.items.length ? this.t.add : this.t.choose;
    if (this.onChange) this.onChange(this.items.length);
  };

  Picker.prototype.count = function () { return this.items.length; };

  /* Upload everything chosen, one request each, reporting progress as it goes.
   *
   * Sequential rather than parallel on purpose: a phone on a weak connection
   * finishes four uploads sooner one at a time than four at once, and the
   * progress a visitor sees actually means something. Individual failures are
   * counted, not thrown -- three photos landing is a better outcome than
   * abandoning the lot because the second one timed out.
   */
  Picker.prototype.upload = function (requestId, token, onProgress) {
    var self = this;
    var total = this.items.length;
    var done = 0;
    var failed = 0;

    return this.items.reduce(function (chain, item) {
      return chain.then(function () {
        return shrink(item.file).then(function (blob) {
          var body = new FormData();
          body.append("token", token);
          body.append("zone", item.zone);
          if (item.zone === "other" && item.zoneLabel) {
            body.append("zone_label", item.zoneLabel.slice(0, 60));
          }
          body.append("file", blob, (item.file.name || "photo").replace(/[^\w.-]/g, "_"));
          return fetch("/api/quotes/" + encodeURIComponent(requestId) + "/photos", {
            method: "POST", body: body
          });
        }).then(function (response) {
          if (response.ok) { done += 1; } else { failed += 1; }
        }, function () {
          failed += 1;
        }).then(function () {
          if (onProgress) onProgress(done, total, failed);
          if (item.tile) item.tile.setAttribute("data-state", failed && !done ? "failed" : "sent");
        });
      });
    }, Promise.resolve()).then(function () {
      self.items.forEach(function (item) { URL.revokeObjectURL(item.url); });
      return { sent: done, failed: failed, total: total };
    });
  };

  window.ProlinePhotos = {
    Picker: Picker,
    text: function (locale) { return T[locale === "en" ? "en" : "fr"]; }
  };
})(window, document);
