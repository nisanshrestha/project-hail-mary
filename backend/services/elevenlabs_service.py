"""ElevenLabs voice services: Audio Isolation + Scribe v2 (STT) + Flash v2.5 (TTS).

Pipeline: Audio Isolation (denoise) → Scribe v2 (STT) → Flash v2.5 (TTS)

Falls back to a no-op mode when API key is not configured, allowing
the text-based interface to function offline.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os

logger = logging.getLogger(__name__)

# ElevenLabs request limits — long LLM briefings exceed TTS max and fail the API call.
TTS_MAX_CHARS = int(os.getenv("ELEVENLABS_TTS_MAX_CHARS", "10000"))

_DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # "Sarah"
_DEFAULT_TTS_MODEL = "eleven_flash_v2_5"
_TTS_FALLBACK_MODELS = ("eleven_multilingual_v2", "eleven_turbo_v2_5")

_client = None
_available = False
_isolation_enabled = True


def init():
    """Initialize the ElevenLabs client."""
    global _client, _available, _isolation_enabled
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key or api_key == "your_elevenlabs_api_key_here":
        logger.warning("ELEVENLABS_API_KEY not set — voice features disabled, text mode only")
        _available = False
        return

    try:
        from elevenlabs.client import ElevenLabs
        _client = ElevenLabs(api_key=api_key)
        _available = True
        _isolation_enabled = os.getenv("ELEVENLABS_ISOLATION", "on").lower() in ("on", "true", "1", "yes")
        logger.info("ElevenLabs client initialized (isolation: %s)",
                     "ON" if _isolation_enabled else "OFF")
    except Exception as e:
        logger.warning("ElevenLabs SDK init failed: %s", e)
        _available = False


def is_available() -> bool:
    return _available


def is_isolation_enabled() -> bool:
    return _isolation_enabled and _available


def set_isolation_enabled(enabled: bool):
    global _isolation_enabled
    _isolation_enabled = enabled


async def isolate_audio(audio_bytes: bytes) -> bytes:
    """Remove background noise via ElevenLabs Audio Isolation API.

    POST /v1/audio-isolation — neural speech separation that strips
    gunfire, explosions, vehicle noise, and other combat interference.

    Args:
        audio_bytes: Raw or pre-denoised WAV/PCM audio.

    Returns:
        Cleaned audio bytes, or original if isolation fails/unavailable.
    """
    if not _available or _client is None or not _isolation_enabled:
        return audio_bytes

    # ElevenLabs requires minimum ~4.6s audio; skip isolation for short clips
    MIN_BYTES = 16000 * 2 * 5  # 5 seconds at 16kHz 16-bit mono = 160,000 bytes
    if len(audio_bytes) < MIN_BYTES:
        logger.debug("Audio too short for isolation (%d bytes), skipping", len(audio_bytes))
        return audio_bytes

    try:
        audio_file = io.BytesIO(audio_bytes)
        ext = "wav" if audio_bytes[:4] == b"RIFF" else "webm"
        audio_file.name = f"audio.{ext}"

        result = _client.audio_isolation.convert(
            audio=audio_file,
        )

        cleaned = b""
        for chunk in result:
            cleaned += chunk

        if cleaned:
            logger.info("ElevenLabs isolation: %d → %d bytes", len(audio_bytes), len(cleaned))
            return cleaned

        logger.warning("ElevenLabs isolation returned empty, using original")
        return audio_bytes

    except Exception as e:
        logger.error("ElevenLabs audio isolation failed, passing through: %s", e)
        return audio_bytes


async def speech_to_text(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using ElevenLabs Scribe v2.

    Args:
        audio_bytes: Cleaned WAV audio (post-denoiser).

    Returns:
        Transcribed text string.
    """
    if not _available or _client is None:
        logger.debug("ElevenLabs STT unavailable, returning empty transcript")
        return ""

    try:
        audio_file = io.BytesIO(audio_bytes)
        ext = "wav" if audio_bytes[:4] == b"RIFF" else "webm"
        audio_file.name = f"audio.{ext}"

        result = _client.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v2",
            language_code="en",
        )

        transcript = result.text if hasattr(result, "text") else str(result)
        logger.info("STT transcript: %s", transcript[:100])
        return transcript

    except Exception as e:
        logger.error("ElevenLabs STT failed: %s", e)
        return ""


