import requests


def nominatim_search(query, limit=5):
    if not query:
        return []
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": limit},
            headers={"User-Agent": "freedom-square-crm-short"},
            timeout=10,
        )
        if response.ok:
            return response.json()
    except Exception:
        return []
    return []
