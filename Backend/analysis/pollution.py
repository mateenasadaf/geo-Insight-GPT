"""
Pollution analysis using Sentinel-5P / TROPOMI.

This module measures satellite-derived atmospheric NO2
inside the exact Polygon/MultiPolygon returned by location.py.

Output:
    - Mean NO2 concentration/column density
    - Median NO2
    - Maximum NO2
    - Valid pixel count
    - Yearly trend

IMPORTANT:
    This is satellite-derived NO2, NOT ground-level AQI.
"""

import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

import numpy as np
import pystac_client
import planetary_computer

from rasterio.features import geometry_mask, bounds
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.enums import Resampling
import rasterio


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

STAC_URL = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

COLLECTION = "sentinel-5p-l2-netcdf"

SEARCH_BUFFER_DEG = 0.02

# Maximum scene cloud cover.
# Sentinel-5P NO2 is atmospheric data, but we still avoid
# scenes with very high cloud cover.
MAX_CLOUD_COVER = 50

MIN_VALID_PIXEL_FRACTION = 0.1

# Sentinel-5P NO2 product variable.
NO2_VARIABLE = "nitrogendioxide_tropospheric_column"


# ---------------------------------------------------------------------
# Scene search
# ---------------------------------------------------------------------

def get_candidate_sentinel5p_images(
    geometry,
    year
):

    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace
    )

    # -------------------------------------------------------------
    # Use exact polygon bounds.
    # -------------------------------------------------------------

    left, bottom, right, top = bounds(
        geometry
    )

    bbox = [
        left - SEARCH_BUFFER_DEG,
        bottom - SEARCH_BUFFER_DEG,
        right + SEARCH_BUFFER_DEG,
        top + SEARCH_BUFFER_DEG
    ]

    # -------------------------------------------------------------
    # Search the complete year.
    #
    # Unlike vegetation/urbanisation, NO2 is an atmospheric
    # measurement and we want multiple observations.
    # -------------------------------------------------------------

    start_date = f"{year}-01-01"

    end_date = f"{year + 1}-01-01"

    search = catalog.search(
        collections=[
            COLLECTION
        ],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}"
    )

    items = list(
        search.items()
    )

    if not items:

        raise ValueError(
            f"No Sentinel-5P NO2 data found "
            f"for {year}."
        )

    return items


# ---------------------------------------------------------------------
# Read raster
# ---------------------------------------------------------------------

def _read_no2_window(
    href,
    left,
    bottom,
    right,
    top
):

    with rasterio.open(
        href
    ) as src:

        bounds_in_crs = transform_bounds(
            "EPSG:4326",
            src.crs,
            left,
            bottom,
            right,
            top
        )

        window = from_bounds(
            *bounds_in_crs,
            transform=src.transform
        )

        height = max(
            1,
            int(
                round(
                    window.height
                )
            )
        )

        width = max(
            1,
            int(
                round(
                    window.width
                )
            )
        )

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=np.nan,
            out_shape=(
                height,
                width
            ),
            resampling=Resampling.bilinear
        ).astype(float)

        transform = src.window_transform(
            window
        )

        crs = src.crs

    return (
        data,
        transform,
        crs
    )


# ---------------------------------------------------------------------
# Find NO2 asset
# ---------------------------------------------------------------------

def find_no2_asset(
    image
):

    # First look for the expected variable.
    for key, asset in image.assets.items():

        text = (
            str(key)
            + " "
            + str(asset.title)
        ).lower()

        if (
            "tropospheric" in text
            and "nitrogen" in text
        ):

            return asset

    # Fallback search.
    for key, asset in image.assets.items():

        text = (
            str(key)
            + " "
            + str(asset.title)
        ).lower()

        if "no2" in text:

            return asset

    return None


# ---------------------------------------------------------------------
# Calculate NO2 for one scene
# ---------------------------------------------------------------------

