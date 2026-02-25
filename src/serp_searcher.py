"""
SerpAPI Searcher Module
Runs targeted searches for grant foundations, prioritizing:
  1. ProPublica Nonprofit Explorer (990 data)
  2. Granted AI (grant-specific directory)
  3. General web fallback
"""

import os
from serpapi import GoogleSearch


PRIORITY_SITES = [
    ("ProPublica", "site:projects.propublica.org/nonprofits"),
    ("Granted",    "site:grantedai.com"),
    ("Candid",     "site:candid.org"),
    ("CauseIQ",    "site:causeiq.com"),
]


def _clean_name(name: str) -> str:
    """Strip noisy suffixes so search hits the actual foundation name."""
    removals = ["inc", "c/o", "the", "llc", "ltd", "foundation", "trust", "corp"]
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t not in removals]
    # Put 'Foundation' back if we stripped everything meaningful
    result = " ".join(cleaned).strip()
    return result if result else name


def _run_query(query: str, api_key: str, num: int = 5) -> list[dict]:
    """Execute a single SerpAPI Google Search and return organic results."""
    try:
        search = GoogleSearch({
            "q": query,
            "api_key": api_key,
            "num": num,
            "gl": "us",
            "hl": "en",
        })
        results = search.get_dict()
        return results.get("organic_results", [])
    except Exception as e:
        print(f"  [SerpAPI] Query failed for '{query}': {e}")
        return []


def _is_relevant(result: dict, clean_name: str) -> bool:
    """Return True if the result title or snippet contains at least one meaningful
    word from the foundation name (basic relevance guard)."""
    keywords = [w for w in clean_name.lower().split() if len(w) > 3]
    if not keywords:
        return True   # can't filter, allow it
    text = (result.get("title", "") + " " + result.get("snippet", "")).lower()
    return any(kw in text for kw in keywords)


def search_foundation(foundation_name: str, website: str | None = None) -> dict:
    """
    Search for a foundation using priority sources.

    Returns:
        {
            "propublica": [...],    # list of result dicts (max 1 relevant)
            "granted":    [...],
            "general":    [...],
            "summary":    str       # concatenated snippet text for the prompt
        }
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError("SERPAPI_KEY not set in environment.")

    clean = _clean_name(foundation_name)
    results = {"propublica": [], "granted": [], "general": []}

    # --- Priority sites: take top 1 relevant result only ---
    for label, site_filter in PRIORITY_SITES:
        query = f"{clean} {site_filter}"
        hits  = _run_query(query, api_key, num=5)   # fetch 5, keep first relevant

        # Keep only the first hit whose title/snippet mentions the foundation
        relevant = [h for h in hits if _is_relevant(h, clean)]
        top = relevant[:1]  # max 1 per source

        key = label.lower()
        results[key] = top
        status = f"1 relevant result" if top else "no relevant results"
        print(f"  [{label}] {status}")

    # --- General fallback if both priority sources failed ---
    if not results["propublica"] and not results["granted"]:
        general_q = f'"{clean}" foundation grants education NJ'
        if website:
            domain = website.replace("https://", "").replace("http://", "").split("/")[0]
            general_q += f" OR site:{domain}"
        hits = _run_query(general_q, api_key, num=5)
        results["general"] = [h for h in hits if _is_relevant(h, clean)][:2]
        print(f"  [General] {len(results['general'])} result(s)")

    # --- Build a compact summary string for the Gemini prompt ---
    snippets = []
    for source_key in ("propublica", "granted", "general"):
        for r in results[source_key]:
            title   = r.get("title", "")
            snippet = r.get("snippet", "")
            link    = r.get("link", "")
            if snippet:
                snippets.append(f"[{source_key.upper()}] {title}\n{snippet}\nURL: {link}")

    results["summary"] = "\n\n".join(snippets) if snippets else "No results found."
    return results
