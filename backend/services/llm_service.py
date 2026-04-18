"""AI brain: OpenAI GPT-4o, Modal-hosted Llama, or offline TCCC rules engine."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from backend.services.triage_engine import TriageResult

logger = logging.getLogger(__name__)

_openai_client = None
_openai_available = False
_modal_available = False
_modal_app_name: str | None = None
_modal_cls_handle = None  # cached modal.Cls lookup for deployed Model
_llm_backend: str | None = None  # "openai" | "modal"
_llm_ready = False

_current_mode: str = "rules"  # "rules" or "ai"


def _resolve_llm_backend() -> tuple[str | None, str | None]:
    """Return (backend, modal_app_name). Backend is openai, modal, or None."""
    explicit = os.getenv("LLM_BACKEND", "").strip().lower()
    modal_app = os.getenv("MODAL_APP_NAME", "").strip() or None
    openai_key = os.getenv("OPENAI_API_KEY", "")
    openai_ok = bool(openai_key and openai_key != "your_openai_api_key_here")

    if explicit in ("openai", "modal"):
        return explicit, modal_app
    if modal_app:
        return "modal", modal_app
    if openai_ok:
        return "openai", None
    return None, modal_app


def init():
    global _openai_client, _openai_available, _modal_available, _modal_app_name
    global _modal_cls_handle, _llm_backend, _llm_ready, _current_mode

    _modal_cls_handle = None

    _current_mode = os.getenv("AI_MODE", "rules").lower()
    _llm_backend, _modal_app_name = _resolve_llm_backend()

    _openai_available = False
    _openai_client = None
    if _llm_backend == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key and api_key != "your_openai_api_key_here":
            try:
                from openai import OpenAI
                _openai_client = OpenAI(api_key=api_key)
                _openai_available = True
                logger.info("OpenAI GPT-4o client initialized")
            except Exception as e:
                logger.warning("OpenAI init failed: %s", e)
        else:
            logger.warning("LLM_BACKEND=openai but OPENAI_API_KEY missing or placeholder")

    _modal_available = False
    if _llm_backend == "modal":
        if not _modal_app_name:
            logger.warning("LLM_BACKEND=modal but MODAL_APP_NAME is not set")
        else:
            try:
                import modal  # noqa: F401
                _modal_available = True
                logger.info(
                    "Modal LLM configured (app=%s). Must match modal.App(\"...\") in your Modal file; "
                    "deploy e.g.: modal deploy llama_sandbox_8b.py",
                    _modal_app_name,
                )
            except ImportError:
                logger.warning("LLM_BACKEND=modal but `modal` package not installed")

    _llm_ready = (_llm_backend == "openai" and _openai_available) or (
        _llm_backend == "modal" and _modal_available and bool(_modal_app_name)
    )

    if _llm_backend and not _llm_ready:
        logger.warning("LLM backend %s not usable; AI mode disabled until configured", _llm_backend)

    if _current_mode == "ai" and not _llm_ready:
        logger.warning("AI mode requested but no LLM backend available, falling back to rules")
        _current_mode = "rules"


def get_mode() -> str:
    return _current_mode


def get_llm_backend() -> str | None:
    return _llm_backend if _llm_ready else None


def set_mode(mode: str) -> str:
    global _current_mode
    mode = mode.lower().strip()
    if mode == "ai" and not _llm_ready:
        logger.warning("Cannot switch to AI mode — no LLM backend configured")
        return _current_mode
    if mode in ("ai", "rules"):
        _current_mode = mode
    return _current_mode


def is_ai_available() -> bool:
    return _llm_ready


SYSTEM_PROMPT = """You are a Tactical Combat Casualty Care (TCCC) assistant embedded in a combat medic's 
field system. You provide concise, actionable triage guidance following MARCH protocol 
(Massive hemorrhage, Airway, Respiration, Circulation, Head/Hypothermia).

