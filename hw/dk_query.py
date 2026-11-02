#!/usr/bin/env python3
"""DigiKey Product Information v4 keyword search, DE locale, EUR prices.

Why this exists rather than importing pwr-mosfet-lib's dslib.prices.digikey_api:
that module is the mature multi-key implementation and is the right thing for bulk
pricing, but it needs the pinned hurricaneJoef digikey-api fork and that project's
venv is an empty husk (venv/bin has no python, 2026-09-12).  v4 keyword search over
plain HTTPS needs no SDK, so this asks for nothing to be installed -- and it lets us
set the locale, which the library hardcodes to x_digikey_locale_site='US'.

Credentials are READ, never printed, from the same gitignored files that project
uses -- one OAuth app per file, CLIENT_ID= / CLIENT_SECRET= lines:

    ~/dev/pv/pwr-mosfet-lib/data/.digikey-api[N]

or from DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET in the environment.  Client
credentials is 2-legged: no browser, no callback, despite CALLBACK_URL sitting in
the file for the v3 flow.

Quota is 120/min and 1,000/day PER KEY and is shared with that project's pricing
runs, so keep queries deliberate.  This tool makes exactly one search per MPN.

    ./dk_query.py BAT54-7-F BAT54W-7-F

Locale matters for a German order: DigiKey may substitute the requested currency,
so the currency actually used is read back from search_locale_used and printed.
Never assume the EUR column is EUR because it was asked for.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import urllib.parse
import urllib.request

CREDS_GLOB = os.path.expanduser("~/dev/pv/pwr-mosfet-lib/data/.digikey-api*")
TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"


def read_creds() -> tuple[str, str, str]:
    """(client_id, client_secret, source) -- environment first, then the files."""
    env_id, env_secret = os.environ.get("DIGIKEY_CLIENT_ID"), os.environ.get("DIGIKEY_CLIENT_SECRET")
    if env_id and env_secret:
        return env_id, env_secret, "environment"
    for path in sorted(glob.glob(CREDS_GLOB)):
        if os.path.isdir(path):
            continue
        kv = {}
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    kv[k.strip()] = v.strip().strip("'\"")
        if kv.get("CLIENT_ID") and kv.get("CLIENT_SECRET"):
            return kv["CLIENT_ID"], kv["CLIENT_SECRET"], os.path.basename(path)
    raise SystemExit(
        "no DigiKey credentials: set DIGIKEY_CLIENT_ID/SECRET or provide %s" % CREDS_GLOB
    )


def get_token(client_id: str, client_secret: str) -> str:
    body = urllib.parse.urlencode(
        {"client_id": client_id, "client_secret": client_secret,
         "grant_type": "client_credentials"}
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tok = json.loads(resp.read())["access_token"]
    return tok


def search(mpn: str, token: str, client_id: str,
           site: str = "DE", lang: str = "de", currency: str = "EUR") -> tuple[dict, dict]:
    """(payload, response_headers).  Headers carry X-RateLimit-Remaining, the only
    view of how much of the shared daily quota this run spent."""
    req = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps({"Keywords": mpn, "Limit": 10, "Offset": 0}).encode(),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "X-DIGIKEY-Client-Id": client_id,
            "Content-Type": "application/json",
            "X-DIGIKEY-Locale-Site": site,
            "X-DIGIKEY-Locale-Language": lang,
            "X-DIGIKEY-Locale-Currency": currency,
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read()), dict(resp.headers)


def ladder(variation: dict) -> str:
    rows = variation.get("StandardPricing") or []
    return "  ".join("%s+ %.4f" % (r.get("BreakQuantity"), r.get("UnitPrice", 0.0))
                     for r in rows[:5]) or "(no ladder)"


def report(mpn: str, payload: dict, headers: dict, requested_currency: str) -> None:
    used = (payload.get("SearchLocaleUsed") or {})
    got_currency = used.get("Currency") or "?"
    print("\n=== %s ===" % mpn)
    print("locale used: site=%s currency=%s   (requested %s)%s"
          % (used.get("Site", "?"), got_currency, requested_currency,
             "   *** SUBSTITUTED ***" if got_currency != requested_currency else ""))
    rem = headers.get("X-RateLimit-Remaining")
    if rem is not None:
        print("daily quota remaining on this key: %s" % rem)

    products = payload.get("Products") or []
    if not products:
        print("no products returned")
        return
    for prod in products:
        pmpn = prod.get("ManufacturerProductNumber") or "?"
        # exact match only: a keyword search happily returns the neighbours, and
        # pricing the wrong sibling is the whole failure mode this guards
        if pmpn.upper() != mpn.upper():
            continue
        mfr = (prod.get("Manufacturer") or {}).get("Name", "?")
        print("%s  %s" % (pmpn, mfr))
        print("  %s" % (prod.get("Description") or {}).get("ProductDescription", ""))
        print("  package: %s" % ((prod.get("Packaging") or {}).get("Value", "?")))
        for p in prod.get("Parameters") or []:
            if p.get("ParameterText") in ("Package / Case", "Supplier Device Package",
                                          "Voltage - DC Reverse (Vr) (Max)",
                                          "Current - Reverse Leakage @ Vr",
                                          "Operating Temperature - Junction"):
                print("  %s: %s" % (p["ParameterText"], p.get("ValueText")))
        print("  datasheet: %s" % prod.get("DatasheetUrl", "?"))
        for v in prod.get("ProductVariations") or []:
            print("  [%s] %s  stock %s  MOQ %s"
                  % (v.get("DigiKeyProductNumber"),
                     (v.get("PackageType") or {}).get("Name", "?"),
                     v.get("QuantityAvailableforPackageType"),
                     v.get("MinimumOrderQuantity")))
            print("      %s" % ladder(v))
        return
    print("no EXACT match for %s in %d returned products: %s"
          % (mpn, len(products),
             ", ".join((p.get("ManufacturerProductNumber") or "?") for p in products[:6])))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    client_id, client_secret, source = read_creds()
    print("credentials from: %s" % source)
    token = get_token(client_id, client_secret)
    print("token acquired (client_credentials, 2-legged)")
    for mpn in argv:
        payload, headers = search(mpn, token, client_id)
        report(mpn, payload, headers, "EUR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
