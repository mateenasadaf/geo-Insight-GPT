from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import json
import traceback
import threading
import queue

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


# ============================================================
# NORMAL ENDPOINT
# ============================================================

@app.post("/ask")
def ask_question(question: str):

    try:

        # 1. Understand question
        plan = understand_question(
            question
        )

        # 2. Run satellite analysis
        results = run_analysis(
            plan
        )

        # 3. Generate AI report
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

        print("\n===== ERROR =====")
        traceback.print_exc()
        print("=================\n")

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# STREAMING ENDPOINT
# ============================================================

@app.post("/ask/stream")
def ask_question_stream(question: str):

    # --------------------------------------------------------
    # Queue used to transfer progress events from the
    # background analysis thread to the SSE response.
    # --------------------------------------------------------

    event_queue = queue.Queue()

    # Sentinel value used to tell the streaming loop
    # that the background worker has finished.
    DONE = object()

    # --------------------------------------------------------
    # Background worker
    # --------------------------------------------------------

    def run_backend():

        try:

            # ------------------------------------------------
            # 1. Understand question
            # ------------------------------------------------

            event_queue.put({
                "type": "status",
                "message":
                    "Understanding your geographic question..."
            })

            plan = understand_question(
                question
            )

            # ------------------------------------------------
            # 2. Start satellite analysis
            # ------------------------------------------------

            event_queue.put({
                "type": "status",
                "message":
                    "Starting satellite analysis..."
            })

            # ------------------------------------------------
            # Progress callback
            # ------------------------------------------------

            def progress_callback(
                event_type,
                message,
                year=None,
                analysis=None,
                total=None,
                completed=None
            ):

                event_queue.put({
                    "type": event_type,
                    "message": message,
                    "year": year,
                    "analysis": analysis,
                    "total": total,
                    "completed": completed
                })

            # ------------------------------------------------
            # Run actual analysis
            # ------------------------------------------------

            results = run_analysis(
                plan,
                progress_callback=progress_callback
            )

            # ------------------------------------------------
            # 3. Generate report
            # ------------------------------------------------

            event_queue.put({
                "type": "status",
                "message":
                    "Generating geographic report..."
            })

            report = generate_report(
                question,
                plan,
                results
            )

            # ------------------------------------------------
            # 4. Final result
            # ------------------------------------------------

            final_result = {
                "question": question,
                "plan": plan,
                "results": results,
                "report": report
            }

            event_queue.put({
                "type": "complete",
                "result": final_result
            })

        except Exception as error:

            print(
                "\n===== STREAMING ERROR ====="
            )

            traceback.print_exc()

            print(
                "===========================\n"
            )

            event_queue.put({
                "type": "error",
                "message": str(error)
            })

        finally:

            # Tell SSE stream that the worker is finished.
            event_queue.put(DONE)

    # --------------------------------------------------------
    # Start backend processing in background
    # --------------------------------------------------------

    worker = threading.Thread(
        target=run_backend,
        daemon=True
    )

    worker.start()

    # --------------------------------------------------------
    # SSE generator
    # --------------------------------------------------------

    def event_stream():

        while True:

            event = event_queue.get()

            # -----------------------------------------------
            # Background worker finished
            # -----------------------------------------------

            if event is DONE:

                break

            # -----------------------------------------------
            # Convert event to SSE format
            # -----------------------------------------------

            event_type = event.get(
                "type",
                "status"
            )

            data = {
                key: value
                for key, value in event.items()
                if key != "type"
            }

            yield (
                f"event: {event_type}\n"
                f"data: {json.dumps(data)}\n\n"
            )

    # --------------------------------------------------------
    # Return live SSE stream
    # --------------------------------------------------------

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no-cache"
        }
    )