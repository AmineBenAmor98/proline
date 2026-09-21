# Pricing v2 — the plan

Two designs to build: the four-step customer form, and the admin screen that
configures what it asks. This is the sequencing, the decisions that block it, and
what is deliberately out of scope.

## The spine: the rate card drives the form

One rule holds this together and prevents the drift that already bit us twice
(`floors` and `property_type` collected and never used):

> **The form asks only what the active rate card can price.**

A modifier with no value in the card is not applied, and the question that feeds
it is not asked. An extra with no price is not offered. A public
`GET /api/quotes/form-config`, derived from the active card, tells the form what to
show.

Three things fall out of this:

- Amine turns capabilities on as he learns his real numbers, without a deploy.
- We never collect an input nothing prices.
- The form and the engine cannot disagree, because there is one source of truth.

It also means **every phase below can ship with its values empty** and change
nothing for a visitor until a real number is entered.

## Phase 0 — decisions, settled

1. **Multipliers stack, under a cap.** A first visit on a place never cleaned
   professionally really is worse than either alone, so they compound. But
   uncapped compounding runs away, so the card carries
   `max_residential_multiplier` (default `2.5`) and the product is clamped to it.
   The breakdown says so when the cap bites.
2. **Multipliers do not apply to extras.** They multiply the base and room work
   only. A per-unit extra already scales with its quantity; multiplying it again
   double-counts and produces numbers a client will argue with.
3. **Order of operations**, fixed and tested:
   `base grid → rooms, kitchen, levels → area → × modifiers (capped) → + extras → − frequency discount → floor at the minimum visit`
   The discount applies to the whole visit including extras, because that is what
   a recurring client understands it to mean. The floor is **last**: it is a
   promise about what the client pays, not about the arithmetic behind it. The
   engine had this backwards until the review below — see *Corrections*.
4. **`vide / fin de bail` stays a modifier.** It is the same scope under different
   conditions, and it usually travels with `premier ménage`, which stacking
   already handles. A separate grid would double the matrix for little gain. If
   real jobs prove otherwise it is one card value to change, not a rewrite.
5. **Area: the form sends a number.** Bands are a UI affordance; the form sends
   the band's midpoint and the engine is untouched. `je ne sais pas` estimates
   from bedrooms via `area_estimate_by_bedrooms` on the card.
6. **Everything ships neutral.** An absent multiplier is 1.0, an absent additive
   is 0, an absent extra is not offered. Phase 2 converts today's flat extras to
   `unit: "flat"` so no visitor sees a different price until Amine enters one.

## Phases 1–2 — foundation and per-unit extras — **shipped**

- `GET /api/quotes/form-config` (public), derived from the active card: which
  extras exist, with what unit, price and wording, in both languages.
- The card's extras are `{code: {unit, cents, label_fr, label_en, per_fr, per_en}}`
  and the request's are a `jsonb` quantity map. Both started life as something
  simpler (`extras_cents: {code: cents}`, and a `varchar(40)[]`); the migrations
  that converted them are folded into `0001` now that nothing has ever been
  deployed.
- `QuoteRequestIn.extras` is `dict[code, qty]`. Three units: `flat` (quantity is
  always 1), `each` (the visitor says), `per_100sqft` (from the area, rounded up).
- The labels moved onto the card. They used to exist in `app/pricing/engine.py`
  and again in the frontend; adding an extra now takes no code in either.
- The form renders the extras it is given, with a stepper for `each`, and the
  breakdown line reads `Vitres intérieures × 6 par fenêtre`.
- The admin request row shows what was asked for, naming each extra from the
  breakdown that priced it, so a total of 462 $ is readable as a work order.
- `/admin/tarifs` edits an extra's price, unit and wording in both languages, adds
  and retires extras, and shows a worked example per row (`8 × 4,00 $ = 32,00 $`)
  because a unit price is not checkable at a glance.

