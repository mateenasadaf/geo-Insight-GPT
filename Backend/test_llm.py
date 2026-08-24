from llm.planner import understand_question


question = input("Ask Geo-Insight GPT: ")

result = understand_question(question)

print("\nLLM PLAN:")
print(result)