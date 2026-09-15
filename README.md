# goldbridge

A small, standalone, private service. It does ONE thing: polls a
third-party gold-trading platform (using credentials the platform owner
issued directly to you) and re-exposes the current buy/sell price as a
plain local JSON endpoint that your main app can read.

**This is deliberately not part of the main goldapp codebase.** It's a
separate project on purpose - keep it that way (see "Keeping this
confidential" below).

## Price formula (must match Farshad's own app)

Farshad's trade board does **not** display `priceBuy` / `priceSell`.
Those fields are bot live-offsets (and sometimes admin-side snapshots).
The on-screen بخرید / بفروشید numbers come from `price ± profit`
(plus `masterProfit`), confirmed in sekefarshad.ir's own frontend
(`mp` / `gp` / `vp` in `/static/js/main.4ad7f49b.js`):

```
customer-buy  (بخرید)  = price + profit + masterProfit
customer-sell (بفروشید) = price - profit - masterProfit
```

The old goldbridge formula (`price + priceSell` / `price + priceBuy`)
is why `/price` sometimes disagreed with the app:

- when both offsets were `0` (the usual idle payload), goldbridge
  returned a flat mid-price while the app still showed `price ± profit`
- when offsets were non-zero they were often a *different* spread than
  `profit` (e.g. ±500k offset vs ±700k profit)

`extract_buy_sell()` / `clean_entry()` now follow the app formula.
A remaining caveat: Farshad then adds a per-user `diff` from
`/userPrices` on top of the board quote. Goldbridge matches the board
a user with `diff=0` sees.

## Matching the Farshad /trade screen (delivery weekday)

Farshad cash tiles are named by **delivery** weekday. The live *main*
quote is usually **tomorrow's** `نقدی …` in Asia/Tehran (Sunday trade →
`نقدی دوشنبه`, not yesterday's `نقدی یکشنبه`). Masters like `id=1` are
often inactive and may be renamed day-to-day; the green/red `/trade`
tiles are the **نقدی** children.

| Farshad tile | list.php id | notes |
|---|---|---|
| نقد … (master, often hidden) | 1 / 7 / … | smaller سود; not the board tile |
| نقدی یکشنبه | 1013 | Sunday delivery |
| نقدی دوشنبه | 1009 | Monday delivery — Sunday's main live tile |
| نقدی سه‌شنبه | 1010 | Tuesday delivery |
| نقدی کارتخوان | 1014 | card-reader variant — not the main cash target |

Default: `BRIDGE_TARGET_MODE=tomorrow` auto-picks tomorrow's active
`نقدی` board card each poll (skips کارتخوان). Pin with
`BRIDGE_TARGET_MODE=fixed` + `BRIDGE_TARGET_PRICE_ID=<id>`.
`GET /price` returns the resolved `id` + `name`.

Farshad's UI also divides Rial by 10 (Toman). Goldbridge still returns
Rial; goldapp already converts for display. Goldapp's own commission
fields (کسر کمیسیون) will still shift the number after goldbridge.

## Farshad's live commission (سود) — the trick

Farshad does **not** show the pure mid on the trade board. They store a
pure mid in `price`, then pad each side by a field they call **سود**
(`profit` in the JSON). Operators change that سود several times an hour.

```
pure mid (API)           = price
Farshad commission (1 side) = profit + masterProfit     ← this is what moves
Farshad بخرید (on screen) = price + commission
Farshad بفروشید (on screen) = price - commission
full screen spread        = 2 × commission
```

Example (live): `price=1039300000`, `profit=700000` → commission =
70,000 Toman each side, screen buy/sell = mid ± 70,000 Toman.

Goldbridge exposes this on every `/price` and `/prices` row:

| field | meaning |
|---|---|
| `base_price` | pure mid (Rial) |
| `profit` | raw Farshad سود (Rial) |
| `master_profit` | extra pad, usually 0 |
| `farshad_commission` | one-sided commission = profit + master_profit |
| `farshad_spread` | full spread = 2 × commission |
| `buy` / `sell` | what Farshad's app shows (diff=0 account) |

### How to set YOUR commission so hedges stay profitable

Your customer buys from you → you must buy the same from Farshad at
Farshad's `buy`. Your customer sells to you → you must sell to Farshad
at Farshad's `sell`.

```
your_customer_buy  >= farshad.buy  + your_extra_margin
your_customer_sell <= farshad.sell - your_extra_margin
```

Equivalently, if you also quote as mid ± your_total_commission:

```
your_total_commission >= farshad_commission + your_extra_margin
```

Poll `/price` (tomorrow auto) or `/price?id=<نقدی id>` about every
second — when `farshad_commission` jumps, raise/lower your margin in
goldapp to match. Do **not** hard-code 70,000 Toman; Farshad changes it.

## Polling cadence (1 second, without breaking the source)

Default `BRIDGE_POLL_SECONDS=1`. That stays safe because:

1. **Apply-first** – every tick updates the target quote immediately,
   even if upstream returned a 1-row truncated catalog
2. **Merge-by-id** – partial catalogs never wipe secondary cards
3. **Throttled full-catalog retry** – only about every 8s (and on cold
   start), not on every truncated tick (so 1s ≠ 2 req/s forever)
4. **RTT-aware sleep** – sleep is `poll - request_time`, so the
   effective interval stays ~1s instead of `1s + network`
5. **Short burst after a move** – `BRIDGE_POLL_FAST_SECONDS` (default
   0.5s) for a few seconds after the primary quote changes

## Setup

```bash
cd goldbridge
python -m venv venv
source venv/Scripts/activate    # Windows Git Bash
# or: source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

Create `.env` (copy `.env.example` and fill in the real values):

```
BRIDGE_SOURCE_UID=94
BRIDGE_SOURCE_UTOKEN=<the real token>
BRIDGE_TARGET_MODE=tomorrow
# tomorrow = auto-pick tomorrow's نقدی … (Asia/Tehran). fixed = pin id below.
BRIDGE_TARGET_PRICE_ID=1009
# fallback / fixed pin (1009 = نقدی دوشنبه)
BRIDGE_POLL_SECONDS=1
# Optional: briefly poll faster after a quote change (defaults 0.5s / 3s window)
# BRIDGE_POLL_FAST_SECONDS=0.5
# BRIDGE_POLL_FAST_WINDOW_SECONDS=3
```

Run it:

```bash
uvicorn main:app --host 127.0.0.1 --port 9100
```

Verify it's working:

```bash
curl http://127.0.0.1:9100/health
curl http://127.0.0.1:9100/price
```

## Wiring it into the main app (zero code changes needed there)

The main app already has a fully generic HTTP price source
(`app/price_sources/api_source.py`) that can point at *any* JSON API.
In the main app's `.env`:

```
GOLDAPP_PRICE_SOURCE=api
GOLDAPP_PRICE_API_URL=http://127.0.0.1:9100/price
GOLDAPP_API_BUY_PATH=buy
GOLDAPP_API_SELL_PATH=sell
```

That's it - no code in the main repo needs to know this bridge, or the
third-party platform behind it, exists at all.

## Keeping this confidential

Confidentiality here comes from **access control**, not from making the
code unreadable:

- Keep this in its own **private** git repo (GitHub/GitLab private
  repo, or no git hosting at all if you'd rather keep it purely local)
- Never commit `.env` - it's already in `.gitignore` below
- Only people who need to run or maintain it should have access to the
  repo or the server it runs on
- Run it bound to `127.0.0.1` only (already the default above) so it's
  never reachable from outside the machine it's on
- If you deploy it on its own small VPS instead of alongside the main
  app, put it behind the same kind of firewall discipline as the main
  app (SSH key auth, no unnecessary open ports)

This gives the platform owner everything they actually need (their
credentials and integration details stay out of any repo anyone else
can see) without making the code itself something even you can't
maintain later.

## Being a respectful API consumer

This authenticates as someone else's real account on a platform you
don't own. `BRIDGE_POLL_SECONDS=1` is the default (with throttled
full-catalog retries). Don't go much below that without checking with
the platform owner first. If this account ever gets rate-limited or
flagged for unusual traffic, it's not just this integration that
breaks - it could affect the actual person whose login this is.