"""
Vegetation trend analysis using Sentinel-2 imagery from Microsoft
Planetary Computer.

Key improvements over the original version:
- Per-pixel cloud/shadow/snow masking using the Scene Classification
  Layer (SCL) band. Scene-level `eo:cloud_cover` describes the whole
  ~110x110 km tile, not the small area of interest (AOI) actually
  being analyzed, so a "clear" scene can still have a cloudy AOI.
- If the chosen scene turns out to have too few valid AOI pixels
  after masking, automatically fall back to the next-cleanest scene
  for that year instead of silently reporting bad numbers.
- Boundless, nodata-aware windowed reads so requests near a tile
  edge don't crash.
- Shape-consistency check between the red and NIR arrays.
- Results are written to CSV in addition to being printed.
- Division-by-zero guard on the percentage-change calculation.
- Flags when the final year in the range is a partial year.
"""
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from rasterio.enums import Resampling
# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

SEARCH_BUFFER_DEG = 0.1      # area to search for candidate scenes
ANALYSIS_BUFFER_DEG = 0.05   # area actually analyzed (the AOI)

MAX_SCENE_CLOUD_COVER = 20       # %, coarse scene-level pre-filter
MIN_VALID_PIXEL_FRACTION = 0.5   # require at least this fraction of
                                  # the AOI to be clear/valid after
                                  # per-pixel masking, or try the next
                                  # scene
NDVI_VEGETATION_THRESHOLD = 0.3

# Sentinel-2 Scene Classification Layer (SCL) codes to exclude:
# 0 = no data, 1 = saturated/defective, 3 = cloud shadow,
# 8/9 = cloud medium/high probability, 10 = thin cirrus, 11 = snow/ice
SCL_EXCLUDE_VALUES = {0, 1, 3, 8, 9, 10, 11}

SENTINEL2_SCALE = 10000.0


def calculate_ndvi(red, nir):
    denominator = nir + red
    return np.divide(
        nir - red,
        denominator,
        out=np.full_like(denominator, np.nan, dtype=float),
        where=denominator != 0,
    )


def get_candidate_sentinel_images(latitude, longitude, year, buffer_deg=SEARCH_BUFFER_DEG):
    """Return the year's scenes sorted from lowest to highest
    scene-level cloud cover. This is only a coarse pre-filter --
    per-pixel validity over the actual AOI is checked separately."""
    catalog = pystac_client.Client.open(
        STAC_URL, modifier=planetary_computer.sign_inplace
    )

    bbox = [
        longitude - buffer_deg,
        latitude - buffer_deg,
        longitude + buffer_deg,
        latitude + buffer_deg,
    ]

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{year}-01-01/{year + 1}-01-01",
        query={"eo:cloud_cover": {"lt": MAX_SCENE_CLOUD_COVER}},
    )

    items = list(search.items())
    if not items:
        raise ValueError(f"No suitable satellite image found for {year}.")

    items.sort(key=lambda item: item.properties.get("eo:cloud_cover", 100))
    return items


def _read_window(href, left, bottom, right, top):
    """Windowed read that is safe near tile edges and returns the
    scene's nodata value so callers can mask it out."""
    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, left, bottom, right, top)
        window = from_bounds(*bounds, transform=src.transform)
        out_shape = (
            max(1, int(round(window.height))),
            max(1, int(round(window.width))),
        )
        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            out_shape=out_shape,
            resampling=Resampling.nearest,
        ).astype(float)
        nodata = src.nodata if src.nodata is not None else 0
    return data, nodata


def _read_aoi_bands(image, left, bottom, right, top):
    """Read red, NIR, and SCL bands for the AOI and build a validity
    mask that excludes nodata, cloud, cloud shadow, cirrus, and snow
    pixels."""
    red, red_nodata = _read_window(image.assets["B04"].href, left, bottom, right, top)
    nir, nir_nodata = _read_window(image.assets["B08"].href, left, bottom, right, top)

    if red.shape != nir.shape:
        raise ValueError(
            f"Red/NIR shape mismatch for {image.id}: {red.shape} vs {nir.shape}"
        )

    valid = (red != red_nodata) & (nir != nir_nodata)

    if "SCL" in image.assets:
        scl, _ = _read_window(image.assets["SCL"].href, left, bottom, right, top)
        if scl.shape == red.shape:
            for code in SCL_EXCLUDE_VALUES:
                valid &= scl != code
        # If SCL comes back at a different resolution/shape, skip the
        # mask rather than fail the whole analysis for that scene.

    return red, nir, valid


