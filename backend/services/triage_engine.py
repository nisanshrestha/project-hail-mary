"""TCCC MARCH-based triage scoring engine.

Classifies injuries into T1 (Immediate), T2 (Delayed), T3 (Minimal),
T4 (Expectant) using a point-based system aligned with 2024 CoTCCC guidelines.

MARCH: Massive hemorrhage, Airway, Respiration, Circulation, Head/Hypothermia
"""

from __future__ import annotations
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Injury taxonomy: canonical injury types mapped to base MARCH scores
# ---------------------------------------------------------------------------

INJURY_DB: dict[str, dict] = {
    # T1 IMMEDIATE (80-100)
    "gsw_chest": {
        "name": "Gunshot wound to chest",
        "base_score": 95,
        "march_category": "R",
        "mechanism": "penetrating",
        "treatment": "Chest seal (vented), needle decompression if tension pneumothorax develops, prepare for chest tube",
        "keywords": ["gsw chest", "gunshot chest", "bullet chest", "shot in chest", "chest gunshot"],
    },
    "gsw_abdomen": {
        "name": "Gunshot wound to abdomen",
        "base_score": 92,
        "march_category": "C",
        "mechanism": "penetrating",
        "treatment": "Wound packing, TXA 1g IV, fluid resuscitation, MEDEVAC urgent surgical",
        "keywords": ["gsw abdomen", "gunshot abdomen", "bullet stomach", "shot in stomach", "abdominal gunshot"],
    },
    "tension_pneumothorax": {
        "name": "Tension pneumothorax",
        "base_score": 96,
        "march_category": "R",
        "mechanism": "penetrating",
        "treatment": "Needle decompression 2nd ICS midclavicular, chest seal, monitor for recurrence",
        "keywords": ["tension pneumothorax", "tension pneumo", "collapsed lung", "chest decompression"],
    },
    "arterial_hemorrhage": {
        "name": "Arterial hemorrhage (extremity)",
        "base_score": 93,
        "march_category": "M",
        "mechanism": "penetrating",
        "treatment": "Tourniquet high and tight, note time, TXA 1g IV, reassess in 2hrs",
        "keywords": ["arterial bleed", "arterial hemorrhage", "spurting blood", "massive bleed"],
    },
    "traumatic_amputation": {
        "name": "Traumatic amputation with active hemorrhage",
        "base_score": 94,
        "march_category": "M",
        "mechanism": "blast",
        "treatment": "Tourniquet proximal to amputation, wound packing, TXA 1g IV, hypothermia prevention",
        "keywords": ["amputation", "traumatic amputation", "amputated", "blown off", "lost arm", "lost leg"],
    },
    "airway_obstruction": {
        "name": "Airway obstruction",
        "base_score": 98,
        "march_category": "A",
        "mechanism": "blunt",
        "treatment": "NPA/OPA insertion, chin lift/jaw thrust, cricothyrotomy if complete obstruction",
        "keywords": ["airway obstruction", "cant breathe", "choking", "blocked airway", "airway blocked"],
    },
    "burns_severe": {
        "name": "Burns >40% BSA",
        "base_score": 85,
        "march_category": "H",
        "mechanism": "blast",
        "treatment": "Remove clothing, cool burns, IV fluid resuscitation (Parkland formula), pain management, hypothermia prevention",
        "keywords": ["severe burns", "major burns", "burns over 40", "extensive burns", "full body burns"],
    },

    # T2 DELAYED (50-79)
    "gsw_extremity": {
        "name": "Gunshot wound to extremity (controlled)",
        "base_score": 65,
        "march_category": "M",
        "mechanism": "penetrating",
        "treatment": "Wound packing, pressure dressing, reassess tourniquet need, antibiotics",
        "keywords": ["gsw extremity", "gunshot arm", "gunshot leg", "shot in arm", "shot in leg",
                      "bullet wound arm", "bullet wound leg", "gsw arm", "gsw leg",
                      "shot in the leg", "shot in the arm", "gunshot wound to the leg",
                      "gunshot wound to the arm", "gunshot to the leg", "gunshot to the arm"],
    },
    "fracture_femur": {
        "name": "Femur fracture",
        "base_score": 60,
        "march_category": "C",
        "mechanism": "blunt",
        "treatment": "Traction splint, pain management (ketamine 50mg IM), monitor for compartment syndrome",
        "keywords": ["broken femur", "femur fracture", "fractured femur", "thigh fracture", "broken thigh"],
    },
    "burns_moderate": {
        "name": "Burns 10-40% BSA",
        "base_score": 62,
        "march_category": "H",
        "mechanism": "blast",
        "treatment": "Cool burns, dry sterile dressings, IV fluids, pain management, hypothermia prevention",
        "keywords": ["moderate burns", "burns", "burned", "partial burns", "second degree burns", "35 percent burns"],
    },
    "blast_tbi": {
        "name": "Blast-induced traumatic brain injury",
        "base_score": 70,
        "march_category": "H",
        "mechanism": "blast",
        "treatment": "Neuro checks q15min, elevate HOB 30°, TXA 1g IV, avoid hypotension, MEDEVAC",
        "keywords": ["blast tbi", "blast brain", "brain injury", "head injury blast", "tbi", "traumatic brain"],
    },
    "blunt_abdominal": {
        "name": "Blunt abdominal trauma (stable)",
        "base_score": 55,
        "march_category": "C",
        "mechanism": "blunt",
        "treatment": "Serial abdominal exams, IV access, fluid resuscitation PRN, MEDEVAC for surgical eval",
        "keywords": ["blunt abdominal", "blunt abdomen", "abdominal trauma", "belly injury"],
    },

    # T3 MINIMAL (20-49)
    "fragment_wound": {
        "name": "Superficial fragment/shrapnel wound",
        "base_score": 35,
        "march_category": "M",
        "mechanism": "blast",
        "treatment": "Wound irrigation, remove accessible fragments, dressing, antibiotics, tetanus if due",
        "keywords": ["fragment wound", "shrapnel", "frag wound", "fragment injury", "shrapnel wound",
                      "shrapnel wounds", "fragment wounds"],
    },
    "laceration": {
        "name": "Laceration (non-arterial)",
        "base_score": 30,
        "march_category": "M",
        "mechanism": "penetrating",
        "treatment": "Direct pressure, wound closure (sutures/staples), dressing, antibiotics",
        "keywords": ["laceration", "lacerations", "cut", "cuts", "minor lacerations", "minor cuts"],
    },
    "concussion": {
        "name": "Mild concussion",
        "base_score": 40,
        "march_category": "H",
        "mechanism": "blunt",
        "treatment": "Neuro checks, rest, no return to duty until symptom-free 24hrs, evacuate if worsens",
        "keywords": ["concussion", "mild concussion", "dazed", "bell rung", "minor head injury", "head bump"],
    },
    "sprain": {
        "name": "Sprain/strain",
        "base_score": 22,
        "march_category": "C",
        "mechanism": "blunt",
        "treatment": "RICE (Rest, Ice, Compression, Elevation), NSAID if tolerated, buddy aid",
        "keywords": ["sprain", "strain", "twisted ankle", "rolled ankle"],
    },
    "minor_burns": {
        "name": "Minor burns (<10% BSA)",
        "base_score": 25,
        "march_category": "H",
        "mechanism": "blast",
        "treatment": "Cool running water, silver sulfadiazine cream, sterile dressing, oral pain relief",
        "keywords": ["minor burns", "small burn", "first degree burn", "hand burn", "face burn minor"],
    },

    # T4 EXPECTANT (0-19)
    "penetrating_head_no_pulse": {
        "name": "Penetrating head wound, no pulse",
        "base_score": 5,
        "march_category": "H",
        "mechanism": "penetrating",
        "treatment": "Comfort measures only, do not delay care of salvageable casualties",
        "keywords": ["head wound no pulse", "penetrating head", "fatal head wound"],
    },
    "burns_unsurvivable": {
        "name": "Burns >85% BSA",
        "base_score": 8,
        "march_category": "H",
        "mechanism": "blast",
        "treatment": "Comfort measures, pain management, do not delay care of salvageable casualties",
        "keywords": ["burns 85", "burns 90", "full body burns unsurvivable", "total body burn"],
    },
}

