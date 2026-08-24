from location import get_coordinates
from analysis.vegetation import calculate_yearly_vegetation


def run_analysis(plan):

    location_name = plan["location"]
    analysis_types = plan["analysis"]

    start_year = plan.get("start_year")
    end_year = plan.get("end_year")

    if start_year is None or end_year is None:
        raise ValueError(
            "Start year and end year are required."
        )

    location = get_coordinates(location_name)

    latitude = location["latitude"]
    longitude = location["longitude"]

    results = {
        "location": location_name,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude
        },
        "period": {
            "start_year": start_year,
            "end_year": end_year
        },
        "analyses": {}
    }

    if "vegetation" in analysis_types:

        vegetation_results = []

        for year in range(start_year, end_year + 1):

            try:

                result = calculate_yearly_vegetation(
                    latitude=latitude,
                    longitude=longitude,
                    year=year
                )

                vegetation_results.append(result)

            except Exception as error:

                vegetation_results.append({
                    "year": year,
                    "error": str(error)
                })

        results["analyses"]["vegetation"] = vegetation_results

    return results