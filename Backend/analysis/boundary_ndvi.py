import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

import numpy as np
import rasterio
import pystac_client
import planetary_computer

from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom, reproject
from rasterio.features import geometry_mask
from rasterio.enums import Resampling

from boundary import get_boundary


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

NDVI_THRESHOLD = 0.3
SCALE = 10000.0

MAX_SCENE_CLOUD_COVER = 20      # %, coarse scene-level pre-filter
MIN_VALID_PIXEL_FRACTION = 0.5  # require at least this fraction of the
                                 # boundary to be valid after masking,
                                 # or fall back to the next scene

# Sentinel-2 Scene Classification Layer (SCL) codes to exclude:
# 0 = no data, 1 = saturated/defective, 3 = cloud shadow,
# 8/9 = cloud medium/high probability, 10 = thin cirrus, 11 = snow/ice
SCL_EXCLUDE = {0, 1, 3, 8, 9, 10, 11}


def get_candidate_images(boundary, year):
    """Return the year's scenes sorted from lowest to highest
    scene-level cloud cover. This is only a coarse pre-filter --
    per-pixel validity over the actual boundary is checked separately,
    since scene-level cloud cover describes the whole tile, not the
    boundary itself."""
    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace
    )

    minx, miny, maxx, maxy = boundary.bounds

    search = catalog.search(
        collections=[COLLECTION],
        bbox=[minx, miny, maxx, maxy],
        datetime=f"{year}-01-01/{year + 1}-01-01",
        query={"eo:cloud_cover": {"lt": MAX_SCENE_CLOUD_COVER}},
    )

    images = list(search.items())
    if not images:
        raise ValueError(f"No Sentinel-2 image found for {year}")

    images.sort(key=lambda image: image.properties.get("eo:cloud_cover", 100))
    return images


def read_band(href, boundary):
    """Read a band windowed to the boundary's bounding box, at the
    band's own native resolution.

    Returns the array, its EXACT transform (computed from a rounded
    window, so it matches the returned array pixel-for-pixel), the
    raster's CRS, and its nodata value.
    """
    with rasterio.open(href) as src:
        minx, miny, maxx, maxy = boundary.bounds

        bounds = transform_bounds("EPSG:4326", src.crs, minx, miny, maxx, maxy)
        window = from_bounds(*bounds, transform=src.transform)

        # Round to whole pixels BEFORE reading. A fractional window
        # gets rounded internally by rasterio when the array is read,
        # but the transform we compute afterwards needs to be based on
        # that SAME rounded window, or the array and its transform
        # silently drift apart by a fraction of a pixel.
        window = window.round_offsets(op="floor").round_lengths(op="ceil")

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
        ).astype(float)

        transform = src.window_transform(window)
        crs = src.crs
        nodata = src.nodata if src.nodata is not None else 0

    return data, transform, crs, nodata


def read_scl_aligned(href, dst_transform, dst_shape, dst_crs):
    """Reproject SCL directly onto the same pixel grid as red/NIR.

    SCL is natively 20 m while B04/B08 are 10 m. Reading it separately
    with its own window + out_shape + boundless (the previous
    approach) does not guarantee the result lands on the exact same
    grid as red/NIR -- it can produce an array that LOOKS the right
    shape but doesn't correspond pixel-for-pixel to red/NIR. That's
    what was causing ~99% of pixels to be masked out even on a scene
    with ~0% reported cloud cover: the mask was being compared against
    the wrong pixels, not against real cloud/shadow pixels.

    reproject() takes an explicit destination transform/CRS/shape, so
    there's no ambiguity about which source pixel maps to which
    destination pixel.
    """
    with rasterio.open(href) as src:
        dst = np.zeros(dst_shape, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
        )
    return dst