# Standard TCCC medications that may conflict with patient allergies
TCCC_STANDARD_MEDS = {
    "Morphine": {"alternatives": ["Ketamine 50mg IM/IV"], "class": "opioid"},
    "Ketamine": {"alternatives": ["Morphine 5mg IV (if no allergy)"], "class": "dissociative"},
    "Penicillin": {"alternatives": ["Moxifloxacin 400mg PO", "Ertapenem 1g IM"], "class": "antibiotic"},
    "NSAID": {"alternatives": ["Acetaminophen 1g PO", "Ketamine low-dose"], "class": "analgesic"},
    "Codeine": {"alternatives": ["Morphine (if no allergy)", "Ketamine"], "class": "opioid"},
    "Aspirin": {"alternatives": ["Acetaminophen 1g PO"], "class": "analgesic"},
    "Tetracycline": {"alternatives": ["Moxifloxacin 400mg PO"], "class": "antibiotic"},
    "Sulfonamide": {"alternatives": ["Moxifloxacin 400mg PO", "Ertapenem 1g IM"], "class": "antibiotic"},
    "TXA": {"alternatives": ["Aminocaproic acid if available"], "class": "antifibrinolytic"},
}

# Condition-based risk modifiers
CONDITION_RISK_MODIFIERS = {
    "Asthma": {"score_add": 5, "warning": "Asthma increases pneumothorax risk; have bronchodilator ready"},
    "Pneumothorax": {"score_add": 8, "warning": "History of pneumothorax — high risk of recurrence, monitor closely"},
    "G6PD deficiency": {"score_add": 3, "warning": "G6PD deficiency — AVOID oxidative drugs (primaquine, dapsone, methylene blue)"},
    "Traumatic brain injury": {"score_add": 5, "warning": "Prior TBI — increased susceptibility to secondary brain injury"},
    "Post-traumatic stress disorder": {"score_add": 0, "warning": "PTSD — patient on sertraline, watch for serotonin syndrome with tramadol"},
    "Type 2 diabetes mellitus": {"score_add": 2, "warning": "Diabetes — impaired wound healing, check glucose, adjust fluid management"},
}


