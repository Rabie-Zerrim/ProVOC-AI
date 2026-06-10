import os
import subprocess
from pathlib import Path


class AudioProcessingError(Exception):
    pass


class UnsupportedFormatError(AudioProcessingError):
    pass


class FFmpegError(AudioProcessingError):
    pass


class AudioProcessor:
    """Preprocessing pipeline: validate format, convert to 16 kHz mono WAV, trim silence."""

    ALLOWED_EXTENSIONS: list[str] = [
        ".wav", ".mp3", ".webm", ".ogg", ".m4a", ".mp4", ".flac"
    ]

    def validate_audio_type(self, file_path: str, content_type: str) -> bool:
        """Check that the file extension is in ALLOWED_EXTENSIONS.

        Raises UnsupportedFormatError if the extension is not recognised.
        The content_type parameter is accepted for interface compatibility
        but the decision is based solely on the file extension.
        """
        ext = Path(file_path).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise UnsupportedFormatError(
                f"Unsupported audio format '{ext}'. "
                f"Allowed extensions: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )
        return True

    def convert_to_wav(self, input_path: str, output_path: str) -> str:
        """Convert any supported audio file to 16 kHz mono WAV via ffmpeg.

        Raises FFmpegError when ffmpeg exits with a non-zero return code.
        """
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ar", "16000",
                "-ac", "1",
                output_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise FFmpegError(f"ffmpeg conversion failed: {result.stderr}")
        return output_path

    def trim_silence(self, input_path: str, output_path: str) -> str:
        """Remove leading silence from the audio file using the silenceremove filter.

        Raises FFmpegError when ffmpeg exits with a non-zero return code.
        """
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-af", "silenceremove=1:0:-50dB",
                output_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise FFmpegError(f"ffmpeg silence removal failed: {result.stderr}")
        return output_path

    def process(self, input_path: str) -> str:
        """Run the full pipeline: validate → convert to WAV → trim silence.

        Returns the path to the processed WAV file.
        The intermediate converted file is deleted in the finally block
        regardless of whether trimming succeeded or failed.
        """
        self.validate_audio_type(input_path, "")
        base = os.path.splitext(input_path)[0]
        converted_path = f"{base}_converted.wav"
        trimmed_path = f"{base}_processed.wav"
        try:
            self.convert_to_wav(input_path, converted_path)
            self.trim_silence(converted_path, trimmed_path)
            return trimmed_path
        finally:
            if os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                except OSError:
                    pass
