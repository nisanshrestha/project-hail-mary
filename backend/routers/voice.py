"""Voice pipeline API route — full mic-to-response cycle.

Audio in → Meta Denoiser → ElevenLabs STT → Intent parse →
FHIR lookup → Triage/LLM → ElevenLabs TTS → Audio out
"""

from __future__ import annotations

import io
import logging
import re
import wave
from dataclasses import asdict

from fastapi import APIRouter, File, UploadFile

from backend.database import get_patient_summary, search_patients_by_name
from backend.services import denoiser_service, elevenlabs_service, llm_service
from backend.services.triage_engine import (
    INJURY_DB,
    match_injury,
    prioritize_casualties,
    triage_casualty,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Soldier name list for intent extraction (populated at startup)
_soldier_names: list[dict] = []


def set_soldier_roster(roster: list[dict]):
    global _soldier_names
    _soldier_names = roster


_VITALS_PHRASES = (
    "baseline vitals",
    "baseline vital",
    "vital signs",
    "heart rate",
    "respiratory rate",
    "breathing rate",
    "live vitals",
    "show vitals",
    "pulse trace",
    "monitor vitals",
    "hr graph",
    "vital monitor",
    "vitals display",
    "pull up vitals",
    "open vitals",
)


def _wants_vitals(transcript: str) -> bool:
    """True if medic is asking for baseline / live vitals (PTT invoke)."""
    t = transcript.lower().strip()
    if not t:
        return False
    if any(p in t for p in _VITALS_PHRASES):
        return True
    # standalone "vitals" (word boundary)
    return bool(re.search(r"\bvitals\b", t))


def _convert_webm_to_wav(audio_bytes: bytes) -> bytes:
    """Best-effort conversion of uploaded audio to WAV format.

    Handles raw PCM and WAV passthrough. For WebM/Opus from browser
    MediaRecorder, we attempt decoding via soundfile.
    """
    if audio_bytes[:4] == b"RIFF":
        return audio_bytes

    try:
        import soundfile as sf
        import numpy as np

        buf = io.BytesIO(audio_bytes)
        audio, sr = sf.read(buf, dtype="float32")
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        wav_buf = io.BytesIO()
        audio_16k = audio
        if sr != 16000:
            ratio = 16000 / sr
            indices = np.arange(0, len(audio), 1 / ratio).astype(int)
            indices = indices[indices < len(audio)]
            audio_16k = audio[indices]

        import numpy as np
        audio_int16 = (audio_16k * 32768).clip(-32768, 32767).astype(np.int16)
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_int16.tobytes())
        return wav_buf.getvalue()
    except Exception as e:
        logger.warning("Audio conversion failed, using raw bytes: %s", e)
        return audio_bytes


