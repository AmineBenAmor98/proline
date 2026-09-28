/* The admin detail page, driven end to end in a real DOM.
 *
 *     node frontend/test/check_admin_edit.js
 *
 * Needs jsdom:  npm i --no-save jsdom
 *
 * Companion to check_form.js, and here for the same reason: the Python suite is
 * thorough about the API and cannot see a page that renders nothing, a field that
 * saves the wrong value, or an error that lands nowhere. The editing this exercises
 * writes to a customer's record, so what the screen sends matters as much as what
 * the endpoint accepts.
 *
 * The API is stubbed. Its behaviour is covered by backend/tests/test_customer_edit.py;
 * what is checked here is the REQUEST BODY the page produces and what it does with
 * the answer.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..");

let failures = 0;
function check(name, ok, extra) {
  console.log((ok ? "  ok   " : "  FAIL ") + name + (ok || extra === undefined ? "" : "  -> " + extra));
  if (!ok) failures++;
}

const REQUEST = {
  id: "11111111-2222-4333-8444-555555555555",
  created_at: "2026-09-20T14:02:00Z",
  status: "new",
  audience: "residential",
  property_type: "condo",
  full_name: "Marie Tremblay",
  company: null,
  email: "marie@example.com",
  phone: "514 555-0142",
  preferred_contact: "email",
  locale: "fr",
  consent_given: true,
  address_line: null,
  city: "Montréal",
  borough: "Rosemont",
  postal_code: null,
  area_sqft: 1200,
  bedrooms: 3,
  bathrooms: 2,
  restrooms: null,
  floors: null,
  frequency: "monthly",
  services: [],
  extras: [],
  modifiers: [],
  night_access: false,
  desired_start: "2026-10-05",
  access_notes: "Code de porte 4412",
  computed_total_cents: 24500,
  computed_breakdown: { lines: [], total_cents: 24500 },
  quoted_total_cents: null,
  utm_source: null, utm_medium: null, utm_campaign: null, gclid: null, landing_path: "/soumission",
  rate_card_version: "placeholder-2026-09",
  photos: [],
  offers: []
};

async function boot(overrides) {
  const html = fs.readFileSync(path.join(ROOT, "admin/demande.html"), "utf8");
  const dom = new JSDOM(html, {
    url: "https://proline-cleaningsolutions.com/admin/demande?id=" + REQUEST.id,
    pretendToBeVisual: true,
    runScripts: "outside-only"
  });
  const { window } = dom;
  window.localStorage.setItem("proline_admin_session",
    JSON.stringify({ token: "stub", username: "admin" }));

  const state = Object.assign({}, REQUEST, overrides || {});
  const calls = [];
  window.__calls = calls;
  window.__answer = null;           // {status, body} for the next PATCH

  window.fetch = function (url, opts) {
    const method = (opts && opts.method) || "GET";
    calls.push({ url: String(url), method, body: opts && opts.body });
    if (method === "PATCH" && /\/customer$/.test(String(url))) {
      const a = window.__answer;
      if (a) {
        return Promise.resolve({ ok: a.status >= 200 && a.status < 400, status: a.status,
          json: () => Promise.resolve(a.body) });
      }
      // The real endpoint answers with the merged record; mimic that.
      Object.assign(state, JSON.parse(opts.body));
      for (const k of Object.keys(state)) if (state[k] === "") state[k] = null;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(state) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(state) });
  };
  window.HTMLElement.prototype.scrollIntoView = function () {};
  window.scrollTo = function () {};
  window.URL.createObjectURL = () => "blob:stub";
  window.URL.revokeObjectURL = () => {};

  for (const f of ["admin-common.js", "demande.js"]) {
    window.eval(fs.readFileSync(path.join(ROOT, "js", f), "utf8"));
  }
  await new Promise((r) => setTimeout(r, 40));
  return window;
}

function click(win, selector) {
  const node = win.document.querySelector(selector);
  if (!node) throw new Error("no such node: " + selector);
  node.dispatchEvent(new win.Event("click", { bubbles: true }));
  return node;
}

function set(win, name, value) {
  const control = win.document.querySelector('[data-form]:not([hidden]) [name="' + name + '"]');
  if (!control) throw new Error("no such control: " + name);
  control.value = value;
  return control;
}

async function save(win, key) {
  win.document.querySelector('[data-form="' + key + '"]')
    .dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 40));
}

function patches(win) {
  return win.__calls.filter((c) => c.method === "PATCH").map((c) => JSON.parse(c.body));
}

(async () => {
  console.log("\n=== admin/demande.html ===");

  // The page has to paint at all before anything else is worth checking.
  {
    const win = await boot();
    check("the page renders", !win.document.getElementById("detail").hidden);
    check("the title carries the name",
      /Marie Tremblay/.test(win.document.getElementById("d-title").textContent),
      win.document.getElementById("d-title").textContent);
    check("all three cards offer an edit",
      win.document.querySelectorAll("[data-edit]").length === 3,
      String(win.document.querySelectorAll("[data-edit]").length));
    check("no editor is open at load",
      win.document.querySelector("[data-form]:not([hidden])") === null);
  }

  // Opening one card.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    const form = win.document.querySelector('[data-form="contact"]');
    check("contact: the form opens", !form.hidden);
    check("contact: the read-only view is hidden",
      win.document.querySelector('[data-view="contact"]').hidden === true);
    check("contact: the fields are prefilled from the record",
      form.querySelector('[name="full_name"]').value === "Marie Tremblay" &&
      form.querySelector('[name="email"]').value === "marie@example.com",
      form.querySelector('[name="full_name"]').value);
    check("contact: an empty field is empty, not 'null'",
      form.querySelector('[name="company"]').value === "",
      JSON.stringify(form.querySelector('[name="company"]').value));
    check("contact: the preferred channel is selected",
      form.querySelector('[name="preferred_contact"]').value === "email");

    // Opening another closes this one: two open forms could disagree.
    click(win, '[data-edit="property"]');
    check("only one card edits at a time",
      win.document.querySelectorAll("[data-form]:not([hidden])").length === 1,
      String(win.document.querySelectorAll("[data-form]:not([hidden])").length));
  }

  // The audience decides which property questions exist.
  {
    const win = await boot();
    click(win, '[data-edit="property"]');
    const names = [...win.document.querySelectorAll('[data-form="property"] [name]')]
      .map((c) => c.name).join(",");
    check("a condo is asked about bedrooms, not washrooms",
      names === "property_type,area_sqft,bedrooms,bathrooms", names);
  }
  {
    const win = await boot({ audience: "commercial", property_type: "retail",
      bedrooms: null, bathrooms: null, restrooms: 4, floors: 2 });
    click(win, '[data-edit="property"]');
    const names = [...win.document.querySelectorAll('[data-form="property"] [name]')]
      .map((c) => c.name).join(",");
    check("a shop is asked about washrooms, not bedrooms",
      names === "property_type,area_sqft,restrooms,floors", names);
  }

  // A save sends only this card's fields, and the page re-renders from the answer.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    set(win, "full_name", "Marie Tremblay-Roy");
    set(win, "address_line", "5600 rue Masson");
    set(win, "postal_code", "H1Y 2X4");
    await save(win, "contact");

    const sent = patches(win);
    check("save: exactly one PATCH", sent.length === 1, String(sent.length));
    if (sent.length) {
      const keys = Object.keys(sent[0]).sort().join(",");
      check("save: only the contact card's fields travel",
        keys === "address_line,borough,city,company,email,full_name,locale,phone,postal_code,preferred_contact",
        keys);
      check("save: no property field is in the body",
        !("area_sqft" in sent[0]) && !("bedrooms" in sent[0]), keys);
      check("save: the edited values are the ones sent",
        sent[0].full_name === "Marie Tremblay-Roy" && sent[0].postal_code === "H1Y 2X4");
    }
    check("save: the editor closes",
      win.document.querySelector("[data-form]:not([hidden])") === null);
    check("save: the page shows the new name",
      /Marie Tremblay-Roy/.test(win.document.getElementById("d-title").textContent),
      win.document.getElementById("d-title").textContent);
    check("save: the address appears in the card",
      /5600 rue Masson/.test(win.document.getElementById("d-contact").textContent),
      win.document.getElementById("d-contact").textContent);
  }

  // Emptying a box has to reach the server as something, or clearing is impossible.
  {
    const win = await boot({ company: "Proline" });
    click(win, '[data-edit="contact"]');
    set(win, "company", "");
    await save(win, "contact");
    check("clearing: the emptied field is sent", patches(win)[0].company === "",
      JSON.stringify(patches(win)[0].company));
  }

  // Cancel must not send anything, and must put the original values back.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    set(win, "full_name", "quelque chose d'autre");
    click(win, '[data-cancel]');
    check("cancel: nothing is sent", patches(win).length === 0);
    check("cancel: the card is read-only again",
      win.document.querySelector('[data-view="contact"]').hidden === false);
    check("cancel: the original name is still on screen",
      /Marie Tremblay/.test(win.document.getElementById("d-title").textContent));
    click(win, '[data-edit="contact"]');
    check("cancel: reopening shows the stored value, not the abandoned one",
      win.document.querySelector('[name="full_name"]').value === "Marie Tremblay",
      win.document.querySelector('[name="full_name"]').value);
  }

  // A field rejection has to land on the field.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    set(win, "email", "pas-un-courriel");
    win.__answer = { status: 422, body: { detail: [
      { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" }
    ] } };
    await save(win, "contact");
    const form = win.document.querySelector('[data-form="contact"]');
    check("422: the form stays open", !form.hidden);
    const err = form.querySelector("#edit-contact-email-err");
    check("422: the message is on the email field", err && !err.hidden && err.textContent.length > 5,
      err ? JSON.stringify(err.textContent) : "missing");
    check("422: the field is marked invalid",
      form.querySelector('[name="email"]').getAttribute("aria-invalid") === "true");
    check("422: the save button works again",
      form.querySelector("[data-save]").disabled === false);
  }

  // The refusal we raise ourselves arrives as a plain string and is written for him.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    set(win, "email", "");
    set(win, "phone", "");
    win.__answer = { status: 422, body: { detail:
      "Gardez au moins un courriel ou un téléphone : sans l'un des deux, la demande ne peut plus être répondue." } };
    await save(win, "contact");
    const box = win.document.querySelector('[data-form="contact"] [data-role="formerror"]');
    check("string 422: the sentence is shown as written",
      box && !box.hidden && /au moins un courriel/.test(box.textContent),
      box ? box.textContent : "missing");
  }

  // A server that is simply down must not look like a validation problem.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    win.__answer = { status: 0, body: null };
    await save(win, "contact");
    const box = win.document.querySelector('[data-form="contact"] [data-role="formerror"]');
    check("network failure: something is said", box && !box.hidden && box.textContent.length > 5,
      box ? JSON.stringify(box.textContent) : "missing");
    check("network failure: the form stays open so the typing is not lost",
      win.document.querySelector('[data-form="contact"]').hidden === false);
  }

  // The notes and the start date are correctable too -- they are what changes on a call.
  {
    const win = await boot();
    click(win, '[data-edit="request"]');
    check("request card: the date is prefilled",
      win.document.querySelector('[name="desired_start"]').value === "2026-10-05",
      win.document.querySelector('[name="desired_start"]').value);
    check("request card: the notes are prefilled",
      win.document.querySelector('[name="access_notes"]').value === "Code de porte 4412");
    set(win, "access_notes", "Code de porte 4412 — chien dans la cour");
    await save(win, "request");
    const sent = patches(win)[0];
    check("request card: only its own fields travel",
      Object.keys(sent).sort().join(",") === "access_notes,desired_start,frequency",
      Object.keys(sent).sort().join(","));
    check("request card: the note is on screen after saving",
      /chien dans la cour/.test(win.document.getElementById("d-notes").textContent),
      win.document.getElementById("d-notes").textContent);
  }

  // Editing the area must not silently rewrite what the customer was quoted.
  {
    const win = await boot();
    const before = win.document.getElementById("d-breakdown").textContent;
    click(win, '[data-edit="property"]');
    set(win, "area_sqft", "2100");
    await save(win, "property");
    check("the computed price is unchanged by an area correction",
      win.document.getElementById("d-breakdown").textContent === before);
    check("the corrected area is on screen",
      /2 100|2 100|2100/.test(win.document.getElementById("d-property").textContent),
      win.document.getElementById("d-property").textContent);
  }

  // The new controls: what was asked for, and the language of the quote.
  {
    const win = await boot({ audience: "commercial", property_type: "retail",
      bedrooms: null, bathrooms: null, restrooms: 4, floors: 2,
      frequency: "monthly", services: ["office_cleaning"], night_access: false });

    click(win, '[data-edit="property"]');
    const types = [...win.document.querySelectorAll('[data-form="property"] [name="property_type"] option')]
      .map((o) => o.value);
    check("property: a shop is offered only commercial types",
      types.length > 0 && !types.includes("condo") && types.includes("retail"),
      types.join(","));
    check("property: the current type is selected",
      win.document.querySelector('[name="property_type"]').value === "retail");
    click(win, '[data-cancel]');

    click(win, '[data-edit="request"]');
    const form = win.document.querySelector('[data-form="request"]');
    check("request: frequency is a dropdown set to the stored value",
      form.querySelector('[name="frequency"]').value === "monthly");
    check("request: the services already asked for are ticked",
      form.querySelector('[data-group="services"][value="office_cleaning"]').checked === true);
    check("request: a service not asked for is not ticked",
      form.querySelector('[data-group="services"][value="carpets"]').checked === false);
    check("request: night access is a single tick", 
      form.querySelector('[name="night_access"]').type === "checkbox");

    form.querySelector('[data-group="services"][value="carpets"]').checked = true;
    form.querySelector('[name="night_access"]').checked = true;
    set(win, "frequency", "weekly");
    await save(win, "request");

    const sent = patches(win)[0];
    check("request: frequency travels as its code", sent.frequency === "weekly", sent.frequency);
    check("request: services travel as an array of codes",
      Array.isArray(sent.services) &&
      sent.services.sort().join(",") === "carpets,office_cleaning",
      JSON.stringify(sent.services));
    check("request: night access travels as a boolean",
      sent.night_access === true, JSON.stringify(sent.night_access));
  }

  // A residential request is not asked commercial questions.
  {
    const win = await boot();
    click(win, '[data-edit="request"]');
    const names = [...win.document.querySelectorAll('[data-form="request"] [name]')]
      .map((c) => c.getAttribute("name"));
    check("a home is not asked about services or night access",
      !names.includes("services") && !names.includes("night_access"), names.join(","));
    await save(win, "request");
    const keys = Object.keys(patches(win)[0]).sort().join(",");
    check("and neither is sent, so neither can be blanked",
      keys === "access_notes,desired_start,frequency", keys);
  }

  // The language of the quote email.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    check("contact: the language is a dropdown on the stored value",
      win.document.querySelector('[name="locale"]').value === "fr");
    set(win, "locale", "en");
    await save(win, "contact");
    check("contact: the language travels", patches(win)[0].locale === "en");
  }

  // THE BREAKDOWN HAS TO ADD UP. It did not: the card printed 175,74 $ + 15,00 $
  // above a total of 162,13 $, because the recurring discount between them was
  // never rendered. Three numbers on one card that do not sum, on the screen
  // where a price is decided and then emailed to a customer.
  {
    const win = await boot({
      frequency: "biweekly",
      computed_total_cents: 16213,
      computed_breakdown: {
        lines: [
          { code: "labour", label_fr: "Main-d'\u0153uvre estim\u00e9e", amount_cents: 17574 },
          { code: "travel", label_fr: "D\u00e9placement", amount_cents: 1500 }
        ],
        subtotal_cents: 19074,
        discount_cents: 2861,
        minimum_adjustment_cents: 0,
        total_cents: 16213
      }
    });
    const rows = [...win.document.querySelectorAll("#d-breakdown .breakdown-row")];
    const read = rows.map((r) => ({
      label: r.children[0].textContent,
      cents: Math.round(parseFloat(
        r.children[2].textContent.replace(/[^\d,.-]/g, "").replace(",", ".")) * 100)
    }));
    const total = read[read.length - 1];
    const before = read.slice(0, -1);

    check("breakdown: the discount is shown at all",
      before.some((r) => /[Rr]abais/.test(r.label)), read.map((r) => r.label).join(" | "));

    // Everything after the subtotal row is what adjusts it; the rows before it
    // are the line items. Either way the last adjustment chain must reach the total.
    const subIndex = before.findIndex((r) => /Sous-total/.test(r.label));
    check("breakdown: a subtotal row separates the lines from the adjustments",
      subIndex > 0, String(subIndex));
    if (subIndex > 0) {
      const lines = before.slice(0, subIndex).reduce((a, r) => a + r.cents, 0);
      const adjustments = before.slice(subIndex + 1).reduce((a, r) => a + r.cents, 0);
      check("breakdown: the line items sum to the subtotal",
        lines === before[subIndex].cents, lines + " vs " + before[subIndex].cents);
      check("breakdown: subtotal plus adjustments equals the total",
        before[subIndex].cents + adjustments === total.cents,
        before[subIndex].cents + " + " + adjustments + " != " + total.cents);
    }

    check("breakdown: the total says what period it covers",
      /par visite/.test(win.document.getElementById("d-breakdown").textContent),
      win.document.getElementById("d-breakdown").textContent.slice(-60));
    check("the send hint says what period it covers",
      /par visite/.test(win.document.getElementById("d-computed-hint").textContent),
      win.document.getElementById("d-computed-hint").textContent);
    check("the price field label says it too",
      /par visite/.test(win.document.getElementById("offer-price-unit").textContent),
      win.document.getElementById("offer-price-unit").textContent);
  }

  // A one-time quote with no discount: the lines already reach the total, so no
  // subtotal row, and the period reads "pour la visite" rather than "par visite".
  {
    const win = await boot({
      frequency: "one_time",
      computed_total_cents: 19074,
      computed_breakdown: {
        lines: [
          { code: "labour", label_fr: "Main-d'\u0153uvre estim\u00e9e", amount_cents: 17574 },
          { code: "travel", label_fr: "D\u00e9placement", amount_cents: 1500 }
        ],
        subtotal_cents: 19074, discount_cents: 0, minimum_adjustment_cents: 0,
        total_cents: 19074
      }
    });
    const text = win.document.getElementById("d-breakdown").textContent;
    check("one-time: no subtotal row when nothing adjusts it", !/Sous-total/.test(text));
    check("one-time: no phantom discount row", !/[Rr]abais/.test(text));
    check("one-time: the period reads for the visit", /pour la visite/.test(text),
      text.slice(-60));
  }

  // Every label must sit with its own value. This is the shape the bug had: the
  // <dt> and <dd> were separate grid items, so a three-column track printed
  // "TYPE | Commerce | SUPERFICIE" on one row and "2112 pi2 | TOILETTES | 88" on
  // the next -- every label reading against somebody else's number.
  {
    const win = await boot({ audience: "commercial", property_type: "retail",
      bedrooms: null, bathrooms: null, restrooms: 88, floors: 3, area_sqft: 2112 });
    const grids = [...win.document.querySelectorAll(".factgrid")];
    let loose = 0, pairs = 0;
    grids.forEach((dl) => {
      loose += [...dl.children].filter((c) => c.tagName !== "DIV").length;
      [...dl.querySelectorAll(".fact")].forEach((f) => {
        const kids = [...f.children].map((c) => c.tagName).join(",");
        if (kids === "DT,DD") pairs++;
      });
    });
    check("no dt or dd is a direct child of a factgrid", loose === 0, String(loose));
    check("every fact is exactly one dt and one dd",
      pairs === win.document.querySelectorAll(".fact").length && pairs > 0, String(pairs));

    const property = win.document.getElementById("d-property");
    const read = [...property.querySelectorAll(".fact")]
      .map((f) => f.querySelector("dt").textContent + "=" + f.querySelector("dd").textContent)
      .join(" | ");
    check("the property card reads label=its own value",
      read === "Superficie=2112 pi\u00b2 | Toilettes=88 | \u00c9tages=3", read);
    check("the type is not repeated from the heading", !/Type=/.test(read), read);
  }

  // Escape is the same as Annuler, and must not fight the other dialogs.
  {
    const win = await boot();
    click(win, '[data-edit="contact"]');
    const escape = new win.KeyboardEvent("keydown", { key: "Escape", bubbles: true });
    win.document.dispatchEvent(escape);
    check("Escape closes the editor",
      win.document.querySelector("[data-form]:not([hidden])") === null);
  }

  console.log(failures ? "\n" + failures + " FAILED\n" : "\nall checks passed\n");
  process.exitCode = failures ? 1 : 0;
})();
