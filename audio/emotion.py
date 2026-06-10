from __future__ import annotations


class EmotionModelError(Exception):
    pass


class AudioLoadError(Exception):
    pass


class EmotionRecognizer:
    """Speech Emotion Recognition using wav2vec2-lg-xlsr.

    The HuggingFace pipeline is loaded lazily on first call to predict()
    and reused for all subsequent calls via the singleton pattern.
    """

    _instance: EmotionRecognizer | None = None

    def __init__(self) -> None:
        self._initialized: bool = False
        self.model = None
        self.processor = None
        self._failed: bool = False
        try:
            self._load_model()
            self._initialized = True
        except Exception:
            self._initialized = False

    @classmethod
    def get_instance(cls) -> EmotionRecognizer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self) -> None:
        """Load the emotion classification pipeline on first use."""
        if self.model is not None or self._failed:
            return
        try:
            from transformers import pipeline  # type: ignore
            self.model = pipeline(
                "audio-classification",
                model="ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",
                framework="pt",
            )
            self._initialized = True
        except Exception as exc:
            self._failed = True
            raise EmotionModelError(f"Failed to load emotion model: {exc}") from exc

    def predict(self, audio_path: str) -> dict:
        """Return emotion prediction for the given audio file.

        Returns a neutral result with zero confidence when the model
        failed to load, rather than propagating the load error.
        """
        try:
            self._load_model()
        except EmotionModelError:
            return {"emotion": "neutral", "confidence": 0.0, "all_scores": {}}

        if self._failed:
            return {"emotion": "neutral", "confidence": 0.0, "all_scores": {}}

        try:
            results: list[dict] = self.model(audio_path, top_k=None)
            all_scores = {r["label"]: round(float(r["score"]), 4) for r in results}
            top = max(results, key=lambda x: x["score"])
            return {
                "emotion": top["label"],
                "confidence": round(float(top["score"]), 4),
                "all_scores": all_scores,
            }
        except Exception as exc:
            raise AudioLoadError(
                f"Failed to process audio at '{audio_path}': {exc}"
            ) from exc
