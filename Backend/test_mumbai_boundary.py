import requests

url = "https://nominatim.openstreetmap.org/search"

params = {
    "q": "Mumbai Municipal Corporation, Maharashtra, India",
    "format": "jsonv2",
    "polygon_geojson": 1,
    "limit": 10
}

headers = {
    "User-Agent": "Geo-Insight-GPT/1.0"
}

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=30
)

response.raise_for_status()

results = response.json()

print(f"\nNumber of results: {len(results)}\n")

for i, result in enumerate(results):

    print("=" * 60)
    print(f"RESULT {i + 1}")

    print("Name:", result.get("display_name"))
    print("Type:", result.get("type"))
    print("Class:", result.get("class"))
    print("OSM type:", result.get("osm_type"))
    print("OSM ID:", result.get("osm_id"))

    geojson = result.get("geojson")

    if geojson:
        print("Geometry:", geojson.get("type"))
    else:
        print("Geometry: None")