**What is not done:** the payload is not versioned, so a page cached from before
this change would submit an array and get a 422. The window is the page cache;
nothing stored is at risk.

## Corrections — found by review after Phase 2

Four of these were live money or availability bugs. None had a test.

1. **The minimum visit was applied before the discount.** A weekly client on a
   120 $ minimum was quoted **102 $** — the discount ate straight through the
   floor — and the discount was computed on the floor rather than on the work,
   inflating it too. The floor is now last, reported as its own
   `minimum_adjustment_cents` so the lines still add up to the total.
2. **`subtotal_cents` reported the floored figure**, so the breakdown did not
   close: lines summing to 37,50 $ under a subtotal of 120 $. It is now the sum
   of the lines, always.
3. **A `per_100sqft` extra with no area was silently dropped.** The visitor
   ticked the baseboards, was charged nothing, and the crew did them for free.
   Now it refuses to price and routes to a person, which the form already says.
4. **A commercial request with no service ticked was priced as office cleaning**,
   with no line saying so. An estimate nobody asked for is worse than none.
   Relatedly, restrooms are now counted before the "nothing to price" check, so a
   restrooms-only contract is a quote rather than an error.
5. **`bedrooms_max` / `bathrooms_max` described a dense grid the card does not
   have** — and nothing read them. Replaced by `residential_cells`, the
   combinations that actually price; the form greys out the rest.
6. **`floors`, the address and the desired start were collected and shown to
   nobody.** They are on the admin row now. That is the rule working in the other
   direction: an input a *person* uses is fine, as long as the person can see it.
7. **`hmac.compare_digest` raises on non-ASCII `str`.** An admin password with an
   accent in it — in Montreal — made every sign-in a 500, including the correct
   one, and a header byte above 0x7f took down every admin endpoint. Compared as
   UTF-8 bytes now.
8. Smaller: a malformed request id was a 500 rather than a 422; `notes` saved
   only when a price was sent with it; the public extras map accepted arbitrary
   keys in any number; `/quotes/price` priced a commercial draft before refusing
   to return it.

## Phase 3 — residential modifiers — **shipped**

A modifier is a question about the job whose answer changes the price:
*premier ménage*, *état du logement*, *animaux*, *logement vide*. All four live
on the rate card, with their wording in both languages, and the form renders
whatever it is given — the pattern extras set.

**One shape, not three.** Every modifier is a question with options. "Premier
ménage ?" is a question with two; "état" is one with three. The alternative was
a type per question (`boolean`, `choice`, `count`) and a branch per type in the
engine, the form and the admin — so a sixth modifier would have cost code in all
three. This way it costs none.

**Two kinds of effect, and the difference is deliberate.** A *multiplier* scales
the work, because a first clean of a cluttered home is the same rooms taking
longer. An *amount* is added after the multiplying, because two additions should
not compound each other. Neither touches the extras: a per-unit extra already
scales with its own quantity, and multiplying it again double-counts
(decision 2).

**Multipliers compound, under `max_residential_multiplier`** (2.5 by default).
A first clean of a very dirty empty home is already 1.4 × 1.45 × 1.15 = 2.33 on
its own. When the cap bites, the line says `(plafonné)`.

**Every question needs a free answer** — enforced in `app/schemas/rate_card.py`.
Without one there is no way to say "this does not apply" and the modifier becomes
a tax on everybody.

**A modifier whose every answer is free is not asked.** Same rule as an extra
with no price: the form asks only what the active card can price, so a question
can be added to a card long before its numbers are settled.

`sort` is explicit on each modifier because **JSONB does not preserve key
order** — Postgres stores an object's keys sorted by length then bytewise, so
"the order the admin wrote them in" does not survive a round trip, and the order
questions are asked in is an editorial decision rather than an accident of
spelling.

The quote line reads `Premier ménage : Oui`, which is why a modifier carries a
`short_fr` separate from its question: a question mark does not belong on an
invoice, and the answer alone ("Oui") says nothing.

