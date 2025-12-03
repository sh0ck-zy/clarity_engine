import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

COPILOT_SYSTEM_PROMPT = """
You are the CLARITY CO-PILOT, a senior data scientist and sports betting analyst assisting a user in tuning an AI prediction system.

YOUR CONTEXT:
You have access to:
1. The Real Match Result (Score, xG).
2. The 'Active' Analysis (The one being debugged).
3. The 'Comparison' Analysis (An older version or different prompt).

YOUR GOAL:
Help the user understand WHY the model succeeded or failed.
Suggest specific improvements to the Prompt or the Logic weights.
If asked, provide Python code snippets or specific text to paste into the Prompt file.

TONE:
Professional, analytical, concise, and helpful. Treat this as a code review session.
"""


class ClarityCopilot:
    """Lightweight wrapper around OpenAI chat for the comparator view."""

    def __init__(self) -> None:
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def chat(self, messages, context_data):
        """
        messages: List of {"role": "user" | "assistant", "content": "..."}
        context_data: Dict containing match info, analysis_a, analysis_b
        """
        # Keep context compact to preserve tokens; indent aids readability during debugging.
        context_str = json.dumps(context_data, indent=2)
        system_message = {
            "role": "system",
            "content": f"{COPILOT_SYSTEM_PROMPT}\n\nCURRENT DATA CONTEXT:\n{context_str}",
        }

        full_history = [system_message] + messages

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", messages=full_history, temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as exc:  # pragma: no cover - defensive
            return f"❌ Copilot Error: {str(exc)}"
