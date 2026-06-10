import logging

import config

logger = logging.getLogger(__name__)

_client = None


def get_langfuse_client():
    global _client
    if _client is not None:
        return _client
    if not config.LANGFUSE_SECRET_KEY or not config.LANGFUSE_PUBLIC_KEY:
        logger.warning("Langfuse credentials not set — prompt management disabled")
        return None
    try:
        from langfuse import Langfuse
        _client = Langfuse(
            secret_key=config.LANGFUSE_SECRET_KEY,
            public_key=config.LANGFUSE_PUBLIC_KEY,
            host=config.LANGFUSE_HOST,
        )
        logger.info("Langfuse client initialized")
        return _client
    except Exception as e:
        logger.warning(f"Langfuse init failed: {e} — using hardcoded prompts")
        return None


def get_prompt(prompt_name: str, fallback: str) -> str:
    client = get_langfuse_client()
    if client is None:
        return fallback
    try:
        prompt = client.get_prompt(prompt_name, fallback=fallback, type="text")
        return prompt.compile()
    except Exception as e:
        logger.warning(f"Failed to fetch prompt '{prompt_name}' from Langfuse: {e} — using fallback")
        return fallback