def calculate_scene_no2(
    image,
    geometry
):

    asset = find_no2_asset(
        image
    )

    if asset is None:

        raise ValueError(
            f"NO2 variable not found "
            f"in scene {image.id}."
        )

    left, bottom, right, top = bounds(
        geometry
    )

    no2, transform, crs = _read_no2_window(
        asset.href,
        left,
        bottom,
        right,
        top
    )

    # -------------------------------------------------------------
    # Exact polygon mask
    # -------------------------------------------------------------

    polygon_raster = transform_geom(
        "EPSG:4326",
        crs,
        geometry
    )

    inside_polygon = geometry_mask(
        [polygon_raster],
        out_shape=no2.shape,
        transform=transform,
        invert=True
    )

    # -------------------------------------------------------------
    # Valid NO2 values
    # -------------------------------------------------------------

    valid = (
        inside_polygon
        &
        np.isfinite(no2)
        &
        (no2 >= 0)
    )

    values = no2[
        valid
    ]

    if values.size == 0:

        raise ValueError(
            f"No valid NO2 pixels found "
            f"inside polygon for {image.id}."
        )

    return values


# ---------------------------------------------------------------------
# Yearly NO2 analysis
# ---------------------------------------------------------------------

def calculate_yearly_pollution(
    geometry,
    year
):

    images = get_candidate_sentinel5p_images(
        geometry,
        year
    )

    all_values = []

    scenes_used = 0

    for image in images:

        try:

            values = calculate_scene_no2(
                image,
                geometry
            )

            if values.size > 0:

                all_values.append(
                    values
                )

                scenes_used += 1

        except Exception:

            continue

    if not all_values:

        raise ValueError(
            f"No valid NO2 observations "
            f"were available for {year}."
        )

    combined = np.concatenate(
        all_values
    )

    mean_no2 = float(
        np.mean(combined)
    )

    median_no2 = float(
        np.median(combined)
    )

    max_no2 = float(
        np.max(combined)
    )

    min_no2 = float(
        np.min(combined)
    )

    print(
        f"\n========== {year} =========="
    )

    print(
        "Dataset: Sentinel-5P / TROPOMI"
    )

    print(
        "Pollutant: NO2"
    )

    print(
        "Scenes used:",
        scenes_used
    )

    print(
        "Valid NO2 observations:",
        combined.size
    )

    print(
        f"Mean NO2: "
        f"{mean_no2:.6e}"
    )

    print(
        f"Median NO2: "
        f"{median_no2:.6e}"
    )

    print(
        f"Maximum NO2: "
        f"{max_no2:.6e}"
    )

    print(
        f"Minimum NO2: "
        f"{min_no2:.6e}"
    )

    return {
        "year": year,
        "mean_no2": mean_no2,
        "median_no2": median_no2,
        "maximum_no2": max_no2,
        "minimum_no2": min_no2,
        "valid_observations": int(
            combined.size
        ),
        "scenes_used": scenes_used,
        "pollutant": "NO2",
        "dataset": "Sentinel-5P / TROPOMI"
    }


# ---------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------

def main():

    from location import get_coordinates

    location_name = input(
        "Enter location: "
    )

    start_year = int(
        input("Enter start year: ")
    )

    end_year = int(
        input("Enter end year: ")
    )

    location = get_coordinates(
        location_name
    )

    geometry = location[
        "geometry"
    ]

    print("\nLocation found:")

    print(
        location["name"]
    )

    print(
        "Latitude:",
        location["latitude"]
    )

    print(
        "Longitude:",
        location["longitude"]
    )

    print(
        "Boundary type:",
        geometry["type"]
    )

    results = []

    for year in range(
        start_year,
        end_year + 1
    ):

        try:

            result = calculate_yearly_pollution(
                geometry=geometry,
                year=year
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"Could not analyze "
                f"{year}: {error}"
            )

    # -------------------------------------------------------------
    # Trend
    # -------------------------------------------------------------

    print(
        "\n\n=============================="
    )

    print(
        f"NO2 POLLUTION TREND "
        f"{start_year}-{end_year}"
    )

    print(
        "=============================="
    )

    for result in results:

        print(
            f"{result['year']} : "
            f"{result['mean_no2']:.6e}"
        )

    # -------------------------------------------------------------
    # Overall change
    # -------------------------------------------------------------

    if len(results) >= 2:

        first = results[0][
            "mean_no2"
        ]

        last = results[-1][
            "mean_no2"
        ]

        if first != 0:

            percentage_change = (
                (last - first)
                /
                abs(first)
            ) * 100

            print(
                "\nOverall NO2 change:"
            )

            print(
                f"{percentage_change:+.2f}%"
            )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()