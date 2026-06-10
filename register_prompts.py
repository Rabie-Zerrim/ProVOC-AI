from langfuse import Langfuse
import config
from prompts import (
    REVIEW_INTERACTION_PROMPT,
    FINAL_REPORT_PROMPT,
)


def register_all_prompts() -> None:
    client = Langfuse(
        secret_key=config.LANGFUSE_SECRET_KEY,
        public_key=config.LANGFUSE_PUBLIC_KEY,
        host=config.LANGFUSE_HOST,
    )

    prompts_to_register = [
        ("review-interaction", REVIEW_INTERACTION_PROMPT),
        ("final-report", FINAL_REPORT_PROMPT),
    ]

    for name, content in prompts_to_register:
        client.create_prompt(
            name=name,
            prompt=content,
            labels=["production"],
        )
        print(f"Registered prompt: {name}")

    print("All prompts registered successfully.")


if __name__ == "__main__":
    register_all_prompts()