**The tester exercises them.** One of the three built-in scenarios is a first
clean of a very dirty house, so a decimal slip in a multiplier moves a number in
`/admin/tarifs` instead of reaching a visitor.

## Phases 4–7 — vertical slices

Each phase is schema → engine → admin section → form section → tests, shipped
end to end. No horizontal layers: every phase leaves the app usable.

| # | Slice | Backend | Admin | Form |
|---|---|---|---|---|
| 4 | **Rooms in detail** | powder rooms, extra rooms, kitchen size, levels | rates section | counters, kitchen choice, levels |
| 5 | **Commercial depth** | per-fixture, per-surface, visits/week, access hours | three sections | fixtures, surfaces, passages, heures |
| 6 | **Periodic work** | scheduled items priced per year | schedule editor | the `travaux périodiques` screen |
| 7 | **Zones and travel** | travel by borough | zone table | address + zone badge |

Phase 4 is next.

The pattern extras and modifiers set is the one to follow: the value, its unit
and its wording all live on the card, the admin edits them with a worked example
beside each row, and the form renders whatever it is given.

## Phase 8 — the form itself

Still last, and unchanged: it only makes sense once the inputs exist.

- Four steps with the progress bar and the collapsing recap.
- Conditional questions (`data-when` extended from audience to any condition).
- `Plus de détails` disclosure per step.
- Address autocomplete and the service-zone check.
- `Estimation` vs `Prix ferme` confidence state.

## Phase 9 — admin v2 layout — **shipped**

Three columns: **rail, editor, tester**. The editor shows one section at a time;
the page used to be a single scroll through eight boxes and every later phase
adds another.

Eight sections, and **every one has something behind it**:

| Group | Section |
|---|---|
| Général | Minimum et déplacement · Rabais de fréquence |
| Résidentiel | Grille de base · Superficie · Modificateurs · Extras et unités |
| Commercial | Cadences par service |
| Historique | Versions publiées |

The original mockup drew twelve, five of which had no backend — built as drawn,
nearly half the menu would have opened empty rooms. **A later phase adds a row to
`SECTIONS` in `rates.js` and a `data-section` box in `tarifs.html`, nothing
else**: that is the whole point of sequencing 9 after the phases that fill it.

**The rail marks edited sections with a dot**, mapped from `flatten()`'s keys by
the `keys` field on each section — one source of truth about what lives where,
rather than a hand-kept list that drifts.

It was a *number* until that number was read by someone who had not written it.
The count was of changed leaf keys, which is a fact about the diff and not a
quantity anyone means: the four standard questions carry ten options between
them, so adding them put a `10` beside *Modificateurs* — directly above a panel
reading "Aucune question pour l'instant" — while the four extras put a `4` beside
*Extras*, close enough to a count of extras to make the wrong reading look right.
The rail only has to answer *where are my unpublished edits*, which a dot answers
and can always back up. The draft bar keeps the precise count, in words.

The chosen section survives a reload, and a validation error in a hidden section
switches to it rather than pointing at something off screen.

Under 1200px the rail lies down as a horizontal scroller and the editor takes the
full width. That breakpoint is 1200 rather than 1080 because between the two, the
three columns left the price matrix below its own minimum width and it scrolled
sideways inside its card. The admin container is also wider than the site's
`--max`, which is a reading measure for prose, not a data screen.

## Out of scope, deliberately

- **Photo upload and AI enrichment.** Its own project. The form reserves the slot
  and the `Estimation → Prix ferme` wording already depends on it.
- **Operations** — scheduling, invoicing, routing, the customer portal.
- **Conversion tracking and the privacy policy.** Both needed before ads, neither
  part of pricing.

## The one thing to do regardless

**Log quoted vs actual hours on every job.** None of the numbers above can be
verified without it, and with it the grid corrects itself from real work. It is a
column in the admin and a habit on site, and it is worth more than any phase here.