Rules:
- Be extremely concise. Battlefield comms must be short and clear.
- Lead with triage category (T1 IMMEDIATE, T2 DELAYED, T3 MINIMAL, T4 EXPECTANT), then injury, blood type, and MARCH focus.
- Prioritize hemorrhage control, airway, breathing, circulation, and transfusion-relevant facts before anything else.
- Reference specific TCCC interventions (tourniquet, chest seal, NPA, needle D/C, TXA, etc.).
- Include blood type for whole blood / transfusion planning when discussing resuscitation.
- If multiple casualties, present them in priority order (T1 first).
- End with MEDEVAC urgency (Urgent, Priority, Routine).
- Mention allergy or drug conflicts only when they change what you would draw up or infuse (not as a generic header).
"""

BRIEFING_SYSTEM_PROMPT = """You are a TCCC field terminal for SINGLE-PATIENT record lookups (not multi-casualty triage).

Your reply MUST start with a structured patient block using EXACTLY these section headers in this order (same spelling and punctuation):
=== PATIENT: <rank> <name> ===
BLOOD TYPE: <type>
BASELINE VITALS: <values or an em dash — if unknown>
MEDICATIONS (active): <list or None reported>
RELEVANT HISTORY: <problem list or None>
DRUG CONTRAINDICATIONS: <NKDA / none known OR listed drugs>

FORBIDDEN: Do not use ALLERGIES, CONDITIONS, or "None known" as section headers. Use RELEVANT HISTORY and DRUG CONTRAINDICATIONS only.
Never omit the BASELINE VITALS line.

