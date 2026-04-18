# Project Hail Mary — Live Demo Script

## Setup

1. Start the server: `python -m backend.main`
2. Open `http://localhost:8000` in Chrome (mic access required for voice)
3. Verify header shows: unit name, status dots (Denoiser/Voice/AI), mode toggle
4. Default mode: **TCCC Rules** (fully offline)

---

## Demo 1: Scenario Walk-through (Checkpoint Ambush)

### Step 1 — Load Scenario
> **Action:** Click **"1: Checkpoint Ambush"** button in the bottom bar.

**Expected Result:**
- Triage queue populates with 4 casualties, sorted by priority
- SGT Morrison appears first (T1, red, score 95)
- Response box shows full TCCC triage report

> **Narrator:** "The system has automatically triaged four casualties from an ambush. Notice SGT Morrison is flagged T1 IMMEDIATE with a gunshot wound to the chest — he gets treated first."

### Step 2 — Review Patient Record
> **Action:** Click **CPL Santos** in the triage queue.

**Expected Result:**
- Right panel shows her full FHIR record
- Allergy tag: **Penicillin (severe)** displayed in red
- Response mentions: "ALLERGY ALERT: Do NOT administer Penicillin. Use Moxifloxacin 400mg PO."

> **Narrator:** "Notice the system flagged Santos' Penicillin allergy and automatically substituted Moxifloxacin. In the chaos of combat, this kind of automated safety check saves lives."

### Step 3 — Review Diabetic Patient
> **Action:** Click **PFC Kim** in the triage queue.

**Expected Result:**
- Right panel shows Type 2 Diabetes condition, Metformin medication
- Condition note in response: "Diabetes — impaired wound healing, check glucose"

> **Narrator:** "Kim has a femur fracture, but the system also surfaces his diabetes history — critical for wound management decisions."

---

## Demo 2: Voice Input (CQB Scenario)

### Step 1 — Voice Command
> **Action:** Hold the **PUSH TO TALK** button and say:
> 
> *"Ortega has a tension pneumothorax, Blake was shot in the leg"*

**Expected Result:**
- Button pulses red during recording
- Transcript appears: "Ortega has a tension pneumothorax, Blake was shot in the leg"
- Triage queue shows: PFC Ortega (T1, score 96), CW2 Blake (T2, score 65)
- Audio response plays back the triage report

> **Narrator:** "The medic just spoke naturally — the system identified both soldiers by name, matched their injuries, pulled their medical records, flagged Blake's Codeine allergy and PTSD medication, and delivered a prioritized treatment plan in under 3 seconds."

### Step 2 — Allergy Conflict Demo
> **Action:** Click **CW2 Blake** to review his record.

**Expected Result:**
- Codeine allergy flagged
- PTSD condition + Sertraline medication shown
- Response warns: "Codeine allergy — use Ketamine. On Sertraline — avoid Tramadol."

> **Narrator:** "Blake is on Sertraline for PTSD. The system warns against Tramadol because of serotonin syndrome risk — that's the kind of drug interaction a medic under fire might not catch."

---

## Demo 3: Text Input + AI Mode Toggle

### Step 1 — Text Input
> **Action:** Type in the text box:
> 
> *"Tanaka traumatic amputation right arm, Volkov burns, Hawkins GSW abdomen"*
>
> Press Enter or click Send.

**Expected Result:**
- Three casualties triaged: Tanaka (T1, 100), Hawkins (T1, 92), Volkov (T2, 62)
- Tanaka's score boosted to 100 by prior pneumothorax history
- Volkov's morphine allergy flagged with Ketamine substitution

### Step 2 — Switch to AI Mode
> **Action:** Toggle the switch from **TCCC RULES** to **GPT-4o**.

> **Action:** Click **"2: IED Convoy"** scenario button.

**Expected Result:**
- Same casualties, but response now shows a narrative AI-generated briefing
- More natural language, clinical reasoning explained
- Same allergy warnings included but woven into narrative

> **Narrator:** "In AI mode, GPT-4o generates a contextual clinical narrative. In Rules mode, it's deterministic template output — no network needed. The medic can toggle based on connectivity."

---

## Demo 4: Roster Lookup

> **Action:** Click **Elena Volkov** in the Unit Roster panel on the left.

**Expected Result:**
- Full patient record appears: CPT, A- blood type
- Morphine allergy (severe) — Respiratory depression and urticaria
- No pre-existing conditions

> **Narrator:** "Even without an active casualty event, medics can look up any soldier's medical record offline — allergies, blood type, medications. This is the FHIR health record acting as a tactical asset."

---

## Key Talking Points

1. **Offline-First:** The FHIR database, triage engine, and rules mode all work with zero network. Voice and AI mode add capability when connectivity exists.

2. **Noise Suppression:** Meta Denoiser strips gunfire and explosions from audio before transcription, enabling reliable voice input in combat.

3. **FHIR R4 Compliance:** All medical data follows the HL7 FHIR R4 standard — interoperable with hospital systems when the soldier reaches Role 2/3 care.

4. **Allergy Safety Net:** The system cross-references every treatment recommendation against the soldier's allergy profile before output. This catches drug conflicts that a medic under stress might miss.

5. **TCCC Alignment:** Triage scoring follows the MARCH protocol from the 2024 Committee on TCCC guidelines — the same framework taught in TCCC courses.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Voice button doesn't work | Check browser mic permissions, use Chrome |
| "Denoiser OFF" status | Normal if PyTorch not installed — STT still works |
| AI toggle won't switch | Set `OPENAI_API_KEY` in `.env` |
| No audio playback | Set `ELEVENLABS_API_KEY` in `.env` |
| Scenario doesn't load | Check server is running on port 8000 |