def calculate_yearly_vegetation(latitude, longitude, year):
    candidates = get_candidate_sentinel_images(latitude, longitude, year)

    left = longitude - ANALYSIS_BUFFER_DEG
    bottom = latitude - ANALYSIS_BUFFER_DEG
    right = longitude + ANALYSIS_BUFFER_DEG
    top = latitude + ANALYSIS_BUFFER_DEG

    last_error = None

    for image in candidates:
        try:
            red, nir, valid = _read_aoi_bands(image, left, bottom, right, top)
        except Exception as error:  # corrupt/missing asset -> try next scene
            last_error = error
            continue

        if valid.size == 0:
            last_error = ValueError("Empty AOI window.")
            continue

        valid_fraction = valid.sum() / valid.size
        if valid_fraction < MIN_VALID_PIXEL_FRACTION:
            # The scene-level cloud cover looked fine, but the AOI
            # itself is too cloudy/empty. Try the next cleanest scene.
            last_error = ValueError(
                f"Only {valid_fraction:.0%} valid pixels in AOI for {image.id}."
            )
            continue

        red_scaled = red / SENTINEL2_SCALE
        nir_scaled = nir / SENTINEL2_SCALE

        ndvi = calculate_ndvi(red_scaled, nir_scaled)
        ndvi_valid = np.where(valid, ndvi, np.nan)

        vegetation_pixels = ndvi_valid > NDVI_VEGETATION_THRESHOLD
        vegetation_percentage = (np.nansum(vegetation_pixels) / valid.sum()) * 100
        average_ndvi = float(np.nanmean(ndvi_valid))

        print(f"\n========== {year} ==========")
        print("Satellite image:", image.id)
        print("Date:", image.datetime)
        print("Scene cloud cover:", image.properties.get("eo:cloud_cover"))
        print(f"Valid AOI pixels: {valid_fraction:.0%}")
        print(f"Vegetation coverage: {vegetation_percentage:.2f}%")
        print(f"Average NDVI: {average_ndvi:.3f}")

        return {
            "year": year,
            "vegetation_percentage": vegetation_percentage,
            "average_ndvi": average_ndvi,
            "image_id": image.id,
            "image_date": str(image.datetime),
            "cloud_cover": image.properties.get("eo:cloud_cover"),
            "valid_pixel_fraction": valid_fraction,
        }

    raise ValueError(
        f"No scene for {year} had enough cloud-free AOI coverage "
        f"(last error: {last_error})"
    )


def save_results_csv(results, path):
    if not results:
        return
    fieldnames = list(results[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main():
    from location import get_coordinates

    location_name = input("Enter location: ")
    start_year = int(input("Enter start year: "))
    end_year = int(input("Enter end year: "))

    location = get_coordinates(location_name)

    latitude = location["latitude"]
    longitude = location["longitude"]

    print("\nLocation found:")
    print(location["name"])
    print("Latitude:", latitude)
    print("Longitude:", longitude)

    results = []
    for year in range(start_year, end_year + 1):
        try:
            results.append(calculate_yearly_vegetation(latitude, longitude, year))
        except Exception as error:
            print(f"Could not analyze {year}: {error}")

    print("\n\n==============================")
    print(f"VEGETATION TREND {start_year}-{end_year}")
    print("==============================")
    for result in results:
        print(f"{result['year']} : {result['vegetation_percentage']:.2f}%")

    if len(results) >= 2:
        first = results[0]["vegetation_percentage"]
        last = results[-1]["vegetation_percentage"]
        change = last - first

        print("\nOverall change:")
        print(f"{change:+.2f} percentage points")

        if first != 0:
            print(f"{(change / first) * 100:+.2f}%")
        else:
            print("Percentage change undefined (starting value was 0%).")

        if change > 0:
            print("Trend: Vegetation increased.")
        elif change < 0:
            print("Trend: Vegetation decreased.")
        else:
            print("Trend: Vegetation remained stable.")

    output_path = Path("vegetation_trend_results.csv")
    save_results_csv(results, output_path)
    print(f"\nResults saved to {output_path}")

    import datetime
    if results and results[-1]["year"] == datetime.date.today().year:
        print(
            f"\nNote: {results[-1]['year']} only covers through the current "
            "date, so it isn't a like-for-like comparison with full prior years."
        )


if __name__ == "__main__":
    main()
