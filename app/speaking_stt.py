"""Offline speech-to-text for the Speaking page (Vosk, no cloud)."""

from __future__ import annotations

import io
import json
import wave
import zipfile
from pathlib import Path

import httpx
from django.conf import settings

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_DIR = Path(settings.BASE_DIR) / "data" / MODEL_NAME

_model = None


def vosk_installed() -> bool:
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    return True


def model_ready() -> bool:
    return MODEL_DIR.is_dir() and any(MODEL_DIR.iterdir())


def ensure_model() -> Path:
    if model_ready():
        return MODEL_DIR

    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    zip_path = MODEL_DIR.parent / f"{MODEL_NAME}.zip"

    with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with zip_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(MODEL_DIR.parent)

    zip_path.unlink(missing_ok=True)

    if not model_ready():
        raise RuntimeError("Speech model download failed.")

    return MODEL_DIR


def _get_model():
    global _model
    if _model is None:
        from vosk import Model

        _model = Model(str(ensure_model()))
    return _model


def transcribe_wav(wav_bytes: bytes) -> str:
    if not vosk_installed():
        raise RuntimeError("Speech recognition is not installed. Run: pip install vosk")

    from vosk import KaldiRecognizer

    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        if handle.getnchannels() != 1:
            raise ValueError("Audio must be mono.")
        if handle.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit PCM.")
        sample_rate = handle.getframerate()
        recognizer = KaldiRecognizer(_get_model(), sample_rate)
        recognizer.SetWords(False)
        while True:
            chunk = handle.readframes(4000)
            if not chunk:
                break
            recognizer.AcceptWaveform(chunk)
        result = json.loads(recognizer.FinalResult())

    return str(result.get("text", "")).strip()
