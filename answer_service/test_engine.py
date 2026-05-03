from llm_engine import evaluate_answer
from scoring import compute_cognitive_score

question = "Tell me about a challenge you faced in a team."

answer = """
In my college project team, we had a conflict regarding task division.
I took initiative to understand everyone's strengths and redistributed work.
I also scheduled daily short meetings to track progress.
Finally, we completed the project before deadline and got good feedback.
"""

scores = evaluate_answer(question, answer)

cognitive_score = compute_cognitive_score(scores)

print("Dimension Scores:", scores)
print("Cognitive Score:", cognitive_score)