# 🌍 Geo-Insight GPT

**Geo-Insight GPT** is an AI-powered geospatial analysis system that combines **Large Language Models (LLMs), satellite imagery, remote sensing, and machine learning** to analyze environmental and urban changes over time and predict future trends.

Users can ask questions in natural language, such as:

> *"How has vegetation changed in Bengaluru from 2020 to 2025?"*

The system identifies the location, analysis factor, and time period, processes **Sentinel-2 satellite imagery**, calculates remote-sensing indices, and presents the results through explanations, graphs, and tables.

---

## 🎯 Objectives

* Analyze historical changes in **vegetation, water, and urbanisation**.
* Use **NDVI, MNDWI, and NDBI** to derive satellite-based measurements.
* Automate satellite-data processing through natural-language queries.
* Predict future changes using **machine-learning models**.
* Visualize historical and predicted trends through graphs.
* Generate understandable explanations using an **LLM**.

---

## ✨ Key Features

### 🌿 Vegetation Analysis

Uses **NDVI (Normalized Difference Vegetation Index)** to analyze vegetation.

* Vegetation coverage
* Average NDVI
* Year-wise analysis
* Historical trend visualization

### 💧 Water Analysis

Uses **MNDWI (Modified Normalized Difference Water Index)** to identify water-related changes.

* Water coverage
* Average MNDWI
* Year-wise analysis
* Historical trend visualization

### 🏙️ Urbanisation Analysis

Uses **NDBI (Normalized Difference Built-up Index)** to analyze built-up areas.

* Built-up coverage
* Average NDBI
* Year-wise analysis
* Urbanisation trends

### 🔮 Future Prediction

The prediction module extends the existing historical analysis by using historical satellite-derived measurements to estimate future trends.

The planned prediction pipeline uses:

**Random Forest Regression** with **Linear Regression as a baseline**.

Predictions will be provided for:

* Vegetation
* Water
* Urbanisation

The frontend will display **historical observations together with future predictions**.

---

## 🛰️ Satellite Data

The project uses **Sentinel-2 Level-2A satellite imagery** accessed through the **Microsoft Planetary Computer**.

### Spectral Indices

| Factor       | Index | Sentinel-2 Bands        |
| ------------ | ----- | ----------------------- |
| Vegetation   | NDVI  | B04 (Red), B08 (NIR)    |
| Water        | MNDWI | B03 (Green), B11 (SWIR) |
| Urbanisation | NDBI  | B08 (NIR), B11 (SWIR)   |

### Formulas

**NDVI**

```text
NDVI = (B08 - B04) / (B08 + B04)
```

**MNDWI**

```text
MNDWI = (B03 - B11) / (B03 + B11)
```

**NDBI**

```text
NDBI = (B11 - B08) / (B11 + B08)
```

---

## ☁️ SCL-Based Cloud Masking

The system uses the **SCL (Scene Classification Layer)** provided with Sentinel-2 Level-2A imagery.

SCL is used to identify and remove:

* Clouds
* Cloud shadows
* Cirrus
* Invalid/unclassified pixels
* Other unsuitable pixels

This helps ensure that spectral-index calculations are performed using valid pixels.

---

## 🏗️ System Architecture

```text
                 USER
                   │
                   ▼
          Next.js Frontend
                   │
                   ▼
             FastAPI Backend
                   │
                   ▼
              LLM Planner
                   │
          ┌────────┴────────┐
          │                 │
     Historical         Prediction
       Analysis            Mode
          │                 │
          ▼                 ▼
    Satellite Data     Historical Data
          │                 │
          ▼                 ▼
  NDVI / MNDWI / NDBI   ML Prediction
          │                 │
          └────────┬────────┘
                   ▼
              LLM Reporter
                   │
                   ▼
              Frontend UI
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        Answer   Graphs    Tables
```

---

## 📂 Project Structure

```text
Geo-Insight-GPT/
│
├── backend/
│   ├── main.py
│   ├── analysis_engine.py
│   ├── location.py
│   ├── boundary.py
│   ├── requirements.txt
│   ├── .env
│   │
│   ├── analysis/
│   │   ├── vegetation.py
│   │   ├── water.py
│   │   └── urbanisation.py
│   │
│   ├── llm/
│   │   ├── planner.py
│   │   └── reporter.py
│   │
│   ├── test_llm.py
│   └── test_pipeline.py
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   └── globals.css
│   │
│   └── package.json
│
└── .gitignore
```

---

## 🔧 Technology Stack

### Backend