After that block you may add at most 2 short sentences of TCCC-relevant guidance if the medic's question needs it.
"""

GENERAL_SYSTEM_PROMPT = """You are a Tactical Combat Casualty Care (TCCC) assistant embedded in a combat medic's field terminal.
The medic's message did not match a named patient or casualty incident on the roster.
Answer their question directly using concise, field-ready language. If they asked a question, answer it.
Stay within TCCC, prehospital combat medicine, and tactical medicine. If the topic is unrelated, give a one-line redirect and one relevant TCCC fact.
Use short paragraphs or bullet lines. No filler.
"""


def _briefing_text_from_facts(lines: list[str]) -> str:
    return "\n".join(lines)


def _llm_briefing_output_valid(text: str, template: str) -> bool:
    """Reject LLM output that reverts to generic ALLERGIES/CONDITIONS labels or drops required lines."""
    if not text or not text.strip():
        return False
    if template in text:
        return True
    if "BASELINE VITALS:" not in text:
        return False
    if "RELEVANT HISTORY:" not in text:
        return False
    if "DRUG CONTRAINDICATIONS:" not in text:
        return False
    if "MEDICATIONS (active):" not in text:
        return False
    if re.search(r"(?m)^\s*ALLERGIES\s*:", text):
        return False
    if re.search(r"(?m)^\s*CONDITIONS\s*:", text):
        return False
    return True


def _build_rules_response(results: list[TriageResult]) -> str:
    """Generate structured template response from triage results."""
    if not results:
        return "No casualties to triage."

    lines = []
    lines.append(f"=== TRIAGE REPORT: {len(results)} CASUALTIES ===\n")

    for i, r in enumerate(results, 1):
        lines.append(f"--- CASUALTY {i}: {r.rank} {r.soldier_name} ---")
        lines.append(f"CATEGORY: {r.category} {r.category_label}")
        lines.append(f"INJURY: {r.injury_name} (Score: {r.final_score}/100)")
        lines.append(f"BLOOD TYPE: {r.blood_type}")
        lines.append(f"MARCH: {r.march_category}")

        treatment = r.modified_treatment if r.modified_treatment else r.treatment
        lines.append(f"TREATMENT: {treatment}")

        if r.category == "T1":
            lines.append("MEDEVAC: URGENT")
        elif r.category == "T2":
            lines.append("MEDEVAC: PRIORITY")
        else:
            lines.append("MEDEVAC: ROUTINE")

        med_notes = []
        if r.allergy_alerts:
            for alert in r.allergy_alerts:
                med_notes.append(f"MED CONFLICT: {alert.warning}")
        if r.condition_alerts:
            for alert in r.condition_alerts:
                med_notes.append(f"COMORBID: {alert.warning}")
        if med_notes:
            lines.append("IF DRAWING MEDS / BLOOD PRODUCTS:")
            lines.extend(med_notes)

        lines.append("")

    t1_count = sum(1 for r in results if r.category == "T1")
    t2_count = sum(1 for r in results if r.category == "T2")
    lines.append(f"SUMMARY: {t1_count} IMMEDIATE, {t2_count} DELAYED, "
                 f"{len(results) - t1_count - t2_count} OTHER")
    lines.append("Treat T1 casualties first in order listed above.")

    return "\n".join(lines)


def _build_context_for_llm(results: list[TriageResult]) -> str:
    """Build structured context string for the LLM."""
    parts = []
    for r in results:
        part = (
            f"Patient: {r.rank} {r.soldier_name}\n"
            f"Blood Type: {r.blood_type}\n"
            f"Injury: {r.injury_name} (MARCH: {r.march_category}, Score: {r.final_score})\n"
            f"Category: {r.category} {r.category_label}\n"
            f"Base Treatment: {r.treatment}\n"
        )
        if r.condition_alerts:
            for c in r.condition_alerts:
                part += f"COMORBID: {c.warning}\n"
        if r.allergy_alerts:
            for a in r.allergy_alerts:
                part += (
                    f"MED CONFLICT: {a.substance} ({a.severity}) — avoid {a.conflicting_med}; "
                    f"prefer {a.alternative}\n"
                )
        parts.append(part)
    return "\n---\n".join(parts)


def _get_modal_cls():
    """Look up deployed @app.cls Model once (same name as Modal script)."""
    global _modal_cls_handle

    import modal

    assert _modal_app_name is not None
    if _modal_cls_handle is not None:
        return _modal_cls_handle

    kwargs: dict[str, Any] = {}
    env_name = os.getenv("MODAL_ENVIRONMENT_NAME", "").strip()
    if env_name:
        kwargs["environment_name"] = env_name
    class_name = (os.getenv("MODAL_CLASS_NAME") or "Model").strip() or "Model"
    _modal_cls_handle = modal.Cls.from_name(_modal_app_name, class_name, **kwargs)
    return _modal_cls_handle


async def _modal_generate(system_prompt: str, user_message: str) -> str:
    Model = _get_modal_cls()
    fn = Model().generate

    try:
        remote_aio = getattr(fn.remote, "aio", None)
        if remote_aio is not None:
            out: Any = await remote_aio(user_message, system_prompt)
            if isinstance(out, str):
                return out
            return str(out)
    except Exception as e:
        logger.debug("Modal .remote.aio failed (%s), using thread fallback", e)

    def _sync() -> str:
        r = fn.remote(user_message, system_prompt)
        return r if isinstance(r, str) else str(r)

    return await asyncio.to_thread(_sync)


async def generate_general_response(user_message: str) -> str:
    """Open-domain TCCC Q&A when no roster patient / injury intent applies."""
    raw = (user_message or "").strip()
    if not raw:
        return "No input. Name a patient + injury for triage, or ask a TCCC question."

    if not _llm_ready:
        return (
            "No roster patient matched. Configure Modal or OpenAI for general TCCC Q&A. "
            "For triage without an LLM, include a soldier name and injury (e.g. gunshot leg)."
        )

    wrapped = (
        "MEDIC MESSAGE (no roster patient matched — answer as general TCCC guidance):\n"
        f"{raw}"
    )

    try:
        if _llm_backend == "modal":
            return await _modal_generate(GENERAL_SYSTEM_PROMPT, wrapped)

        if _llm_backend == "openai" and _openai_client:
            response = _openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
                    {"role": "user", "content": wrapped},
                ],
                temperature=0.35,
                max_tokens=1200,
            )
            out = response.choices[0].message.content
            if out:
                return out
    except Exception as e:
        logger.error("General LLM call failed: %s", e)

    return (
        "Could not reach the LLM. Check Modal/OpenAI. For roster triage, say a soldier name and injury."
    )


async def generate_response(
    results: list[TriageResult],
    *,
    medic_transcript: str | None = None,
) -> str:
    """Generate triage response in current mode.

    medic_transcript: raw STT / text from the medic — include so the LLM sees what was actually said.
    """
    if _current_mode == "rules" or not _llm_ready:
        return _build_rules_response(results)

    context = _build_context_for_llm(results)
    medic_block = ""
    if medic_transcript and medic_transcript.strip():
        medic_block = (
            "MEDIC REPORT (verbatim from speech-to-text or typed input):\n"
            f"{medic_transcript.strip()}\n\n---\n\n"
        )
    user_msg = (
        f"{medic_block}"
        f"Triage {len(results)} casualties. Provide concise TCCC guidance "
        f"in priority order.\n\n{context}"
    )

    try:
        if _llm_backend == "modal":
            return await _modal_generate(SYSTEM_PROMPT, user_msg)

        if _llm_backend == "openai" and _openai_client:
            response = _openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            return response.choices[0].message.content

    except Exception as e:
        logger.error("LLM call failed, falling back to rules: %s", e)

    return _build_rules_response(results)


async def generate_patient_briefing(
    patient_summary: dict,
    *,
    medic_transcript: str | None = None,
) -> str:
    """Generate a briefing for a single patient lookup.

    medic_transcript: raw STT / text so the LLM can answer the medic's actual question.
    """
    name = patient_summary.get("name", "Unknown")
    rank = patient_summary.get("rank", "")
    blood = patient_summary.get("blood_type", "Unknown")
    allergies = patient_summary.get("allergies", [])
    conditions = patient_summary.get("conditions", [])
    meds = patient_summary.get("medications", [])

    vitals = patient_summary.get("vitals") or {}
    vit_parts = []
    for key, label in (
        ("hr", "HR"),
        ("bp_sys", "BP"),
        ("rr", "RR"),
        ("spo2", "SpO2"),
        ("temp", "temp"),
    ):
        o = vitals.get(key)
        if not o:
            continue
        val = o.get("value")
        unit = o.get("unit") or ""
        if val is None:
            continue
        if key == "bp_sys":
            dia = vitals.get("bp_dia")
            dval = dia.get("value") if dia else None
            if dval is not None:
                vit_parts.append(f"BP {val}/{dval} mmHg")
            elif val is not None:
                vit_parts.append(f"BP sys {val} mmHg")
            continue
        vit_parts.append(f"{label} {val}{unit}")
    vitals_line = "BASELINE VITALS: " + (" · ".join(vit_parts) if vit_parts else "—")

    lines = [
        f"=== PATIENT: {rank} {name} ===",
        f"BLOOD TYPE: {blood}",
        vitals_line,
    ]

    if meds:
        lines.append(f"MEDICATIONS (active): {', '.join(meds)}")
    else:
        lines.append("MEDICATIONS (active): None reported")

    if conditions:
        cond_strs = [c["name"] if isinstance(c, dict) else c for c in conditions]
        lines.append(f"RELEVANT HISTORY: {', '.join(cond_strs)}")
    else:
        lines.append("RELEVANT HISTORY: None")

    if allergies:
        allergy_strs = [f"{a['substance']} ({a['severity']})" for a in allergies]
        lines.append(f"DRUG CONTRAINDICATIONS: {', '.join(allergy_strs)}")
    else:
        lines.append("DRUG CONTRAINDICATIONS: NKDA / none known")

    template = _briefing_text_from_facts(lines)

    if _current_mode == "ai" and _llm_ready:
        try:
            medic_block = ""
            if medic_transcript and medic_transcript.strip():
                medic_block = (
                    "MEDIC REPORT (verbatim from speech-to-text or typed input):\n"
                    f"{medic_transcript.strip()}\n\n---\n\n"
                )
            user_msg = (
                f"{medic_block}"
                "Start your reply with the STRUCTURED RECORD below copied verbatim (every line, same headers). "
                "Do not rename sections to ALLERGIES or CONDITIONS. "
                "After that block, you may add at most 2 short sentences only if needed for the medic report above.\n\n"
                f"{template}"
            )
            if _llm_backend == "modal":
                out = await _modal_generate(BRIEFING_SYSTEM_PROMPT, user_msg)
                if _llm_briefing_output_valid(out, template):
                    return out
                logger.warning("Modal briefing failed format check; using template")
                return template

            if _llm_backend == "openai" and _openai_client:
                response = _openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.2,
                    max_tokens=500,
                )
                out = response.choices[0].message.content or ""
                if _llm_briefing_output_valid(out, template):
                    return out
                logger.warning("OpenAI briefing failed format check; using template")
                return template
        except Exception as e:
            logger.error("LLM briefing failed: %s", e)

    return template