@dataclass
class AllergyAlert:
    substance: str
    severity: str
    conflicting_med: str
    alternative: str
    warning: str


@dataclass
class ConditionAlert:
    condition: str
    warning: str
    score_modifier: int


@dataclass
class TriageResult:
    soldier_id: str
    soldier_name: str
    rank: str
    blood_type: str
    injury_key: str
    injury_name: str
    base_score: int
    final_score: int
    category: str  # T1, T2, T3, T4
    category_label: str  # IMMEDIATE, DELAYED, MINIMAL, EXPECTANT
    march_category: str
    mechanism: str
    treatment: str
    allergy_alerts: list[AllergyAlert] = field(default_factory=list)
    condition_alerts: list[ConditionAlert] = field(default_factory=list)
    modified_treatment: str = ""


def classify(score: int) -> tuple[str, str]:
    if score >= 80:
        return "T1", "IMMEDIATE"
    elif score >= 50:
        return "T2", "DELAYED"
    elif score >= 20:
        return "T3", "MINIMAL"
    else:
        return "T4", "EXPECTANT"


def match_injury(description: str) -> str | None:
    """Fuzzy-match a free-text injury description to a canonical injury key."""
    desc_lower = description.lower().strip()
    best_key = None
    best_matches = 0

    for key, injury in INJURY_DB.items():
        for kw in injury["keywords"]:
            kw_words = set(kw.lower().split())
            desc_words = set(desc_lower.split())
            overlap = len(kw_words & desc_words)
            if overlap > best_matches or (overlap == best_matches and kw.lower() in desc_lower):
                best_matches = overlap
                best_key = key

    if best_matches > 0:
        return best_key

    for key, injury in INJURY_DB.items():
        for kw in injury["keywords"]:
            if kw.lower() in desc_lower or desc_lower in kw.lower():
                return key

    return None


