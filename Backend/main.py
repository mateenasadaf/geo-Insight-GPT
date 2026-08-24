from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from llm.planner import understand_question
from llm.reporter import generate_report
from analysis_engine import run_analysis


app = FastAPI(title="Geo-Insight GPT API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Geo-Insight GPT Backend Running"
    }


@app.post("/ask")
def ask_question(question: str):

    try:

        # -----------------------------
        # 1. Understand the question
        # -----------------------------

        plan = understand_question(question)

        # -----------------------------
        # 2. Run real satellite analysis
        # -----------------------------

        results = run_analysis(plan)

        # -----------------------------
        # 3. Generate AI report
        # -----------------------------

        report = generate_report(
            question,
            plan,
            results
        )

        return {
            "question": question,
            "plan": plan,
            "results": results,
            "report": report
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )