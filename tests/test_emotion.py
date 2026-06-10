"""Tests for audio.emotion — EmotionRecognizer."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from audio.emotion import EmotionRecognizer, AudioLoadError


def _fresh_recognizer() -> EmotionRecognizer:
    """Return a new EmotionRecognizer with cleared singleton state."""
    EmotionRecognizer._instance = None
    return EmotionRecognizer()


def test_predict_returns_dict() -> None:
    """predict() should return a dict with emotion, confidence, all_scores keys."""
    recognizer = _fresh_recognizer()

    # Simulate a loaded pipeline that returns classification scores
    mock_pipeline = MagicMock(return_value=[
        {"label": "happy", "score": 0.87},
        {"label": "sad", "score": 0.05},
        {"label": "angry", "score": 0.08},
    ])
    recognizer.model = mock_pipeline
    recognizer._initialized = True
    recognizer._failed = False

    result = recognizer.predict("fake_audio.wav")

    assert isinstance(result, dict)
    assert result["emotion"] == "happy"
    assert abs(result["confidence"] - 0.87) < 0.001
    assert "all_scores" in result
    assert "happy" in result["all_scores"]


def test_predict_fallback_on_missing_file() -> None:
    """predict() should return neutral fallback when the model failed to load."""
    recognizer = _fresh_recognizer()
    recognizer._failed = True  # simulate a prior model load failure

    result = recognizer.predict("/nonexistent/audio.wav")

    assert result == {"emotion": "neutral", "confidence": 0.0, "all_scores": {}}


def test_singleton_returns_same_instance() -> None:
    """get_instance() must return the exact same object on repeated calls."""
    EmotionRecognizer._instance = None

    first = EmotionRecognizer.get_instance()
    second = EmotionRecognizer.get_instance()

    assert first is second
