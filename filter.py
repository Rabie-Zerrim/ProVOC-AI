import json

from fastapi import APIRouter, Depends
from groq import Groq
from pydantic import BaseModel

from auth import get_current_user
from config import GROQ_API_KEY, LLM_MODEL
from langfuse_client import get_prompt
from prompts import _FILTER_PROMPT_FALLBACK

router = APIRouter(prefix="/api/chat", tags=["chat"])
_groq = Groq(api_key=GROQ_API_KEY)


class FilterRequest(BaseModel):
    text: str


@router.post("/filter")
async def filter_text(
    body: FilterRequest,
    user_id: str = Depends(get_current_user),
):
    filter_prompt = get_prompt("chat-filter", _FILTER_PROMPT_FALLBACK)
    prompt = filter_prompt.replace("{text}", body.text)
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
