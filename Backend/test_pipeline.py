from llm.planner import understand_question
from llm.reporter import generate_report
from analysis_engine import run_analysis


question = input(
    "Ask Geo-Insight GPT: "
)

print("\nUnderstanding question...")

plan = understand_question(question)

print("\nLLM PLAN:")
print(plan)


print("\nRunning satellite analysis...")

results = run_analysis(plan)

print("\nREAL SATELLITE RESULTS:")
print(results)


print("\nGenerating final report...")

answer = generate_report(
    question,
    plan,
    results
)

print("\n==============================")
print("GEO-INSIGHT GPT REPORT")
print("==============================\n")

print(answer)