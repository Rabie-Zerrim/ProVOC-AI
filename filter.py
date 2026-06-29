import json

from fastapi import APIRouter, Depends
from groq import Groq
from pydantic import BaseModel

from auth import get_current_user
from config import GROQ_API_KEY, LLM_MODEL

router = APIRouter(prefix="/api/chat", tags=["chat"])
_groq = Groq(api_key=GROQ_API_KEY)

_FILTER_PROMPT = (
    'You are a content moderation assistant. Analyze the following review text and classify it.\n'
    'Return ONLY a JSON object with no extra text, no markdown, no backticks:\n'
    '- If the text contains profanity, hate speech, slurs, or discriminatory language:\n'
    '  {"result": "block", "reason": "inappropriate_content"}\n'
    '- If the text is aggressive, hostile, or excessively negative in tone but contains no slurs:\n'
    '  {"result": "warn", "suggestion": "Consider rephrasing in a more constructive way"}\n'
    '- If the text is acceptable:\n'
    '  {"result": "ok"}\n\n'
    'Review text:\n'
    '"""{text}"""'
)


class FilterRequest(BaseModel):
    text: str


@router.post("/filter")
async def filter_text(
    body: FilterRequest,
    user_id: str = Depends(get_current_user),
):
    prompt = _FILTER_PROMPT.format(text=body.text)
    try:
        response = _groq.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content.strip())
    except Exception:
        return {"approved": True}

    result = data.get("result", "ok")
    if result == "block":
        return {"approved": False, "reason": "inappropriate_content"}
    if result == "warn":
        return {
            "approved": True,
            "warning": "tone_aggressive",
            "suggestion": data.get("suggestion", "Consider rephrasing in a more constructive way"),
        }
    return {"approved": True}
