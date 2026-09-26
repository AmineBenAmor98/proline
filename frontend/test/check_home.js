/* The home page's calculator preview, in a real DOM.
 *
 *     node frontend/test/check_home.js
 *
 * ONE PROPERTY MATTERS HERE and it is not "the number appears": it is that the
 * panel NEVER SHOWS A FIGURE IT WAS NOT GIVEN. The thing it replaced was
 * `[PRIX] $` hard-coded into the markup, and the tempting fix -- typing a number
 * in -- would have quoted every visitor a price nothing kept true. So the tests
 * that matter are the failure paths: no rate card, and no network.
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

async function boot(page, answer) {
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, page), "utf8"), {
    url: "https://proline-cleaningsolutions.com/",
    runScripts: "outside-only"
  });
  const { window } = dom;
  const calls = [];
  window.__calls = calls;
  window.fetch = function (url, opts) {
    calls.push({ url: String(url), body: opts && opts.body });
    if (answer === "offline") return Promise.reject(new Error("no network"));
    if (answer === 409) {
      return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
  };
  window.eval(fs.readFileSync(path.join(ROOT, "js", "home.js"), "utf8"));
  await new Promise((r) => setTimeout(r, 30));
  return window;
}

const text = (w, id) => w.document.getElementById(id).textContent;
const shown = (w, id) => w.document.getElementById(id).hidden === false;

(async () => {
  for (const page of ["index.html", "en/index.html"]) {
    console.log("\n=== " + page + " (calculator preview) ===");

    // No rate card prices this home: the panel must stay wordy and numberless.
    {
      const win = await boot(page, 409);
      check("409: no figure is shown", !shown(win, "demo-price"));
      check("409: no divider hanging over nothing", !shown(win, "demo-rule"));
      check("409: the invitation is still there", text(win, "demo-note").length > 20,
        JSON.stringify(text(win, "demo-note")));
      check("409: no digits leaked into the panel",
        !/\d[\d\s,.]*\s*\$|\$\s*\d/.test(text(win, "demo-price")), text(win, "demo-price"));
    }

    // The network is gone. Same outcome, and nothing about our rate card on screen.
    {
      const win = await boot(page, "offline");
      check("offline: no figure is shown", !shown(win, "demo-price"));
      check("offline: the invitation is unchanged", text(win, "demo-note").length > 20);
    }

    // A real answer: the figure, the divider and the firm-price wording together.
    {
      const win = await boot(page, { total_cents: 17500, lines: [] });
      check("priced: the figure appears", shown(win, "demo-price") &&
        /175/.test(text(win, "demo-price")), text(win, "demo-price"));
      check("priced: the divider appears with it", shown(win, "demo-rule"));
      check("priced: the per-visit line appears", shown(win, "demo-unit"));
      check("priced: the note becomes the firm-price wording",
        /1[\s, ]?100/.test(text(win, "demo-note")), text(win, "demo-note"));

      const sent = win.__calls.filter((c) => /quotes\/price/.test(c.url));
      check("priced: one call, to the real endpoint", sent.length === 1, String(sent.length));
      if (sent.length) {
        const body = JSON.parse(sent[0].body);
        check("priced: it asks for the home the chips describe",
          body.property.area_sqft === 1100 && body.property.bedrooms === 3 &&
          body.property.bathrooms === 2 && body.frequency === "biweekly",
          JSON.stringify(body.property) + " " + body.frequency);
        check("priced: it asks as a resident, or the endpoint answers 403",
          body.audience === "residential", body.audience);
      }
    }

    // A malformed answer must not print "undefined" where a price goes.
    {
      const win = await boot(page, { lines: [] });
      check("garbage answer: still no figure", !shown(win, "demo-price"),
        text(win, "demo-price"));
    }
  }

  console.log(failures ? "\n" + failures + " FAILED\n" : "\nall checks passed\n");
  process.exitCode = failures ? 1 : 0;
})();
