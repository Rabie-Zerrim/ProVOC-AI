from __future__ import annotations

import json

import groq as groq_lib

import config


class LLMError(Exception):
    pass


class ModelUnavailableError(LLMError):
    pass


class LLMAgent:
    """Centralised LLM agent that transparently falls back to a smaller model.

    Primary model is read from config at class-definition time so that a
    single env-var change at startup is enough to switch models.
    """

    PRIMARY_MODEL: str = config.LLM_MODEL
    FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    _instance: LLMAgent | None = None

    def __init__(self) -> None:
        self._client = groq_lib.Groq(api_key=config.GROQ_API_KEY)

    @classmethod
    def get_instance(cls) -> LLMAgent:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Call the LLM and return the response content string.

        Tries PRIMARY_MODEL first; on groq.APIError falls back to
        FALLBACK_MODEL. Raises ModelUnavailableError when both fail.
        """
        primary_exc: Exception | None = None
        for idx, model in enumerate((self.PRIMARY_MODEL, self.FALLBACK_MODEL)):
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            try:
                response = self._client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except groq_lib.APIError as exc:
                if idx == 0:
                    # Primary model failed — try fallback
                    primary_exc = exc
                    continue
                raise ModelUnavailableError(
                    f"Both models unavailable. "
                    f"Primary ({self.PRIMARY_MODEL}): {primary_exc}; "
                    f"Fallback ({self.FALLBACK_MODEL}): {exc}"
                ) from exc
        raise ModelUnavailableError("All models exhausted")

    def analyze_review(self, review_text: str, platform: str) -> dict:
        """Analyse a review text and return a structured dict.

        The model is asked to return JSON with keys:
        sentiment, rating, key_points, summary.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a review analysis expert. "
                    "Analyse the given review and return a JSON object with keys: "
                    "sentiment, rating, key_points, summary."
                ),
            },
            {
                "role": "user",
                "content": f"Analyse this {platform} review:\n{review_text}",
            },
        ]
        raw = self.complete(messages, response_format={"type": "json_object"})
        return json.loads(raw)

    def generate_review(self, transcript: str, tone: str, platform: str) -> str:
        """Generate a review text from a spoken transcript.

        Args:
            transcript: Raw transcription of the user's voice note.
            tone: Desired tone, e.g. "Firm", "Polite", "Neutral".
            platform: Target platform, e.g. "Yelp", "Google".

        Returns:
            The generated review as a plain string.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a review writer. "
                    f"Generate a {tone} review suitable for {platform} "
                    f"based on the transcript provided."
                ),
            },
            {"role": "user", "content": transcript},
        ]
        return self.complete(messages)
