"""Tests for audio.processor — AudioProcessor."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from audio.processor import AudioProcessor, UnsupportedFormatError


def test_validate_accepts_wav() -> None:
    """validate_audio_type() should return True for a .wav file."""
    processor = AudioProcessor()
    result = processor.validate_audio_type("recording.wav", "audio/wav")
    assert result is True


def test_validate_rejects_unknown_extension() -> None:
    """validate_audio_type() should raise UnsupportedFormatError for .txt files."""
    processor = AudioProcessor()
    with pytest.raises(UnsupportedFormatError):
        processor.validate_audio_type("notes.txt", "text/plain")


def test_unsupported_format_raises_error() -> None:
    """UnsupportedFormatError is raised for every extension not in ALLOWED_EXTENSIONS."""
    processor = AudioProcessor()
    unsupported = [".txt", ".pdf", ".zip", ".avi", ".exe"]
    for ext in unsupported:
        with pytest.raises(UnsupportedFormatError, match="Unsupported audio format"):
            processor.validate_audio_type(f"file{ext}", "application/octet-stream")
