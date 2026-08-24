import os
from google import genai


client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def generate_report(question, plan, satellite_results):

    prompt = f"""
You are Geo-Insight GPT, a geographic analysis assistant.

The user asked:

{question}

The question was interpreted as:

{plan}

Below are REAL satellite-analysis results calculated
from Sentinel-2 imagery:

{satellite_results}

Your job is to explain these results clearly.

IMPORTANT RULES:

1. Use ONLY the supplied satellite results for numerical claims.
2. Do NOT invent values, dates, satellite images, or trends.
3. Explain what NDVI and vegetation coverage mean when useful.
4. Compare the years provided in the data.
5. Mention the selected observation dates when relevant.
6. If the final year is incomplete, explicitly mention that.
7. Distinguish between vegetation coverage and average NDVI.
8. Explain major increases or decreases visible in the data.
9. Do not claim that satellite data proves the cause of a change.
10. If the data is insufficient to answer part of the question,
    clearly say so.

Give the answer in a clear report format:

## Summary

Brief overall finding.

## Year-by-Year Analysis

Explain the important changes across the years.

## Trend

Describe the overall trend using the supplied numbers.

## Important Note

Mention limitations such as observation dates,
partial years, or differences in satellite observations.

Keep the explanation understandable to a normal user,
but make it technically accurate.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    return response.text