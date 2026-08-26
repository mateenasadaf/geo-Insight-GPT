"""
Agriculture analysis using ESA WorldCover.

Purpose:
    Estimate cropland coverage inside the exact geographic
    boundary returned by location.py.

Data:
    ESA WorldCover 10 m global land-cover product.

WorldCover cropland class:
    40 = Cropland

Important:
    WorldCover provides global maps for 2020 and 2021.
    Therefore this module does not pretend to provide
    annual cropland measurements for years where a
    comparable WorldCover map is unavailable.
"""

import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

import numpy as np
import pystac_client
import planetary_computer
import rasterio

from rasterio.features import geometry_mask, bounds
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.enums import Resampling


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

STAC_URL = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

COLLECTION = "esa-worldcover"

# WorldCover cropland class
CROPLAND_CLASS = 40

# WorldCover maps currently supported by this module
SUPPORTED_YEARS = {
    2020,
    2021
}


# ---------------------------------------------------------------------
# Find WorldCover image
# ---------------------------------------------------------------------

def get_worldcover_image(
    geometry,
    year
):

    if year not in SUPPORTED_YEARS:

        raise ValueError(
            f"ESA WorldCover is currently supported "
            f"only for {sorted(SUPPORTED_YEARS)}. "
            f"Year {year} is not available."
        )

    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace
    )

    left, bottom, right, top = bounds(
        geometry
    )

    search = catalog.search(
        collections=[COLLECTION],
        bbox=[
            left,
            bottom,
            right,
            top
        ]
    )

    items = list(
        search.items()
    )

    if not items:

        raise ValueError(
            f"No ESA WorldCover tile found "
            f"for the selected location in {year}."
        )

    # WorldCover uses different product versions
    # for 2020 and 2021.
    target_version = (
        "v100"
        if year == 2020
        else "v200"
    )

    versioned_items = [
        item
        for item in items
        if target_version in item.id
        or target_version in str(
            item.properties
        )
    ]

    if versioned_items:

        return versioned_items[0]

    return items[0]


# ---------------------------------------------------------------------
# Read WorldCover raster
# ---------------------------------------------------------------------

def read_worldcover_aoi(
    image,
    geometry
):

    left, bottom, right, top = bounds(
        geometry
    )

    asset = None

    # ---------------------------------------------------------------
    # Find the WorldCover map asset.
    # ---------------------------------------------------------------

    for key, candidate in image.assets.items():

        media_type = (
            candidate.media_type
            or ""
        )

        title = (
            candidate.title
            or ""
        )

        combined = (
            key.lower()
            + " "
            + media_type.lower()
            + " "
            + title.lower()
        )

        if (
            "map" in combined
            or "tif" in media_type.lower()
            or "geotiff" in media_type.lower()
        ):

            asset = candidate

            break

    if asset is None:

        raise ValueError(
            "Could not find the WorldCover "
            "map asset."
        )

    with rasterio.open(
        asset.href
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

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            resampling=Resampling.nearest
        )

        transform = src.window_transform(
            window
        )

        crs = src.crs

        nodata = (
            src.nodata
            if src.nodata is not None
            else 0
        )

    # ---------------------------------------------------------------
    # Transform exact location polygon
    # ---------------------------------------------------------------

    polygon_raster = transform_geom(
        "EPSG:4326",
        crs,
        geometry
    )

    # ---------------------------------------------------------------
    # Exact polygon mask
    # ---------------------------------------------------------------

    inside_polygon = geometry_mask(
        [polygon_raster],
        out_shape=data.shape,
        transform=transform,
        invert=True
    )

    valid = (
        data != nodata
    )

    valid &= inside_polygon

    return (
        data,
        valid,
        inside_polygon
    )


# ---------------------------------------------------------------------
# Agriculture calculation
# ---------------------------------------------------------------------

def calculate_yearly_agriculture(
    geometry,
    year
):

    image = get_worldcover_image(
        geometry,
        year
    )

    (
        landcover,
        valid,
        inside_polygon
    ) = read_worldcover_aoi(
        image,
        geometry
    )

    polygon_pixels = int(
        inside_polygon.sum()
    )

    if polygon_pixels == 0:

        raise ValueError(
            "The selected polygon does not "
            "overlap the WorldCover tile."
        )

    valid_pixels = int(
        valid.sum()
    )

    if valid_pixels == 0:

        raise ValueError(
            "No valid WorldCover pixels "
            "were found inside the polygon."
        )

    # ---------------------------------------------------------------
    # Identify cropland
    # ---------------------------------------------------------------

    cropland_pixels = (
        (landcover == CROPLAND_CLASS)
        &
        valid
    )

    cropland_count = int(
        cropland_pixels.sum()
    )

    # ---------------------------------------------------------------
    # Calculate percentage
    # ---------------------------------------------------------------

    cropland_percentage = (
        cropland_count
        /
        valid_pixels
    ) * 100

    valid_fraction = (
        valid_pixels
        /
        polygon_pixels
    )

    print(
        f"\n========== {year} =========="
    )

    print(
        "Dataset: ESA WorldCover"
    )

    print(
        "WorldCover cropland class:",
        CROPLAND_CLASS
    )

    print(
        "Exact polygon pixels:",
        polygon_pixels
    )

    print(
        "Valid polygon pixels:",
        valid_pixels
    )

    print(
        f"Valid polygon coverage: "
        f"{valid_fraction:.0%}"
    )

    print(
        "Cropland pixels:",
        cropland_count
    )

    print(
        f"Cropland coverage: "
        f"{cropland_percentage:.2f}%"
    )

    return {
        "year": year,
        "cropland_percentage":
            cropland_percentage,
        "cropland_pixels":
            cropland_count,
        "valid_pixels":
            valid_pixels,
        "valid_pixel_fraction":
            valid_fraction,
        "dataset":
            "ESA WorldCover"
    }


# ---------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------

def main():

    from location import get_coordinates

    location_name = input(
        "Enter location: "
    )

    year = int(
        input(
            "Enter agriculture year "
            "(2020 or 2021): "
        )
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
        "Boundary type:",
        geometry["type"]
    )

    result = calculate_yearly_agriculture(
        geometry=geometry,
        year=year
    )

    print(
        "\n\n=============================="
    )

    print(
        "AGRICULTURE ANALYSIS"
    )

    print(
        "=============================="
    )

    print(
        f"Year: {result['year']}"
    )

    print(
        f"Cropland coverage: "
        f"{result['cropland_percentage']:.2f}%"
    )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()