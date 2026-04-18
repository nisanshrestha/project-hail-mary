# AI mode — live demo role-play script

Use with **AI** toggled **ON** in the header. Speak clearly; hold **PTT** through each line (or use **text input** with the same wording).

**Setup (you say once to yourself)**  
- Confirm **`GET /api/mode`** shows `ai_available: true` and `llm_backend: "modal"` (or refresh the page and check the **AI (modal)** status).  
- First Modal call after idle can take **1–2 minutes** — wait for the response before judging a failure.

---

## Act 1 — Single casualty, immediate (T1)

**You (medic):**  
“Hail Mary, this is Medic. **Morrison** has a **gunshot wound to the chest**. Sucking chest wound, dropping sat, I need priority and treatment, over.”

**What to watch:**  
- Transcript shows **Morrison** + chest injury.  
- **Response** should be **TCCC-style narrative** (not only a raw roster dump): category, MARCH, allergy/condition notes if relevant, MEDEVAC tone.  
- **Audio** plays if ElevenLabs is configured.

---

## Act 2 — Two casualties, priority order

**You (medic):**  
“Two patients. **Williams** has **shrapnel wounds** to the thigh, bleeding controlled. **Santos** has a **gunshot to the leg**, still bleeding. Who do I treat first?”

**What to watch:**  
- Both names resolve; injuries map to **fragment** / **extremity GSW** style language.  
- **Triage order** in the queue should reflect severity (listen/read the AI summary).

---

## Act 3 — Allergy flag (from scenario DNA)

**You (medic):**  
“**Santos** took fragments in the leg. I need antibiotics plan — she has **penicillin allergy**.”

**What to watch:**  
- System should surface **penicillin** conflict if the rules layer passes it through; AI narrative should **not** recommend penicillin-class prophylaxis blindly.

---

## Act 4 — Patient lookup only (briefing path)

**You (medic):**  
“Record on **Tanaka**, what’s his history?”

**What to watch:**  
- **Briefing-style** answer (prior lung history in seed data may appear in narrative).  
- If you **only** say a last name with **no injury words**, the app uses the **briefing** path, not full multi-casualty triage.

---

## Act 4b — Live HR/RR graph (PTT)

**You (medic):**  
“**Morrison** **baseline vitals**” or “**Santos** **show vitals**” or “**heart rate** for **Kim**.”

**What to watch:**  
- Patient record opens (or refreshes) with **LIVE TRACE — HR / RR** (dashed = baseline from record, solid = simulated trace).  
- Response text is a short confirmation; the **graph scrolls into view** with a brief highlight.

---

## Act 5 — Multi-casualty push (text is easier than voice)

Paste into **text input** (one message):

“**Kim** has a **broken femur** from the blast. **Volkov** has **traumatic amputation** with **massive bleeding**. **Nair** has **shrapnel wounds**. Triage all three.”

**What to watch:**  
- Three entries in **triage queue**; AI response summarizes **order** and key actions.

---

## Phrases that register well (keywords / fuzzy match)

| Intent              | Example phrases |
|---------------------|-----------------|
| GSW chest           | “gunshot to the chest”, “GSW chest”, “shot in the chest” |
| GSW extremity       | “gunshot to the leg”, “shot in the leg”, “bullet wound leg” |
| Fragment / shrapnel | “shrapnel”, “fragment wound”, “frag injury” |
| Amputation          | “traumatic amputation”, “amputation”, “leg blown off” |
| Femur fracture      | “broken femur”, “femur fracture” |
| Tension PTX         | “tension pneumothorax”, “collapsed lung” |
| Baseline vitals PTT | “baseline vitals”, “show vitals”, “heart rate”, “vital signs”, “live vitals” (with a soldier name) |

Use **last names** from the roster (**Morrison, Santos, Kim, Williams, Volkov, Tanaka**, etc.) — the matcher keys off **family** or **given** name in the transcript.

---

## If the AI reads like the old “rules template”

- **AI mode** not actually on → toggle **AI** and confirm `mode` in API.  
- **`ai_available: false`** → fix `.env` (`LLM_BACKEND`, `MODAL_APP_NAME`, Modal token) and restart API.  
- **Modal cold start** — repeat the same prompt after ~60–120 s.  
- **Injury not detected** — add explicit keywords from the table above so the request hits **triage** (`generate_response`) not only **briefing**.
