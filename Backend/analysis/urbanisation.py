"""
Urbanisation analysis using Sentinel-2 imagery from Microsoft
Planetary Computer.

Method:
    NDBI = (SWIR - NIR) / (SWIR + NIR)

Built-up pixels are identified using:
    NDBI >= 0
    AND
    NDVI < 0.2

The analysis is restricted to the exact Polygon/MultiPolygon
returned by location.py.

Sentinel-2 bands:
    B08 -> NIR  (10 m)
    B11 -> SWIR (20 m)
    B04 -> Red  (10 m)
    SCL -> Scene Classification Layer

CHANGES FROM ORIGINAL VERSION
------------------------------
1. Scene search now uses a bbox derived from the polygon's own
   bounds (+ small buffer), not a fixed 0.1-degree box around the
   centroid. The old approach could miss scenes, or fail to fully
   cover the AOI, whenever the polygon was larger than ~11 km
   across (e.g. a city or district boundary).

2. Scene search is now restricted to a fixed month window
   (SEASON_START_MONTH -> SEASON_END_MONTH) applied every year,
   instead of searching the full calendar year. Comparing the
   single least-cloudy image of an entire year across multiple
   years introduces seasonal bias into NDVI/NDBI (e.g. a June
   image one year vs a December image the next), which can make
   "built-up %" swing for reasons that have nothing to do with
   urbanisation. Adjust SEASON_START_MONTH/SEASON_END_MONTH below
   to a window that is dry/leaf-off or otherwise consistent for
   your region.

3. B04 (red) and B11 (SWIR) are now resampled with bilinear
   interpolation onto the B08 10 m grid, instead of nearest
   neighbour. Nearest neighbour produces blocky artifacts in NDBI
   when upsampling the 20 m SWIR band. SCL (a categorical/label
   band) still uses nearest neighbour, which is correct for it.
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

# Buffer (degrees) added around the polygon's own bounding box when
# searching for candidate scenes. This just needs to be large enough
# to comfortably guarantee full scene coverage of the AOI edges; it
# is no longer used as the sole basis of the search area.
SEARCH_BUFFER_DEG = 0.02

MAX_SCENE_CLOUD_COVER = 20

MIN_VALID_PIXEL_FRACTION = 0.5

# NDBI threshold for potential built-up pixels
NDBI_BUILTUP_THRESHOLD = 0.0

# NDVI safeguard:
# vegetation with high NDVI should not be classified as built-up.
NDVI_VEGETATION_THRESHOLD = 0.2

SENTINEL2_SCALE = 10000.0

# Fixed seasonal search window, applied to every year in the trend.
# Keeping this consistent year-to-year avoids comparing e.g. a wet
# season image in one year to a dry season image in another, which
# would otherwise show up as spurious change in built-up coverage.
# ADJUST THESE to a low-cloud, phenologically stable window for the
# region under study.
SEASON_START_MONTH = 1
SEASON_END_MONTH = 3


# Sentinel-2 SCL values to exclude
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
# Index calculations
# ---------------------------------------------------------------------

def calculate_ndvi(red, nir):

    denominator = nir + red

    return np.divide(
        nir - red,
        denominator,
        out=np.full_like(
            denominator,
            np.nan,
            dtype=float
        ),
        where=denominator != 0
    )


def calculate_ndbi(nir, swir):

    denominator = swir + nir

    return np.divide(
        swir - nir,
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
    # Bbox derived from the polygon's own bounds, not a fixed box
    # around a single point. This guarantees the search area always
    # covers the full AOI, regardless of how large the polygon is.
    # -------------------------------------------------------------

    left, bottom, right, top = bounds(geometry)

    bbox = [
        left - SEARCH_BUFFER_DEG,
        bottom - SEARCH_BUFFER_DEG,
        right + SEARCH_BUFFER_DEG,
        top + SEARCH_BUFFER_DEG
    ]

    # -------------------------------------------------------------
    # Fixed seasonal window, applied every year, to keep the trend
    # comparable across years.
    # -------------------------------------------------------------

    start_date = f"{year}-{season_start_month:02d}-01"

    if season_end_month == 12:

        end_date = f"{year + 1}-01-01"

    else:

        end_date = f"{year}-{season_end_month + 1:02d}-01"

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

    items = list(search.items())

    if not items:

        raise ValueError(
            f"No suitable satellite image found for {year} "
            f"in the window {start_date} to {end_date}."
        )

    items.sort(
        key=lambda item:
        item.properties.get(
            "eo:cloud_cover",
            100
        )
    )

    return items


# ---------------------------------------------------------------------
# Read raster window
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

    with rasterio.open(href) as src:

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
                    int(round(window.height))
                ),
                max(
                    1,
                    int(round(window.width))
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
    # Read B08 first.
    #
    # B08 is 10 m and becomes our reference grid.
    # ---------------------------------------------------------------

    nir, nir_nodata, nir_transform, nir_crs = _read_window(
        image.assets["B08"].href,
        left,
        bottom,
        right,
        top
    )

    # ---------------------------------------------------------------
    # Read B04 onto the B08 grid.
    #
    # Bilinear resampling is used because reflectance is a
    # continuous quantity; nearest neighbour is only appropriate
    # for categorical bands like SCL.
    # ---------------------------------------------------------------

    red, red_nodata, red_transform, red_crs = _read_window(
        image.assets["B04"].href,
        left,
        bottom,
        right,
        top,
        target_shape=nir.shape,
        resampling=Resampling.bilinear
    )

    # ---------------------------------------------------------------
    # Read B11.
    #
    # B11 is native 20 m, so it is upsampled onto B08's 10 m grid.
    # Bilinear resampling avoids the blocky artifacts nearest
    # neighbour would introduce into NDBI.
    # ---------------------------------------------------------------

    swir, swir_nodata, swir_transform, swir_crs = _read_window(
        image.assets["B11"].href,
        left,
        bottom,
        right,
        top,
        target_shape=nir.shape,
        resampling=Resampling.bilinear
    )

    # ---------------------------------------------------------------
    # Check shapes
    # ---------------------------------------------------------------

    if red.shape != nir.shape:

        raise ValueError(
            f"B04/B08 shape mismatch for "
            f"{image.id}: "
            f"{red.shape} vs {nir.shape}"
        )

    if swir.shape != nir.shape:

        raise ValueError(
            f"B11/B08 shape mismatch for "
            f"{image.id}: "
            f"{swir.shape} vs {nir.shape}"
        )

    # ---------------------------------------------------------------
    # Transform exact polygon into raster CRS
    # ---------------------------------------------------------------

    polygon_raster = transform_geom(
        "EPSG:4326",
        nir_crs,
        geometry
    )

    # ---------------------------------------------------------------
    # Exact polygon mask
    # ---------------------------------------------------------------

    inside_polygon = geometry_mask(
        [polygon_raster],
        out_shape=nir.shape,
        transform=nir_transform,
        invert=True
    )

    # ---------------------------------------------------------------
    # Basic valid-pixel mask
    #
    # Note: bilinear resampling can produce values very close to,
    # but not exactly equal to, nodata at the edges of nodata
    # regions, so this equality check is a coarse first pass;
    # the SCL mask below is the primary quality filter.
    # ---------------------------------------------------------------

    valid = (
        (nir != nir_nodata)
        &
        (red != red_nodata)
        &
        (swir != swir_nodata)
    )

    # Only pixels inside the exact location
    valid &= inside_polygon

    # ---------------------------------------------------------------
    # SCL masking
    # ---------------------------------------------------------------

    if "SCL" in image.assets:

        scl, _, _, _ = _read_window(
            image.assets["SCL"].href,
            left,
            bottom,
            right,
            top,
            target_shape=nir.shape,
            resampling=Resampling.nearest
        )

        for code in SCL_EXCLUDE_VALUES:

            valid &= scl != code

    return (
        red,
        nir,
        swir,
        valid,
        inside_polygon
    )


# ---------------------------------------------------------------------
# Yearly urbanisation analysis
# ---------------------------------------------------------------------

def calculate_yearly_urbanisation(
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
                red,
                nir,
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
        # Check polygon coverage
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
        # Valid pixel fraction
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
        # Scale Sentinel-2 reflectance
        # -----------------------------------------------------------

        red_scaled = (
            red / SENTINEL2_SCALE
        )

        nir_scaled = (
            nir / SENTINEL2_SCALE
        )

        swir_scaled = (
            swir / SENTINEL2_SCALE
        )

        # -----------------------------------------------------------
        # Calculate indices
        # -----------------------------------------------------------

        ndvi = calculate_ndvi(
            red_scaled,
            nir_scaled
        )

        ndbi = calculate_ndbi(
            nir_scaled,
            swir_scaled
        )

        # -----------------------------------------------------------
        # Apply valid-pixel mask
        # -----------------------------------------------------------

        ndvi_valid = np.where(
            valid,
            ndvi,
            np.nan
        )

        ndbi_valid = np.where(
            valid,
            ndbi,
            np.nan
        )

        # -----------------------------------------------------------
        # Built-up classification
        #
        # NDBI >= 0
        # AND
        # NDVI < 0.2
        # -----------------------------------------------------------

        builtup_pixels = (
            (ndbi_valid >= NDBI_BUILTUP_THRESHOLD)
            &
            (ndvi_valid < NDVI_VEGETATION_THRESHOLD)
        )

        # -----------------------------------------------------------
        # Calculate percentages
        # -----------------------------------------------------------

        builtup_percentage = (
            np.nansum(
                builtup_pixels
            )
            /
            valid.sum()
        ) * 100

        average_ndbi = float(
            np.nanmean(
                ndbi_valid
            )
        )

        average_ndvi = float(
            np.nanmean(
                ndvi_valid
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
            f"Built-up coverage: "
            f"{builtup_percentage:.2f}%"
        )

        print(
            f"Average NDBI: "
            f"{average_ndbi:.3f}"
        )

        print(
            f"Average NDVI: "
            f"{average_ndvi:.3f}"
        )

        return {
            "year": year,
            "builtup_percentage": builtup_percentage,
            "average_ndbi": average_ndbi,
            "average_ndvi": average_ndvi,
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

    latitude = location["latitude"]

    longitude = location["longitude"]

    geometry = location["geometry"]

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

            result = calculate_yearly_urbanisation(
                latitude=latitude,
                longitude=longitude,
                geometry=geometry,
                year=year
            )

            results.append(result)

        except Exception as error:

            print(
                f"Could not analyze "
                f"{year}: {error}"
            )

    print(
        "\n\n=============================="
    )

    print(
        f"URBANISATION TREND "
        f"{start_year}-{end_year}"
    )

    print(
        "=============================="
    )

    for result in results:

        print(
            f"{result['year']} : "
            f"{result['builtup_percentage']:.2f}%"
        )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()