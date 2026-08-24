import pystac_client
import planetary_computer


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

MAX_SCENE_CLOUD_COVER = 20


def get_monthly_images(latitude, longitude, year, month):

    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace
    )

    bbox = [
        longitude - 0.1,
        latitude - 0.1,
        longitude + 0.1,
        latitude + 0.1
    ]

    if month == 12:
        start_date = f"{year}-12-01"
        end_date = f"{year + 1}-01-01"
    else:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month + 1:02d}-01"

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}",
        query={
            "eo:cloud_cover": {
                "lt": MAX_SCENE_CLOUD_COVER
            }
        }
    )

    images = list(search.items())

    images.sort(
        key=lambda item:
        item.properties.get("eo:cloud_cover", 100)
    )

    return images


if __name__ == "__main__":

    latitude = 12.9716
    longitude = 77.5946

    year = 2020
    month = 3

    images = get_monthly_images(
        latitude,
        longitude,
        year,
        month
    )

    print(
        f"\nSentinel-2 observations for "
        f"{year}-{month:02d}: {len(images)}"
    )

    for image in images:

        print(
            image.datetime,
            "| Cloud:",
            image.properties.get("eo:cloud_cover"),
            "| ID:",
            image.id
        )