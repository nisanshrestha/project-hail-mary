/**
 * UI rendering — field-hardened for gloves + goggles.
 * All text large, all targets 60px+, max contrast.
 */

const UI = (() => {
    /** Triage tier + frontline action cue (not clinical jargon alone). */
    const CAT_HINT = {
        T1: 'BLEED / AIRWAY FIRST',
        T2: 'HOLD — PREP EVAC',
        T3: 'MINIMAL INTERVENTION',
        T4: 'EXPECTANT — COMFORT',
    };
    const MARCH = { M: 'HEMORRHAGE', A: 'AIRWAY', R: 'RESPIRATION', C: 'CIRCULATION', H: 'HEAD/HYPO' };

    let _vitalsRaf = null;
    let _responseAudioUrl = null;
    let _comparePreUrl = null;
    let _comparePostUrl = null;
    const VITALS_MAX = 72;

    function stopVitalsLiveGraph() {
        if (_vitalsRaf != null) {
            cancelAnimationFrame(_vitalsRaf);
            _vitalsRaf = null;
        }
    }

    function startVitalsLiveGraph(patient) {
        stopVitalsLiveGraph();
        const canvas = document.getElementById('vitals-hr-rr-canvas');
        if (!canvas || !patient) return;

        const v = patient.vitals || {};
        const baseHr = Number(v.hr?.value) || 72;
        const baseRr = Number(v.rr?.value) || 16;

        const hrBuf = [];
        const rrBuf = [];
        hrBuf.push(baseHr, baseHr);
        rrBuf.push(baseRr, baseRr);
        let last = 0;
        const intervalMs = 180;

        function draw() {
            const ctx = canvas.getContext('2d');
            const dpr = window.devicePixelRatio || 1;
            const w = canvas.clientWidth || 400;
            const h = canvas.clientHeight || 140;
            if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
                canvas.width = Math.floor(w * dpr);
                canvas.height = Math.floor(h * dpr);
            }
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            const W = canvas.clientWidth;
            const H = canvas.clientHeight;
            const mid = H * 0.5;
            const pad = 8;

            ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-well') || '#141a21';
            ctx.fillRect(0, 0, W, H);

            const hrMin = 40;
            const hrMax = 200;
            const rrMin = 4;
            const rrMax = 44;

            function yHr(val) {
                const t = (val - hrMin) / (hrMax - hrMin);
                return pad + (1 - Math.min(1, Math.max(0, t))) * (mid - 2 * pad);
            }
            function yRr(val) {
                const t = (val - rrMin) / (rrMax - rrMin);
                return mid + pad + (1 - Math.min(1, Math.max(0, t))) * (H - mid - 2 * pad);
            }

            ctx.strokeStyle = 'rgba(76, 144, 240, 0.35)';
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.moveTo(pad, yHr(baseHr));
            ctx.lineTo(W - pad, yHr(baseHr));
            ctx.stroke();
            ctx.strokeStyle = 'rgba(100, 200, 180, 0.35)';
            ctx.beginPath();
            ctx.moveTo(pad, yRr(baseRr));
            ctx.lineTo(W - pad, yRr(baseRr));
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.strokeStyle = 'rgba(76, 144, 240, 0.9)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            const n = hrBuf.length;
            if (n > 1) {
                for (let i = 0; i < n; i++) {
                    const x = pad + (i / (VITALS_MAX - 1)) * (W - 2 * pad);
                    const y = yHr(hrBuf[i]);
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
            }
            ctx.stroke();

            ctx.strokeStyle = 'rgba(100, 220, 200, 0.95)';
            ctx.beginPath();
            if (rrBuf.length > 1) {
                for (let i = 0; i < rrBuf.length; i++) {
                    const x = pad + (i / (VITALS_MAX - 1)) * (W - 2 * pad);
                    const y = yRr(rrBuf[i]);
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
            }
            ctx.stroke();

            ctx.fillStyle = 'rgba(200, 210, 220, 0.85)';
            ctx.font = '600 11px system-ui, sans-serif';
            ctx.fillText(`HR ${Math.round(hrBuf[hrBuf.length - 1] || baseHr)}`, pad, pad + 10);
            ctx.fillStyle = 'rgba(120, 220, 200, 0.95)';
            ctx.fillText(`RR ${(rrBuf[rrBuf.length - 1] || baseRr).toFixed(1)}`, pad, mid + 12);

            ctx.strokeStyle = 'rgba(255,255,255,0.08)';
            ctx.beginPath();
            ctx.moveTo(0, mid);
            ctx.lineTo(W, mid);
            ctx.stroke();
        }

        function tick(now) {
            if (now - last < intervalMs) {
                _vitalsRaf = requestAnimationFrame(tick);
                return;
            }
            last = now;
            const prevH = hrBuf.length ? hrBuf[hrBuf.length - 1] : baseHr;
            const prevR = rrBuf.length ? rrBuf[rrBuf.length - 1] : baseRr;
            hrBuf.push(
                Math.min(200, Math.max(40, prevH + (Math.random() - 0.5) * 8 + (Math.random() - 0.5) * 3))
            );
            rrBuf.push(
                Math.min(44, Math.max(4, prevR + (Math.random() - 0.5) * 3))
            );
            if (hrBuf.length > VITALS_MAX) hrBuf.shift();
            if (rrBuf.length > VITALS_MAX) rrBuf.shift();
            draw();
            _vitalsRaf = requestAnimationFrame(tick);
        }

        _vitalsRaf = requestAnimationFrame(tick);
    }

    function scrollVitalsIntoView() {
        const sec = document.getElementById('vitals-live-section');
        if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function renderTriageQueue(queue) {
        const el = document.getElementById('triage-queue');
        if (!queue || queue.length === 0) {
            el.innerHTML = `
                <div class="empty-state">
                    <div class="icon">+</div>
                    <p>NO CASUALTIES REPORTED.<br>
                       SPEAK OR TYPE SOLDIER NAME + INJURY.<br>
                       LOAD SCENARIO FROM BOTTOM.</p>
                </div>`;
            return;
        }

        el.innerHTML = queue.map((r, i) => {
            const comorbid = (r.condition_alerts?.length || 0) > 0;
            const urgent = r.category === 'T1' || r.category === 'T2';
            const warn = urgent || comorbid ? '<span class="alert-indicator">&#x26A0;</span>' : '';
            const bt = r.blood_type ? `<span class="triage-blood">${r.blood_type}</span>` : '';
            return `
            <div class="triage-card ${r.category.toLowerCase()}"
                 onclick="App.selectCasualty(${i})">
                <div class="triage-badge">
                    ${r.category}
                    <span class="cat-sub">${CAT_HINT[r.category] || ''}</span>
                </div>
                <div class="triage-info">
                    <h3>${warn}${r.rank} ${r.soldier_name} ${bt}</h3>
                    <div class="injury">${r.injury_name}</div>
                    <span class="march-badge">${r.march_category} // ${MARCH[r.march_category] || ''}</span>
                </div>
                <div class="triage-score">${r.final_score}</div>
            </div>`;
        }).join('');
    }

    function renderPatientDetail(patient) {
        const el = document.getElementById('patient-detail');
        stopVitalsLiveGraph();
        if (!patient) {
            renderDefaultDetail(el);
            return;
        }

        const p = patient;
        const age = p.age ? `${p.age}yr` : '';
        const gender = p.gender ? p.gender.charAt(0).toUpperCase() : '';
        const ht = p.height_cm ? `${p.height_cm}cm` : '';
        const wt = p.weight_kg ? `${p.weight_kg}kg` : '';
        const bmi = (p.height_cm && p.weight_kg)
            ? (p.weight_kg / ((p.height_cm / 100) ** 2)).toFixed(1)
            : '';

        const allergies = p.allergies?.length
            ? p.allergies.map(a => {
                const rx = a.reaction ? `<div class="tag-detail">${esc(a.reaction)}</div>` : '';
                return `<div class="detail-tag allergy-tag">
                    <div class="tag-head">&#x26A0; ${esc(a.substance)} <span class="tag-sev">[${(a.severity || '').toUpperCase()}]</span></div>
                    ${rx}
                </div>`;
            }).join('')
            : '<span class="none-tag">NKDA — No Known Drug Allergies</span>';

        const conditions = p.conditions?.length
            ? p.conditions.map(c => {
                const obj = typeof c === 'string' ? { name: c, note: '' } : c;
                const note = obj.note ? `<div class="tag-detail">${esc(obj.note)}</div>` : '';
                return `<div class="detail-tag condition-tag">
                    <div class="tag-head">${esc(obj.name)}</div>
                    ${note}
                </div>`;
            }).join('')
            : '<span class="none-tag">NONE</span>';

        const meds = p.medications?.length
            ? p.medications.map(m =>
                `<span class="detail-tag med-tag">${esc(m)}</span>`
            ).join('')
            : '<span class="none-tag">NONE</span>';

        // Vitals grid
        const v = p.vitals || {};
        const vitalRows = [
            ['HR',     v.hr?.value,     v.hr?.unit     || 'bpm'],
            ['BP',     (v.bp_sys?.value && v.bp_dia?.value) ? `${v.bp_sys.value}/${v.bp_dia.value}` : null, 'mmHg'],
            ['RR',     v.rr?.value,     v.rr?.unit     || '/min'],
            ['SpO2',   v.spo2?.value,   v.spo2?.unit   || '%'],
            ['Temp',   v.temp?.value,   v.temp?.unit   || '°C'],
        ].filter(r => r[1] != null);

        const vitalsGridHtml = vitalRows.length
            ? `<div class="vitals-grid">${vitalRows.map(([label, val, unit]) =>
                `<div class="vital-cell">
                    <span class="vital-label">${label}</span>
                    <span class="vital-value">${val}</span>
                    <span class="vital-unit">${unit}</span>
                </div>`
            ).join('')}</div>`
            : '<span class="none-tag">NO BASELINE RECORDED</span>';

        const hasHrRr = v.hr?.value != null && v.rr?.value != null;
        const liveChartHtml = hasHrRr
            ? `<div class="vitals-live-section" id="vitals-live-section">
                <div class="vitals-live-head">
                    <span class="vitals-live-title">LIVE TRACE — HR / RR</span>
                    <span class="vitals-live-hint">Dashed = baseline · PTT: name + &quot;vitals&quot;</span>
                </div>
                <div class="vitals-canvas-wrap">
                    <canvas id="vitals-hr-rr-canvas" class="vitals-hr-rr-canvas"></canvas>
                </div>
                <div class="vitals-legend-row">
                    <span class="leg-hr">━ HR (bpm)</span>
                    <span class="leg-rr">━ RR (/min)</span>
                    <span class="leg-bl">┌ baseline</span>
                </div>
            </div>`
            : '';

        el.innerHTML = `
            <div class="patient-header">
                <span class="patient-rank">${p.rank || ''}</span>
                <span class="patient-name">${esc(p.name)}</span>
            </div>

            <div class="bio-grid">
                <div class="bio-cell"><span class="bio-label">AGE/SEX</span><span class="bio-value">${age} ${gender}</span></div>
                <div class="bio-cell"><span class="bio-label">DOB</span><span class="bio-value">${p.dob || '—'}</span></div>
                <div class="bio-cell"><span class="bio-label">BLOOD</span><span class="bio-value blood-val">${p.blood_type || 'UNK'}</span></div>
                <div class="bio-cell"><span class="bio-label">HT / WT</span><span class="bio-value">${ht} / ${wt}${bmi ? ` (BMI ${bmi})` : ''}</span></div>
                <div class="bio-cell"><span class="bio-label">MOS</span><span class="bio-value">${p.mos || '—'}</span></div>
                <div class="bio-cell"><span class="bio-label">DoD ID</span><span class="bio-value">${p.dod_id || '—'}</span></div>
                <div class="bio-cell"><span class="bio-label">LAST DEPLOY</span><span class="bio-value">${p.last_deployment || '—'}</span></div>
                <div class="bio-cell"><span class="bio-label">TETANUS</span><span class="bio-value">${p.tetanus_date || '—'}</span></div>
            </div>

            <div class="detail-section">
                <h4>BASELINE VITALS</h4>
                ${liveChartHtml}
                ${vitalsGridHtml}
            </div>
            <div class="detail-section">
                <h4>MEDICATIONS — FIELD RELEVANT</h4>
                ${meds}
            </div>
            <div class="detail-section">
                <h4>RELEVANT HISTORY</h4>
                ${conditions}
            </div>
            <div class="detail-section detail-section-secondary">
                <h4>DRUG CONTRAINDICATIONS</h4>
                ${allergies}
            </div>
            <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-solid)">
                <div class="panel-title" style="margin-top:0">UNIT ROSTER</div>
                <div class="roster-list" id="roster-list-inner"></div>
            </div>
        `;
        renderRosterInto(document.getElementById('roster-list-inner'));
        if (hasHrRr) {
            setTimeout(() => startVitalsLiveGraph(p), 80);
        }
    }

    function esc(t) {
        if (!t) return '';
        const d = document.createElement('div');
        d.textContent = t;
        return d.innerHTML;
    }

    function renderDefaultDetail(el) {
        el.innerHTML = `
            <div class="panel-title" style="margin-top:0">UNIT ROSTER</div>
            <div class="roster-list" id="roster-list"></div>
        `;
    }

    let _patients = [];

    function renderRoster(patients) {
        _patients = patients;
        const container = document.getElementById('roster-list');
        if (container) renderRosterInto(container);
    }

    function renderRosterInto(container) {
        if (!container) return;
        if (!_patients || _patients.length === 0) {
            container.innerHTML = '<div class="none-tag">NO PERSONNEL</div>';
            return;
        }
        container.innerHTML = _patients.map(p => {
            const blood = p.blood_type
                ? `<span class="roster-blood">${p.blood_type}</span>`
                : '<span class="roster-blood roster-blood-unk">UNK</span>';
            return `
            <div class="roster-item" onclick="App.selectPatient('${p.id}')">
                <span class="name">${p.name} ${blood}</span>
                <span class="rank">${p.rank || ''}</span>
            </div>`;
        }).join('');
    }

    function setIsolationCompare(data) {
        const wrap = document.getElementById('isolation-compare-wrap');
        const note = document.getElementById('isolation-compare-note');
        const preEl = document.getElementById('audio-pre-isolation');
        const postEl = document.getElementById('audio-post-isolation');
        if (!wrap || !preEl || !postEl) return;

        if (_comparePreUrl) {
            URL.revokeObjectURL(_comparePreUrl);
            _comparePreUrl = null;
        }
        if (_comparePostUrl) {
            URL.revokeObjectURL(_comparePostUrl);
            _comparePostUrl = null;
        }
        preEl.removeAttribute('src');
        postEl.removeAttribute('src');

        if (note) {
            note.hidden = true;
            note.textContent = '';
        }

        if (!data) {
            wrap.hidden = true;
            return;
        }

        if (data.omitted) {
            wrap.hidden = false;
            if (note) {
                note.hidden = false;
                note.textContent = data.reason
                    ? `Comparison audio omitted: ${data.reason}`
                    : 'Comparison audio omitted (size limit).';
            }
            return;
        }

        if (note) note.hidden = true;

        function attach(el, b64, mime, which) {
            try {
                const binary = atob(b64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                const blob = new Blob([bytes], { type: mime || 'audio/wav' });
                const url = URL.createObjectURL(blob);
                if (which === 'pre') _comparePreUrl = url;
                else _comparePostUrl = url;
                el.src = url;
            } catch (e) {
                console.warn('Isolation compare decode failed:', e);
            }
        }

        attach(preEl, data.pre_b64, data.pre_mime, 'pre');
        attach(postEl, data.post_b64, data.post_mime, 'post');
        wrap.hidden = false;
    }

    function setVoicePipelineReport(report) {
        const bar = document.getElementById('stt-confidence-bar');
        if (!bar) return;
        if (!report) {
            bar.classList.add('stt-confidence-bar--standby');
            bar.innerHTML = `
                <div class="stt-line-primary stt-line-standby">STT confidence — standby</div>
                <div class="stt-line-pipeline stt-line-standby">After PTT: Meta DNS64 → ElevenLabs isolation → Scribe v2; scores populate here.</div>`;
            return;
        }

        bar.classList.remove('stt-confidence-bar--standby');

        const lang = report.stt_language_pct != null ? `${report.stt_language_pct}%` : '—';
        const words = report.stt_words_pct != null ? `${report.stt_words_pct}%` : '—';

        const dnsMap = {
            applied: 'Meta DNS64: applied',
            skipped_non_wav: 'Meta DNS64: skipped (non-WAV input)',
            unavailable: 'Meta DNS64: unavailable',
        };
        const isoMap = {
            applied: 'ElevenLabs isolation: applied',
            skipped_short: 'ElevenLabs isolation: skipped (clip under ~5s)',
            skipped_disabled: 'ElevenLabs isolation: disabled',
            unavailable: 'ElevenLabs isolation: unavailable',
            error: 'ElevenLabs isolation: error',
            passthrough_empty: 'ElevenLabs isolation: empty response',
        };

        const dns = dnsMap[report.meta_denoiser] || `Meta DNS64: ${report.meta_denoiser}`;
        const iso = isoMap[report.elevenlabs_isolation] || `ElevenLabs isolation: ${report.elevenlabs_isolation}`;
        const isoDetail = report.elevenlabs_isolation_detail
            ? ` <span class="stt-pipe-detail">(${escapeHtml(String(report.elevenlabs_isolation_detail))})</span>`
            : '';
        const errLine = report.stt_error
            ? `<div class="stt-line-pipeline stt-stt-err">Scribe error: ${escapeHtml(String(report.stt_error))}</div>`
            : '';

        bar.innerHTML = `
            <div class="stt-line-primary">STT (ElevenLabs Scribe v2) — language ${lang} · word confidence ${words}</div>
            <div class="stt-line-pipeline">${dns} · ${iso}${isoDetail}</div>
            ${errLine}`;
    }

    function renderResponse(text, audioB64, voicePipelineReport) {
        const box = document.getElementById('response-box');
        const audioEl = document.getElementById('audio-response');

        if (_responseAudioUrl) {
            URL.revokeObjectURL(_responseAudioUrl);
            _responseAudioUrl = null;
        }

        if (!text) {
            box.innerHTML = '<span class="none-tag">STANDBY</span>';
            if (audioEl) {
                audioEl.removeAttribute('src');
                audioEl.style.display = 'none';
            }
            const ttsClear = document.getElementById('tts-play-btn');
            if (ttsClear) ttsClear.style.display = 'none';
            setVoicePipelineReport(null);
            setIsolationCompare(null);
            return;
        }

        let html = escapeHtml(text);

        html = html.replace(/\*{3}\s*ALLERGY ALERT:.*?\*{3}/g,
            m => `<span class="med-conflict-line">${m}</span>`);
        html = html.replace(/ALLERGY ALERT:/g,
            '<span class="med-conflict-line">ALLERGY ALERT:</span>');
        html = html.replace(/IF DRAWING MEDS \/ BLOOD PRODUCTS:/g,
            '<span class="response-section-label">IF DRAWING MEDS / BLOOD PRODUCTS:</span>');
        html = html.replace(/MED CONFLICT:/g,
            '<span class="med-conflict-line">MED CONFLICT:</span>');
        html = html.replace(/COMORBID:/g,
            '<span class="comorbid-line">COMORBID:</span>');
        html = html.replace(/CONDITION NOTE:/g,
            '<span class="comorbid-line">CONDITION NOTE:</span>');
        html = html.replace(/^BLOOD TYPE:/gm,
            '<span class="blood-line">BLOOD TYPE:</span>');
        html = html.replace(/^MARCH:/gm,
            '<span class="march-line">MARCH:</span>');
        html = html.replace(/^INJURY:/gm,
            '<span class="injury-line">INJURY:</span>');
        html = html.replace(/MEDEVAC: URGENT/g,
            '<span style="color:var(--t1);font-weight:700">MEDEVAC: URGENT</span>');
        html = html.replace(/MEDEVAC: PRIORITY/g,
            '<span style="color:var(--t2);font-weight:700">MEDEVAC: PRIORITY</span>');
        html = html.replace(/MEDEVAC: ROUTINE/g,
            '<span style="color:var(--t3)">MEDEVAC: ROUTINE</span>');
        html = html.replace(/CATEGORY: T1 IMMEDIATE/g,
            '<span style="color:var(--t1);font-weight:700">CATEGORY: T1 IMMEDIATE</span>');
        html = html.replace(/CATEGORY: T2 DELAYED/g,
            '<span style="color:var(--t2);font-weight:700">CATEGORY: T2 DELAYED</span>');
        html = html.replace(/CATEGORY: T3 MINIMAL/g,
            '<span style="color:var(--t3);font-weight:700">CATEGORY: T3 MINIMAL</span>');
        html = html.replace(/CATEGORY: T4 EXPECTANT/g,
            '<span style="color:var(--t4);font-weight:700">CATEGORY: T4 EXPECTANT</span>');
        html = html.replace(/(TREATMENT:)/g,
            '<span style="color:var(--text-heading)">$1</span>');

        box.innerHTML = html;

        if (!audioEl) return;

        const ttsBtn = document.getElementById('tts-play-btn');
        const showTtsBtn = () => {
            if (ttsBtn) ttsBtn.style.display = 'inline-flex';
        };
        const hideTtsBtn = () => {
            if (ttsBtn) ttsBtn.style.display = 'none';
        };

        if (ttsBtn) {
            ttsBtn.onclick = null;
        }

        if (audioB64) {
            try {
                const binary = atob(audioB64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) {
                    bytes[i] = binary.charCodeAt(i);
                }
                const blob = new Blob([bytes], { type: 'audio/mpeg' });
                _responseAudioUrl = URL.createObjectURL(blob);
                audioEl.src = _responseAudioUrl;
                audioEl.style.display = 'block';
                audioEl.setAttribute('playsinline', '');
                showTtsBtn();
                if (ttsBtn) {
                    ttsBtn.onclick = () => {
                        audioEl.play().catch((err) => console.warn('TTS play failed:', err));
                    };
                }
                audioEl.load();
                audioEl.play().catch(() => {
                    /* Autoplay often blocked until user gesture — button remains visible */
                });
            } catch (e) {
                console.error('Failed to load TTS audio:', e);
                audioEl.removeAttribute('src');
                audioEl.style.display = 'none';
                hideTtsBtn();
            }
        } else {
            audioEl.removeAttribute('src');
            audioEl.style.display = 'none';
            hideTtsBtn();
        }

        setVoicePipelineReport(voicePipelineReport || null);
    }

    function updateStatus(config) {
        document.getElementById('status-denoiser').className =
            `status-dot ${config.denoiser_available ? 'on' : 'off'}`;
        document.getElementById('status-elevenlabs').className =
            `status-dot ${config.elevenlabs_available ? 'on' : 'off'}`;
        document.getElementById('status-ai').className =
            `status-dot ${config.ai_available ? 'on' : 'off'}`;

        const aiLabel = document.getElementById('ai-label');
        if (aiLabel) {
            const b = config.llm_backend;
            aiLabel.textContent = b ? `AI (${b})` : 'AI';
        }

        const name = (config.unit_name || '1st Platoon Alpha Co').toUpperCase().replace(/_/g, ' ');
        document.getElementById('unit-name').textContent = name;

        document.getElementById('mode-toggle').checked = config.mode === 'ai';
        updateModeLabels(config.mode);
    }

    function updateModeLabels(mode) {
        document.getElementById('label-rules').classList.toggle('active', mode === 'rules');
        document.getElementById('label-ai').classList.toggle('active', mode === 'ai');
    }

    function setTranscript(text) {
        document.getElementById('transcript-text').textContent = text || 'STANDBY';
    }

    function setLastCommand(text) {
        const el = document.getElementById('last-command');
        if (el) el.textContent = text || '';
    }

    function setPttState(state) {
        const btn = document.getElementById('ptt-button');
        btn.className = `ptt-button ${state}`;
        const label = btn.querySelector('.ptt-label');
        if (state === 'recording') label.textContent = 'REC';
        else if (state === 'processing') label.textContent = 'WAIT';
        else label.textContent = 'PTT';
    }

    function setScenarioActive(id) {
        document.querySelectorAll('.scenario-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.scenario === id);
        });
    }

    function escapeHtml(t) {
        const d = document.createElement('div');
        d.textContent = t;
        return d.innerHTML;
    }

    return {
        renderTriageQueue, renderPatientDetail, renderResponse,
        renderRoster, updateStatus, updateModeLabels,
        setTranscript, setLastCommand, setPttState, setScenarioActive,
        scrollVitalsIntoView, stopVitalsLiveGraph, startVitalsLiveGraph,
        setIsolationCompare,
    };
})();
