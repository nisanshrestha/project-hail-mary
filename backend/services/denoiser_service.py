"""Meta Denoiser wrapper for combat noise suppression.

Uses facebook/denoiser (DNS64 pretrained model) to strip gunfire,
explosions, and ambient battlefield noise from voice recordings,
isolating the combat medic's speech for reliable STT.

Falls back to passthrough if denoiser/torch is unavailable.
"""

from __future__ import annotations

import io
import logging
import struct
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_denoiser_model = None
_denoiser_available = False

SAMPLE_RATE = 16_000


def _load_model():
    global _denoiser_model, _denoiser_available
    try:
        import torch
        from denoiser import pretrained
        _denoiser_model = pretrained.dns64()
        _denoiser_model.eval()
        if torch.cuda.is_available():
            _denoiser_model = _denoiser_model.cuda()
        _denoiser_available = True
        logger.info("Meta Denoiser DNS64 model loaded successfully")
    except Exception as e:
        logger.warning("Meta Denoiser unavailable, audio will pass through unfiltered: %s", e)
        _denoiser_available = False


def init():
    """Pre-load the denoiser model at startup."""
    _load_model()


def is_available() -> bool:
    return _denoiser_available


def _wav_bytes_to_numpy(wav_bytes: bytes) -> np.ndarray:
    """Convert WAV bytes to float32 numpy array, resampling to 16kHz mono."""
    buf = io.BytesIO(wav_bytes)
    try:
        import soundfile as sf
        audio, sr = sf.read(buf, dtype="float32")
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            ratio = SAMPLE_RATE / sr
            indices = np.arange(0, len(audio), 1 / ratio).astype(int)
            indices = indices[indices < len(audio)]
            audio = audio[indices]
        return audio
    except Exception:
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth == 2:
            fmt = f"<{n_frames * n_channels}h"
            samples = np.array(struct.unpack(fmt, raw), dtype=np.float32) / 32768.0
        else:
            samples = np.frombuffer(raw, dtype=np.float32)

        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        if framerate != SAMPLE_RATE:
            ratio = SAMPLE_RATE / framerate
            indices = np.arange(0, len(samples), 1 / ratio).astype(int)
            indices = indices[indices < len(samples)]
            samples = samples[indices]

        return samples


def _numpy_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert float32 numpy array back to WAV bytes."""
    buf = io.BytesIO()
    audio_int16 = np.clip(audio * 32768, -32768, 32767).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def denoise_audio(audio_bytes: bytes) -> bytes:
    """Remove battlefield noise from audio.

    Args:
        audio_bytes: Raw WAV audio bytes from the medic's microphone.

    Returns:
        Cleaned WAV audio bytes with voice isolated.
    """
    if not _denoiser_available or _denoiser_model is None:
        logger.debug("Denoiser not available, passing audio through")
        return audio_bytes

    try:
        import torch

        audio_np = _wav_bytes_to_numpy(audio_bytes)

        tensor = torch.from_numpy(audio_np).float().unsqueeze(0).unsqueeze(0)

        device = next(_denoiser_model.parameters()).device
        tensor = tensor.to(device)

        with torch.no_grad():
            enhanced = _denoiser_model(tensor)

        enhanced_np = enhanced.squeeze().cpu().numpy()

        return _numpy_to_wav_bytes(enhanced_np)

    except Exception as e:
        logger.error("Denoiser processing failed, returning original audio: %s", e)
        return audio_bytes


def denoise_file(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Denoise a WAV file on disk (utility for batch processing)."""
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_stem(input_path.stem + "_clean")
    else:
        output_path = Path(output_path)

    with open(input_path, "rb") as f:
        raw = f.read()

    cleaned = denoise_audio(raw)

    with open(output_path, "wb") as f:
        f.write(cleaned)

    return output_path
