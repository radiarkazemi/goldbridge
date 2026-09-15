# Goldapp price cards — how to keep them on the correct Farshad cash

Use this when a cash card shows the wrong / stuck price (common after a weekday
rollover). Farshad changes which **نقدی …** id is live every day; goldapp cards
must not stay pinned to yesterday’s Farshad id.

---

## TL;DR (what to do)

| Card purpose | `goldbridge_item_id` | `price_source_item_id` | Notes |
|---|---|---|---|
| **Main cash (نقدی)** | **`900000`** | `null` | Stable goldbridge alias = tomorrow’s live Farshad نقدی |
| متفرقه | `900001` (keep) | **`900000`** | Mirrors main cash |
| نقد کارتخوان | `900002` (keep) | **`900000`** | Mirrors main cash (or pin Farshad `1014` if you want that tile) |
| Coins / other Farshad items | real Farshad id (`3`, `4`, …) | `null` | Only if that Farshad id is stable |

**Do not** pin main cash to `1013`, `1009`, `1011`, etc. Those ids are weekday
tiles and go inactive the next day.

---

## Why cards break

Farshad names cash by **delivery weekday** (Asia/Tehran):

| Tehran weekday today | Live main نقدی (tomorrow delivery) | Typical Farshad id |
|---|---|---|
| Saturday | نقدی یکشنبه | `1013` |
| Sunday | نقدی دوشنبه | `1009` |
| Monday | نقدی سه‌شنبه | `1010` |
| Tuesday | نقدی چهارشنبه | `1011` |
| Wednesday | نقدی پنجشنبه | (if present) |
| … | … | … |

Goldbridge already auto-picks that tile on `GET /price` (`BRIDGE_TARGET_MODE=tomorrow`).

Goldapp **price cards** store a fixed `goldbridge_item_id`. If that id is a
Farshad weekday id (e.g. `1013`), the card goes stale overnight.

**Fix:** pin main cash to goldbridge synthetic id **`900000`**, which always
mirrors tomorrow’s live نقدی (name + buy/sell update automatically).

---

## Production layout (after the Sep 15 fix)

Enabled cards should look like:

| display_name | goldbridge_item_id | price_source_item_id | enabled |
|---|---|---|---|
| نقدی | **900000** | null | yes |
| متفرقه | 900001 | **900000** | yes |
| نقد کارتخوان | 900002 | **900000** | yes |

Commission rows for main cash should also use `goldbridge_item_id = 900000`
(not `1013`).

---

## How to update cards (admin UI)

If your admin “price cards” screen edits the same DB fields:

1. Open **Admin → Price cards**.
2. Find the main cash card (often still labeled like نقدی یکشنبه / id 1013).
3. Set **Goldbridge item id** to **`900000`**.
4. Clear any **price source / mirror id** on that card (`null`).
5. Enable buy/sell as needed; keep override-source on if you use that flag.
6. For **متفرقه** / **کارتخوان** synthetic cards: set **price source** = **`900000`**.
7. Save. Refresh customer `/ws/price` or wait one poll (~0.5–1s).

If the UI only lets you pick from `/prices`, choose the row:

- `id: 900000`
- `name: نقدی …` (whatever tomorrow’s day name is)
- `related_id: <real Farshad id>` (e.g. 1011) — informational

---

## How to update cards (SQL on VPS)

```sql
-- Main cash: unpin weekday id → stable alias
UPDATE price_cards
SET goldbridge_item_id = 900000,
    display_name = COALESCE(NULLIF(display_name, ''), 'نقدی'),
    is_enabled = true,
    orderable_buy = true,
    orderable_sell = true,
    override_source_restriction = true,
    price_source_item_id = NULL
WHERE goldbridge_item_id IN (1013, 1009, 1010, 1011, 1012);

-- Keep commissions attached to the card
UPDATE price_card_commissions
SET goldbridge_item_id = 900000
WHERE goldbridge_item_id IN (1013, 1009, 1010, 1011, 1012);

-- Synthetic mirrors follow main cash
UPDATE price_cards
SET price_source_item_id = 900000
WHERE goldbridge_item_id IN (900001, 900002);
```

Then confirm:

```sql
SELECT goldbridge_item_id, display_name, is_enabled, price_source_item_id
FROM price_cards
WHERE is_enabled = true
ORDER BY sort_order, goldbridge_item_id;
```

---

## How to verify (VPS)

```bash
# Goldbridge primary (real Farshad id, e.g. 1011 on Tuesday)
curl -s -H "Authorization: Bearer $BRIDGE_API_KEY" http://127.0.0.1:9100/price | jq .

# Alias goldapp should read
curl -s -H "Authorization: Bearer $BRIDGE_API_KEY" http://127.0.0.1:9100/prices \
  | jq '.prices[] | select(.id==900000)'
```

Checks:

- [ ] `/price` `name` is tomorrow’s نقدی (Tue → `نقدی چهارشنبه`)
- [ ] Alias `900000` has the **same** `buy` / `sell` as `/price`
- [ ] Alias `related_id` equals `/price.id` (real Farshad id)
- [ ] Goldapp enabled main card uses `goldbridge_item_id = 900000`
- [ ] App buy/sell (before your commission) match goldbridge alias (Rial; Toman = `/10`)

---

## Card field meanings (goldapp)

| Field | Meaning |
|---|---|
| `goldbridge_item_id` | Which row in goldbridge `GET /prices` this card is |
| `price_source_item_id` | Optional: use **another** item’s live buy/sell (mirror) |
| `display_name` | Optional label; `null` → use goldbridge `name` |
| `is_enabled` | Shown to customers |
| `orderable_buy` / `orderable_sell` | Customer can place that side |
| `override_source_restriction` | Ignore Farshad allow_buy/allow_sell when true |

Mirrors (`900001` / `900002`): keep their own synthetic ids for orders/ledger,
but set `price_source_item_id = 900000` so quotes track main cash.

---

## What goldapp code should assume going forward

1. **Main cash product** → always goldbridge id **`900000`** (not a Farshad weekday id).
2. Prefer `GET /price` for “the” cash quote, or `/prices` row `900000`.
3. Read `farshad_commission` to size your margin; do not hard-code 70,000 Toman.
4. Apply shop margin **in goldapp**; goldbridge no longer pads ±10k.
5. Units from goldbridge are **Rial**. If `GOLDAPP_PRICE_API_RIAL_TO_TOMAN=true`, divide by 10 for UI.

Optional future improvement: if admin UI lists Farshad weekday ids, hide them for
“main cash” and only offer `900000`, or auto-remap any `10xx` نقدی pin to `900000`.

---

## Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Cash stuck / not moving | Card pinned to inactive Farshad id (`1013`, …) | Set card to `900000` |
| App ≠ Farshad screen | Looking at نقدی شنبه (`1012`) vs main tomorrow tile | Compare names; main is tomorrow’s day |
| کارتخوان wrong | Mirror still on old master `1` | `price_source_item_id = 900000` |
| Alias missing | Goldbridge old build | Deploy branch with primary alias; restart `goldbridge` |
| `/price` id keeps changing daily | Expected (real Farshad id) | App cards should use `900000`, not `/price.id` |

---

## Related docs

- Full API/commission handoff: `docs/goldapp-handoff-goldbridge-changes.md`
- Goldbridge PR: https://github.com/radiarkazemi/goldbridge/pull/3
