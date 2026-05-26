#!/usr/bin/env python3
"""
Quick smoke test: send a sample transcript through the Groq/Llama pipeline
and print the raw output so you can judge quality before any further work.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from prompts import REVIEW_ANALYSIS_PROMPT

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL    = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

SAMPLE_TRANSCRIPT = (
    "I went to Bella Italia last night with my family. The pasta was absolutely "
    "amazing, really fresh and full of flavor. The service was a bit slow — we "
    "waited almost 30 minutes for our mains — but the staff were friendly and "
    "apologized. Prices are a little high for the portion sizes but overall it "
    "was a great evening. I'd give it maybe 4 out of 5 stars."
)

LISTING_CONTEXT = {
    "business_name": "Bella Italia",
    "network_names": ["Yelp", "Google"],
    "network_preferences": {"Yelp": "detailed", "Google": "concise"},
}


def build_system_prompt(ctx: dict, language: str) -> str:
    lang_name = {"en": "English", "fr": "French", "es": "Spanish"}.get(language, language)
    return (
        REVIEW_ANALYSIS_PROMPT
        + f"\n\nBUSINESS CONTEXT:\n"
        f"- Business Name: {ctx['business_name']}\n"
        f"- Social Networks: {', '.join(ctx['network_names'])}\n"
        f"- Network Preferences: {ctx['network_preferences']}\n"
        f"\nUSER LANGUAGE: {lang_name} — ALL your responses must be in {lang_name}.\n"
    )


def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set in .env")
        return

    client = Groq(api_key=GROQ_API_KEY)
    system_prompt = build_system_prompt(LISTING_CONTEXT, "en")

    print(f"Model  : {LLM_MODEL}")
    print(f"Input  : {SAMPLE_TRANSCRIPT}\n")
    print("=" * 60)
    print("STEP 1 — Initial analysis (start_session call)")
    print("=" * 60)

    r1 = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": SAMPLE_TRANSCRIPT},
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    step1_out = r1.choices[0].message.content
    print(step1_out)

    print("\n" + "=" * 60)
    print("STEP 2 — Approve / final JSON (approve call)")
    print("=" * 60)

    approval_prompt = (
        'Based on the conversation history, return ONLY a valid JSON object '
        '(no markdown, no explanation) with this exact structure:\n'
        '{\n'
        '  "improved_text": "The polished review text",\n'
        '  "rating": 4,\n'
        '  "sentiment": "Positive",\n'
        '  "tone": "Enthusiastic",\n'
        '  "key_points": ["Great service", "Good food", "Fair price"]\n'
        '}\n'
        'sentiment must be exactly one of: "Positive", "Negative", "Neutral"\n'
        'rating must be an integer between 1 and 5.'
    )

    r2 = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system",    "content": system_prompt},
            {"role": "assistant", "content": step1_out},
            {"role": "user",      "content": approval_prompt},
        ],
        temperature=0.2,
        max_tokens=512,
    )
    print(r2.choices[0].message.content)


if __name__ == "__main__":
    main()
