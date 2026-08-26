from google import genai
from dotenv import load_dotenv
import os
import json
from datetime import datetime

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def understand_question(question):

    current_year = datetime.now().year

    prompt = f"""
You are the planning component of Geo-Insight GPT.

Analyze the user's geographic question and extract the required information.

Extract:

1. location
2. analysis types
3. start year
4. end year

Possible analysis types:
- vegetation
- development
- water
- agriculture
- disaster
- environment
- complete_report

RULES:

LOCATION:
- Extract the geographic location mentioned by the user.
- It can be ANY city, district, state, country, region, etc.
- Do not assume Bengaluru or any other specific location.

ANALYSIS:
- Vegetation questions → ["vegetation"]
- Development/urbanization questions → ["development"]
- Water questions → ["water"]
- Agriculture/crop questions → ["agriculture"]
- Disaster questions → ["disaster"]
- General environmental questions → ["environment"]
- Broad questions such as "How has Mumbai changed?" → ["complete_report"]

YEARS:

1. "from 2010 to 2020"
   → start_year = 2010
   → end_year = 2020

2. "between 2015 and 2023"
   → start_year = 2015
   → end_year = 2023

3. "since 2015"
   → start_year = 2015
   → end_year = {current_year}

4. "in the last 5 years"
   → start_year = {current_year - 5}
   → end_year = {current_year}

5. "over the past 10 years"
   → start_year = {current_year - 10}
   → end_year = {current_year}

6. If the user explicitly provides years, ALWAYS use those exact years.

7. If the user does not mention any time period:
   → start_year = null
   → end_year = null

Do NOT assume 2020 or 2026 when the user does not provide a time period.

Current year: {current_year}

User question:
{question}

Return ONLY valid JSON.

Use exactly this structure:

{{
    "location": "",
    "analysis": [],
    "start_year": null,
    "end_year": null
}}
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    result = response.text.strip()

    # Remove markdown code fences if Gemini returns them
    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    return json.loads(result)