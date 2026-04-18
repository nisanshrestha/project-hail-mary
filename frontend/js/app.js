/**
 * Main application controller — state management and API calls.
 */

const App = (() => {
    const API = '';
    let state = {
        patients: [],
        triageQueue: [],
        selectedPatient: null,
        mode: 'rules',
        config: {},
        scenarios: [],
        currentScenario: null,
    };

    async function init() {
        await loadConfig();
        await loadPatients();
        await loadScenarios();
        setupEventListeners();
        UI.renderTriageQueue([]);
        UI.renderPatientDetail(null);
        UI.renderResponse(null);
    }

    async function loadConfig() {
        try {
            const res = await fetch(`${API}/api/mode`);
            state.config = await res.json();
            state.mode = state.config.mode;
            UI.updateStatus(state.config);
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }

    async function loadPatients() {
        try {
            const res = await fetch(`${API}/api/patients`);
            const data = await res.json();
            state.patients = data.patients || [];
            UI.renderRoster(state.patients);
        } catch (e) {
            console.error('Failed to load patients:', e);
        }
    }

    async function loadScenarios() {
        try {
            const res = await fetch(`${API}/api/scenarios`);
            if (res.ok) {
                state.scenarios = await res.json();
            }
        } catch (e) {
            console.warn('Scenarios not available:', e);
        }
    }

    function setupEventListeners() {
        const pttBtn = document.getElementById('ptt-button');
        if (pttBtn) {
            pttBtn.addEventListener('mousedown', startVoice);
            pttBtn.addEventListener('mouseup', stopVoice);
            pttBtn.addEventListener('mouseleave', () => {
                if (Voice.getState() === 'recording') stopVoice();
            });
            pttBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startVoice(); }, { passive: false });
            pttBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopVoice(); }, { passive: false });
            pttBtn.addEventListener('touchcancel', () => stopVoice());
        }

        const textInput = document.getElementById('text-input');
        const textSubmit = document.getElementById('text-submit');
        if (textSubmit) {
            textSubmit.addEventListener('click', () => submitText(textInput.value));
        }
        if (textInput) {
            textInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') submitText(textInput.value);
            });
        }

        const modeToggle = document.getElementById('mode-toggle');
        if (modeToggle) {
            modeToggle.addEventListener('change', () => toggleMode(modeToggle.checked));
        }
        const labelRules = document.getElementById('label-rules');
        const labelAi = document.getElementById('label-ai');
        if (labelRules) {
            labelRules.addEventListener('click', (e) => {
                e.preventDefault();
                if (modeToggle && modeToggle.checked) toggleMode(false);
            });
        }
        if (labelAi) {
            labelAi.addEventListener('click', (e) => {
                e.preventDefault();
                if (modeToggle && !modeToggle.checked) toggleMode(true);
            });
        }

        document.querySelectorAll('.scenario-btn').forEach(btn => {
            btn.addEventListener('click', () => loadScenario(btn.dataset.scenario));
        });
    }

    async function startVoice() {
        try {
            UI.setPttState('recording');
            UI.setTranscript('Listening...');
            await Voice.startRecording();
        } catch (e) {
            UI.setPttState('');
            UI.setTranscript('Mic access denied');
        }
    }

    async function stopVoice() {
        UI.setPttState('processing');
        const audioBlob = await Voice.stopRecording();
        if (!audioBlob) {
            UI.setPttState('');
            return;
        }

        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        try {
            const res = await fetch(`${API}/api/voice/process`, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            await handleResponse(data);
        } catch (e) {
            console.error('Voice processing failed:', e);
            UI.setTranscript('Processing failed — try text input');
        }

        UI.setPttState('');
    }

    async function submitText(text) {
        if (!text || !text.trim()) return;
        UI.setLastCommand(text);
        document.getElementById('text-input').value = '';

        try {
            const res = await fetch(`${API}/api/voice/text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });
            const data = await res.json();
            await handleResponse(data);
        } catch (e) {
            console.error('Text processing failed:', e);
        }
    }

    async function handleResponse(data) {
        if (data.transcript) {
            UI.setTranscript(data.transcript);
            UI.setLastCommand(data.transcript);
        } else if (data.message) {
            /* e.g. STT failed (quota, API error) — voice route returns message, not transcript */
            UI.setTranscript(data.message);
        }

        if (data.triage_queue && data.triage_queue.length > 0) {
            state.triageQueue = data.triage_queue;
            UI.renderTriageQueue(state.triageQueue);
        }

        if (data.patients && data.patients.length > 0) {
            const p0 = data.patients[0];
            if (data.vitals_focus && p0.id) {
                await selectPatient(p0.id);
            } else {
                selectPatientData(p0);
            }
        }

        if (data.vitals_focus) {
            setTimeout(() => {
                UI.scrollVitalsIntoView();
                const sec = document.getElementById('vitals-live-section');
                if (sec) {
                    sec.classList.add('vitals-focus-flash');
                    setTimeout(() => sec.classList.remove('vitals-focus-flash'), 1200);
                }
            }, 220);
        }

        const outText = data.response_text || data.message || null;
        UI.renderResponse(outText, data.audio_b64);
    }

    async function toggleMode(isAi) {
        const newMode = isAi ? 'ai' : 'rules';
        try {
            const res = await fetch(`${API}/api/mode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode }),
            });
            const data = await res.json();
            state.mode = data.mode;
            UI.updateModeLabels(data.mode);
            document.getElementById('mode-toggle').checked = data.mode === 'ai';
        } catch (e) {
            console.error('Mode toggle failed:', e);
        }
    }

    function selectCasualty(index) {
        const r = state.triageQueue[index];
        if (!r) return;
        const patient = state.patients.find(p => p.id === r.soldier_id);
        if (patient) {
            selectPatientData(patient);
        }
        document.querySelectorAll('.triage-card').forEach((card, i) => {
            card.classList.toggle('selected', i === index);
        });
    }

    async function selectPatient(patientId) {
        try {
            const res = await fetch(`${API}/api/patients/${patientId}`);
            const patient = await res.json();
            selectPatientData(patient);
        } catch (e) {
            console.error('Failed to load patient:', e);
        }
    }

    function selectPatientData(patient) {
        state.selectedPatient = patient;
        UI.renderPatientDetail(patient);
    }

    async function loadScenario(scenarioId) {
        UI.setScenarioActive(scenarioId);
        state.currentScenario = scenarioId;

        const scenarioData = {
            'scenario-1': {
                name: 'Ambush at Checkpoint Delta',
                casualties: [
                    { soldier_id: 'soldier-001', injury_key: 'gsw_chest' },
                    { soldier_id: 'soldier-002', injury_key: 'fragment_wound' },
                    { soldier_id: 'soldier-003', injury_key: 'fracture_femur' },
                    { soldier_id: 'soldier-005', injury_key: 'laceration' },
                ],
            },
            'scenario-2': {
                name: 'IED Strike on Convoy',
                casualties: [
                    { soldier_id: 'soldier-011', injury_key: 'traumatic_amputation' },
                    { soldier_id: 'soldier-006', injury_key: 'burns_moderate' },
                    { soldier_id: 'soldier-008', injury_key: 'blast_tbi' },
                    { soldier_id: 'soldier-007', injury_key: 'fragment_wound' },
                    { soldier_id: 'soldier-012', injury_key: 'gsw_abdomen' },
                ],
            },
            'scenario-3': {
                name: 'Building Assault CQB',
                casualties: [
                    { soldier_id: 'soldier-010', injury_key: 'tension_pneumothorax' },
                    { soldier_id: 'soldier-009', injury_key: 'gsw_extremity' },
                    { soldier_id: 'soldier-005', injury_key: 'concussion' },
                ],
            },
        };

        const scenario = scenarioData[scenarioId];
        if (!scenario) return;

        UI.setLastCommand(`Loading scenario: ${scenario.name}`);

        try {
            const res = await fetch(`${API}/api/triage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    casualties: scenario.casualties.map(c => ({
                        soldier_id: c.soldier_id,
                        injury_description: '',
                        injury_key: c.injury_key,
                    })),
                }),
            });
            const data = await res.json();
            state.triageQueue = data.triage_queue || [];
            UI.renderTriageQueue(state.triageQueue);
            UI.renderResponse(data.response_text, null);

            if (state.triageQueue.length > 0) {
                selectCasualty(0);
            }
        } catch (e) {
            console.error('Scenario load failed:', e);
        }
    }

    return { init, selectCasualty, selectPatient, loadScenario };
})();

document.addEventListener('DOMContentLoaded', App.init);
