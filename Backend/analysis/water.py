"""
Water-body analysis using Sentinel-2 imagery from Microsoft
Planetary Computer.

Method:
    MNDWI = (Green - SWIR) / (Green + SWIR)

Water pixels are initially identified using:
    MNDWI > 0

The analysis is restricted to the exact Polygon/MultiPolygon
returned by location.py.

Sentinel-2 bands:
    B03 -> Green (10 m)
    B11 -> SWIR  (20 m)
    SCL -> Scene Classification Layer

Processing:
    Exact polygon
        ↓
    Polygon-derived satellite search
        ↓
    Fixed seasonal window
        ↓
    B03 + B11
        ↓
    Resample B11 to B03 grid
        ↓
    SCL masking
        ↓
    MNDWI
        ↓
    Water pixels
        ↓
    Water coverage %
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

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

COLLECTION = "sentinel-2-l2a"

# Buffer around the polygon's bounding box for scene search.
# This is ONLY used for finding candidate satellite scenes.
SEARCH_BUFFER_DEG = 0.02

MAX_SCENE_CLOUD_COVER = 20

MIN_VALID_PIXEL_FRACTION = 0.5

# Initial MNDWI threshold.
WATER_MNDWI_THRESHOLD = 0.0

SENTINEL2_SCALE = 10000.0


# ---------------------------------------------------------------------
# Fixed seasonal window
# ---------------------------------------------------------------------

# Keep the same months for every year to reduce seasonal bias.
#
# You can change these later depending on the region.
#
# January -> March
SEASON_START_MONTH = 1
SEASON_END_MONTH = 3


# ---------------------------------------------------------------------
# Sentinel-2 SCL values to exclude
# ---------------------------------------------------------------------

SCL_EXCLUDE_VALUES = {
    0,   # No data
    1,   # Saturated / defective
    3,   # Cloud shadow
    8,   # Cloud medium probability
    9,   # Cloud high probability
    10,  # Thin cirrus
    11   # Snow / ice
}


# ---------------------------------------------------------------------
# MNDWI
# ---------------------------------------------------------------------

def calculate_mndwi(
    green,
    swir
):

    denominator = green + swir

    return np.divide(
        green - swir,
        denominator,
        out=np.full_like(
            denominator,
            np.nan,
            dtype=float
        ),
        where=denominator != 0
    )


# ---------------------------------------------------------------------
# Sentinel-2 scene search
# ---------------------------------------------------------------------

def get_candidate_sentinel_images(
    geometry,
    year,
    season_start_month=SEASON_START_MONTH,
    season_end_month=SEASON_END_MONTH
):

    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace
    )

    # -------------------------------------------------------------
    # Use the actual polygon bounds.
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
    # Fixed seasonal window.
    # -------------------------------------------------------------

    start_date = (
        f"{year}-"
        f"{season_start_month:02d}-01"
    )

    if season_end_month == 12:

        end_date = (
            f"{year + 1}-01-01"
        )

    else:

        end_date = (
            f"{year}-"
            f"{season_end_month + 1:02d}-01"
        )

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

    items = list(
        search.items()
    )

    if not items:

        raise ValueError(
            f"No suitable satellite image found "
            f"for {year} in the window "
            f"{start_date} to {end_date}."
        )

    # Least cloudy scene first.
    items.sort(
        key=lambda item:
        item.properties.get(
            "eo:cloud_cover",
            100
        )
    )

    return items


# ---------------------------------------------------------------------
# Raster window reader
# ---------------------------------------------------------------------

def _read_window(
    href,
    left,
    bottom,
    right,
    top,
    target_shape=None,
    resampling=Resampling.nearest
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

        if target_shape is None:

            out_shape = (
                max(
                    1,
                    int(
                        round(
                            window.height
                        )
                    )
                ),
                max(
                    1,
                    int(
                        round(
                            window.width
                        )
                    )
                )
            )

        else:

            out_shape = target_shape

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            out_shape=out_shape,
            resampling=resampling
        ).astype(float)

        nodata = (
            src.nodata
            if src.nodata is not None
            else 0
        )

        transform = src.window_transform(
            window
        )

        crs = src.crs

    return (
        data,
        nodata,
        transform,
        crs
    )


# ---------------------------------------------------------------------
# Read exact polygon AOI
# ---------------------------------------------------------------------

def _read_aoi_data(
    image,
    geometry
):

    # ---------------------------------------------------------------
    # Polygon bounding box
    # ---------------------------------------------------------------

    left, bottom, right, top = bounds(
        geometry
    )

    # ---------------------------------------------------------------
    # B03 = Green, 10 m.
    #
    # B03 becomes our reference grid.
    # ---------------------------------------------------------------

    green, green_nodata, green_transform, green_crs = (
        _read_window(
            image.assets["B03"].href,
            left,
            bottom,
            right,
            top
        )
    )

    # ---------------------------------------------------------------
    # B11 = SWIR, native 20 m.
    #
    # Resample B11 to the B03 10 m grid.
    # Bilinear is used because reflectance is continuous.
    # ---------------------------------------------------------------

    swir, swir_nodata, swir_transform, swir_crs = (
        _read_window(
            image.assets["B11"].href,
            left,
            bottom,
            right,
            top,
            target_shape=green.shape,
            resampling=Resampling.bilinear
        )
    )

    # ---------------------------------------------------------------
    # Check shapes
    # ---------------------------------------------------------------

    if swir.shape != green.shape:

        raise ValueError(
            f"B03/B11 shape mismatch for "
            f"{image.id}: "
            f"{green.shape} vs {swir.shape}"
        )

    # ---------------------------------------------------------------
    # Transform exact polygon into raster CRS
    # ---------------------------------------------------------------

    polygon_raster = transform_geom(
        "EPSG:4326",
        green_crs,
        geometry
    )

    # ---------------------------------------------------------------
    # Exact polygon mask
    # ---------------------------------------------------------------

    inside_polygon = geometry_mask(
        [polygon_raster],
        out_shape=green.shape,
        transform=green_transform,
        invert=True
    )

    # ---------------------------------------------------------------
    # Basic valid-pixel mask
    # ---------------------------------------------------------------

    valid = (
        (green != green_nodata)
        &
        (swir != swir_nodata)
    )

    # Only pixels inside the exact polygon.
    valid &= inside_polygon

    # ---------------------------------------------------------------
    # SCL cloud/shadow masking
    # ---------------------------------------------------------------

    if "SCL" in image.assets:

        scl, _, _, _ = _read_window(
            image.assets["SCL"].href,
            left,
            bottom,
            right,
            top,
            target_shape=green.shape,
            resampling=Resampling.nearest
        )

        for code in SCL_EXCLUDE_VALUES:

            valid &= scl != code

    return (
        green,
        swir,
        valid,
        inside_polygon
    )


# ---------------------------------------------------------------------
# Yearly water analysis
# ---------------------------------------------------------------------

def calculate_yearly_water(
    latitude,
    longitude,
    geometry,
    year
):

    candidates = get_candidate_sentinel_images(
        geometry,
        year
    )

    last_error = None

    for image in candidates:

        try:

            (
                green,
                swir,
                valid,
                inside_polygon
            ) = _read_aoi_data(
                image,
                geometry
            )

        except Exception as error:

            last_error = error

            continue

        # -----------------------------------------------------------
        # Polygon pixels
        # -----------------------------------------------------------

        polygon_pixels = int(
            inside_polygon.sum()
        )

        if polygon_pixels == 0:

            last_error = ValueError(
                "Polygon does not overlap "
                "the satellite image."
            )

            continue

        # -----------------------------------------------------------
        # Valid coverage
        # -----------------------------------------------------------

        valid_fraction = (
            valid.sum()
            /
            polygon_pixels
        )

        if valid_fraction < MIN_VALID_PIXEL_FRACTION:

            last_error = ValueError(
                f"Only {valid_fraction:.0%} valid "
                f"pixels inside polygon for "
                f"{image.id}."
            )

            continue

        # -----------------------------------------------------------
        # Scale reflectance
        # -----------------------------------------------------------

        green_scaled = (
            green / SENTINEL2_SCALE
        )

        swir_scaled = (
            swir / SENTINEL2_SCALE
        )

        # -----------------------------------------------------------
        # MNDWI
        # -----------------------------------------------------------

        mndwi = calculate_mndwi(
            green_scaled,
            swir_scaled
        )

        mndwi_valid = np.where(
            valid,
            mndwi,
            np.nan
        )

        # -----------------------------------------------------------
        # Water classification
        #
        # MNDWI > 0
        # -----------------------------------------------------------

        water_pixels = (
            mndwi_valid
            >
            WATER_MNDWI_THRESHOLD
        )

        # -----------------------------------------------------------
        # Water percentage
        # -----------------------------------------------------------

        water_percentage = (
            np.nansum(
                water_pixels
            )
            /
            valid.sum()
        ) * 100

        # -----------------------------------------------------------
        # Average MNDWI
        # -----------------------------------------------------------

        average_mndwi = float(
            np.nanmean(
                mndwi_valid
            )
        )

        # -----------------------------------------------------------
        # Output
        # -----------------------------------------------------------

        print(
            f"\n========== {year} =========="
        )

        print(
            "Satellite image:",
            image.id
        )

        print(
            "Date:",
            image.datetime
        )

        print(
            "Scene cloud cover:",
            image.properties.get(
                "eo:cloud_cover"
            )
        )

        print(
            "Exact polygon pixels:",
            polygon_pixels
        )

        print(
            "Valid polygon pixels:",
            int(valid.sum())
        )

        print(
            f"Valid polygon coverage: "
            f"{valid_fraction:.0%}"
        )

        print(
            f"Water coverage: "
            f"{water_percentage:.2f}%"
        )

        print(
            f"Average MNDWI: "
            f"{average_mndwi:.3f}"
        )

        return {
            "year": year,
            "water_percentage": water_percentage,
            "average_mndwi": average_mndwi,
            "image_id": image.id,
            "image_date": str(
                image.datetime
            ),
            "cloud_cover": image.properties.get(
                "eo:cloud_cover"
            ),
            "valid_pixel_fraction": valid_fraction
        }

    raise ValueError(
        f"No scene for {year} had enough "
        f"valid coverage inside the exact "
        f"polygon "
        f"(last error: {last_error})"
    )


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

    latitude = location[
        "latitude"
    ]

    longitude = location[
        "longitude"
    ]

    geometry = location[
        "geometry"
    ]

    print("\nLocation found:")

    print(
        location["name"]
    )

    print(
        "Latitude:",
        latitude
    )

    print(
        "Longitude:",
        longitude
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

            result = calculate_yearly_water(
                latitude=latitude,
                longitude=longitude,
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

    # ---------------------------------------------------------------
    # Trend
    # ---------------------------------------------------------------

    print(
        "\n\n=============================="
    )

    print(
        f"WATER TREND "
        f"{start_year}-{end_year}"
    )

    print(
        "=============================="
    )

    for result in results:

        print(
            f"{result['year']} : "
            f"{result['water_percentage']:.2f}%"
        )

    # ---------------------------------------------------------------
    # Overall change
    # ---------------------------------------------------------------

    if len(results) >= 2:

        first = results[0][
            "water_percentage"
        ]

        last = results[-1][
            "water_percentage"
        ]

        change = last - first

        print(
            "\nOverall change:"
        )

        print(
            f"{change:+.2f} "
            f"percentage points"
        )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()