def check_allergy_conflicts(allergies: list[dict], treatment: str) -> list[AllergyAlert]:
    """Check if recommended TCCC treatment conflicts with patient allergies."""
    alerts = []
    treatment_lower = treatment.lower()

    for allergy in allergies:
        substance = allergy.get("substance", "")
        severity = allergy.get("severity", "unknown")

        for med_name, med_info in TCCC_STANDARD_MEDS.items():
            if med_name.lower() in substance.lower() or substance.lower() in med_name.lower():
                if med_name.lower() in treatment_lower:
                    alerts.append(AllergyAlert(
                        substance=substance,
                        severity=severity,
                        conflicting_med=med_name,
                        alternative=", ".join(med_info["alternatives"]),
                        warning=(
                            f"Allergic to {substance} ({severity}) — do not give {med_name}; "
                            f"use {', '.join(med_info['alternatives'])}"
                        ),
                    ))
                    break

    for allergy in allergies:
        substance = allergy.get("substance", "")
        severity = allergy.get("severity", "unknown")
        if "morphine" in substance.lower() and "morphine" not in treatment_lower and "opioid" not in treatment_lower:
            if "pain" in treatment_lower or "analges" in treatment_lower:
                alerts.append(AllergyAlert(
                    substance=substance,
                    severity=severity,
                    conflicting_med="Morphine (standard TCCC analgesic)",
                    alternative="Ketamine 50mg IM/IV",
                    warning=(
                        f"Opioid allergy ({substance}) — prefer ketamine for analgesia, not morphine"
                    ),
                ))

    return alerts


def check_condition_risks(conditions: list[str], injury_key: str) -> list[ConditionAlert]:
    """Check pre-existing conditions that modify risk for this injury."""
    alerts = []

    for condition in conditions:
        for known_cond, modifier in CONDITION_RISK_MODIFIERS.items():
            if known_cond.lower() in condition.lower():
                alerts.append(ConditionAlert(
                    condition=condition,
                    warning=modifier["warning"],
                    score_modifier=modifier["score_add"],
                ))

    return alerts


def build_modified_treatment(base_treatment: str,
                             allergy_alerts: list[AllergyAlert]) -> str:
    """Rewrite treatment plan substituting allergenic medications."""
    modified = base_treatment
    for alert in allergy_alerts:
        med = alert.conflicting_med.lower()
        if med in modified.lower():
            import re
            pattern = re.compile(re.escape(med), re.IGNORECASE)
            modified = pattern.sub(f"[CONTRAINDICATED-{alert.conflicting_med}→{alert.alternative}]", modified)
    return modified


def triage_casualty(
    soldier_id: str,
    soldier_name: str,
    rank: str,
    blood_type: str,
    injury_description: str,
    allergies: list[dict],
    conditions: list[str],
    injury_key_override: str | None = None,
) -> TriageResult:
    """Score and classify a single casualty."""
    injury_key = injury_key_override or match_injury(injury_description)

    if not injury_key or injury_key not in INJURY_DB:
        injury_key = "fragment_wound"

    injury = INJURY_DB[injury_key]
    base_score = injury["base_score"]

    allergy_alerts = check_allergy_conflicts(allergies, injury["treatment"])
    condition_alerts = check_condition_risks(conditions, injury_key)

    score_mod = sum(a.score_modifier for a in condition_alerts)
    final_score = min(100, base_score + score_mod)

    category, label = classify(final_score)
    modified_treatment = build_modified_treatment(injury["treatment"], allergy_alerts)

    return TriageResult(
        soldier_id=soldier_id,
        soldier_name=soldier_name,
        rank=rank,
        blood_type=blood_type or "Unknown",
        injury_key=injury_key,
        injury_name=injury["name"],
        base_score=base_score,
        final_score=final_score,
        category=category,
        category_label=label,
        march_category=injury["march_category"],
        mechanism=injury["mechanism"],
        treatment=injury["treatment"],
        allergy_alerts=allergy_alerts,
        condition_alerts=condition_alerts,
        modified_treatment=modified_treatment,
    )


def prioritize_casualties(results: list[TriageResult]) -> list[TriageResult]:
    """Sort casualties by priority: T1 first (highest score first within tier)."""
    tier_order = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}
    return sorted(results, key=lambda r: (tier_order.get(r.category, 99), -r.final_score))
