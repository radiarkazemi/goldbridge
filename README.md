# goldbridge

A small, standalone, private service. It does ONE thing: polls a
third-party gold-trading platform (using credentials the platform owner
issued directly to you) and re-exposes the current buy/sell price as a
plain local JSON endpoint that your main app can read.

**This is deliberately not part of the main goldapp codebase.** It's a
separate project on purpose - keep it that way (see "Keeping this
confidential" below).

## ⚠️ Before you trust this in production

The price formula in `extract_buy_sell()` (in `main.py`) is my best
read of the one sample response you shared, cross-checked against the
بخرید/بفروشید numbers in your screenshot at a different point in time -
it matched the *pattern* (buy > sell, right rough magnitude) but I
could not verify it against a live, simultaneous side-by-side
comparison. **Before switching your main app over to this source**, run
`goldbridge` for a few minutes and compare its `/price` output
side-by-side against what `sekefarshad.ir`'s own web UI is showing at
the exact same moment. If the numbers don't match, the fix is entirely
inside `extract_buy_sell()` - it's a ~15 line function.

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