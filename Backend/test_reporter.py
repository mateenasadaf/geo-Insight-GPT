from llm.reporter import generate_report


question = (
    "How has vegetation changed in Bengaluru "
    "from 2020 to 2026?"
)

plan = {
    "location": "Bengaluru",
    "analysis": ["vegetation"],
    "start_year": 2020,
    "end_year": 2026
}

satellite_results = {
    "2020": {
        "vegetation_percentage": 34.14,
        "average_ndvi": 0.261
    },
    "2021": {
        "vegetation_percentage": 40.04,
        "average_ndvi": 0.287
    },
    "2022": {
        "vegetation_percentage": 17.34,
        "average_ndvi": 0.179
    },
    "2023": {
        "vegetation_percentage": 19.26,
        "average_ndvi": 0.183
    },
    "2024": {
        "vegetation_percentage": 9.75,
        "average_ndvi": 0.154
    },
    "2025": {
        "vegetation_percentage": 29.76,
        "average_ndvi": 0.208
    },
    "2026": {
        "vegetation_percentage": 12.53,
        "average_ndvi": 0.155
    }
}


answer = generate_report(
    question,
    plan,
    satellite_results
)

print("\n==============================")
print("GEO-INSIGHT GPT REPORT")
print("==============================\n")

print(answer)