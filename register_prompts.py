from langfuse import Langfuse
import config
from prompts import (
    _REVIEW_ANALYSIS_PROMPT_FALLBACK,
    _REVIEW_INTERACTION_PROMPT_FALLBACK,
    _FINAL_REPORT_PROMPT_FALLBACK,
)


def register_all_prompts():
    client = Langfuse(
        secret_key=config.LANGFUSE_SECRET_KEY,
        public_key=config.LANGFUSE_PUBLIC_KEY,
        host=config.LANGFUSE_HOST,
    )
    for name, content in [
        ("system-prompt", _REVIEW_ANALYSIS_PROMPT_FALLBACK),
        ("review-interaction", _REVIEW_INTERACTION_PROMPT_FALLBACK),
        ("final-report", _FINAL_REPORT_PROMPT_FALLBACK),
    ]:
        client.create_prompt(name=name, prompt=content, labels=["production"])
        print(f"Registered: {name}")


if __name__ == "__main__":
    register_all_prompts()
