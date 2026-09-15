# Goldapp integration handoff — goldbridge API changes

Give this document to the agent working on **goldapp** (the customer-facing app).
Goldbridge (price source on the VPS) was updated. Goldapp must consume the new
fields and stop assuming old behavior.

**Production goldbridge:** `http://127.0.0.1:9100` on VPS `185.7.172.20`  
**Branch deployed:** `cursor/match-farshad-screen-price-0329`  
**Auth:** `Authorization: Bearer <BRIDGE_API_KEY>` (same key as today)

**Updating goldapp price cards (main cash / mirrors):** see
[`docs/goldapp-price-cards-update.md`](./goldapp-price-cards-update.md).
Main cash must use stable goldbridge id **`900000`**, not Farshad weekday ids
(`1013`, `1009`, `1011`, …).

---

## 1. What was wrong before

1. Goldbridge sometimes used Farshad `priceBuy` / `priceSell` (bot offsets). Farshad’s **app screen** does **not** use those. It uses:
   ```
   buy  = price + profit + masterProfit
   sell = price - profit - masterProfit
   ```
2. Default target used to follow a fixed id (often yesterday’s `نقدی یکشنبه` = `1013`). Farshad’s **main cash** is named by **delivery weekday** — on Sunday the live tile is **`نقدی دوشنبه` = id `1009`**, not یکشنبه.
3. Farshad’s live commission (**سود** / `profit`) changes several times per hour. Goldapp needs that value to size its own margin so hedges stay profitable.
4. Old goldbridge also auto-applied `BRIDGE_SHOP_MARGIN_TOMAN=10000` (±10,000 Toman). **That automatic padding is removed.** Goldapp must apply its own margin.

---

## 2. Current production `.env` on goldbridge

```
BRIDGE_TARGET_MODE=tomorrow
BRIDGE_TARGET_PRICE_ID=1009
BRIDGE_POLL_SECONDS=1
```

`GET /price` (no query) auto-picks **tomorrow’s** Farshad `نقدی …` tile in Asia/Tehran (Sunday → **نقدی دوشنبه** / 1009). Response includes `id` + `name`. Pin with `BRIDGE_TARGET_MODE=fixed` if needed.

---

## 3. New / changed API fields

### `GET /price` and `GET /price?id=<id>`

Example (production shape):

```json
{
  "buy": 1038200000.0,
  "sell": 1036800000.0,
  "name": "نقدی یکشنبه",
  "base_price": 1037500000.0,
  "profit": 700000.0,
  "master_profit": 0.0,
  "farshad_commission": 700000.0,
  "farshad_spread": 1400000.0,
  "updated_at": "2026-09-12T08:12:21.295568+00:00",
  "source_updated_at": "2026-09-12 11:42:15",
  "stale": false
}
```

| Field | Unit | Meaning |
|---|---|---|
| `base_price` | Rial | Farshad **pure mid** (before their commission) |
| `profit` | Rial | Farshad raw **سود** (changes live) |
| `master_profit` | Rial | Extra pad; usually `0` |
| `farshad_commission` | Rial | **One-sided** commission = `profit + master_profit` |
| `farshad_spread` | Rial | Full screen spread = `2 × farshad_commission` = `buy - sell` |
| `buy` | Rial | Farshad on-screen **بخرید** (customer buys from Farshad) |
| `sell` | Rial | Farshad on-screen **بفروشید** (customer sells to Farshad) |
| `name` | — | Instrument name — verify it matches the Farshad tile you intend |
| `stale` | bool | If true, treat quotes carefully |

### `GET /prices`

Same per-row fields, plus:

| Field | Meaning |
|---|---|
| `related_id` | If set, this card follows that master (e.g. 1013 → related_id 1) |
| `related_diff` | Offset vs master |
| `active` | Farshad `isActive` |

### Units

- Goldbridge returns **Rial**.
- Farshad UI and usually goldapp admin UI show **Toman** = Rial `/ 10`.
- Example: `farshad_commission: 700000` Rial = **70,000 Toman** each side.

---

## 4. Instrument map (do not confuse these)

| Farshad UI | id | Typical commission | Notes |
|---|---|---|---|
| نقد … (hidden master) | `1` / `7` / … | ~30,000 Toman/side | often inactive — **not** the board tile |
| نقدی یکشنبه | `1013` | ~70,000 Toman/side | Sunday delivery (yesterday on a Sunday session) |
| **نقدی دوشنبه** | **`1009`** | varies | Monday delivery — **Sunday’s auto `/price` target** |
| نقدی سه‌شنبه | `1010` | varies | Tuesday delivery |
| نقدی کارتخوان | `1014` | varies | POS card — not the main cash target |