def _sanitize_tts_input(text: str) -> str:
    """Strip characters that can break TTS or inflate payload size."""
    if not text:
        return ""
    # NUL / control chars (except common whitespace)
    out = []
    for ch in text:
        o = ord(ch)
        if o == 0 or (o < 32 and ch not in "\t\n\r"):
            continue
        out.append(ch)
    s = "".join(out)
    # Collapse excessive newlines (briefings use many === lines)
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    return s.strip()


def _tts_sync(text: str) -> str:
    """Blocking TTS; run via asyncio.to_thread from async routes."""
    from elevenlabs import VoiceSettings

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", _DEFAULT_VOICE)
    primary = os.getenv("ELEVENLABS_TTS_MODEL", _DEFAULT_TTS_MODEL)
    models_to_try = (primary,) + tuple(m for m in _TTS_FALLBACK_MODELS if m != primary)

    def _collect(gen) -> bytes:
        parts: list[bytes] = []
        for chunk in gen:
            if isinstance(chunk, (bytes, bytearray)):
                parts.append(bytes(chunk))
            elif chunk is not None:
                parts.append(bytes(chunk))
        return b"".join(parts)

    last_err: Exception | None = None
    for model_id in models_to_try:
        # Try with voice settings, then minimal args (some accounts reject custom settings).
        for use_settings in (True, False):
            try:
                if use_settings:
                    audio_gen = _client.text_to_speech.convert(
                        voice_id,
                        text=text,
                        model_id=model_id,
                        output_format="mp3_44100_128",
                        voice_settings=VoiceSettings(
                            stability=0.55,
                            similarity_boost=0.75,
                            style=0.25,
                            speed=1.0,
                        ),
                    )
                else:
                    audio_gen = _client.text_to_speech.convert(
                        voice_id,
                        text=text,
                        model_id=model_id,
                        output_format="mp3_44100_128",
                    )
                audio_bytes = _collect(audio_gen)
                if not audio_bytes:
                    logger.warning(
                        "ElevenLabs TTS empty stream (model=%s settings=%s)",
                        model_id,
                        use_settings,
                    )
                    continue
                logger.info(
                    "TTS ok: model=%s settings=%s %d bytes MP3",
                    model_id,
                    use_settings,
                    len(audio_bytes),
                )
                return base64.b64encode(audio_bytes).decode("utf-8")
            except Exception as e:
                last_err = e
                logger.warning(
                    "ElevenLabs TTS error model=%s settings=%s: %s",
                    model_id,
                    use_settings,
                    e,
                )

    if last_err:
        logger.error("ElevenLabs TTS exhausted all models and fallbacks: %s", last_err)
    return ""


async def text_to_speech(text: str) -> str:
    """Convert text to speech using ElevenLabs Flash v2.5 (with fallbacks).

    Args:
        text: The triage response text to synthesize.

    Returns:
        Base64-encoded MP3 audio string.
    """
    if not _available or _client is None:
        logger.debug("ElevenLabs TTS unavailable, returning empty audio")
        return ""

    raw = _sanitize_tts_input(text or "")
    if not raw:
        return ""

    if len(raw) > TTS_MAX_CHARS:
        logger.info(
            "TTS text truncated from %d to %d chars for API limits",
            len(raw),
            TTS_MAX_CHARS,
        )
        raw = raw[: TTS_MAX_CHARS].rstrip() + "\n…"

    try:
        return await asyncio.to_thread(_tts_sync, raw)
    except Exception:
        logger.exception("ElevenLabs TTS thread failed")
        return ""
