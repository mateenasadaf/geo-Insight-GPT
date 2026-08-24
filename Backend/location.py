from geopy.geocoders import Nominatim


geolocator = Nominatim(
    user_agent="geo-insight-gpt"
)


def get_coordinates(location_name):

    location = geolocator.geocode(
        location_name
    )

    if location is None:
        raise ValueError(
            f"Could not find location: {location_name}"
        )

    return {
        "name": location.address,
        "latitude": location.latitude,
        "longitude": location.longitude
    }