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

## Matching the Farshad /trade screen (id=1 vs نقدی …)

Farshad's trade board does **not** show `id=1`. `id=1` is the inactive
master (`نقد یکشنبه`, `isActive=0`, `profit=300000`). The green/red
tiles are the **نقدی** children:

| Farshad tile | list.php id | related_id | profit (Rial) | UI spread (Toman) |
|---|---|---|---|---|
| نقد یکشنبه (master, hidden) | 1 | — | 300,000 | ±30,000 |
| نقدی یکشنبه (on /trade) | 1013 | 1 | 700,000 | ±70,000 |
| نقدی دوشنبه (on /trade) | 1009 | 7 | 700,000 | ±70,000 |
| نقدی کارتخوان (on /trade) | 1014 | 1 | 700,000 | ±70,000 (+ live offsets) |

Worked example from a simultaneous screenshot + `list.php` dump:

- Farshad **نقدی دوشنبه** showed 104,410,000 / 104,270,000 Toman
- `id=1009`: `price=1043400000`, `profit=700000`
- `(price ± profit) / 10` = 104,410,000 / 104,270,000 — exact match
- Goldbridge `/price` (id=1) is a different row: ±30,000 Toman, not ±70,000

To match a Farshad tile, call `GET /price?id=1013` (or set
`BRIDGE_TARGET_PRICE_ID=1013`). `GET /prices` now includes `related_id`
and `profit` so you can see which cards follow which master.

Farshad's UI also divides Rial by 10 (Toman). Goldbridge still returns
Rial; goldapp already converts for display. Goldapp's own commission
fields (کسر کمیسیون) will still shift the number after goldbridge.

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
BRIDGE_TARGET_PRICE_ID=1
# 1 = master نقد یکشنبه (hidden). Use 1013 to match Farshad /trade نقدی یکشنبه.
BRIDGE_POLL_SECONDS=20
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
don't own. `BRIDGE_POLL_SECONDS=20` is intentionally conservative -
don't drop this much lower without checking with the platform owner
first. If this account ever gets rate-limited or flagged for unusual
traffic, it's not just this integration that breaks - it could affect
the actual person whose login this is.