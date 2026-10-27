"""
parts_desk.py
=============
Detroit Diesel 6-71 parts desk: each major component of the engine, the
manual pages that cover it, and live sources for it found through String.

  - Manual pages come from data/catalog.json, exported from an OCR'd library
    of marine-engine manuals; part numbers come from GM Diesel's 1953 Series 71
    owners parts book (the manuals themselves aren't in this repo).
  - Sources are String /v1/search results for the part, cached so a demo
    never waits on the same search twice (refresh=True re-runs it).
  - check_listing() pulls price/stock from one vendor page with String's
    jsonSchema extraction, alongside what a plain HTTP request gets.
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT          = Path(__file__).parent
CATALOG       = json.loads((ROOT / "data/catalog.json").read_text())
SEED_SOURCES  = ROOT / "data/parts_sources.json"
# Serverless hosts only allow writes under /tmp; locally the seed file is updated in place.
SOURCES_CACHE = Path("/tmp/parts_sources.json") if os.getenv("VERCEL") else SEED_SOURCES
SOURCES_SHOWN = 8
API_ROOT      = "https://request.usestring.ai/v1"

# Extra search words per part, for the String query.
SEARCH_TERMS = {
    "thermostat": "thermostat",           "heat_exch": "heat exchanger marine",
    "oil_cooler": "oil cooler",           "oil_filter": "lube oil filter",
    "injector": "unit injector",          "head_gasket": "cylinder head gasket",
    "liner": "cylinder liner kit",        "alternator": "alternator",
    "starter": "starter motor",           "blower": "roots blower",
    "governor": "limiting speed mechanical governor",
    "fuel_pump": "fuel pump",             "fuel_filter": "fuel filter element",
    "water_pump": "fresh water pump",     "raw_water": "raw water pump impeller",
    "exh_valve": "exhaust valve",
}

# Parts whose 1953 numbers have since been superseded: searching by number finds
# other engines' parts, so these search by name only.
SEARCH_BY_NAME = {"oil_cooler", "oil_filter", "liner", "blower", "fuel_pump"}

PART_IDS = {p["id"]: p for p in CATALOG}
_sources_lock = threading.Lock()


# ── String ───────────────────────────────────

def api_key() -> str | None:
    return os.getenv("STRING_API_KEY")


def _post(endpoint: str, body: dict, timeout: int) -> requests.Response:
    r = requests.post(
        f"{API_ROOT}/{endpoint}",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    r.raise_for_status()
    return r


def string_search(query: str, engine: str = "google") -> list[dict]:
    """Top organic results: [{position, title, url, displayUrl, snippet, ...}]."""
    body = _post("search", {"query": query, "engine": engine}, timeout=60).json()
    return [r for r in body.get("results", []) if r.get("url")]


# ── Sources ──────────────────────────────────

def _load_sources() -> dict:
    path = SOURCES_CACHE if SOURCES_CACHE.exists() else SEED_SOURCES
    return json.loads(path.read_text()) if path.exists() else {}


def sources(part_id: str, refresh: bool = False) -> dict:
    """Live web listings for a part via String search; cached on disk."""
    cache = _load_sources()
    if part_id in cache and not refresh:
        return cache[part_id]
    numbers = PART_IDS[part_id]["part_numbers"]
    query = " ".join(["Detroit Diesel 6-71", SEARCH_TERMS[part_id], *[n["pn"] for n in numbers[:1] if part_id not in SEARCH_BY_NAME], "for sale"])
    t = time.time()
    results = string_search(query)[:SOURCES_SHOWN]
    entry = {
        "query":     query,
        "seconds":   round(time.time() - t, 2),
        "fetched":   time.strftime("%Y-%m-%d %H:%M"),
        "results":   [{"title": r.get("title"), "url": r["url"], "snippet": r.get("snippet", ""),
                       "domain": urlparse(r["url"]).hostname} for r in results],
    }
    with _sources_lock:
        cache = _load_sources()
        cache[part_id] = entry
        SOURCES_CACHE.write_text(json.dumps(cache, indent=1))
    return entry


def listed_urls() -> set[str]:
    return {r["url"] for e in _load_sources().values() for r in e["results"]}


# ── Listing checks ───────────────────────────

LISTING_SCHEMA = {
    "type": "object",
    "properties": {
        "product":     {"type": "string", "description": "Product name as listed"},
        "part_number": {"type": ["string", "null"], "description": "Manufacturer or Detroit Diesel part number, if shown"},
        "price":       {"type": ["number", "null"], "description": "Current price as a number, without currency symbol"},
        "currency":    {"type": ["string", "null"], "description": "e.g. USD"},
        "in_stock":    {"type": ["boolean", "null"], "description": "true if listed as in stock or available"},
        "condition":   {"type": ["string", "null"], "description": "new, rebuilt, used, or remanufactured, if stated"},
    },
    "required": ["product"],
}

BLOCK_MARKERS = ("captcha", "access denied", "just a moment", "pardon our interruption",
                 "verify you are human", "are you a robot", "request blocked")


def plain_check(url: str) -> dict:
    """What an ordinary scraper gets from the same URL — the comparison String is measured against."""
    t = time.time()
    try:
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; parts-desk/1.0)"})
        head = r.text[:5000].lower()
        blocked = r.status_code >= 400 or len(r.text) < 1000 or any(m in head for m in BLOCK_MARKERS)
        return {"status": r.status_code, "blocked": blocked, "seconds": round(time.time() - t, 2)}
    except Exception as e:
        return {"status": None, "blocked": True, "error": type(e).__name__, "seconds": round(time.time() - t, 2)}


def _string_check(url: str) -> dict:
    t = time.time()
    r = _post("fetch", {"url": url, "jsonSchema": LISTING_SCHEMA}, timeout=180)
    seconds = round(time.time() - t, 2)
    if r.headers.get("X-Json-Schema-Applied") == "true":
        return {"ok": True, "seconds": seconds, **r.json()}
    return {"ok": False, "seconds": seconds,
            "reason": r.headers.get("X-Json-Schema-Fallback-Reason") or "not a product page"}


def check_listing(url: str) -> dict:
    """Price/stock for one vendor page via String's structured extraction, alongside
    what a plain HTTP request gets from the same page. Both run in parallel."""
    with ThreadPoolExecutor(2) as pool:
        string_f, plain_f = pool.submit(_string_check, url), pool.submit(plain_check, url)
        return {**string_f.result(), "plain": plain_f.result()}
