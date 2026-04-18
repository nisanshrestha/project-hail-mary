# Project Hail Mary — Combat Medic FHIR Assistant

Offline-capable, voice-driven combat medic triage assistant with FHIR R4 health records, TCCC-based injury prioritization, and AI-augmented decision support.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Run the server
python -m backend.main
```

Open **http://localhost:8000** in your browser.

## Architecture

- **Backend:** Python + FastAPI serving REST API and static frontend
- **Database:** SQLite with FHIR R4 JSON resources (12 pre-seeded soldiers)
- **Audio Pipeline:** Meta Denoiser (noise suppression) → ElevenLabs Scribe v2 (STT) → ElevenLabs Flash v2.5 (TTS)
- **AI Brain:** Toggle between OpenAI GPT-4o and offline TCCC rules engine

## AI Modes

| Mode | Network Required | Description |
|------|-----------------|-------------|
| **Rules** (default) | No | Pure TCCC MARCH-based triage logic with template responses |
| **AI** | Yes (OpenAI API) | GPT-4o generates narrative care plans with clinical reasoning |

## Demo

Load pre-built scenarios from the bottom bar to simulate mass casualty events:

1. **Ambush at Checkpoint Delta** — 4 casualties, GSW + fragment wounds
2. **IED Strike on Convoy** — 5 casualties, amputation + burns + blast TBI
3. **Building Assault CQB** — 3 casualties, pneumothorax + GSW

See `demo/demo_script.md` for the full role-play walkthrough.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ELEVENLABS_API_KEY` | For voice | ElevenLabs API key for STT/TTS |
| `OPENAI_API_KEY` | For AI mode | OpenAI API key for GPT-4o |
| `AI_MODE` | No | `rules` (default) or `ai` |
| `UNIT_NAME` | No | Display name for the unit |
