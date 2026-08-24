import pystac_client
import planetary_computer
import requests


def get_best_satellite_image(
    latitude,
    longitude,
    start_date,
    end_date
):
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )

    bbox = [
        longitude - 0.1,
        latitude - 0.1,
        longitude + 0.1,
        latitude + 0.1
    ]

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}",
        query={
            "eo:cloud_cover": {
                "lt": 20
            }
        }
    )

    items = list(search.items())

    if not items:
        print("No satellite images found.")
        return

    # Select image with lowest cloud cover
    best_image = min(
        items,
        key=lambda item: item.properties.get(
            "eo:cloud_cover", 100
        )
    )

    print("Best image found:")
    print("ID:", best_image.id)
    print("Date:", best_image.datetime)
    print(
        "Cloud cover:",
        best_image.properties.get("eo:cloud_cover")
    )

    # Get the RGB image
    rgb_asset = best_image.assets["visual"]

    image_url = rgb_asset.href

    print("Downloading image...")

    response = requests.get(image_url)

    if response.status_code == 200:
        with open("satellite_image.tif", "wb") as file:
            file.write(response.content)

        print("Image downloaded successfully!")
        print("Saved as: satellite_image.tif")

    else:
        print("Failed to download image.")


if __name__ == "__main__":

    get_best_satellite_image(
        latitude=12.9716,
        longitude=77.5946,
        start_date="2026-01-01",
        end_date="2026-08-22"
    )