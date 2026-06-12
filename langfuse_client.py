from langfuse import Langfuse
import config
import logging

logger = logging.getLogger(__name__)
_client: Langfuse | None = None


def get_langfuse_client() -> Langfuse | None:
    global _client
    if _client is not None:
        return _client
    if not config.LANGFUSE_SECRET_KEY or not config.LANGFUSE_PUBLIC_KEY:
        logger.warning("Langfuse credentials not set")
        return None
    try:
        _client = Langfuse(
            secret_key=config.LANGFUSE_SECRET_KEY,
            public_key=config.LANGFUSE_PUBLIC_KEY,
            host=config.LANGFUSE_HOST,
        )
        return _client
    except Exception as e:
        logger.warning(f"Langfuse init failed: {e}")
        return None


def get_prompt(prompt_name: str, fallback: str) -> str:
    client = get_langfuse_client()
    if client is None:
        return fallback
    try:
        prompt = client.get_prompt(prompt_name)
        return prompt.compile()
    except Exception as e:
        logger.warning(f"Failed to fetch prompt '{prompt_name}': {e}")
        return fallback