Default `/price` uses `BRIDGE_TARGET_MODE=tomorrow` (Asia/Tehran). Do not hard-code 1013 for “today’s main cash.”

---

## 5. What goldapp should implement

### A. Read Farshad commission from goldbridge

Prefer `farshad_commission` from `/price` (or the chosen `id`).

```
farshad_commission_toman = farshad_commission / 10
```

Do **not** hard-code 70,000. Poll often (goldbridge refreshes ~1s); when `farshad_commission` changes, update goldapp margin.

### B. Hedge-safe customer quotes

Farshad `buy` = price you pay when **you buy from Farshad** (to cover a customer buy).  
Farshad `sell` = price you receive when **you sell to Farshad** (after a customer sell).

```
goldapp_customer_buy_price  >= farshad.buy  + your_extra_margin
goldapp_customer_sell_price <= farshad.sell - your_extra_margin
```

If goldapp also quotes as mid ± commission:

```
your_total_commission >= farshad_commission + your_extra_margin
```

Old bridge shop margin was 10,000 Toman. Re-apply that (or any desired extra) **inside goldapp**, not by expecting goldbridge to pad.

### C. Wire API paths (if not already)

Typical goldapp env (adjust names to your project):

```
GOLDAPP_PRICE_SOURCE=api
GOLDAPP_PRICE_API_URL=http://127.0.0.1:9100/price
GOLDAPP_API_BUY_PATH=buy
GOLDAPP_API_SELL_PATH=sell
GOLDAPP_PRICE_API_KEY=<same as BRIDGE_API_KEY>
```

**Extend the price DTO / parser** to also read:

- `base_price`
- `farshad_commission`
- `farshad_spread`
- `profit`
- `id`
- `name`
- `stale`

If goldapp only mapped `buy`/`sell` before, add the commission fields so the admin UI or margin engine can react. Prefer trusting `/price`’s resolved `id`/`name` when using the default tomorrow mode.

### D. Optional: pick instrument by id

```
GET /price          # tomorrow's main نقدی (auto)
GET /price?id=1009  # pin نقدی دوشنبه
GET /prices         # discover ids, related_id, farshad_commission per row
```

---

## 6. Breaking changes for goldapp

| Before | After |
|---|---|
| `/price` often tracked id `1` (master) or fixed `1013` | `/price` auto-tracks **tomorrow’s نقدی …** (e.g. Sunday → **1009** نقدی دوشنبه); response includes `id` |
| Bridge may have added ±10k Toman shop margin | **No shop margin** from bridge — pure Farshad screen quote |
| Commission not exposed | Use **`farshad_commission`** |
| Formula may have used priceBuy/priceSell | Formula is **price ± profit** |

Expect displayed goldapp prices to move closer to Farshad’s نقدی tile, then diverge only by **your** configured extra margin.

---

## 7. Quick verification checklist

On the VPS (or via goldapp’s server-side HTTP client):

```bash
curl -s -H "Authorization: Bearer $BRIDGE_API_KEY" http://127.0.0.1:9100/price | jq .
```

Confirm:

- [ ] `id` / `name` match **tomorrow’s** main نقدی tile (Sunday → `1009` / `نقدی دوشنبه`)
- [ ] `farshad_commission` is present and non-zero
- [ ] `buy == base_price + farshad_commission`
- [ ] `sell == base_price - farshad_commission`
- [ ] `stale == false`
- [ ] Goldapp customer buy ≥ Farshad `buy` + extra margin
- [ ] Goldapp customer sell ≤ Farshad `sell` - extra margin

Compare side-by-side with Farshad web/app **tomorrow delivery** نقدی tile (Toman = Rial/10).

---

## 8. Out of scope / still Farshad-side

- Per-user Farshad `diff` from `/userPrices` is **not** included. Goldbridge matches a Farshad account with `diff=0`. If the logged-in Farshad user has a personal diff, the app can still differ by that amount.
- Goldapp’s own “کسر کمیسیون” / manual price overrides remain goldapp responsibility.

---

## 9. Suggested goldapp code tasks for the other agent

1. Update price-source client/schema to parse `base_price`, `farshad_commission`, `farshad_spread`, `profit`, `master_profit`, `name`, `stale`.
2. Drive dynamic margin from `farshad_commission` (+ configurable extra Toman).
3. Prefer default `/price` (tomorrow auto) or map products by delivery weekday — do **not** hard-code 1013 as “today’s main cash.”
4. Remove any assumption that goldbridge already added 10,000 Toman shop margin.
5. Add a small admin/debug readout: Farshad mid, Farshad commission (Toman), our extra margin, final customer buy/sell.
6. Test against live `127.0.0.1:9100/price` on the VPS.

---

## 10. Reference PR

https://github.com/radiarkazemi/goldbridge/pull/3