def _extract_intent(transcript: str) -> dict:
    """Parse transcript to extract soldier names and injury descriptions.

    Uses positional proximity: each soldier is associated with the injury
    keywords that appear closest to their name in the transcript.

    Returns dict with:
        - soldiers: list of matched patient summaries
        - injuries: dict mapping soldier_id → injury key
        - raw_transcript: original text
    """
    transcript_lower = transcript.lower().strip()
    found_soldiers = []
    injuries_map = {}

    # Find soldiers and their positions in the transcript
    soldier_positions: list[tuple[int, dict]] = []
    for soldier in _soldier_names:
        name = soldier.get("name", "").lower()
        family = name.split()[-1] if name else ""
        given = name.split()[0] if name else ""

        pos = -1
        if family and family in transcript_lower:
            pos = transcript_lower.index(family)
        elif given and given in transcript_lower:
            pos = transcript_lower.index(given)

        if pos >= 0:
            found_soldiers.append(soldier)
            soldier_positions.append((pos, soldier))

    if not found_soldiers:
        words = transcript_lower.split()
        for word in words:
            if len(word) >= 3:
                matches = search_patients_by_name(word)
                for m in matches:
                    summary = get_patient_summary(m["id"])
                    if summary and summary not in found_soldiers:
                        found_soldiers.append(summary)
                        pos = transcript_lower.find(word)
                        soldier_positions.append((pos if pos >= 0 else 0, summary))

    soldier_positions.sort(key=lambda x: x[0])

    # Find all injury keyword matches and their positions
    injury_patterns = []
    for key, injury in INJURY_DB.items():
        for kw in injury["keywords"]:
            injury_patterns.append((kw.lower(), key))
    injury_patterns.sort(key=lambda x: -len(x[0]))

    injury_positions: list[tuple[int, str]] = []
    matched_keys = set()
    for kw, key in injury_patterns:
        if kw in transcript_lower and key not in matched_keys:
            pos = transcript_lower.index(kw)
            injury_positions.append((pos, key))
            matched_keys.add(key)

    # Associate each injury with the nearest preceding soldier by position
    if soldier_positions and injury_positions:
        if len(soldier_positions) == 1:
            best_injury = min(injury_positions, key=lambda x: x[0])
            injuries_map[soldier_positions[0][1]["id"]] = best_injury[1]
        else:
            for inj_pos, inj_key in injury_positions:
                candidates = sorted(soldier_positions,
                                    key=lambda s: abs(inj_pos - s[0]))
                for _, soldier in candidates:
                    sid = soldier["id"]
                    if sid not in injuries_map:
                        injuries_map[sid] = inj_key
                        break

    # STT rarely matches exact keyword substrings (e.g. "gunshot wound to the leg"
    # does not contain "gunshot leg"). Fuzzy-match the full transcript so triage
    # runs and generate_response() can call the LLM instead of raw patient dumps.
    if soldier_positions and not injuries_map:
        loose_key = match_injury(transcript)
        if loose_key:
            for _, soldier in soldier_positions:
                injuries_map[soldier["id"]] = loose_key
                break

    return {
        "soldiers": found_soldiers,
        "injuries": injuries_map,
        "raw_transcript": transcript,
    }


@router.post("/process")
async def process_voice(audio: UploadFile = File(...)):
    """Full voice pipeline: audio → denoise → STT → triage → TTS."""
    audio_bytes = await audio.read()
    logger.info("Received audio: %d bytes, content_type=%s", len(audio_bytes), audio.content_type)

    # Try WAV conversion for local denoiser; keep original for ElevenLabs fallback
    wav_bytes = _convert_webm_to_wav(audio_bytes)
    is_wav = wav_bytes[:4] == b"RIFF"

    if is_wav:
        # Stage 1: Meta Denoiser (local, offline) — needs WAV
        cleaned_audio = denoiser_service.denoise_audio(wav_bytes)
        # Stage 2: ElevenLabs Audio Isolation (cloud) — accepts WAV
        cleaned_audio = await elevenlabs_service.isolate_audio(cleaned_audio)
    else:
        # Browser sent WebM/Opus that couldn't be converted to WAV locally.
        # Skip local denoiser, send original to ElevenLabs isolation (accepts WebM).
        logger.info("WAV conversion failed, sending original %s to ElevenLabs directly",
                     audio.content_type)
        cleaned_audio = await elevenlabs_service.isolate_audio(audio_bytes)

    transcript = await elevenlabs_service.speech_to_text(cleaned_audio)

    if not transcript:
        return {
            "transcript": "",
            "message": "Could not transcribe audio. Please try again or use text input.",
            "patients": [],
            "triage_queue": [],
            "response_text": "",
            "audio_b64": "",
            "vitals_focus": False,
        }

    intent = _extract_intent(transcript)
    soldiers = intent["soldiers"]
    injuries = intent["injuries"]

    triage_results = []
    if injuries:
        for soldier in soldiers:
            sid = soldier["id"]
            if sid in injuries:
                raw_conds = soldier.get("conditions", [])
                cond_names = [c["name"] if isinstance(c, dict) else c for c in raw_conds]
                result = triage_casualty(
                    soldier_id=sid,
                    soldier_name=soldier["name"],
                    rank=soldier.get("rank", ""),
                    blood_type=soldier.get("blood_type", "Unknown"),
                    injury_description="",
                    allergies=soldier.get("allergies", []),
                    conditions=cond_names,
                    injury_key_override=injuries[sid],
                )
                triage_results.append(result)

    wants_v = _wants_vitals(transcript)

    if triage_results:
        prioritized = prioritize_casualties(triage_results)
        response_text = await llm_service.generate_response(
            prioritized,
            medic_transcript=transcript,
        )
    elif soldiers:
        if wants_v and not triage_results:
            n = soldiers[0].get("name", "Unknown")
            response_text = (
                f"Baseline vitals — live HR/RR trace for {n}. "
                "Dashed lines: recorded baseline. Solid lines: simulated field monitor."
            )
            prioritized = []
        else:
            briefings = []
            for s in soldiers:
                brief = await llm_service.generate_patient_briefing(
                    s,
                    medic_transcript=transcript,
                )
                briefings.append(brief)
            response_text = "\n\n".join(briefings)
            prioritized = []
    else:
        response_text = await llm_service.generate_general_response(transcript)
        prioritized = []

    vitals_focus = bool(soldiers) and wants_v

    audio_b64 = ""
    if response_text and elevenlabs_service.is_available():
        audio_b64 = await elevenlabs_service.text_to_speech(response_text)

    return {
        "transcript": transcript,
        "patients": soldiers,
        "triage_queue": [asdict(r) for r in prioritized] if triage_results else [],
        "response_text": response_text,
        "audio_b64": audio_b64,
        "mode": llm_service.get_mode(),
        "vitals_focus": vitals_focus,
    }


