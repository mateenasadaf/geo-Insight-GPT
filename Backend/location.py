from geopy.geocoders import Nominatim


geolocator = Nominatim(
    user_agent="geo-insight-gpt"
)


def get_coordinates(location_name):

    location = geolocator.geocode(
        location_name,
        exactly_one=True,
        addressdetails=True,
        geometry="geojson"
    )

    if location is None:
        raise ValueError(
            f"Could not find location: {location_name}"
        )

    geometry = location.raw.get("geojson")

    if geometry is None:
        raise ValueError(
            f"No geographic boundary found for: {location_name}"
        )

    geometry_type = geometry.get("type")

    if geometry_type not in ["Polygon", "MultiPolygon"]:
        raise ValueError(
            f"Exact boundary not found for '{location_name}'. "
            f"Nominatim returned a {geometry_type} instead of a Polygon."
        )

    return {
        "name": location.address,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "geometry": geometry
    }