def analyze_boundary(location_name, year):
    boundary = get_boundary(location_name)
    candidates = get_candidate_images(boundary, year)

    last_error = None

    for image in candidates:
        print("\nSelected satellite image:")
        print("ID:", image.id)
        print("Date:", image.datetime)
        print("Cloud cover:", image.properties.get("eo:cloud_cover"))

        try:
            red, red_transform, red_crs, red_nodata = read_band(
                image.assets["B04"].href, boundary
            )
            nir, nir_transform, nir_crs, nir_nodata = read_band(
                image.assets["B08"].href, boundary
            )

            print("\nBand shapes:")
            print("Red:", red.shape)
            print("NIR:", nir.shape)

            if red.shape != nir.shape:
                raise ValueError(
                    f"B04/B08 shape mismatch: {red.shape} vs {nir.shape}"
                )

            if red_crs != nir_crs:
                raise ValueError(
                    f"B04/B08 CRS mismatch: {red_crs} vs {nir_crs}"
                )

            # Affine transforms are floats under the hood. B04/B08 share
            # the same grid in practice, but compare with a tolerance
            # rather than strict `!=` so floating-point noise can't
            # trigger a false failure.
            if not red_transform.almost_equals(nir_transform, precision=1e-6):
                raise ValueError(
                    "B04 and B08 are not on the same pixel grid: "
                    f"{red_transform} vs {nir_transform}"
                )

            boundary_projected = transform_geom(
                "EPSG:4326", red_crs, boundary.__geo_interface__
            )

            inside_boundary = geometry_mask(
                [boundary_projected],
                out_shape=red.shape,
                transform=red_transform,
                invert=True,
            )

            boundary_pixel_count = int(np.sum(inside_boundary))
            print("\nBoundary mask:")
            print("Pixels inside boundary:", boundary_pixel_count)

            if boundary_pixel_count == 0:
                raise ValueError("Boundary mask produced zero pixels.")

            scl = read_scl_aligned(
                image.assets["SCL"].href,
                dst_transform=red_transform,
                dst_shape=red.shape,
                dst_crs=red_crs,
            )

            valid = (
                inside_boundary
                & (red != red_nodata)
                & (nir != nir_nodata)
            )
            for code in SCL_EXCLUDE:
                valid &= scl != code

            valid_pixel_count = int(np.sum(valid))
            valid_fraction = valid_pixel_count / boundary_pixel_count

            print("Valid pixels after SCL masking:", valid_pixel_count)
            print(f"Valid fraction of boundary: {valid_fraction:.1%}")

            if valid_fraction < MIN_VALID_PIXEL_FRACTION:
                raise ValueError(
                    f"Only {valid_fraction:.1%} of the boundary is valid "
                    f"after masking (need >= {MIN_VALID_PIXEL_FRACTION:.0%})"
                )

        except Exception as error:
            print(f"Skipping {image.id}: {error}")
            last_error = error
            continue

        # ------------------------------------------------------------
        # A usable scene was found -- compute NDVI
        # ------------------------------------------------------------
        red_scaled = red / SCALE
        nir_scaled = nir / SCALE

        denominator = nir_scaled + red_scaled
        ndvi = np.divide(
            nir_scaled - red_scaled,
            denominator,
            out=np.full_like(denominator, np.nan, dtype=float),
            where=denominator != 0,
        )
        ndvi[~valid] = np.nan

        vegetation_pixels = ndvi > NDVI_THRESHOLD
        vegetation_pixel_count = int(np.nansum(vegetation_pixels))
        vegetation_percentage = (vegetation_pixel_count / valid_pixel_count) * 100
        average_ndvi = float(np.nanmean(ndvi))

        print("\n================================")
        print("BOUNDARY-BASED VEGETATION")
        print("================================")
        print("Location:", location_name)
        print("Year:", year)
        print("Image ID:", image.id)
        print("Valid pixels:", valid_pixel_count)
        print("Vegetation pixels:", vegetation_pixel_count)
        print(f"Vegetation coverage: {vegetation_percentage:.2f}%")
        print(f"Average NDVI: {average_ndvi:.3f}")
        print(f"NDVI minimum: {np.nanmin(ndvi):.3f}")
        print(f"NDVI maximum: {np.nanmax(ndvi):.3f}")

        return {
            "location": location_name,
            "year": year,
            "image_id": image.id,
            "cloud_cover": image.properties.get("eo:cloud_cover"),
            "boundary_pixels": boundary_pixel_count,
            "valid_pixels": valid_pixel_count,
            "valid_pixel_fraction": valid_fraction,
            "vegetation_pixels": vegetation_pixel_count,
            "vegetation_percentage": vegetation_percentage,
            "average_ndvi": average_ndvi,
            "ndvi_min": float(np.nanmin(ndvi)),
            "ndvi_max": float(np.nanmax(ndvi)),
        }

    raise ValueError(
        f"No scene for {year} had enough valid boundary coverage "
        f"(last error: {last_error})"
    )


if __name__ == "__main__":

    location = "Bengaluru"

    for year in range(2020, 2027):

        print("\n\n")
        print("########################################")
        print(f"ANALYZING {location} - {year}")
        print("########################################")

        try:
            result = analyze_boundary(
                location_name=location,
                year=year
            )

            print("\nYEAR RESULT")
            print(
                f"{year}: "
                f"{result['vegetation_percentage']:.2f}% vegetation | "
                f"NDVI: {result['average_ndvi']:.3f}"
            )

        except Exception as error:

            print(
                f"\nCould not analyze {year}: {error}"
            )