* **Python**
* **FastAPI**
* **Uvicorn**
* **Rasterio**
* **NumPy**
* **PySTAC Client**
* **Planetary Computer**
* **GeoPandas / geospatial libraries**

### AI / LLM

* **LLM-based question planning**
* **LLM-based report generation**
* **OpenRouter / Gemini integration**

### Remote Sensing

* **Sentinel-2 Level-2A**
* **NDVI**
* **MNDWI**
* **NDBI**
* **SCL masking**

### Machine Learning

* **Scikit-learn**
* **Random Forest Regression**
* **Linear Regression baseline**

### Frontend

* **Next.js**
* **React**
* **TypeScript**
* **CSS**
* Interactive graphs and tables

---

## 🔄 How It Works

### 1. User asks a question

```text
"How has vegetation changed in Bengaluru
from 2020 to 2025?"
```

### 2. LLM Planner

Extracts:

```text
Location → Bengaluru
Factor   → Vegetation
Start    → 2020
End      → 2025
Intent   → Historical analysis
```

### 3. Location Processing

The location is converted into geographic information required for satellite analysis.

### 4. Satellite Data Retrieval

Suitable Sentinel-2 imagery is retrieved from the Microsoft Planetary Computer.

### 5. Preprocessing

```text
Satellite imagery
       ↓
SCL layer
       ↓
Cloud/invalid pixel masking
       ↓
Valid pixels
```

### 6. Index Calculation

The appropriate index is calculated:

```text
Vegetation → NDVI
Water → MNDWI
Urbanisation → NDBI
```

### 7. Historical Analysis

The system generates year-wise measurements.

### 8. Future Prediction

For prediction queries:

```text
Historical measurements
        ↓
Feature preparation
        ↓
ML model
        ↓
Future predicted values
```

### 9. LLM Explanation

The LLM receives the calculated results and generates a natural-language explanation.

### 10. Frontend

The user receives:

* AI explanation
* Metrics
* Historical values
* Predicted values
* Graphs
* Tables

---

## 🚀 Running the Backend

Create and activate a virtual environment:

```bash
python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start FastAPI:

```bash
uvicorn main:app --reload
```

The backend will run locally on:

```text
http://127.0.0.1:8000
```

---

## 🚀 Running the Frontend

Navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will then be available through the local Next.js development server.

---

## 🔐 Environment Variables

API keys should be stored in `.env` rather than directly inside source code.

Example:

```text
OPENROUTER_API_KEY=your_api_key
```

The `.env` file should **not be committed to GitHub**.

---

## 📊 Example Queries

### Historical Analysis

```text
How has vegetation changed in Bengaluru from 2020 to 2025?
```

```text
How has water changed in Kolkata from 2021 to 2025?
```

```text
How has urbanisation changed in Mumbai from 2020 to 2025?
```

### Future Prediction

```text
What is likely to happen to vegetation in Bengaluru
over the next 3 years?
```

```text
Predict urbanisation in Bengaluru for the next 5 years.
```

```text
Will water coverage increase or decrease in this area?
```

### Combined Analysis

```text
How has vegetation changed from 2020 to 2025
and what is likely to happen over the next 3 years?
```

---

## ⚠️ Limitations

* Satellite observations represent selected observations rather than continuous ground measurements.
* Seasonal differences can affect comparisons between years.
* Future predictions are **model-based estimates**, not guaranteed outcomes.
* Prediction reliability depends on the amount and quality of historical data.
* Satellite-derived trends do not by themselves establish causality.

---

## 🔮 Future Scope

* Improve prediction accuracy using additional temporal observations.
* Incorporate external geographic and environmental variables.
* Improve model validation and uncertainty estimation.
* Optimize satellite-data processing performance.
* Expand interactive prediction visualizations.
* Improve real-time processing and progress reporting.

---

## 📌 Current Project Scope

The current Geo-Insight GPT system focuses on:

```text
🌿 Vegetation
💧 Water
🏙️ Urbanisation
```

with both:

```text
Historical Analysis
        +
Future Prediction
```

The prediction feature is an **extension of the existing satellite-analysis pipeline**, not a replacement for it.

<img width="1130" height="786" alt="Screenshot 2026-08-26 124801" src="https://github.com/user-attachments/assets/e311bc3b-ffdf-46b0-a218-589429c3c811" />
<img width="970" height="636" alt="Screenshot 2026-08-26 124809" src="https://github.com/user-attachments/assets/22941919-7151-4a33-83cb-27ad3e7548d9" />


<img width="945" height="730" alt="Screenshot 2026-08-26 124821" src="https://github.com/user-attachments/assets/48f2033d-13fd-4723-b7f6-19da3e329222" />

