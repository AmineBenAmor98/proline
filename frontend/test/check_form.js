/* The quote form, driven end to end in a real DOM.
 *
 *     node frontend/test/check_form.js               # French
 *     node frontend/test/check_form.js en/soumission.html
 *
 * Needs jsdom:  npm i --no-save jsdom
 *
 * WHY THIS EXISTS. The Python suite covers the API thoroughly and passed green
 * through every one of these: a detail page that rendered nothing, a price
 * breakdown showing raw codes, a 422 the form reported as "sending failed, call
 * us", and a photo block that never appeared because an unrelated crash killed the
 * line that mounts it. None of them are API bugs. All of them are what a visitor
 * sees, and nothing was looking at that.
 *
 * So this loads the real markup, runs the real scripts against it, and asserts on
 * what ends up on screen -- which error box is visible, what text is in it, what
 * the form actually posted. Add a case here whenever something reaches the browser
 * that the API tests could not have caught.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..");
const PAGE = process.argv[2] || "soumission.html";

let failures = 0;
function check(name, ok, extra) {
  console.log((ok ? "  ok   " : "  FAIL ") + name + (ok || extra === undefined ? "" : "  -> " + extra));
  if (!ok) failures++;
}

const FORM_CONFIG = {
  modifiers: [], extras: [], residential_cells: [],
  photos_enabled: true, photo_max_count: 10,
  photo_zones_residential: [
    { value: "kitchen", label_fr: "Cuisine", label_en: "Kitchen" },
    { value: "other", label_fr: "Autre", label_en: "Other" }
  ],
  photo_zones_commercial: [
    { value: "workstations", label_fr: "Postes de travail", label_en: "Workstations" },
    { value: "other", label_fr: "Autre", label_en: "Other" }
  ]
};

async function boot(search) {
  const html = fs.readFileSync(path.join(ROOT, PAGE), "utf8");
  const dom = new JSDOM(html, {
    url: "https://proline-cleaningsolutions.com/soumission" + (search || ""),
    pretendToBeVisual: true,
    runScripts: "outside-only"
  });
  const { window } = dom;

  // Keep a log of every call and let each test decide the answer.
  const calls = [];
  window.__calls = calls;
  window.__next = null;                 // {status, body} for the next /api/quotes
  window.fetch = function (url, opts) {
    calls.push({ url: String(url), opts: opts });
    if (String(url).indexOf("/form-config") !== -1) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(FORM_CONFIG) });
    }
    if (/\/api\/quotes$/.test(String(url))) {
      const n = window.__next || { status: 201, body: { id: "abcdef12-0000-0000-0000-000000000000", message_fr: "ok", message_en: "ok" } };
      return Promise.resolve({
        ok: n.status < 400, status: n.status,
        json: () => Promise.resolve(n.body)
      });
    }
    return Promise.resolve({ ok: false, status: 409, json: () => Promise.reject(new Error("no")) });
  };
  window.HTMLElement.prototype.scrollIntoView = function () {};
  window.scrollTo = function () {};
  // jsdom has no blob URLs; the picker only ever uses them for the thumbnail.
  window.URL.createObjectURL = function () { return "blob:stub"; };
  window.URL.revokeObjectURL = function () {};

  // The page's own scripts, in load order.
  for (const f of ["photos.js", "quote.js"]) {
    const code = fs.readFileSync(path.join(ROOT, "js", f), "utf8");
    window.eval(code);
  }
  await new Promise((r) => setTimeout(r, 30));   // let the form-config promise settle
  return window;
}

function set(win, name, value) {
  const el = win.document.querySelector('[name="' + name + '"]');
  el.value = value;
  el.dispatchEvent(new win.Event("input", { bubbles: true }));
  el.dispatchEvent(new win.Event("change", { bubbles: true }));
  return el;
}

function pick(win, name, value) {
  const el = win.document.querySelector('[name="' + name + '"][value="' + value + '"]');
  el.checked = true;
  el.dispatchEvent(new win.Event("change", { bubbles: true }));
  return el;
}

function errText(win, id) {
  const box = win.document.getElementById("err-" + id);
  if (!box) return "(no such error box)";
  return box.hidden ? "" : box.textContent;
}

function fillCommercial(win, restrooms) {
  pick(win, "property_type", "retail");
  set(win, "area_sqft", "2112");
  set(win, "restrooms", String(restrooms));
  set(win, "full_name", "Amine Ben Amor");
  set(win, "email", "a@example.com");
  const consent = win.document.querySelector('[name="consent_given"]');
  consent.checked = true;
  consent.dispatchEvent(new win.Event("change", { bubbles: true }));
}

async function submit(win) {
  win.document.getElementById("quote-form")
    .dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 30));
}

(async () => {
  console.log("\n=== " + PAGE + " ===");

  // 1. His exact case: 222 washrooms must be caught before anything is sent.
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 222);
    const before = win.__calls.filter((c) => /\/api\/quotes$/.test(c.url)).length;
    await submit(win);
    const after = win.__calls.filter((c) => /\/api\/quotes$/.test(c.url)).length;
    check("222 washrooms: nothing is sent", after === before, after + " calls");
    check("222 washrooms: the field says why", /200/.test(errText(win, "restrooms")),
      JSON.stringify(errText(win, "restrooms")));
    check("222 washrooms: step 1 is shown",
      win.document.querySelector('[data-step="1"]') === null ||
      !win.document.querySelector('[data-step="1"]').hidden);
    const box = win.document.getElementById("form-error");
    check("222 washrooms: no phone number", box.hidden || !/242-4779/.test(box.textContent),
      box.textContent);
  }

  // 2. 200 is inside the cap and goes out.
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 200);
    await submit(win);
    const sent = win.__calls.filter((c) => /\/api\/quotes$/.test(c.url));
    check("200 washrooms: the request is sent", sent.length === 1, sent.length + " calls");
    if (sent.length) {
      const body = JSON.parse(sent[0].opts.body);
      check("200 washrooms: restrooms travels as a number", body.property.restrooms === 200,
        JSON.stringify(body.property));
      check("200 washrooms: no residential fields leak", body.property.bedrooms === undefined,
        JSON.stringify(body.property));
    }
    check("200 washrooms: the confirmation is on screen",
      !win.document.getElementById("done").hidden);
  }

  // 3. A server 422 on a field the form did not catch: marked, not "call us".
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 200);
    win.__next = { status: 422, body: { detail: [{
      loc: ["body", "property", "restrooms"], msg: "Input should be less than or equal to 200",
      type: "less_than_equal"
    }] } };
    await submit(win);
    check("server 422 restrooms: marked on the field", errText(win, "restrooms") !== "",
      JSON.stringify(errText(win, "restrooms")));
    const box = win.document.getElementById("form-error");
    check("server 422 restrooms: not the phone number", !/242-4779/.test(box.textContent),
      box.textContent);
    check("server 422 restrooms: the button works again",
      !win.document.getElementById("submit-btn").disabled);
  }

  // 4. A 422 on a field with no entry in the table: named, still not "call us".
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 200);
    win.__next = { status: 422, body: { detail: [{
      loc: ["body", "frequency"], msg: "Input should be ...", type: "enum"
    }] } };
    await submit(win);
    const box = win.document.getElementById("form-error");
    check("unmapped 422: says which answer", !box.hidden && box.textContent.length > 10,
      JSON.stringify(box.textContent));
    check("unmapped 422: not the phone number", !/242-4779/.test(box.textContent),
      box.textContent);
  }

  // 5. The consent 422, which arrives as a plain string.
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 200);
    win.__next = { status: 422, body: { detail: "consent is required to answer the request" } };
    await submit(win);
    check("consent 422: marked on the checkbox", errText(win, "consent_given") !== "",
      JSON.stringify(errText(win, "consent_given")));
  }

  // 6. A send that really did fail still points at the telephone.
  {
    const win = await boot("?audience=commercial");
    fillCommercial(win, 200);
    win.__next = { status: 502, body: {} };
    await submit(win);
    const box = win.document.getElementById("form-error");
    check("502: the phone number IS offered", /242-4779|242 4779/.test(box.textContent),
      box.textContent);
  }

  // 7. Residential: hidden commercial numbers must not block the send.
  {
    const win = await boot("?audience=residential");
    pick(win, "property_type", "house");
    set(win, "area_sqft", "1400");
    const r = win.document.querySelector('[name="restrooms"]');
    r.value = "999";                       // left behind in the hidden half
    set(win, "full_name", "Test");
    set(win, "email", "t@example.com");
    const consent = win.document.querySelector('[name="consent_given"]');
    consent.checked = true;
    consent.dispatchEvent(new win.Event("change", { bubbles: true }));
    await submit(win);
    const sent = win.__calls.filter((c) => /\/api\/quotes$/.test(c.url));
    check("residential: a stale hidden 999 does not block", sent.length === 1,
      sent.length + " calls, err=" + JSON.stringify(errText(win, "restrooms")));
    if (sent.length) {
      const body = JSON.parse(sent[0].opts.body);
      check("residential: restrooms is not sent", body.property.restrooms === undefined,
        JSON.stringify(body.property));
    }
  }

  // 8. The picker, with an empty rate card -- which is where this site stands.
  {
    const win = await boot("?audience=commercial");
    const host = win.document.getElementById("photo-picker");
    check("picker: mounted even with no priced cells",
      host && host.querySelector(".photo-drop") !== null);
    check("picker: the block is visible",
      !win.document.getElementById("photo-block").hidden);

    // The zone list must follow the type of place, which is chosen after mounting.
    pick(win, "property_type", "retail");
    await new Promise((r) => setTimeout(r, 20));

    const dt = { files: [new win.File([new Uint8Array([1, 2, 3])], "a.png", { type: "image/png" })] };
    const drop = new win.Event("drop", { bubbles: true, cancelable: true });
    drop.dataTransfer = dt;
    host.querySelector(".photo-drop").dispatchEvent(drop);
    await new Promise((r) => setTimeout(r, 20));

    const select = host.querySelector(".photo-zone");
    const nameBox = host.querySelector(".photo-zone-name");
    check("picker: a tile appeared", select !== null);
    if (!select) { console.log(failures ? "" : ""); }
    else {
      check("picker: a shop is offered commercial rooms",
        [...select.options].map((o) => o.value).join(",") === "workstations,other",
        [...select.options].map((o) => o.value).join(","));

      check("picker: the name box starts hidden", nameBox && nameBox.hidden === true);
      select.value = "other";
      select.dispatchEvent(new win.Event("change", { bubbles: true }));
      check('picker: "Autre" opens the name box', nameBox.hidden === false);
      nameBox.value = "Arrière-boutique";
      nameBox.dispatchEvent(new win.Event("input", { bubbles: true }));

      // Switch to a home: the list changes, "other" survives, the typed name with it.
      pick(win, "property_type", "house");
      await new Promise((r) => setTimeout(r, 20));
      const after = host.querySelector(".photo-zone");
      check("picker: a home is offered residential rooms",
        [...after.options].map((o) => o.value).join(",") === "kitchen,other",
        [...after.options].map((o) => o.value).join(","));
      check('picker: "other" survives the switch', after.value === "other", after.value);
      check("picker: the typed name survives with it",
        host.querySelector(".photo-zone-name").value === "Arrière-boutique",
        host.querySelector(".photo-zone-name").value);

      // And a room that does not exist in the new list falls back rather than lying.
      after.value = "kitchen";
      after.dispatchEvent(new win.Event("change", { bubbles: true }));
      check("picker: leaving Autre hides and clears the box",
        host.querySelector(".photo-zone-name").hidden === true &&
        host.querySelector(".photo-zone-name").value === "");
      pick(win, "property_type", "retail");
      await new Promise((r) => setTimeout(r, 20));
      const back = host.querySelector(".photo-zone");
      check("picker: a room the new list lacks falls back to its first",
        back.value === "workstations", back.value);
    }
  }

  console.log(failures ? "\n" + failures + " FAILED\n" : "\nall checks passed\n");
  process.exitCode = failures ? 1 : 0;
})();
