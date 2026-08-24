import osmnx as ox


def get_boundary(location_name):

    print(f"Searching boundary for: {location_name}")

    # Try the user's exact query first
    queries = [
        location_name,
        f"{location_name}, India"
    ]

    last_error = None

    for query in queries:

        try:
            print(f"Trying: {query}")

            gdf = ox.geocode_to_gdf(query)

            if gdf.empty:
                print("No result found.")
                continue

            # Find a polygon/multipolygon result
            polygon_rows = gdf[
                gdf.geometry.geom_type.isin(
                    ["Polygon", "MultiPolygon"]
                )
            ]

            if polygon_rows.empty:
                print(
                    f"No Polygon/MultiPolygon found for: {query}"
                )
                continue

            # Use the first valid polygon result
            boundary = polygon_rows.geometry.iloc[0]

            print("\nLocation:")
            print(polygon_rows.name.iloc[0])

            print("\nGeometry type:")
            print(boundary.geom_type)

            print("\nArea bounds:")
            print(boundary.bounds)

            return boundary

        except Exception as e:
            print(f"Error while searching {query}: {e}")
            last_error = e

    raise ValueError(
        f"Could not find a valid geographic boundary for "
        f"'{location_name}'."
    ) from last_error


if __name__ == "__main__":

    location = input(
        "Enter city, state or country: "
    )

    boundary = get_boundary(location)

    print("\nActual boundary obtained successfully!")

    print("Minimum longitude:", boundary.bounds[0])
    print("Minimum latitude:", boundary.bounds[1])
    print("Maximum longitude:", boundary.bounds[2])
    print("Maximum latitude:", boundary.bounds[3])

    print("\nNumber of boundary points:")

    if boundary.geom_type == "Polygon":

        print(len(boundary.exterior.coords))

    elif boundary.geom_type == "MultiPolygon":

        print(
            sum(
                len(polygon.exterior.coords)
                for polygon in boundary.geoms
            )
        )