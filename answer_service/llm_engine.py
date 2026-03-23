import os
import json
from dotenv import load_dotenv
from groq import Groq
from answer_service.prompt import SYSTEM_PROMPT, build_prompt

load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY", "")
)
def evaluate_answer(question: str, answer: str):

    user_prompt = build_prompt(question, answer)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    output_text = response.choices[0].message.content

    try:
        scores = json.loads(output_text)
        return scores
    except:
        return {
            "error": "Parsing failed",
            "raw_output": output_text
        }