#!/usr/bin/env python3
"""iPhone Duo stock watcher: London + Detroit. Pushes a phone alert when stock appears.

Setup:
  1. pip install requests
  2. Fill in CONFIG below (part numbers, Best Buy key/SKU, ntfy topic).
  3. Install the free ntfy app on your phone and subscribe to your topic.
  4. Run: python duo_watch.py   (or schedule it / leave it running)
"""
import time, os, sys, json, requests

CONFIG = {["MK2E4QN/A", "MK2D4QN/A"]}
    "ntfy_topic": os.environ.get("NTFY_TOPIC", "CHANGE-ME-to-something-unguessable"),
    "interval_seconds": 300,          # be polite; don't go below ~120
    # Apple part numbers: open the Duo's buy page, pick a model, view page source,
    # search for "MK" or "part" to find the code (e.g. MK2K4QL/A style).
    "apple": [
        {"label": "Apple UK (London)", "base": "https://www.apple.com/uk", "location": "SW12 9AA",
         "parts": ["PART_NUMBER_HERE"]},
        {"label": "Apple US (Detroit)", "base": "https://www.apple.com", "location": "48226",
         "parts": ["PART_NUMBER_HERE"]},
    ],
    # Best Buy: free API key at developer.bestbuy.com; SKU from the product page URL.
    "bestbuy": {"key": os.environ.get("BESTBUY_KEY", ""), "skus": ["SKU_HERE"], "zip": "48226", "radius_miles": 25},
}

HEADERS = {"User-Agent": "Mozilla/5.0 (stock-watcher personal use)"}
STATE = "seen.json"  # remembers alerts between runs (used in --once mode)
seen = set()  # alert keys already sent, so you only get pinged on new availability


def notify(title, msg):
    print(f"ALERT: {title} | {msg}")
    try:
        requests.post(f"https://ntfy.sh/{CONFIG['ntfy_topic']}", data=msg.encode(),
                      headers={"Title": title, "Priority": "high"}, timeout=15)
    except requests.RequestException as e:
        print("ntfy failed:", e)


def check_apple(cfg):
    found = set()
    for i, part in enumerate(cfg["parts"]):
        if part == "PART_NUMBER_HERE":
            continue
        r = requests.get(f"{cfg['base']}/shop/fulfillment-messages", headers=HEADERS, timeout=20,
                         params={"pl": "true", "mts.0": "regular", "mts.1": "compact",
                                 "parts.0": part, "location": cfg["location"]})
        r.raise_for_status()
        stores = r.json().get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
        for s in stores:
            info = s.get("partsAvailability", {}).get(part, {})
            if info.get("pickupDisplay") == "available":
                found.add((f"{cfg['label']}: {s.get('storeName')}", part))
    return found


def check_bestbuy(cfg):
    found = set()
    if not cfg["key"]:
        return found
    for sku in cfg["skus"]:
        if sku == "SKU_HERE":
            continue
        url = (f"https://api.bestbuy.com/v1/stores(area({cfg['zip']},{cfg['radius_miles']}))"
               f"+products(sku={sku})")
        r = requests.get(url, timeout=20, params={"apiKey": cfg["key"], "format": "json",
                                                   "show": "storeId,name,city,products.sku"})
        r.raise_for_status()
        for s in r.json().get("stores", []):
            if s.get("products"):
                found.add((f"Best Buy: {s['name']} ({s['city']})", sku))
    return found


def run_checks():
    results = set()
    for cfg in CONFIG["apple"]:
        try:
            results |= check_apple(cfg)
        except Exception as e:
            print(f"{cfg['label']} error:", e)
    try:
        results |= check_bestbuy(CONFIG["bestbuy"])
    except Exception as e:
        print("Best Buy error:", e)
    for where, item in results:
        if (where, item) not in seen:
            seen.add((where, item))
            notify("iPhone Duo in stock", where)
    # forget anything that sold out so a restock alerts again
    seen.intersection_update(results)
    print(time.strftime("%H:%M:%S"), f"{len(results)} location(s) with stock")


def main():
    if "--once" in sys.argv:  # single run, for GitHub Actions / cron
        try:
            seen.update(tuple(x) for x in json.load(open(STATE)))
        except Exception:
            pass
        run_checks()
        json.dump(sorted(seen), open(STATE, "w"))
        return
    print("Watching... Ctrl+C to stop.")
    while True:
        run_checks()
        time.sleep(CONFIG["interval_seconds"])


if __name__ == "__main__":
    main()