@router.post("/text")
async def process_text(body: dict):
    """Text-based input (bypass voice pipeline for offline/demo use)."""
    text = body.get("text", "")
    if not text:
        return {"error": "No text provided"}

    intent = _extract_intent(text)
    soldiers = intent["soldiers"]
    injuries = intent["injuries"]

    triage_results = []
    if injuries:
        for soldier in soldiers:
            sid = soldier["id"]
            if sid in injuries:
                raw_conds = soldier.get("conditions", [])
                cond_names = [c["name"] if isinstance(c, dict) else c for c in raw_conds]
                result = triage_casualty(
                    soldier_id=sid,
                    soldier_name=soldier["name"],
                    rank=soldier.get("rank", ""),
                    blood_type=soldier.get("blood_type", "Unknown"),
                    injury_description="",
                    allergies=soldier.get("allergies", []),
                    conditions=cond_names,
                    injury_key_override=injuries[sid],
                )
                triage_results.append(result)

    wants_v = _wants_vitals(text)

    if triage_results:
        prioritized = prioritize_casualties(triage_results)
        response_text = await llm_service.generate_response(
            prioritized,
            medic_transcript=text,
        )
    elif soldiers:
        if wants_v and not triage_results:
            n = soldiers[0].get("name", "Unknown")
            response_text = (
                f"Baseline vitals — live HR/RR trace for {n}. "
                "Dashed lines: recorded baseline. Solid lines: simulated field monitor."
            )
            prioritized = []
        else:
            briefings = []
            for s in soldiers:
                brief = await llm_service.generate_patient_briefing(
                    s,
                    medic_transcript=text,
                )
                briefings.append(brief)
            response_text = "\n\n".join(briefings)
            prioritized = []
    else:
        response_text = await llm_service.generate_general_response(text)
        prioritized = []

    vitals_focus = bool(soldiers) and wants_v

    audio_b64 = ""
    if response_text and elevenlabs_service.is_available():
        audio_b64 = await elevenlabs_service.text_to_speech(response_text)

    return {
        "transcript": text,
        "patients": soldiers,
        "triage_queue": [asdict(r) for r in prioritized] if triage_results else [],
        "response_text": response_text,
        "audio_b64": audio_b64,
        "mode": llm_service.get_mode(),
        "vitals_focus": vitals_focus,
    }
