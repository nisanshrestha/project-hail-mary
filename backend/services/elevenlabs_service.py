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
import math
import os
from typing import Any

logger = logging.getLogger(__name__)

# ElevenLabs request limits — long LLM briefings exceed TTS max and fail the API call.
TTS_MAX_CHARS = int(os.getenv("ELEVENLABS_TTS_MAX_CHARS", "10000"))

_DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # "Sarah"
_DEFAULT_TTS_MODEL = "eleven_flash_v2_5"
_TTS_FALLBACK_MODELS = ("eleven_multilingual_v2", "eleven_turbo_v2_5")

_client = None
_available = False
_isolation_enabled = True


def _isolation_env_enabled() -> bool:
    """True when ElevenLabs audio isolation should run (default: on).

    Empty or unset ``ELEVENLABS_ISOLATION`` is treated as **on** so a blank
    ``.env`` line does not accidentally disable filtering.
    """
    raw = os.getenv("ELEVENLABS_ISOLATION", "on").strip().lower()
    if not raw:
        return True
    return raw in ("on", "true", "1", "yes")


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
        _isolation_enabled = _isolation_env_enabled()
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


async def isolate_audio_with_meta(audio_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Audio Isolation API — returns cleaned bytes and status for UI / telemetry.

    Status values: ``applied``, ``skipped_short``, ``skipped_disabled``, ``unavailable``, ``error``.
    """
    meta: dict[str, Any] = {"status": "unavailable", "detail": None}

    if not _available or _client is None:
        meta["status"] = "unavailable"
        meta["detail"] = "elevenlabs client off"
        return audio_bytes, meta

    if not _isolation_enabled:
        meta["status"] = "skipped_disabled"
        meta["detail"] = "isolation off"
        return audio_bytes, meta

    # Always call the isolation API when enabled (no minimum-length skip).
    # Very short clips may still be rejected by the API; errors fall through below.
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
            meta["status"] = "applied"
            meta["detail"] = f"{len(audio_bytes)}→{len(cleaned)} B"
            return cleaned, meta

        logger.warning("ElevenLabs isolation returned empty, using original")
        meta["status"] = "passthrough_empty"
        return audio_bytes, meta

    except Exception as e:
        logger.error("ElevenLabs audio isolation failed, passing through: %s", e)
        meta["status"] = "error"
        meta["detail"] = str(e)[:160]
        return audio_bytes, meta


async def isolate_audio(audio_bytes: bytes) -> bytes:
    """Remove background noise via ElevenLabs Audio Isolation API."""
    b, _ = await isolate_audio_with_meta(audio_bytes)
    return b


def _parse_speech_to_text_result(result: Any) -> dict[str, Any]:
    """Extract text and confidence fields from Scribe v2 response (chunk or multichannel)."""
    chunk = result
    if hasattr(result, "transcripts") and result.transcripts:
        chunk = result.transcripts[0]
    if chunk is None or not hasattr(chunk, "text"):
        return {
            "text": "",
            "language_confidence": None,
            "word_confidence": None,
        }

    text = (chunk.text or "").strip()
    lang_p = getattr(chunk, "language_probability", None)

    words = getattr(chunk, "words", None) or []
    token_probs: list[float] = []
    for w in words:
        wt = getattr(w, "type", None)
        if hasattr(wt, "value"):
            wt = wt.value
        if str(wt) != "word":
            continue
        lp = getattr(w, "logprob", None)
        if lp is None:
            continue
        # log p (natural); higher is better; cap for exp stability
        token_probs.append(math.exp(min(0.0, float(lp))))

    word_conf = sum(token_probs) / len(token_probs) if token_probs else None

    return {
        "text": text,
        "language_confidence": float(lang_p) if lang_p is not None else None,
        "word_confidence": word_conf,
    }


async def transcribe_audio(audio_bytes: bytes) -> dict[str, Any]:
    """Transcribe with ElevenLabs Scribe v2; return text + confidence metrics.

    ``language_confidence`` is language-detection score (0–1). ``word_confidence``
    is mean token probability derived from word-level ``logprob`` values.
    """
    if not _available or _client is None:
        logger.debug("ElevenLabs STT unavailable, returning empty transcript")
        return {"text": "", "language_confidence": None, "word_confidence": None}

    try:
        audio_file = io.BytesIO(audio_bytes)
        ext = "wav" if audio_bytes[:4] == b"RIFF" else "webm"
        audio_file.name = f"audio.{ext}"

        result = _client.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v2",
            language_code="en",
            timestamps_granularity="word",
        )

        out = _parse_speech_to_text_result(result)
        logger.info("STT transcript: %s", (out["text"] or "")[:100])
        return out

    except Exception as e:
        logger.error("ElevenLabs STT failed: %s", e)
        return {"text": "", "language_confidence": None, "word_confidence": None, "error": str(e)}


async def speech_to_text(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using ElevenLabs Scribe v2 (text only)."""
    data = await transcribe_audio(audio_bytes)
    return data.get("text") or ""


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
                            speed=1.5,
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
