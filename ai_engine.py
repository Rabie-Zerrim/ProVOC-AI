import json

import groq as _groq_module
from groq import Groq

from config import GROQ_API_KEY, LLM_MODEL

client = Groq(api_key=GROQ_API_KEY)


async def extract_review_insights(transcription: str) -> str:
    """Analyse a transcribed review and return structured insights as a JSON string."""
    prompt = f"""
    Analyze the following user review transcription and extract structured insights:
    Review: "{transcription}"

    Return ONLY a JSON object with:
    - entities: List of key entities (names, locations, dishes, services)
    - keywords: Top 5 descriptive adjectives or nouns
    - sentiment: Score from 0 to 1
    - category: "positive", "negative", or "neutral"
    - summarized_text: A concise 2-sentence version of the review
    """

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except _groq_module.APIError as e:
        print(f"Groq API error: {e}")
        return json.dumps({
            "entities": [],
            "keywords": [],
            "sentiment": 0.5,
            "category": "neutral",
            "summarized_text": transcription[:100]
        })
