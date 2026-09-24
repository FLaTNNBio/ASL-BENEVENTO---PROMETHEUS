// Extracted from index.html — keep behavior identical.
// Loaded as an ES module to avoid global leaks; we will re-expose functions used by inline handlers on `window`.

(function () {

// === Tab switch (unica fonte di verità) ===
// Usa i tab ARIA: mode-algo / mode-editor / mode-config
// === Tab switch (unica fonte di verità) ===
    function setPanelMode(mode) {
        if (mode === 'mode-algo' || mode === 'mode-editor') {
            try {
                swapParamProfile(mode);
            } catch {
            }
        }
        const tabs = document.querySelectorAll('.mode-switch [role="tab"]');
        const panes = document.querySelectorAll('.mode-pane[role="tabpanel"]');

        let activated = false;
        tabs.forEach(btn => {
            const target = btn.getAttribute('aria-controls');
            const active = (target === mode);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
            btn.classList.toggle('is-active', active);
            if (active) activated = true;
        });
        panes.forEach(p => p.hidden = (p.id !== mode));
        try {
            localStorage.setItem('panel.mode', mode);
        } catch {
        }
        if (!activated) {
            document.querySelector(`.mode-switch [role="tab"][aria-controls="${mode}"]`)
                ?.dispatchEvent(new Event('click', {bubbles: true}));
        }
        if (mode === 'mode-editor') {
            try {
                refreshParamSummary();
            } catch {
            }
        }
    }

    function euroSafe(n) {
        try {
            return Number(n || 0).toLocaleString('it-IT', {style: 'currency', currency: 'EUR'})
        } catch {
            return (n || 0) + ' €'
        }
    }

    function fmtCSV(s) {
        return String(s || '').split(',').filter(Boolean).map(p => p.trim()).join(' · ')
    }

    function paramGlanceFromBody(body) {
        const T = fmtCSV(body.T) || '—';
        const medici = (body.doctors_total || '—') + (body.doctors_budget_mode ? ` (${body.doctors_budget_mode})` : '');
        const budget = body.budget_total ? euroSafe(body.budget_total) : '—';
        // se vuoi una 4a chip, aggiungi ad es. vincolo medico:
        const vincolo = (body.doctor_cover || 'off') + (body.doctor_codes ? ` · ${fmtCSV(body.doctor_codes)}` : '');

        return [
            `<span class="chip"><span class="k">Soglie T</span><span class="v">${T}</span></span>`,
            `<span class="chip"><span class="k">Medici</span><span class="v">${medici}</span></span>`,
            `<span class="chip"><span class="k">Budget</span><span class="v">${budget}</span></span>`,
            `<span class="chip"><span class="k">Vincolo</span><span class="v">${vincolo}</span></span>`
        ].join('');
    }

    function cfgRecapPills(body) {
        const fmt = (s) => String(s || '').split(',').filter(Boolean).map(p => p.trim()).join(' · ');
        const budget = body?.budget_total ? euroSafe(body.budget_total) : '—';
        const medici = (body?.doctors_total ?? '—') + (body?.doctors_budget_mode ? ` (${body.doctors_budget_mode})` : '');
        return [
            `<span class="kchip"><span class="k">Soglie T</span> <span class="v">${fmt(body?.T) || '—'}</span></span>`,
            `<span class="kchip"><span class="k">Medici</span> <span class="v">${medici}</span></span>`,
            `<span class="kchip"><span class="k">Budget</span> <span class="v">${budget}</span></span>`
        ].join('');
    }


    function cfgRecapList(body) {
        // se hai già paramSummaryFromBody, riusala per la tabella completa
        if (typeof paramSummaryFromBody === 'function') return paramSummaryFromBody(body || {});
        const row = (k, v) => `<div class="k">${k}</div><div class="v">${v || '—'}</div>`;
        const fmt = (s) => String(s || '').split(',').filter(Boolean).map(p => p.trim()).join(' · ');
        return [
            row('Soglie T', fmt(body?.T)),
            row('Velocità relative', fmt(body?.type_speed)),
            row('CAPEX unitari', fmt(body?.purchase_costs)),
            row('OPEX unitari', fmt(body?.opex_costs)),
            row('Staff per tipo', fmt(body?.staff_per_type)),
            row('Vincolo medico', (body?.doctor_cover || 'off') + (body?.doctor_codes ? ` · ${fmt(body.doctor_codes)}` : '')),
            row('Medici totali', (body?.doctors_total || '—') + (body?.doctors_budget_mode ? ` (${body.doctors_budget_mode})` : '')),
            row('Budget', body?.budget_total ? euroSafe(body.budget_total) : '—'),
            row('Basi', (body?.bases || '—') + ' · limit=' + (body?.limit_bases || 0)),
            row('Full coverage', body?.full_coverage || '—'),
            row('Reloc. PSAUT', body?.reloc_psaut || 'off'),
            row('Threads / Time limit', (body?.threads || '—') + ' / ' + (body?.time_limit_sec || '—'))
        ].join('');
    }


    const _origRefreshParamSummary = typeof refreshParamSummary === 'function' ? refreshParamSummary : null;

    function refreshParamSummary() {
        const body = buildRunBody();
        try {
            Object.assign(body, readNursesAndCouplingFromUI());
        } catch {
        }
        /*// === FORCE ANY 100%: preset pro-copertura (senza modificare la UI) ===
        try {
            // Obiettivo: massimizza copertura, ignora costo
            body.objective = 'max_cover_budget';
            body.lambda_cost = 0;

            // Niente tetto economico rigido
            if ('budget_total' in body) delete body.budget_total;
            body.budget_mode = body.budget_mode || 'purchase';

            // Non spegnere famiglie con medico
            body.turnoff_doctor_families = 'off';

            // Copertura con medico non deve bloccare ANY
            body.doctor_cover = 'feasible-only';

            // Allarga spazio decisionale
            body.bases = 'ALL';
            body.reloc_psaut = 'on';

            // Assicura type-speed PSAUT per evitare warning
            const tsMap = parsePairs(body.type_speed || '');
            if (!('PSAUT' in tsMap)) tsMap.PSAUT = '0.90';
            body.type_speed = stringifyPairs(tsMap);
        } catch (e) {
            console.warn('[FORCE_ANY] preset non applicato:', e);
        }*/


// dettagli (kv) – usa la tua funzione già esistente se c'è
        if (_origRefreshParamSummary) {
            try {
                _origRefreshParamSummary();
            } catch {
            }
        } else {
            const kv = document.getElementById('paramSummary');
            if (kv) kv.innerHTML = paramSummaryFromBody(body);
        }
        // glance (chip)
        const glance = document.getElementById('paramGlance');
        if (glance) glance.innerHTML = paramGlanceFromBody(body);
    }

// testo summary Mostra/Nascondi
    document.getElementById('paramDetails')?.addEventListener('toggle', (e) => {
        const sm = e.currentTarget.querySelector('summary');
        if (sm) sm.textContent = e.currentTarget.open ? 'Nascondi dettagli' : 'Mostra dettagli';
    });

    function bindTabs() {
        document.querySelectorAll('.mode-switch .tab[role="tab"]').forEach(btn => {
            btn.addEventListener('click', () => setPanelMode(btn.getAttribute('aria-controls')));
        });
        let saved = 'mode-algo';
        try {
            saved = localStorage.getItem('panel.mode') || 'mode-algo';
        } catch {
        }
        if (!document.getElementById(saved)) saved = 'mode-algo'; // <-- fallback se "mode-budget" non esiste più
        setPanelMode(saved);
    }


    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindTabs, {once: true});
    } else {
        bindTabs();
    }
    window.setPanelMode = setPanelMode;
})();


// ======= CONFIG EXPORT / IMPORT =======

// Cattura tutto ciò che serve a ricostruire lo stato
function buildConfigSnapshot() {
    const body = buildRunBody();
    // NEW: porta dentro anche i parametri infermieri & coupling
    try {
        Object.assign(body, readNursesAndCouplingFromUI());
    } catch {
    }

    return {
        version: 1,
        ts: new Date().toISOString(),
        last_run_kind: LAST_RUN_KIND || null,
        run_url: RUN_URL || null,
        body,
        plan: (Array.isArray(MP_PLAN) ? MP_PLAN : []).map(r => ({...r}))
    };
}


function downloadConfigSnapshot() {
    try {
        const snap = buildConfigSnapshot();
        const blob = new Blob([JSON.stringify(snap, null, 2)], {type: 'application/json'});
        const a = document.createElement('a');
        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.href = URL.createObjectURL(blob);
        a.download = `config_${ts}.json`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            URL.revokeObjectURL(a.href);
            a.remove();
        }, 800);
    } catch (e) {
        alert('Impossibile esportare la configurazione: ' + (e?.message || e));
    }
}

function showCfgLoadRecap({title, subtitle, body, ts, run_url} = {}) {
    const box = document.getElementById('cfgLoadRecap');
    const tEl = document.getElementById('cfgRecapTitle');
    const sEl = document.getElementById('cfgRecapSubtitle');
    const pills = document.getElementById('cfgRecapPills');
    const kvEl = document.getElementById('cfgRecapKV');
    if (!box) return;

    // --- util ---
    const euro = n => {
        if (n === null || n === undefined || n === '') return '—';
        const v = Number(String(n).replace(/[^\d.,-]/g, '').replace(',', '.'));
        return isFinite(v) ? v.toLocaleString('it-IT', {style: 'currency', currency: 'EUR'}) : String(n);
    };
    const norm = v => (v ?? '—');
    const asLines = (v) => {
        if (!v) return [];
        if (Array.isArray(v)) return v.map(String);
        if (typeof v === 'string') return v.split(',').map(s => s.trim()).filter(Boolean);
        if (typeof v === 'object') return Object.entries(v).map(([k, val]) => `${k}=${val}`);
        return [String(v)];
    };
    const fmtSpeed = (arr) => asLines(arr).map(x =>
        x.replace(/=([\d.]+)x?$/i, (_m, g) => `=${parseFloat(g).toFixed(2)}×`)
    );
    const fmtMoneyLines = (arr) => asLines(arr).map(x => {
        const m = x.match(/^([^=]+)=(.+)$/);
        if (!m) return x;
        return `${m[1]}=${euro(m[2])}`;
    });

    // --- header ---
    if (tEl) tEl.textContent = title || 'Config caricata';
    if (sEl) {
        const bits = [];
        if (subtitle) bits.push(String(subtitle));
        if (ts) bits.push(new Date(ts).toLocaleString('it-IT'));
        if (run_url) bits.push(`/runs/${String(run_url).split('/').pop()}`);
        sEl.textContent = bits.filter(Boolean).join('  •  ');
    }

    // --- pillole (compatte, come in Valutazione) ---
    const doctorBadge = (body?.doctors_total != null)
        ? `${body.doctors_total} ${body?.doctors_budget_mode ? `(${body.doctors_budget_mode})` : ''}`
        : '—';
    const threshold = norm(body?.T && asLines(body.T).join(' · '));

    if (pills) {
        pills.innerHTML = [
            ['Soglie T', threshold],
            ['Medici', doctorBadge],
            ['Budget', body?.budget_total ? euro(body.budget_total) : '—'],
            ['Vincolo', [norm(body?.doctor_cover), asLines(body?.doctor_codes).join(' · ')].filter(Boolean).join(' · ')]
        ].map(([k, v]) => `
      <span class="pill ghost">
        <span class="k">${k}</span><span class="v">${v}</span>
      </span>
    `).join('');
    }

    // --- dettaglio: usa paramSummaryFromBody se presente, altrimenti fallback esteso ---
    if (kvEl) {
        if (typeof window.paramSummaryFromBody === 'function') {
            // Renderer unificato (garantisce TUTTI i parametri)
            kvEl.innerHTML = window.paramSummaryFromBody(body || {});
        } else {
            // Fallback in stile dt/dd, ESTESO con tutti i parametri extra
            const rows = [
                ['Soglie T', asLines(body?.T)],
                ['Velocità relative', fmtSpeed(body?.type_speed)],
                ['CAPEX unitari', fmtMoneyLines(body?.purchase_costs)],
                ['OPEX unitari', fmtMoneyLines(body?.opex_costs)],
                ['Staff per tipo', asLines(body?.staff_per_type)],
                ['Vincolo medico', [norm(body?.doctor_cover), asLines(body?.doctor_codes).join(' · ')].filter(Boolean).join(' · ')],
                ['Medici totali', doctorBadge],
                ['Budget', body?.budget_total ? euro(body.budget_total) : '—'],
                ['Basi', [norm(body?.bases), body?.limit_bases ? `limit=${body.limit_bases}` : ''].filter(Boolean).join(' · ')],
                ['Full coverage', norm(body?.full_coverage)],
                ['Reloc. PSAUT', norm(body?.reloc_psaut || 'off')],
                ['Threads / Time limit', `${norm(body?.threads)} / ${norm(body?.time_limit_sec)}`],

                // === Parametri aggiuntivi dell’algoritmo ===
                // ['Relax weights', asLines(body?.relax_weights)],
                ['Objective / λcost', [norm(body?.objective), (body?.lambda_cost ?? '—')].join(' / ')],
                ['Turnoff doctor families', norm(body?.turnoff_doctor_families)],
                ['PSAUT vincoli', [`min=${norm(body?.psaut_min)}`, `exact=${norm(body?.psaut_exact)}`].join(' · ')],
                ['Infermieri per tipo', asLines(body?.nurses_per_type)],
                ['Budget infermieri', [`tot=${norm(body?.nurses_total)}`, `unit=${euro(body?.nurse_unit_opex)}`].join(' · ')],
                ['Trasporto automedica', norm(body?.auto_med_transport)]
            ];

            kvEl.innerHTML = rows.map(([k, v]) => {
                const lines = Array.isArray(v) ? v : asLines(v);
                const dd = lines.length
                    ? `<ul class="kv-lines">${lines.map(s => `<li>${s}</li>`).join('')}</ul>`
                    : `<div class="kv-val">—</div>`;
                return `<dt>${k}</dt><dd>${dd}</dd>`;
            }).join('');
        }
    }

    box.hidden = false;
}


window.showCfgLoadRecap = showCfgLoadRecap;


// Applica i valori del JSON alla UI e agli hidden
function applyConfigSnapshot(snap) {
    if (!snap || typeof snap !== 'object') throw new Error('Snapshot vuoto');

    const body = snap.body || {};

    // ---- helper
    const setVal = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.value = (v ?? '');
    };
    const setChk = (id, on) => {
        const el = document.getElementById(id);
        if (el) el.checked = !!on;
    };
    const tryNum = (x) => (x == null || x === '' ? '' : Number(x));

    // === Soglie T
    (function restoreT() {
        const T = parsePairs(body.T || '');
        const def = {ROSSO: 8, GIALLO: 20, VERDE: 30, BIANCO: 45};
        ['ROSSO', 'GIALLO', 'VERDE', 'BIANCO'].forEach(k => {
            const slider = document.getElementById('t' + k);
            if (slider) slider.value = Number(T[k] ?? def[k]);
        });
        // sync -> hidden
        if (typeof syncParamT === 'function') syncParamT();
    })();

    // === Type-speed
    (function restoreTS() {
        const TS = parsePairs(body.type_speed || '');
        const def = {AUTO_MED: 0.90, AMB_ALS: 0.98, AMB_ILS: 1.00};
        ['AUTO_MED', 'AMB_ALS', 'AMB_ILS'].forEach(k => {
            const s = document.getElementById('sp' + k);
            if (s) s.value = Number(TS[k] ?? def[k]);
            const o = document.getElementById('sp' + k + '_val');
            if (o && s) o.textContent = Number(s.value).toFixed(2) + '×';
        });
        if (typeof syncTypeSpeed === 'function') syncTypeSpeed();
    })();

    // === CAPEX / OPEX
    (function restoreCosts() {
        const CX = parsePairs(body.purchase_costs || '');
        const OX = parsePairs(body.opex_costs || '');
        ['AUTO_MED', 'AMB_ALS', 'AMB_ILS', 'PSAUT'].forEach(k => {
            const cx = document.getElementById('cx' + k);
            if (cx) cx.value = tryNum(CX[k] ?? 0);
            const ox = document.getElementById('ox' + k);
            if (ox) ox.value = tryNum(OX[k] ?? 0);
        });
        if (typeof syncCapex === 'function') syncCapex();
        if (typeof syncOpex === 'function') syncOpex();
    })();

    // === Doctor codes (checkbox) + modalità
    (function restoreDoctors() {
        const codes = new Set(parseList(body.doctor_codes || ''));
        [['ROSSO', 'dcROSSO'], ['GIALLO', 'dcGIALLO'], ['VERDE', 'dcVERDE'], ['BIANCO', 'dcBIANCO']]
            .forEach(([k, id]) => setChk(id, codes.has(k)));
        setVal('docMode', body.doctors_budget_mode || document.getElementById('docMode')?.value || 'absolute');
        setVal('docTotal', body.doctors_total ?? document.getElementById('docTotal')?.value ?? '');
        // -> hidden
        setVal('docCodes', body.doctor_codes || '');
        setVal('docCover', body.doctor_cover || document.getElementById('docCover')?.value || 'strict');
        if (typeof syncDocCodes === 'function') syncDocCodes();
    })();

    // === Staff per tipo
    (function restoreStaff() {
        const ST = parsePairs(body.staff_per_type || '');
        const def = {PSAUT: 6, AUTO_MED: 6, AMB_ALS: 6};
        [['stPSAUT', 'PSAUT'], ['stAUTO_MED', 'AUTO_MED'], ['stAMB_ALS', 'AMB_ALS']]
            .forEach(([id, k]) => setVal(id, tryNum(ST[k] ?? def[k])));
        if (typeof syncStaff === 'function') syncStaff();
    })();

    // === Budget economico (UI ↔ hidden)
    (function restoreBudget() {
        const bt = body.budget_total ?? '';
        let bm = (body.budget_mode || '').toLowerCase();
        // mappa solver→UI
        const mapHiddenToUi = (v) => v === 'purchase' ? 'capex' : (v === 'all' ? 'capex_opex' : '');
        const uiBM = mapHiddenToUi(bm);
        setVal('uiBudgetTotal', bt);
        const sel = document.getElementById('uiBudgetMode');
        if (sel) sel.value = uiBM;
        // e aggiorna gli hidden usati dal backend
        const hBT = document.getElementById('budgetTotal');
        if (hBT) hBT.value = bt;
        const hBM = document.getElementById('budgetMode');
        if (hBM) hBM.value = (uiBM === 'capex' ? 'purchase' : uiBM === 'capex_opex' ? 'all' : '');
    })();
// === NEW: infermieri & coupling ===
    (function restoreNurses() {
        // usa il setVal già definito sopra

        // Supporta sia stringa "A=1,B=2" sia oggetto {A:1,B:2}
        let pairs = {};
        if (body.nurses_per_type && typeof body.nurses_per_type === 'object') {
            pairs = body.nurses_per_type;
        } else {
            pairs = String(body.nurses_per_type || '')
                .split(/[;,]+/).map(s => s.trim()).filter(Boolean)
                .reduce((a, s) => {
                    const [k, v] = s.split('=');
                    a[k?.trim()] = Number(v || 0);
                    return a;
                }, {});
        }

        setVal('nuPSAUT', pairs.PSAUT ?? document.getElementById('nuPSAUT')?.value ?? '');
        setVal('nuAUTO_MED', pairs.AUTO_MED ?? document.getElementById('nuAUTO_MED')?.value ?? '');
        setVal('nuAMB_ALS', pairs.AMB_ALS ?? document.getElementById('nuAMB_ALS')?.value ?? '');
        setVal('nuAMB_ILS', pairs.AMB_ILS ?? document.getElementById('nuAMB_ILS')?.value ?? '');

        if (body.nurses_total != null) setVal('nurTotal', body.nurses_total);
        if (body.nurse_unit_opex != null) setVal('nurOpex', body.nurse_unit_opex);

        // default 'off' se assente
        setVal('autoMedCoupling', body.auto_med_transport ?? (document.getElementById('autoMedCoupling')?.value || 'off'));
    })();

    // === Avanzate / varie
    setVal('bases', body.bases ?? 'ATT_POT');
    setVal('limitBases', body.limit_bases ?? '0');
    setVal('fullcov', body.full_coverage ?? 'strict');
    setVal('psautMin', body.psaut_min ?? (document.getElementById('psautMin')?.value || ''));
    setVal('psautExact', body.psaut_exact ?? (document.getElementById('psautExact')?.value || ''));
    setVal('reloc', body.reloc_psaut ?? (document.getElementById('reloc')?.value || 'off'));
    setVal('threads', body.threads ?? (document.getElementById('threads')?.value || '8'));
    setVal('tl', body.time_limit_sec ?? (document.getElementById('tl')?.value || ''));

    // Verbose (switch ↔ select hidden)
    const vSel = document.getElementById('verbose');
    const vSw = document.getElementById('verboseSwitch');
    if (vSel) vSel.value = (body.verbose && String(body.verbose).trim()) ? '--verbose' : (vSel.value || '');
    if (vSw) vSw.checked = (vSel?.value === '--verbose');

    // === Piano su mappa (editor)
    if (Array.isArray(snap.plan)) {
        MP_PLAN = snap.plan.map(r => ({
            base_comune: r.base_comune,
            tipo: r.tipo,
            qty: Number(r.qty || 0),
            source: r.source || 'any'
        }));
        MP_COUNTS_BY_BASE = new Map();
        MP_PLAN.forEach(r => {
            const m = MP_COUNTS_BY_BASE.get(r.base_comune) || {};
            m[r.tipo] = (m[r.tipo] || 0) + Number(r.qty || 0);
            MP_COUNTS_BY_BASE.set(r.base_comune, m);
        });
        if (typeof mp_renderPlanTable === 'function') mp_renderPlanTable();
        if (typeof mp_updateEditorButtons === 'function') mp_updateEditorButtons();
    }

    // === Modalità pannello
    if (typeof window.setPanelMode === 'function') {
        const pane = (snap.last_run_kind === 'editor') ? 'mode-editor' : 'mode-algo';
        try {
            window.setPanelMode(pane);
        } catch {
        }
    }

    // (opzionale) riusa il run_url della snapshot
    if (snap.run_url) {
        RUN_URL = snap.run_url;
        try {
            updateDownloadButtons();
        } catch {
        }
    }
}

// Collega i pulsanti (insieme agli altri in mp_bindUI)
function bindConfigIO() {
    const btnDl = document.getElementById('dlConfig');
    if (btnDl && !btnDl.dataset.bound) {
        btnDl.dataset.bound = '1';
        btnDl.addEventListener('click', downloadConfigSnapshot);
    }
    const inpUp = document.getElementById('upConfig');
    if (inpUp && !inpUp.dataset.bound) {
        inpUp.dataset.bound = '1';
        inpUp.addEventListener('change', (e) => {
            const f = e.target.files && e.target.files[0];
            if (f) importConfigFromFile(f);
            // reset per permettere ricarichi dello stesso file
            e.target.value = '';
        });
    }
}

// ==== next block ====
async function importConfigFromFile(file) {
    const text = await file.text();
    const snap = JSON.parse(text);

    await applyConfigSnapshot(snap);

    // se la snapshot ha un run, ricarica i dati e bottoni; resta in “Config”
    const hasRun = !!(snap.run_url || RUN_URL);
    const hasPlan = Array.isArray(snap.plan) && snap.plan.length > 0;

    // ... dentro importConfigFromFile(file)
    if (hasRun) {
        RUN_URL = fixRunPath(snap.run_url || RUN_URL);
        LAST_RUN_KIND = (snap.last_run_kind === 'algo' || snap.last_run_kind === 'editor')
            ? snap.last_run_kind : 'editor';
        updateDownloadButtons();
        await reloadData();
        // === Fallback: se ANY < 100, un secondo run con T minime ragionevoli ===
        try {
            const tot = covTotals(LAST_COV_ANY);
            const pct = tot && tot.pct != null ? Number(tot.pct) : null;
            if (pct != null && pct < 100) {
                const bump = {ROSSO: 10, GIALLO: 25, VERDE: 35, BIANCO: 50};
                const Tmap = parsePairs(body.T || '');
                for (const k in bump) {
                    const cur = Number(Tmap[k] || 0);
                    if (!(cur > 0) || cur < bump[k]) Tmap[k] = String(bump[k]);
                }
                body.T = stringifyPairs(Tmap);
                // Re-run con le nuove soglie
                if (log) log.textContent = (log.textContent || '') + '\n\n[Re-run] Forzo soglie minime per raggiungere 100% ANY...';
                const res2 = await fetch('/api/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                const j2 = await res2.json();
                if (j2 && j2.ok) {
                    RUN_URL = j2.out_web || fixRunPath(j2.out_dir || RUN_URL);
                    updateDownloadButtons();
                    await reloadData();
                } else {
                    console.warn('[Re-run] fallito:', j2 && (j2.error || j2));
                }
            }
        } catch (e) {
            console.warn('[FORCE_ANY] fallback non applicato:', e);
        }
// <— disegna unità
        await renderCriticita(true);        // <— AGGIUNGI: coropleta criticità (quantili ricalcolati)
        setPanelMode('mode-config');
        if (typeof showCfgLoadRecap === 'function') showCfgLoadRecap({
            body: snap.body || buildRunBody(),
            run_url: RUN_URL,
            ts: snap.ts
        });
    } else if (hasPlan) {
        await mp_eval();                    // fa reloadData() ma non accende la coropleta
        await renderCriticita(true);        // <— AGGIUNGI qui anche per i piani caricati
        setPanelMode('mode-config');
        if (typeof showCfgLoadRecap === 'function') showCfgLoadRecap({body: snap.body || buildRunBody(), ts: snap.ts});
    } else {
        setPanelMode('mode-config');
        if (typeof showCfgLoadRecap === 'function') showCfgLoadRecap({body: snap.body || buildRunBody(), ts: snap.ts});
        await renderCriticita(true);        // <— opzionale, per coerenza
    }

    // resta nella scheda Config e mostra il recap dei parametri salvati nel file
    setPanelMode('mode-config');
    showCfgLoadRecap({body: snap.body || buildRunBody(), ts: snap.ts, run_url: RUN_URL});
}

function parseNursesFromTxt(text = '') {
    const rx = /Nurses\s+required\s+by\s+active\s+slots\s*=\s*([0-9]+(?:[.,][0-9]+)?)/i;
    const m = rx.exec(text || '');
    if (!m) return NaN;
    return Number(String(m[1]).replace(',', '.'));
}


/* ===========================
*  DASHBOARD 118 — SCRIPT
* =========================== */
let LAST_RUN_KIND = null; // 'algo' o 'editor'
let RUN_URL = null;                   // URL del run (es. /runs/run_YYYYMMDD_HHMMSS)
let CONFIG = {dataDir: null};      // valorizzato da /api/config o fallback
let MP_PREVIEW_LAYER; // anteprima piano persistente

const ACTIVE_118_RUN_STORAGE_KEY =
    'planning118:activeRun:v1';


function persistActive118Run() {
    if (!RUN_URL) {
        return;
    }
    try {
        sessionStorage.setItem(ACTIVE_118_RUN_STORAGE_KEY,JSON.stringify({run_url: RUN_URL, last_run_kind: LAST_RUN_KIND || 'algo'}));
        console.log('[Planning 118] active run saved',RUN_URL);

    } catch (error) {
        console.warn('[Planning 118] active run save failed', error);
    }
}

function clearPersistedActive118Run() {
    try {
        sessionStorage.removeItem(ACTIVE_118_RUN_STORAGE_KEY);
    } catch {}
}


async function restoreActive118Run() {
    let saved = null;
    try {
        const raw =sessionStorage.getItem(ACTIVE_118_RUN_STORAGE_KEY);
        if (!raw) {
            return false;
        }
        saved =JSON.parse(raw);
    } catch {
        clearPersistedActive118Run();
        return false;
    }

    if (!saved?.run_url || typeof saved.run_url !== 'string') {
        clearPersistedActive118Run();
        return false;
    }

    const restoredUrl =fixRunPath(saved.run_url);
    if (!restoredUrl) {
        clearPersistedActive118Run();
        return false;
    }


    // Verifica che gli artifact del run esistano ancora
    const chosenExists =await fileExists(`${restoredUrl}/chosen_slots.csv`);
    const coverageExists =await fileExists(`${restoredUrl}/coverage_summary.csv`);
    if (!chosenExists || !coverageExists) {
        console.warn('[Planning 118] saved run no longer available', restoredUrl);
        clearPersistedActive118Run();
        return false;
    }


    // Ripristino stato frontend
    RUN_URL =restoredUrl;
    LAST_RUN_KIND = saved.last_run_kind === 'editor' ? 'editor': 'algo';
    console.log('[Planning 118] restoring active run', RUN_URL);

    updateDownloadButtons();
    await reloadData();
    // La mappa delle criticità viene ricostruita
    // usando la severity attualmente ripristinata.
    try {
        await renderCriticita(true);
    } catch (error) {
        console.warn('[Planning 118] criticality restore failed', error);
    }


    try {
        LAST_SIG =computeSignature();
    } catch {}
    return true;
}


// EXPLAIN RESULTS 118
let EXPLAIN_118_LOADED_RUN_ID = null;

const EXPLAIN_118_CACHE_VERSION = 'v2';

const EXPLAIN_118_INFLIGHT =
    new Map();


function explain118StorageKey(
    runId
) {

    return (
        `explain118:${EXPLAIN_118_CACHE_VERSION}:`
        + runId
    );
}


function getCachedExplain118(
    runId
) {

    if (!runId) {
        return null;
    }


    const key =
        explain118StorageKey(
            runId
        );


    try {

        const raw =
            sessionStorage.getItem(
                key
            );


        if (!raw) {

            console.log(
                '[Explain Results 118] '
                + 'CACHE MISS',
                runId
            );

            return null;
        }


        const data =
            JSON.parse(
                raw
            );


        if (
            data?.status !== 'ok'
            || data?.run_id !== runId
            || !data?.explanation
        ) {

            sessionStorage.removeItem(
                key
            );

            console.log(
                '[Explain Results 118] '
                + 'CACHE INVALID',
                runId
            );

            return null;
        }


        console.log(
            '[Explain Results 118] '
            + 'CACHE HIT',
            runId
        );


        return data;


    } catch (error) {

        console.warn(
            '[Explain Results 118] '
            + 'cache read error',
            error
        );

        return null;
    }
}


function cacheExplain118(
    runId,
    data
) {

    if (
        !runId
        || data?.status !== 'ok'
        || data?.run_id !== runId
    ) {

        return;
    }


    try {

        sessionStorage.setItem(
            explain118StorageKey(
                runId
            ),
            JSON.stringify(
                data
            )
        );


        console.log(
            '[Explain Results 118] '
            + 'CACHE SAVED',
            runId
        );


    } catch (error) {

        console.warn(
            '[Explain Results 118] '
            + 'cache write error',
            error
        );
    }
}


function removeCachedExplain118(
    runId
) {

    if (!runId) {
        return;
    }


    try {

        sessionStorage.removeItem(
            explain118StorageKey(
                runId
            )
        );


        console.log(
            '[Explain Results 118] '
            + 'CACHE REMOVED',
            runId
        );


    } catch (error) {
        console.warn('[Explain Results 118] cache remove error', error);
    }
}


function clearAllExplain118Cache() {

    try {

        const keysToRemove = [];


        for (
            let index = 0;
            index < sessionStorage.length;
            index += 1
        ) {

            const key =
                sessionStorage.key(
                    index
                );


            if (
                key
                && key.startsWith(
                    'explain118:'
                )
            ) {

                keysToRemove.push(
                    key
                );
            }
        }


        for (
            const key
            of keysToRemove
        ) {

            sessionStorage.removeItem(
                key
            );
        }


        console.log(
            '[Explain Results 118] '
            + 'all cached explanations removed'
        );


    } catch (error) {

        console.warn(
            '[Explain Results 118] '
            + 'cache reset failed',
            error
        );
    }


    EXPLAIN_118_INFLIGHT.clear();

    EXPLAIN_118_LOADED_RUN_ID =
        null;
}


function updateReset118Button() {

    const button =
        document.getElementById(
            'btnReset118'
        );


    if (!button) {
        return;
    }


    button.hidden =
        !current118RunId();
}

function current118RunId() {

    if (!RUN_URL) {return null;}
    const normalized = String(RUN_URL).replace(/\\/g, '/').replace(/\/+$/, '');
    const parts = normalized.split('/').filter(Boolean);
    if (!parts.length) {
        return null;
    }

    const runId = parts[parts.length - 1];
    if (!/^run_[A-Za-z0-9_.-]+$/.test(runId)) {return null;}
    return runId;
}

function updateExplain118Button() {

    const button =document.getElementById('explain118Button');
    if (!button) {
        return;
    }
    button.hidden =!current118RunId();
}

function setExplain118PanelOpen(open) {
    const panel =document.getElementById('explain118Panel');
    const backdrop =document.getElementById('explain118Backdrop');
    const button =document.getElementById('explain118Button');

    if (!panel || !backdrop) {
        return;
    }

    panel.classList.toggle('is-open',!!open);
    panel.setAttribute('aria-hidden',open ? 'false' : 'true');
    backdrop.hidden =!open;

    if (button) {
        button.setAttribute('aria-expanded',open ? 'true' : 'false');
    }
}

function clearExplain118Content() {

    const content =document.getElementById('explain118Content');
    const error =document.getElementById('explain118Error');
    const loading =document.getElementById('explain118Loading');

    if (content) {
        content.hidden = true;
    }

    if (error) {
        error.hidden = true;
        error.textContent = '';
    }

    if (loading) {
        loading.hidden = true;
    }
}


function renderExplain118List(elementId,items) {

    const element =document.getElementById(elementId);
    if (!element) {
        return;
    }

    element.innerHTML = '';
    for (const item of (Array.isArray(items)? items: [])) {
        const li =document.createElement('li');

        // textContent:
        // nessun HTML proveniente dal modello.
        li.textContent =String(item);
        element.appendChild(li);
    }
}

function renderExplain118Resources(
    allocation
) {

    const container =
        document.getElementById(
            'explain118Resources'
        );

    const section =
        document.getElementById(
            'explain118ResourcesSection'
        );


    if (!container || !section) {
        return;
    }

    container.innerHTML = '';

    const bases =Array.isArray(allocation?.bases) ? allocation.bases : [];
    section.hidden = bases.length === 0;

    for (const baseItem of bases) {
        const card =document.createElement('div');
        card.className = 'explain118-resource-base';
        const name =document.createElement('div');
        name.className = 'explain118-resource-base__name';
        name.textContent =String( baseItem?.base || 'Base non disponibile');
        const list =document.createElement('ul');
        list.className ='explain118-resource-base__items';
        const resources =Array.isArray(baseItem?.resources) ? baseItem.resources : [];

        for (const resource of resources) {
            const li =document.createElement('li');
            // Usiamo la denominazione già costruita deterministicamente dal backend.
            li.textContent = String(resource?.display_text || '');
            list.appendChild(li);
        }
        card.append(name,list);
        container.appendChild(card);
    }
}


function renderExplain118Response(data) {
    const explanation =data?.explanation || {};
    const title =document.getElementById('explain118ExplanationTitle');
    const summary =document.getElementById('explain118Summary');
    const note =document.getElementById('explain118ImportantNote');
    const content =document.getElementById('explain118Content');

    if (title) {
        title.textContent =explanation.title || 'Spiegazione dei risultati';
    }

    if (summary) {
        summary.textContent = explanation.summary || 'Spiegazione non disponibile.';
    }


    if (note) {

        note.textContent = explanation.important_note || '';
    }

    const changes = Array.isArray(explanation.what_changes) ? explanation.what_changes : [];
    renderExplain118List('explain118Changes', changes);
    const changesSection =document.getElementById('explain118ChangesSection');
    if (changesSection) {
        changesSection.hidden = changes.length === 0;
    }

    renderExplain118Resources(data?.resource_allocation);

    const territorial = Array.isArray(explanation.territorial_notes) ? explanation.territorial_notes : [];
    renderExplain118List('explain118Territory',territorial);
    const territorySection =document.getElementById('explain118TerritorySection');

    if (territorySection) {
        territorySection.hidden =territorial.length === 0;
    }

    if (content) {
        content.hidden = false;
    }
}

async function loadExplain118() {

    const runId =
        current118RunId();


    if (!runId) {

        alert(
            'Esegui o apri prima '
            + 'una pianificazione 118.'
        );

        return;
    }


    console.log(
        '[Explain Results 118] OPEN',
        runId
    );


    setExplain118PanelOpen(
        true
    );


    clearExplain118Content();


    const runLabel =
        document.getElementById(
            'explain118RunLabel'
        );

    const loading =
        document.getElementById(
            'explain118Loading'
        );

    const error =
        document.getElementById(
            'explain118Error'
        );


    if (runLabel) {

        runLabel.textContent =
            `Run: ${runId}`;
    }


    // =======================================================
    // 1. CACHE
    // =======================================================

    const cached =
        getCachedExplain118(
            runId
        );


    if (cached) {

        EXPLAIN_118_LOADED_RUN_ID =
            runId;


        renderExplain118Response(
            cached
        );


        return;
    }


    // =======================================================
    // 2. REQUEST GIÀ IN CORSO
    //
    // Impedisce due chiamate contemporanee
    // per lo stesso run.
    // =======================================================

    let requestPromise =
        EXPLAIN_118_INFLIGHT.get(
            runId
        );


    if (!requestPromise) {

        console.log(
            '[Explain Results 118] '
            + 'BACKEND REQUEST',
            runId
        );


        requestPromise = (
            async () => {

                const response =
                    await fetch(
                        `/api/118/explain/`
                        + encodeURIComponent(
                            runId
                        )
                    );


                let data = null;


                try {

                    data =
                        await response.json();


                } catch {

                    throw new Error(
                        'Risposta Explain Results '
                        + 'non valida.'
                    );
                }


                if (
                    !response.ok
                    || data?.status !== 'ok'
                ) {

                    throw new Error(
                        data?.message
                        || (
                            'Spiegazione '
                            + 'non disponibile.'
                        )
                    );
                }


                // Salviamo SUBITO dopo
                // una risposta valida.
                cacheExplain118(
                    runId,
                    data
                );


                return data;
            }
        )();


        EXPLAIN_118_INFLIGHT.set(
            runId,
            requestPromise
        );


    } else {

        console.log(
            '[Explain Results 118] '
            + 'REUSE IN-FLIGHT REQUEST',
            runId
        );
    }


    // =======================================================
    // 3. UI
    // =======================================================

    if (loading) {
        loading.hidden = false;
    }


    try {

        const data =
            await requestPromise;


        // Nel frattempo potrebbe essere
        // cambiato il run.
        if (
            current118RunId()
            !== runId
        ) {

            console.warn(
                '[Explain Results 118] '
                + 'response ignored: run changed'
            );

            return;
        }


        EXPLAIN_118_LOADED_RUN_ID =
            runId;


        renderExplain118Response(
            data
        );


    } catch (err) {

        console.error(
            '[Explain Results 118]',
            err
        );


        if (error) {

            error.textContent =
                err?.message
                || (
                    'Impossibile generare '
                    + 'la spiegazione.'
                );

            error.hidden = false;
        }


    } finally {

        // Eliminiamo solo la richiesta in corso,
        // NON la spiegazione salvata.
        if (
            EXPLAIN_118_INFLIGHT.get(
                runId
            )
            === requestPromise
        ) {

            EXPLAIN_118_INFLIGHT.delete(
                runId
            );
        }


        if (loading) {
            loading.hidden = true;
        }
    }
}


function bindExplain118UI() {
    const button =document.getElementById('explain118Button');
    const close = document.getElementById('explain118Close');
    const backdrop =document.getElementById('explain118Backdrop');
    // MAIN BUTTON
    if (button && !button.dataset.explainBound) {
        button.dataset.explainBound ='1';
        button.addEventListener('click',event => {
                event.preventDefault();
                console.log('[Explain Results 118] click');
                loadExplain118();
            }
        );
    }

    // CLOSE
    if (close && !close.dataset.explainBound) {
        close.dataset.explainBound = '1';
        close.addEventListener('click', () => {
                setExplain118PanelOpen(false);
            }
        );
    }

    // BACKDROP
    if (backdrop && !backdrop.dataset.explainBound) {
        backdrop.dataset.explainBound ='1';
        backdrop.addEventListener('click',() => {setExplain118PanelOpen(false);});
    }

    // ESCAPE
    if (!document.documentElement.dataset.explain118EscapeBound) {
        document.documentElement.dataset.explain118EscapeBound ='1';
        document.addEventListener(
            'keydown',
            event => {
                if (event.key === 'Escape') {
                    setExplain118PanelOpen(false);
                }
            }
        );
    }
    updateExplain118Button();
    console.log('[Explain Results 118] UI bound',{button: !!button, runId: current118RunId()});
}

const FILES = () => RUN_URL ? ({
    chosen: `${RUN_URL}/chosen_slots.csv`,
    covAny: `${RUN_URL}/coverage_summary.csv`,
    covDoc: `${RUN_URL}/doctor_coverage_summary.csv`,
    docTxt: `${RUN_URL}/doctors_summary.txt`,
    runSummary: `${RUN_URL}/run_summary.csv`,
}) : null;

const TYPE_COLOR = {
    PSAUT: 'var(--psaut)',
    AUTO_MED: 'var(--auto)',
    AMB_ALS: 'var(--als)',
    AMB_ILS: 'var(--ils)',
    CMR: 'var(--cmr)' // ⬅️ nuovo
};

function iconFor(type) {
    const html = {
        PSAUT: `<i class="fa-solid fa-building fa-lg" style="color:${TYPE_COLOR.PSAUT}"></i>`,
        AUTO_MED: `<i class="fa-solid fa-car fa-lg" style="color:${TYPE_COLOR.AUTO_MED}"></i>`,
        AMB_ALS: `<i class="fa-solid fa-truck-medical fa-lg" style="color:${TYPE_COLOR.AMB_ALS}"></i>`,
        AMB_ILS: `<i class="fa-solid fa-truck-medical fa-lg" style="color:${TYPE_COLOR.AMB_ILS}"></i>`,
        CMR: `<i class="fa-solid fa-truck-medical fa-lg" style="color:${TYPE_COLOR.CMR}"></i>` // ⬅️ nuovo
    }[type] || '<i class="fa-solid fa-location-dot fa-lg" style="color:#555"></i>';
    return L.divIcon({className: 'pin', html, iconSize: [28, 28], iconAnchor: [14, 28], popupAnchor: [0, -28]});
}


function loadCSV(path) {
    return new Promise((resolve, reject) => {
        Papa.parse(path, {
            download: true, header: true, skipEmptyLines: true,
            complete: res => resolve(res.data), error: err => reject(err)
        });
    });
}

function isTruthy(v) {
    if (v == null) return false;
    const s = String(v).trim().toLowerCase();
    return s === '1' || s === 'true' || s === 'yes' || s === 'y' || s === 'si' || s === 'sì';
}


function euro(n) {
    try {
        return Number(n || 0).toLocaleString('it-IT', {style: 'currency', currency: 'EUR'});
    } catch {
        return (n || 0) + ' €';
    }
}

let LAST_SIG = null; // firma dell’ultima valutazione riuscita
// Profili parametri per pannello
let PARAM_PROFILES = {'mode-algo': null, 'mode-editor': null};
let CURRENT_MODE = 'mode-algo';

// Legge i parametri correnti dal pannello (riusa la tua funzione)
function captureBodyFromUI() {
    return buildRunBody(); // include T, type-speed, costi, staff, medici, budget, ecc.
}

// Applica un "body" al pannello (senza toccare la mappa/plan)
function applyBodyToUI(body) {
    if (!body || typeof body !== 'object') return;

    const setVal = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.value = (v ?? '');
    };
    const setChk = (id, on) => {
        const el = document.getElementById(id);
        if (el) el.checked = !!on;
    };

    // Parser KV robusto: "A=1,B=2" oppure "A:1;B:2" (anche misti)
    const parseKVPairs = (s) => Object.fromEntries(
        String(s || '')
            .split(/[;,]+/)
            .map(kv => kv.trim())
            .filter(Boolean)
            .map(kv => {
                const [k, v] = kv.includes('=') ? kv.split('=') : kv.split(':');
                return [String(k || '').trim(), Number(v)];
            })
    );

    // Parser lista semplice: "ROSSO, GIALLO; VERDE"
    const parseList = (s) => new Set(
        String(s || '')
            .split(/[;,]+/)
            .map(x => x.trim())
            .filter(Boolean)
    );

    // --- Soglie T
    (function restoreT() {
        const T = parseKVPairs(body.T || '');
        const def = {ROSSO: 8, GIALLO: 20, VERDE: 30, BIANCO: 45};
        ['ROSSO', 'GIALLO', 'VERDE', 'BIANCO'].forEach(k => {
            const slider = document.getElementById('t' + k);
            if (slider) slider.value = Number(T[k] ?? def[k]);
        });
        if (typeof syncParamT === 'function') syncParamT();
    })();

    // --- Type-speed
    (function restoreTS() {
        const TS = parseKVPairs(body.type_speed || '');
        const def = {AUTO_MED: 0.90, AMB_ALS: 0.98, AMB_ILS: 1.00};
        ['AUTO_MED', 'AMB_ALS', 'AMB_ILS'].forEach(k => {
            const s = document.getElementById('sp' + k);
            if (s) s.value = Number(TS[k] ?? def[k]);
            const o = document.getElementById('sp' + k + '_val');
            if (o && s) o.textContent = Number(s.value).toFixed(2) + '×';
        });
        if (typeof syncTypeSpeed === 'function') syncTypeSpeed();
    })();

    // --- CAPEX / OPEX
    (function restoreCosts() {
        const CX = parseKVPairs(body.purchase_costs || '');
        const OX = parseKVPairs(body.opex_costs || '');
        ['AUTO_MED', 'AMB_ALS', 'AMB_ILS', 'PSAUT'].forEach(k => {
            const cx = document.getElementById('cx' + k);
            if (cx) cx.value = CX[k] ?? 0;
            const ox = document.getElementById('ox' + k);
            if (ox) ox.value = OX[k] ?? 0;
        });
        if (typeof syncCapex === 'function') syncCapex();
        if (typeof syncOpex === 'function') syncOpex();
    })();

    // --- Medici (mode, total, cover, codici)
    (function restoreDoctors() {
        const codes = parseList(body.doctor_codes || '');
        [['ROSSO', 'dcROSSO'], ['GIALLO', 'dcGIALLO'], ['VERDE', 'dcVERDE'], ['BIANCO', 'dcBIANCO']]
            .forEach(([k, id]) => setChk(id, codes.has(k)));
        setVal('docMode', body.doctors_budget_mode ?? 'absolute');
        setVal('docTotal', body.doctors_total ?? '');
        setVal('docCodes', body.doctor_codes || '');
        setVal('docCover', body.doctor_cover ?? 'strict');
        if (typeof syncDocCodes === 'function') syncDocCodes();
    })();

    // --- Staff per tipo
    (function restoreStaff() {
        const ST = parseKVPairs(body.staff_per_type || '');
        const def = {PSAUT: 6, AUTO_MED: 6, AMB_ALS: 6};
        [['stPSAUT', 'PSAUT'], ['stAUTO_MED', 'AUTO_MED'], ['stAMB_ALS', 'AMB_ALS']]
            .forEach(([id, k]) => setVal(id, ST[k] ?? def[k]));
        if (typeof syncStaff === 'function') syncStaff();
    })();

    // --- Budget economico (UI ↔ hidden)
    (function restoreBudget() {
        const bt = body.budget_total ?? '';
        let bm = (body.budget_mode || '').toLowerCase(); // 'purchase' | 'all'
        const ui = (bm === 'purchase') ? 'capex' : (bm === 'all' ? 'capex_opex' : '');
        setVal('uiBudgetTotal', bt);
        const sel = document.getElementById('uiBudgetMode');
        if (sel) sel.value = ui;
        const hBT = document.getElementById('budgetTotal');
        if (hBT) hBT.value = bt;
        const hBM = document.getElementById('budgetMode');
        if (hBM) hBM.value = (ui === 'capex' ? 'purchase' : ui === 'capex_opex' ? 'all' : '');
    })();

    // --- Avanzate/varie
    setVal('bases', body.bases ?? 'ATT_POT');
    setVal('limitBases', body.limit_bases ?? '0');
    setVal('fullcov', body.full_coverage ?? 'strict');
    setVal('psautMin', body.psaut_min ?? '');
    setVal('psautExact', body.psaut_exact ?? '');
    setVal('reloc', body.reloc_psaut ?? 'off');
    setVal('threads', body.threads ?? '8');
    setVal('tl', body.time_limit_sec ?? '');

    // Verbose (select + switch)
    const vSel = document.getElementById('verbose');
    const vSw = document.getElementById('verboseSwitch');
    if (vSel) vSel.value = (body.verbose && String(body.verbose).trim()) ? '--verbose' : '';
    if (vSw) vSw.checked = (vSel?.value === '--verbose');
}

// ========= PARAM SUMMARY RENDER =========
function gatherParamState() {
    const val = id => document.getElementById(id)?.value ?? '';

    const num = id => {
        const v = Number(val(id));
        return Number.isFinite(v) ? v : '';
    };

    const read4 = (prefix) => ({
        AUTO_MED: num(prefix + 'AUTO_MED'),
        AMB_ALS: num(prefix + 'AMB_ALS'),
        AMB_ILS: num(prefix + 'AMB_ILS'),
        PSAUT: num(prefix + 'PSAUT'),
    });

    const parseSet = (s) => new Set(String(s || '')
        .split(/[;,]+/)
        .map(x => x.trim().toUpperCase())
        .filter(Boolean));

    return {
        T: {
            ROSSO: num('tROSSO'),
            GIALLO: num('tGIALLO'),
            VERDE: num('tVERDE'),
            BIANCO: num('tBIANCO'),
        },
        TS: {
            AUTO_MED: Number(val('spAUTO_MED') || 0.90),
            AMB_ALS: Number(val('spAMB_ALS') || 0.98),
            AMB_ILS: Number(val('spAMB_ILS') || 1.00),
        },
        CAPEX: read4('cx'),
        OPEX: read4('ox'),
        STAFF: {
            PSAUT: num('stPSAUT'),
            AUTO_MED: num('stAUTO_MED'),
            AMB_ALS: num('stAMB_ALS'),
        },
        DOC: {
            codes: parseSet(val('docCodes')),
            total: val('docTotal'),
            mode: val('docMode') || 'absolute',
        },
        BUDGET: {
            total: val('budgetTotal'),
            mode: val('budgetMode'), // 'purchase' | 'all' | ''
        },
        misc: {
            bases: val('bases') || 'ATT_POT',
            limitBases: val('limitBases') || '0',
            fullcov: val('fullcov') || 'strict',
            reloc: val('reloc') || 'off',
            threads: val('threads') || '8',
            tl: val('tl') || '',
        }
    };
}

function renderParamSummary(state = gatherParamState()) {
    const $box = document.getElementById('param-summary');
    if (!$box) return;

    const simboloeuro = (n) => n === '' ? '—' : new Intl.NumberFormat('it-IT', {
        style: 'currency', currency: 'EUR', maximumFractionDigits: 0
    }).format(Number(n || 0));

    const x = (n) => (n === '' ? '—' : Number(n).toFixed(2) + '×');
    const i = (n) => (n === '' ? '—' : String(n));

    const kv = (obj, fmt = (v) => v, mono = false) =>
        `<div class="kv">${Object.entries(obj).map(([k, v]) =>
            `<span class="pill ${mono ? 'mono' : ''}">${k.replace('_', ' ')}=${fmt(v)}</span>`).join(' ')}</div>`;

    const docBadges = () => {
        const have = state.DOC.codes;
        const badge = (name, cls) =>
            `<span class="badge"><span class="dot ${cls}"></span>${name}${have.has(name) ? '' : ' <span class="muted">(no)</span>'}</span>`;
        return `<div class="badges">${[
            badge('ROSSO', 'rosso'),
            badge('GIALLO', 'giallo'),
            badge('VERDE', 'verde'),
            badge('BIANCO', 'bianco')
        ].join('')}</div>`;
    };

    const budgetText = () => {
        if (!state.BUDGET.mode) return '<span class="warn">Non impostato</span>';
        const label = state.BUDGET.mode === 'purchase' ? 'solo CAPEX' : 'CAPEX + OPEX';
        return `${simboloeuro(state.BUDGET.total)} <span class="muted">(${label})</span>`;
    };

    // dentro renderParamSummary(...) dopo i blocchi esistenti:

    $box.innerHTML = `
  <dt>Soglie T</dt>
  <dd>${kv(state.T, i, true)}</dd>

  <dt>Velocità relative</dt>
  <dd>${kv(state.TS, x)}</dd>

  <dt>CAPEX unitari</dt>
  <dd>${kv(state.CAPEX, simboloeuro, true)}</dd>

  <dt>OPEX unitari</dt>
  <dd>${kv(state.OPEX, simboloeuro, true)}</dd>

  <dt>Staff per tipo</dt>
  <dd>${kv(state.STAFF, i, true)}</dd>

  <dt>Vincolo medico</dt>
  <dd>${state.misc.fullcov === 'strict' ? '<span class="ok">strict</span>' : state.misc.fullcov} · ${docBadges()}</dd>

  <dt>Medici totali</dt>
  <dd>${i(state.DOC.total)} <span class="muted">(${state.DOC.mode})</span></dd>

  <dt>Budget</dt>
  <dd>${budgetText()}</dd>

  <dt>Basi</dt>
  <dd>${state.misc.bases} <span class="muted">· limit=${state.misc.limitBases}</span></dd>

  <dt>Reloc. PSAUT</dt>
  <dd>${state.misc.reloc}</dd>

  <dt>Threads / Time limit</dt>
  <dd>${state.misc.threads} <span class="muted">/</span> ${state.misc.tl || '—'}</dd>

  <!-- === NEW: extra algoritmo (lettura diretta dalla UI) === 
  <dt>Relax weights</dt>
  <dd><code class="mono">${i(document.getElementById('relaxWeights')?.value || '')}</code></dd>-->

  <dt>PSAUT vincoli</dt>
  <dd>min=${i(document.getElementById('psautMin')?.value || '')} · exact=${i(document.getElementById('psautExact')?.value || '')}</dd>

  <dt>Infermieri per tipo</dt>
  <dd>${kv({
        PSAUT: i(document.getElementById('nuPSAUT')?.value || ''),
        AUTO_MED: i(document.getElementById('nuAUTO_MED')?.value || ''),
        AMB_ALS: i(document.getElementById('nuAMB_ALS')?.value || ''),
        AMB_ILS: i(document.getElementById('nuAMB_ILS')?.value || '')
    }, i, true)}</dd>

  <dt>Budget infermieri</dt>
  <dd>tot=${i(document.getElementById('nurTotal')?.value || '')}
      · unit=${i(document.getElementById('nurOpex')?.value || '')}</dd>

  <dt>Trasporto automedica</dt>
  <dd>${i(document.getElementById('autoMedCoupling')?.value || 'off')}</dd>
`;


    // Nota in calce
    const foot = document.getElementById('param-footnote');
    if (foot) {
        const s = state;
        let txt = 'Riepilogo sintetico del piano: ';
        const doctorTxt = (s.DOC.total ? `${s.DOC.total} medici (${s.DOC.mode})` : 'medici non impostati');
        const budgetTxt = (s.BUDGET.mode ? `${simboloeuro(s.BUDGET.total)} ${s.BUDGET.mode === 'purchase' ? 'CAPEX' : 'TOT'}` : 'budget non impostato');
        txt += `${doctorTxt}, ${budgetTxt}, vincolo "${s.misc.fullcov}", basi ${s.misc.bases}.`;
        foot.textContent = txt;
    }
}

// --- Azioni pulsanti
document.getElementById('btnOpenParams')?.addEventListener('click', () => {
    // usa l’unica fonte di verità dei tab
    if (typeof window.setPanelMode === 'function') {
        window.setPanelMode('mode-algo');
    } else {
        // fallback: clicca il tab ARIA
        document.getElementById('tab-algo')?.click() ||
        document.querySelector('[role="tab"][aria-controls="mode-config"]')?.click();
    }
    document.getElementById('uiBudgetMode')?.scrollIntoView({behavior: 'smooth', block: 'start'});
});

document.getElementById('btnShowAll')?.addEventListener('click', () => {
    // qui puoi eventualmente espandere un accordion; per ora facciamo solo un flash
    const box = document.getElementById('paramBox');
    if (!box) return;
    box.style.boxShadow = '0 0 0 3px rgba(59,130,246,.35)';
    setTimeout(() => box.style.boxShadow = 'none', 600);
});
document.getElementById('btnCopyConfig')?.addEventListener('click', () => {
    const s = gatherParamState();
    const payload = {
        T: s.T, type_speed: s.TS,
        purchase_costs: s.CAPEX, opex_costs: s.OPEX,
        staff_per_type: s.STAFF,
        doctor_codes: [...s.DOC.codes].join(','),
        doctors_total: s.DOC.total, doctors_budget_mode: s.DOC.mode,
        budget_total: s.BUDGET.total, budget_mode: s.BUDGET.mode,
        bases: s.misc.bases, limit_bases: s.misc.limitBases,
        full_coverage: s.misc.fullcov, reloc_psaut: s.misc.reloc,
        threads: s.misc.threads, time_limit_sec: s.misc.tl
    };
    const text = JSON.stringify(payload, null, 2);
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('btnCopyConfig');
        if (btn) {
            btn.textContent = 'Copiato!';
            setTimeout(() => btn.innerHTML = '<i class="fa-solid fa-copy"></i> Copia config', 1200);
        }
    });
});

// --- Hook: ricalcola al volo quando cambia qualcosa nel pannello opzioni
function installParamSummaryAutoRefresh() {
    const scope = document; // restringi se vuoi
    scope.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('input', () => renderParamSummary());
        el.addEventListener('change', () => renderParamSummary());
    });
}

// === CHIAMATE DI INIZIALIZZAZIONE (mettile dove carichi la UI) ===
// 1) dopo applyBodyToUI(...)
renderParamSummary();
// 2) una volta al boot
installParamSummaryAutoRefresh();


// Salva profilo corrente e carica quello della modalità richiesta
function swapParamProfile(nextMode) {
    try {
        if (CURRENT_MODE) PARAM_PROFILES[CURRENT_MODE] = captureBodyFromUI();
    } catch {
    }
    if (!PARAM_PROFILES[nextMode]) {
        // Prima volta: inizializza con lo stato attuale per non mostrare campi vuoti
        PARAM_PROFILES[nextMode] = PARAM_PROFILES[CURRENT_MODE] || captureBodyFromUI();
    }
    applyBodyToUI(PARAM_PROFILES[nextMode]);
    CURRENT_MODE = nextMode;
}

function computeSignature() {
    // NB: buildRunBody() già include tutti i parametri dell’algoritmo
    const body = buildRunBody();
    return JSON.stringify({body, plan: MP_PLAN});
}

async function ensureFreshEvaluation() {
    // NON forzare /api/evaluate se l’ultimo risultato è dell’algoritmo
    if (LAST_RUN_KIND !== 'editor') return;
    const sig = computeSignature();
    if (sig !== LAST_SIG) {
        const ok = await mp_eval();
        if (!ok) throw new Error('Valutazione fallita');
        LAST_SIG = sig;
    }
}


/* ====== PDF Report (stato + helper) ====== */
let LAST_CHOSEN = [], LAST_COV_ANY = [], LAST_COV_DOC = [], LAST_DOCTORS_TXT = '';

function covTotals(arr) {
    const row = findTotalRow(arr);
    if (!row) return {calls: null, uncovered: null, pct: null};
    return {calls: row.total_calls, uncovered: row.total_uncovered, pct: pctFrom(row)};
}

function prepareCosts(chosen) {
    const capexKV = parsePairs(document.getElementById('capex')?.value || '');
    const opexKV = parsePairs(document.getElementById('opex')?.value || '');
    const CX = Object.fromEntries(Object.entries(capexKV).map(([k, v]) => [k, Number(v || 0)]));
    const OX = Object.fromEntries(Object.entries(opexKV).map(([k, v]) => [k, Number(v || 0)]));
    const counts = {}, newCnt = {};
    for (const r of chosen || []) {
        const t = String(r.tipo || r.type || '').toUpperCase();
        if (!t) continue;
        counts[t] = (counts[t] || 0) + 1;

        // “nuovo” vs “fisso” per CAPEX acquisti
        const siteId = String(r.site_id || r.site || r.slot || '');
        const origin = String(r.origin || r.src || '').toLowerCase();
        const isFixed =
            isTruthy(r.is_fixed) || /^fix[_-]/i.test(siteId) || /(^|[^a-z])fix[^a-z]?/i.test(siteId) ||
            origin === 'base' || origin === 'fixed';

        const hasExplicitNew = ('is_new' in r) || ('new' in r) || ('purchase' in r) || ('is_purchase' in r) || ('acquisto' in r);
        const isNew = hasExplicitNew
            ? (isTruthy(r.is_new) || isTruthy(r.new) || isTruthy(r.purchase) || isTruthy(r.is_purchase) || isTruthy(r.acquisto))
            : !isFixed;

        if (isNew) newCnt[t] = (newCnt[t] || 0) + 1;
    }
    const types = Object.keys(counts).sort();
    const perType = types.map(t => {
        const n = counts[t] || 0, nNew = newCnt[t] || 0, cx = CX[t] || 0, ox = OX[t] || 0;
        return {tipo: t, n, nNew, cxUnit: cx, oxUnit: ox, cxTot: n * cx, oxTot: n * ox, cxNew: nNew * cx};
    });
    const totals = perType.reduce((a, r) => ({
        units: a.units + r.n,
        newUnits: a.newUnits + r.nNew,
        capex: a.capex + r.cxTot,
        opex: a.opex + r.oxTot,
        capexNew: a.capexNew + r.cxNew
    }), {units: 0, newUnits: 0, capex: 0, opex: 0, capexNew: 0});
    return {perType, totals};
}

async function trySaveReportOnServer(blob, filename) {
    try {
        const base64 = await new Promise(res => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result.split(',')[1]);
            fr.readAsDataURL(blob);
        });
        const r = await fetch('/api/save-report', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({run_url: RUN_URL, filename, data_base64: base64})
        });
        return r.ok;
    } catch {
        return false;
    }
}


function fixRunPath(p) {
    if (!p) return '';
    let s = String(p).trim().replace(/\\/g, '/');
    if (!s) return '';
    if (s.startsWith('/runs/')) return s;
    const i = s.toLowerCase().lastIndexOf('/runs/');
    if (i >= 0) return s.slice(i);          // “…/runs/2025_..” -> “/runs/2025_..”
    const j = s.toLowerCase().indexOf('runs/');
    if (j >= 0) return '/' + s.slice(j);    // “runs/2025_..”   -> “/runs/2025_..”
    return '';
}


function updateDownloadButtons() {
    const files = FILES();
    const box = document.getElementById('dlBox');
    updateExplain118Button();
    updateReset118Button();

    if (!box || !files) {
        if (box) box.hidden = true;   // ← usa hidden, coerente con resetRunView
        return;
    }

    const setA = (id, url, name) => {
        const a = document.getElementById(id);
        if (!a) return;
        a.href = url;
        a.setAttribute('download', name || url.split('/').pop());
        a.target = '_blank';
    };

    setA('dlChosen', files.chosen, 'chosen_slots.csv');
    setA('dlAny', files.covAny, 'coverage_summary.csv');
    setA('dlDoc', files.covDoc, 'doctor_coverage_summary.csv');
    setA('dlDoctors', files.docTxt, 'doctors_summary.txt');

    const all = document.getElementById('dlAll');
    if (all) {
        all.onclick = async () => {
            try {
                const zip = new JSZip();
                const entries = [
                    ['chosen_slots.csv', files.chosen],
                    ['coverage_summary.csv', files.covAny],
                    ['doctor_coverage_summary.csv', files.covDoc],
                    ['doctors_summary.txt', files.docTxt],
                ];
                await Promise.all(entries.map(async ([name, url]) => {
                    const r = await fetch(url);
                    if (!r.ok) throw new Error('Errore fetching ' + name);
                    zip.file(name, await r.blob());
                }));
                const blob = await zip.generateAsync({type: 'blob'});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                a.download = `reports_${ts}.zip`;
                document.body.appendChild(a);
                a.click();
                setTimeout(() => {
                    URL.revokeObjectURL(a.href);
                    a.remove();
                }, 800);
            } catch (e) {
                alert('Impossibile creare lo ZIP: ' + e.message);
            }
        };
    }

    box.hidden = false;             // ← mostra davvero i bottoni
}


function renderCosts(chosen) {

    const box = document.getElementById('costsBox');
    const el = document.getElementById('costs');
    if (!box || !el) return;

    if (!Array.isArray(chosen) || !chosen.length) {
        box.hidden = true;          // <— invece di box.style.display='none'
        el.innerHTML = '';
        return;
    }


    const capexKV = parsePairs(document.getElementById('capex')?.value || '');
    const opexKV = parsePairs(document.getElementById('opex')?.value || '');
    const CAPEX = Object.fromEntries(Object.entries(capexKV).map(([k, v]) => [k, Number(v || 0)]));
    const OPEX = Object.fromEntries(Object.entries(opexKV).map(([k, v]) => [k, Number(v || 0)]));

    const counts = {}, newCnt = {};
    chosen.forEach(r => {
        const t = String(r.tipo || r.type || '').toUpperCase();
        if (!t) return;
        counts[t] = (counts[t] || 0) + 1;
        // Nuove vs di base (fallback: tutto ciò che NON è FIX_ è considerato nuovo)
        const siteId = String(r.site_id || r.site || r.slot || '');
        const origin = String(r.origin || r.src || '').toLowerCase();
        const isFixed =
            isTruthy(r.is_fixed) ||                      // flag esplicito
            /^fix[_-]/i.test(siteId) ||                  // es. FIX_001@Apice
            /(^|[^a-z])fix[^a-z]?/i.test(siteId) ||      // qualunque variante "fix"
            origin === 'base' || origin === 'fixed';

        const hasExplicitNewFlag = (
            'is_new' in r || 'new' in r || 'purchase' in r || 'is_purchase' in r || 'acquisto' in r
        );

        const isNew = hasExplicitNewFlag
            ? (isTruthy(r.is_new) || isTruthy(r.new) || isTruthy(r.purchase) || isTruthy(r.is_purchase) || isTruthy(r.acquisto))
            : !isFixed;   // se non ci sono flag, tutto ciò che non è FIX_ viene contato come nuovo

        if (isNew) newCnt[t] = (newCnt[t] || 0) + 1;
    });

    const types = Object.keys(counts).sort();
    const perType = types.map(t => {
        const n = counts[t] || 0, nNew = newCnt[t] || 0;
        const cx = CAPEX[t] || 0, ox = OPEX[t] || 0;
        const cxAll = n * cx, oxAll = n * ox, cxNew = nNew * cx;
        return {t, n, nNew, cx, ox, cxAll, oxAll, cxNew};
    });

    const totUnits = perType.reduce((s, r) => s + r.n, 0);
    const totNew = perType.reduce((s, r) => s + r.nNew, 0);
    const totCapexAll = perType.reduce((s, r) => s + r.cxAll, 0);
    const totOpexAll = perType.reduce((s, r) => s + r.oxAll, 0);
    const totCapexNew = perType.reduce((s, r) => s + r.cxNew, 0);
    const maxCxAll = Math.max(1, ...perType.map(r => r.cxAll));
    const maxOxAll = Math.max(1, ...perType.map(r => r.oxAll));

    const rows = perType.map(r => `
    <tr>
      <td>${r.t} <span class="costs-badge">${r.n}</span></td>
      <td class="num">${r.n}</td>
      <td class="num">${r.nNew}</td>
      <td class="num">${euro(r.cx)}</td>
      <td class="num">${euro(r.ox)}</td>
      <td class="num">
        <div>${euro(r.cxAll)}</div>
        <div class="costs-bar"><span style="--w:${(r.cxAll / maxCxAll * 100).toFixed(1)}%"></span></div>
      </td>
      <td class="num">
        <div>${euro(r.oxAll)}</div>
        <div class="costs-bar"><span style="--w:${(r.oxAll / maxOxAll * 100).toFixed(1)}%"></span></div>
      </td>
    </tr>
  `).join('');

    el.innerHTML = `
    <div class="costs-kpis">
      <span class="kchip">Unità attive <b>${totUnits}</b></span>
      <span class="kchip">Unità nuove <b>${totNew}</b></span>
      <span class="kchip">CAPEX totale <b>${euro(totCapexAll)}</b></span>
      <span class="kchip">OPEX totale <b>${euro(totOpexAll)}</b></span>
    </div>
    <div class="costs-table-wrap">
      <table class="costs-table">
        <thead>
          <tr>
            <th>Tipo</th>
            <th># Attive</th>
            <th># Nuove</th>
            <th>CAPEX / unità</th>
            <th>OPEX / unità</th>
            <th>CAPEX Totale (annuo eq.)</th>
            <th>OPEX Totale (annuo)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
        <tfoot>
          <tr>
            <td>Totale</td>
            <td class="num">${totUnits}</td>
            <td class="num">${totNew}</td>
            <td></td><td></td>
            <td class="num">${euro(totCapexAll)}</td>
            <td class="num">${euro(totOpexAll)}</td>
          </tr>
          <tr>
            <td colspan="5" style="text-align:right">CAPEX “Acquisti” (solo nuove):</td>
            <td colspan="2" class="num"><b>${euro(totCapexNew)}</b></td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;

    box.hidden = false;

}


// Geocoding: prova vari file/colonne
async function loadGeo() {
    const base = CONFIG.dataDir;
    const candidates = [
        `${base}/comuni_geocoded.csv`,
        `${base}/geocoded_communes.csv`,
        `${base}/sites_geocoded.csv`
    ];
    for (const p of candidates) {
        try {
            const data = await loadCSV(p);
            if (Array.isArray(data) && data.length) return data;
        } catch {
        }
    }
    return [];
}

// ---- Verifica file minimi ----
async function fileExists(path) {
    try {
        const r = await fetch(path, {method: 'GET', cache: 'no-store'});
        return r.ok;
    } catch {
        return false;
    }
}

async function preflightData(base) {
    const must = [`${base}/comuni.csv`, `${base}/od_time_min.csv`];
    const demandA = `${base}/weighted_demand_by_comune_code.csv`;
    const demandB = `${base}/demand_by_comune_code.csv`;
    const sitesCsv = `${base}/sites.csv`;
    const presAtt = `${base}/presidi_attuali.csv`;
    const sitesGeo = `${base}/sites_geocoded.csv`;

    const checks = await Promise.all([
        ...must.map(fileExists), fileExists(demandA), fileExists(demandB), fileExists(sitesCsv), fileExists(presAtt), fileExists(sitesGeo)
    ]);
    const missing = [];
    if (!checks[0]) missing.push(`${base}/comuni.csv`);
    if (!checks[1]) missing.push(`${base}/od_time_min.csv`);
    if (!(checks[2] || checks[3])) missing.push(`${base}/weighted_demand_by_comune_code.csv OR ${base}/demand_by_comune_code.csv`);
    if (!(checks[4] || checks[5] || checks[6])) missing.push(`${base}/sites.csv OR (${base}/presidi_attuali.csv) OR ${base}/sites_geocoded.csv`);

    return {
        ok: missing.length === 0,
        missing,
        message: missing.length ? 'Dati mancanti in DATA DIR' : 'Dati OK: file minimi presenti'
    };
}

// ---- UI safe (gli elementi potrebbero non esserci) ----
function renderDataStatus(diag) {
    const el = document.getElementById('dataStatus');
    if (!el) return;
    if (!diag) {
        el.textContent = '';
        return;
    }
    if (diag.ok) {
        el.innerHTML = `✅ <b>${diag.message}</b>`;
    } else {
        el.innerHTML = `❌ <b>${diag.message}</b><br>Assicurati di avere:
      <ul style="margin:6px 0 0 18px;">
        <li><code>comuni.csv</code></li>
        <li><code>od_time_min.csv</code></li>
        <li><code>demand_by_comune_code.csv</code> oppure <code>weighted_demand_by_comune_code.csv</code></li>
        <li><code>sites.csv</code> oppure <code>presidi_attuali.csv</code> oppure <code>sites_geocoded.csv</code></li>
      </ul>`;
    }
}

// ---- Config backend + fallback automatici ----
async function loadConfig() {
    try {
        const r = await fetch('/api/config', {cache: 'no-store'});
        if (!r.ok) {
            CONFIG.dataDir = '';
            return;
        }
        const j = await r.json();
        let dir = (typeof j.data_dir === 'string') ? j.data_dir.trim() : '';
        if (/^(null|undefined|none)?$/i.test(dir)) dir = '';
        CONFIG.dataDir = dir;
    } catch {
        CONFIG.dataDir = '';
    }
}

async function ensureValidDataDir() {
    const candidates = [];
    if (CONFIG.dataDir && !/^(null|undefined|none)$/i.test(CONFIG.dataDir)) {
        candidates.push(CONFIG.dataDir);
    }
    candidates.push('dataset/data', 'data'); // fallback

    let lastDiag = null;
    for (const base of candidates) {
        const diag = await preflightData(base);
        lastDiag = diag;
        if (diag.ok) {
            CONFIG.dataDir = base;
            const pi = document.getElementById('pathInfo');
            if (pi) pi.innerHTML = `DATA DIR: <code>${base}</code> · OUT DIR: <i>auto</i>${base === 'data' ? ' <span class="muted">(fallback)</span>' : ''}`;
            const dd = document.getElementById('dataDir');
            if (dd) dd.value = base;
            renderDataStatus(diag);
            return;
        }
    }
    const pi = document.getElementById('pathInfo');
    if (pi) pi.innerHTML = `DATA DIR: <code>${candidates[0] || 'data'}</code> · OUT DIR: <i>auto</i>`;
    renderDataStatus(lastDiag);
}

const PH118_SEVERITY_SELECTION_STORAGE_KEY = "ph118SelectedSeverityScenario";

function getStoredSeveritySelection() {

    const raw = localStorage.getItem( PH118_SEVERITY_SELECTION_STORAGE_KEY);
    if (!raw) {
        return null;
    }
    try {
        const parsed =JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") {
            return null;
        }
        return parsed;

    }catch {
        localStorage.removeItem(PH118_SEVERITY_SELECTION_STORAGE_KEY);
        return null;
    }
}


function restoreSeveritySelection() {

    const saved = getStoredSeveritySelection();
    if (!saved) {
        return;
    }

    const sourceEl =document.getElementById("severitySource");
    const scenarioEl =document.getElementById("severityScenarioId");
    const runEl =document.getElementById("severitySourceRunId");
    const metricEl =document.getElementById("severityMetric");

    if (scenarioEl) {
        scenarioEl.value =saved.severity_scenario_id || "";
    }

    if (runEl) {
        runEl.value = saved.source_run_id || "";
    }


    if (metricEl) {
        metricEl.value = saved.metric || "";
    }


    if (sourceEl) {
        sourceEl.value = (saved.severity_source === "population_health" && saved.severity_scenario_id) ? ("population_health") : ("original");
    }

    refreshSeveritySourceUI();
}

function persistSeveritySourceSelection() {

    const source =(document.getElementById("severitySource")?.value || "original").trim();
    const previous =getStoredSeveritySelection() || {};

    const selection = {
        ...previous,
        severity_source: source,
        severity_scenario_id: (document.getElementById("severityScenarioId")?.value || "" ).trim(),
        source_run_id:(document.getElementById("severitySourceRunId")?.value || "").trim(),
        metric:(document.getElementById("severityMetric" )?.value || "").trim(),
    };

    localStorage.setItem(PH118_SEVERITY_SELECTION_STORAGE_KEY,JSON.stringify(selection));
}


// ---- Fonte severità territoriale ----
function severityMetricLabel(metric) {
    const labels = {
        patient_count: 'Pazienti per 1000 residenti',
        mean_baseline_need: 'Bisogno medio baseline'
    };
    return labels[String(metric || '').trim()] || metric || '—';
}

function refreshSeveritySourceUI() {
    const sourceEl = document.getElementById('severitySource');
    const detailsEl = document.getElementById('severityPhDetails');

    if (!sourceEl || !detailsEl) return;

    const source = (sourceEl.value || 'original').trim();

    if (source === 'population_health') {
        detailsEl.hidden = false;
        const runId =(document.getElementById('severitySourceRunId')?.value || '').trim();
        const metric = (document.getElementById('severityMetric')?.value || '').trim();
        const scenarioId = (document.getElementById('severityScenarioId')?.value || '').trim();
        const runHost = document.getElementById('severityPhRun');
        const metricHost = document.getElementById('severityPhMetric');
        const scenarioHost = document.getElementById('severityPhScenario');

        if (runHost) runHost.textContent = runId || 'Nessun run selezionato';
        if (metricHost) metricHost.textContent = severityMetricLabel(metric);
        if (scenarioHost) scenarioHost.textContent = scenarioId || 'Nessuno scenario selezionato';

    } else {
        detailsEl.hidden = true;
    }
}

function validateSeveritySelection() {
    const source =(document.getElementById('severitySource')?.value || 'original').trim();
    if (source === 'original') {
        return {ok: true, source: 'original' };
    }
    if (source !== 'population_health') {
        return {ok: false, message: 'Fonte di severità territoriale non valida.'};
    }
    const scenarioId =(document.getElementById('severityScenarioId')?.value || '').trim();
    if (!scenarioId) {
        return {ok: false,  message: 'Hai selezionato Population Health, ma non è stato ancora scelto uno scenario di severità. Genera e conferma prima lo scenario dalla pagina Population Health.' };
    }

    return {ok: true, source: 'population_health', scenarioId };
}



// ---- Body per /api/run con paracadute su data_dir ----
function buildRunBody() {
    const q = id => (document.getElementById(id)?.value || '').trim();

    // fallback robusto per data_dir
    const safeDataDir =
        (CONFIG.dataDir && !/^(null|undefined|none)$/i.test(CONFIG.dataDir))
            ? CONFIG.dataDir
            : 'data';

    const body = {
        data_dir: safeDataDir,
        out_dir: '',
        relax_weights: q('relaxWeights'),
        T: q('paramT'),
        type_speed: q('typeSpeed'),
        purchase_costs: q('capex'),
        opex_costs: q('opex'),
        doctor_codes: q('docCodes'),
        doctor_cover: q('docCover'),
        staff_per_type: q('staff'),
        doctors_total: q('docTotal'),
        doctors_budget_mode: q('docMode'),
        reloc_psaut: q('reloc'),
        psaut_min: q('psautMin'),
        psaut_exact: q('psautExact'),
        bases: q('bases'),
        limit_bases: q('limitBases'),
        full_coverage: q('fullcov'),
        threads: q('threads'),
        time_limit_sec: q('tl'),
        verbose: q('verbose')
    };
    //body.objective = 'max_cover_budget';   // sempre massimizza copertura entro budget
    // (opzionale) body.lambda_cost = 1.0;
    body.objective =q('objective')|| 'max_cover_budget';

    // Fonte della severità territoriale.
    // Il browser invia esclusivamente l'ID logico dello scenario,mai un path del filesystem.
    const severitySource =(document.getElementById('severitySource')?.value || 'original').trim();
    body.severity_source = severitySource;
    if (severitySource === 'population_health') {
        const scenarioId =(document.getElementById('severityScenarioId')?.value || '').trim();

        if (scenarioId) {
            body.severity_scenario_id = scenarioId;
        }
    }

    // ⬇️ NUOVO: budget economico opzionale dal tab Budget
    const bt = q('budgetTotal');
    const bm = q('budgetMode');
    if (bt) body.budget_total = bt;     // es: 2000000
    if (bm) body.budget_mode = bm;     // es: capex / capex_opex

    // --- AUTO: spegni vincolo medico se non ci sono medici liberi oltre i PSAUT ---
    const docTot = Number(document.getElementById('docTotal')?.value || 0);
    const staffKV = (document.getElementById('staff')?.value || '')
        .split(',').reduce((a, s) => {
            const [k, v] = s.split('=');
            if (k) a[k.trim()] = Number(v || 0);
            return a;
        }, {});
    const psautExact = Number((document.getElementById('psautExact')?.value || 0));
    const psautMin = Number((document.getElementById('psautMin')?.value || 0));
    const psautNeed = (psautExact ? psautExact : psautMin) * (Number(staffKV.PSAUT || 6));
    const freeDocs = docTot - psautNeed;

    if (freeDocs <= 0) {
        body.doctor_cover = 'off';  // niente vincolo medico
        body.doctor_codes = '';     // nessun codice richiede medico
    }
    // body.turnoff_doctor_families = 'false'
    body.turnoff_doctor_families = 'on';

    /* Garantisce la presenza del moltiplicatore PSAUT nel type_speed.È un default tecnico dell'ottimizzatore,non una decisione del chatbot. */
    if (typeof body.type_speed === "string" && !/(^|,)PSAUT=/.test( body.type_speed)) {
        body.type_speed +=",PSAUT=0.90";
    }
    return body;
}

let CRIT_LAYER, CRIT_POLY_LAYER;   // cerchi o poligoni
let CRIT_DATA = null;              // Map(comune -> {score, classe})
let CRIT_DISPLAY_MODE = "quantile";
let CRIT_LEGEND_EL = null;


// ---- Mappa ----
let map, layersByType;
const BENEVENTO_CENTER = [41.13, 14.78];
const BENEVENTO_BOUNDS = L.latLngBounds([40.85, 14.20], [41.60, 15.25]);

// Mapping bidirezionale key -> elementi UI
const ROW_BY_KEY = new Map();     // key -> <div.item>
const MARKER_BY_KEY = new Map();  // key -> Leaflet marker
let CURRENT_KEY = null;

function clearFocus() {
    if (!CURRENT_KEY) return;
    ROW_BY_KEY.get(CURRENT_KEY)?.classList.remove('is-active', 'pulse');
    CURRENT_KEY = null;
}


function focusCard(key, {scroll = true, pulse = true} = {}) {
    if (!key) return;
    if (CURRENT_KEY !== key) clearFocus();
    const el = ROW_BY_KEY.get(key);
    if (!el) return;
    el.classList.add('is-active');
    if (pulse) el.classList.add('pulse'), setTimeout(() => el.classList.remove('pulse'), 1000);
    if (scroll) el.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    CURRENT_KEY = key;
}

function hoverCard(key, on) {
    const el = ROW_BY_KEY.get(key);
    if (el) el.classList.toggle('is-hover', !!on);
}

function slotKeyFromRecord(r, i) {
    return String(r.site_id || r.site || r.slot || `slot_${i}`);
}

let MP_PLAN = [];                         // [{base_comune,tipo,qty,source}]
let MP_SITE_MARKERS = [];                 // [{marker,comune,nome}]
let MP_COUNTS_BY_BASE = new Map();        // base -> { tipo -> qty }
let MP_COMMUNES = [];                     // [{comune,lat,lon}]
let MP_FREE_LAYER;                        // layer per clic liberi

// util distanza/snap
function mp_haversineKm(aLat, aLon, bLat, bLon) {
    const R = 6371, rad = x => x * Math.PI / 180, dLat = rad(bLat - aLat), dLon = rad(bLon - aLon);
    const A = Math.sin(dLat / 2) ** 2 + Math.cos(rad(aLat)) * Math.cos(rad(bLat)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(A));
}

function mp_nearestComune(lat, lon) {
    if (!MP_COMMUNES.length) return null;
    let best = null, bestD = 1e9;
    for (const c of MP_COMMUNES) {
        const d = mp_haversineKm(lat, lon, c.lat, c.lon);
        if (d < bestD) {
            bestD = d;
            best = c;
        }
    }
    return best ? {...best, dist_km: bestD} : null;
}

// carica comuni (per snap)
// carica comuni (per snap) — più nomi supportati
async function mp_loadCommunes() {
    const base = CONFIG.dataDir || 'data';
    const candidates = [
        `${base}/comuni_geocoded.csv`,
        `${base}/geocoded_communes.csv`,
        `${base}/comuni.csv`
    ];
    let rows = [], used = null;
    for (const u of candidates) {
        if (!(await fileExists(u))) continue;
        try {
            const tmp = await loadCSV(u);
            if (tmp && tmp.length) {
                rows = tmp;
                used = u;
                break;
            }
        } catch {
        }
    }
    if (!rows.length) {
        MP_COMMUNES = [];
        console.warn('[MP] Nessun file comuni con coordinate trovato:', candidates.join(' , '));
        const h = document.getElementById('mp-hint');
        if (h) h.innerHTML = '⚠️ Fornisci un CSV con colonne lat/lon (es. <code>comuni_geocoded.csv</code>).';
        return;
    }
    console.log('[MP] comuni da', used);

    const comK = pickKeyCI(rows[0], ['comune', 'base_comune', 'name', 'denominazione', 'site', 'site_name']) || 'comune';
    const latK = pickKeyCI(rows[0], ['lat', 'latitude', 'latitudine', 'y']) || 'lat';
    const lonK = pickKeyCI(rows[0], ['lon', 'lng', 'long', 'longitude', 'longitudine', 'x']) || 'lon';
    const istatK = pickKeyCI(rows[0], ['istat', 'codice_istat', 'comune_code', 'codice_comune']);
    MP_COMMUNES = rows
        .map(r => ({
            comune: normalizeComune(r[comK] || ''),
            lat: latK ? +r[latK] : NaN,
            lon: lonK ? +r[lonK] : NaN,
            istat: istatK && r[istatK] != null ? String(r[istatK]).padStart(6, '0') : ''
        }))
        .filter(r => r.comune);

}


// carica presìdi e crea marker cliccabili
// carica presìdi e crea marker cliccabili — più nomi supportati
let MP_SITES = []; // {comune, lat, lon, nome}

async function mp_loadSitesLayer() {
    const base = CONFIG.dataDir || 'data';
    const candidates = [
        `${base}/sites_geocoded.csv`,
        `${base}/presidi_attuali.csv`,
        `${base}/sites.csv`
    ];
    let rows = [], used = null;
    for (const u of candidates) {
        if (!(await fileExists(u))) continue;
        try {
            const tmp = await loadCSV(u);
            if (tmp && tmp.length) {
                rows = tmp;
                used = u;
                break;
            }
        } catch {
        }
    }
    if (!rows.length) {
        console.warn('[MP] Nessun file presìdi trovato:', candidates.join(' , '));
        return;
    }
    console.log('[MP] elenco presìdi da', used);

    const latK = ['lat', 'Lat', 'latitude', 'Latitude'].find(k => k in rows[0]);
    const lonK = ['lon', 'Lon', 'lng', 'Lng', 'longitude', 'Longitude'].find(k => k in rows[0]);
    const comK = ['comune', 'Comune', 'base_comune', 'BASE_COMUNE', 'name'].find(k => k in rows[0]) || 'comune';
    const nameK = ['nome', 'Nome', 'site_name', 'Site', 'denominazione'].find(k => k in rows[0]) || comK;

    MP_SITES = rows.map(r => {
        let lat = latK ? parseFloat(r[latK]) : NaN;
        let lon = lonK ? parseFloat(r[lonK]) : NaN;
        const comune = normalizeComune(r[comK] || '');
        if ((!Number.isFinite(lat) || !Number.isFinite(lon)) && MP_COMMUNES.length) {
            const c = MP_COMMUNES.find(x => x.comune === comune && Number.isFinite(x.lat) && Number.isFinite(x.lon));
            if (c) {
                lat = c.lat;
                lon = c.lon;
            }
        }
        return {comune, lat, lon, nome: (r[nameK] || comune || 'Sito').toString()};
    });
}

// --- Recap della configurazione caricata (scheda Config) ---


// badge su marker
function mp_updateMarkerBadge(marker, baseComune) {
    const counts = MP_COUNTS_BY_BASE.get(baseComune);
    const title = marker.options.title || baseComune;
    if (!counts) {
        marker.unbindTooltip();
        marker.bindTooltip(`<div><strong>${title}</strong><br/><span style="color:#6b7280">${baseComune}</span></div>`);
        return;
    }
    const chips = Object.entries(counts).map(([t, q]) => `<span class="mp-badge">${t}: ${q}</span>`).join(' ');
    marker.unbindTooltip();
    marker.bindTooltip(`<div><strong>${title}</strong><br/><span style="color:#6b7280">${baseComune}</span><div style="margin-top:4px">${chips}</div></div>`);
}

// piano (aggiungi / rimuovi / render)
function mp_addToPlan(base_comune, tipo, qty, source) {
    const key = `${base_comune}||${tipo}||${source}`;
    let row = MP_PLAN.find(r => `${r.base_comune}||${r.tipo}||${r.source}` === key);
    if (!row) {
        row = {base_comune, tipo, qty: 0, source};
        MP_PLAN.push(row);
    }
    row.qty += qty;

    if (!MP_COUNTS_BY_BASE.has(base_comune)) MP_COUNTS_BY_BASE.set(base_comune, {});
    const m = MP_COUNTS_BY_BASE.get(base_comune);
    m[tipo] = (m[tipo] || 0) + qty;

    mp_renderPlanTable();
    mp_updateEditorButtons(); // 🔧 nuovo
}

function mp_removeFromPlan(base_comune, tipo, source, qty = 1) {
    const key = `${base_comune}||${tipo}||${source}`;
    const i = MP_PLAN.findIndex(r => `${r.base_comune}||${r.tipo}||${r.source}` === key);
    if (i >= 0) {
        MP_PLAN[i].qty -= qty;
        if (MP_PLAN[i].qty <= 0) MP_PLAN.splice(i, 1);
    }
    const m = MP_COUNTS_BY_BASE.get(base_comune) || {};
    if (m[tipo]) {
        m[tipo] -= qty;
        if (m[tipo] <= 0) delete m[tipo];
    }
    if (Object.keys(m).length === 0) MP_COUNTS_BY_BASE.delete(base_comune);
    const rec = MP_SITE_MARKERS.find(x => x.comune === base_comune);
    if (rec) mp_updateMarkerBadge(rec.marker, base_comune);
    mp_renderPlanTable();
    mp_updateEditorButtons();
}


// Abilita/disabilita i pulsanti dell'editor
function mp_updateEditorButtons() {
    const hasPlan = MP_PLAN.length > 0;
    const comuneInput = document.getElementById('mp-comune');
    const comuneOk = !!mp_findComuneByName(comuneInput?.value || '') || !!MP_SITES.find(s => s.comune === normalizeComune(comuneInput?.value || ''));

    const btnMostra = document.querySelector('#map-plan-editor button.btn.ghost.block');     // "Mostra"
    const btnAdd = document.querySelector('#map-plan-editor button.btn.block');           // "Aggiungi al piano" (il primo .btn.block)
    const btnClear = document.getElementById('mp-clear');
    const btnExport = document.getElementById('mp-export');
    const btnEval = document.getElementById('btnEvalFromMap');

    if (btnMostra) btnMostra.disabled = !comuneOk;
    if (btnAdd) btnAdd.disabled = !comuneOk;
    if (btnClear) btnClear.disabled = !hasPlan;
    if (btnExport) btnExport.disabled = !hasPlan;
    if (btnEval) btnEval.disabled = !hasPlan;
}

function mp_renderPlanTable() {
    const el = document.getElementById('mp-table');
    if (!el) return; // <<— evita il crash
    if (!MP_PLAN.length) {
        el.innerHTML = `<em style="color:#6b7280">Nessuna unità nel piano.</em>`;
        return;
    }
    let html = `<table style="width:100%;font-size:12px;border-collapse:collapse">
    <thead><tr>
      <th style="text-align:left">Presidio/Comune</th>
      <th>Tipo</th><th>Sorgente</th><th>Qty</th><th></th>
    </tr></thead><tbody>`;
    for (const r of MP_PLAN) {
        html += `<tr>
      <td>${r.base_comune}</td>
      <td style="text-align:center">${r.tipo}</td>
      <td style="text-align:center">${r.source}</td>
      <td style="text-align:center">${r.qty}</td>
      <td style="text-align:right">
        <button class="btn small" onclick="mp_removeFromPlan('${r.base_comune.replace(/'/g, "\\'")}','${r.tipo}','${r.source}',1)">-1</button>
        <button class="btn small secondary" onclick="mp_removeFromPlan('${r.base_comune.replace(/'/g, "\\'")}','${r.tipo}','${r.source}',${r.qty})">rimuovi</button>
      </td>
    </tr>`;
    }
    html += `</tbody></table>`;
    el.innerHTML = html;
}


function mp_clear() {
    MP_PLAN = [];
    MP_COUNTS_BY_BASE.clear();
    document.getElementById('mp-table').innerHTML = `<em style="color:#6b7280;font-size:12px">Nessuna unità nel piano.</em>`;
    MP_FREE_LAYER && MP_FREE_LAYER.clearLayers();
    for (const rec of MP_SITE_MARKERS) mp_updateMarkerBadge(rec.marker, rec.comune);
}


// Popola la tendina con l’elenco dei comuni caricati
function mp_populateComuneList() {
    const dl = document.getElementById('mp-comuni-list');
    if (!dl) return;
    // evita duplicati
    const seen = new Set();
    const opts = [];
    for (const c of MP_COMMUNES) {
        if (c && c.comune && !seen.has(c.comune)) {
            seen.add(c.comune);
            opts.push(`<option value="${c.comune}"></option>`);
        }
    }
    dl.innerHTML = opts.join('');
}

// Trova il record del comune (normalizzando il nome)
function mp_findComuneByName(name) {
    const q = normalizeComune(name);
    if (!q) return null;
    return MP_COMMUNES.find(c => c.comune === q) || null;
}

// Evidenzia il punto e centra la mappa
function mp_zoomAndPing(lat, lon, label, tipo) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    try {
        map.setView([lat, lon], Math.max(map.getZoom(), 12), {animate: true});
    } catch {
    }
    const icon = iconFor((tipo || '').toUpperCase() || 'AMB_ILS'); // 🚑 stesse icone del modello
    const m = L.marker([lat, lon], {icon}).addTo(MP_FREE_LAYER)
        .bindTooltip(label || 'Selezione');

}

async function mp_addFromDropdown(addToPlan = true) {
    const inp = document.getElementById('mp-comune');
    if (!inp) return;
    const tipo = (document.getElementById('mp-type')?.value || 'AMB_ILS').toUpperCase();

    const rec = mp_findComuneByName(inp.value) || MP_SITES.find(s => s.comune === normalizeComune(inp.value));
    if (!rec) {
        alert('Comune non trovato. Sceglilo dalla lista.');
        return;
    }

    if (Number.isFinite(rec.lat) && Number.isFinite(rec.lon)) {
        mp_zoomAndPing(rec.lat, rec.lon, rec.comune, tipo);
    } else {
        alert(`Coordinate non disponibili per "${rec.comune}". Fornisci un CSV geocodificato.`);
    }

    if (addToPlan) {
        const qty = Math.max(1, parseInt(document.getElementById('mp-qty').value || '1', 10));
        const src = (document.getElementById('mp-source').value || 'any').toLowerCase();
        mp_addToPlan(rec.comune, tipo, qty, src);
    }
}


// valuta con /api/evaluate riusando la pipeline esistente
async function mp_eval() {
    try {
        // pulizia vista, ma mantieni l’estensione mappa
        resetRunView({keepExtent: true});
        const severityCheck = validateSeveritySelection();
        if (!severityCheck.ok) {
            alert(severityCheck.message);
            return;
        }

        // body base
        const body = buildRunBody();

        // ⬇️ porta dentro anche i parametri INFERMIERI/coupling dalla UI
        try {
            Object.assign(body, readNursesAndCouplingFromUI());
        } catch {
        }

        // piano dall’editor
        body.plan = Array.isArray(MP_PLAN) ? MP_PLAN.slice() : [];

        // chiama backend
        const res = await fetch('/api/evaluate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const j = await res.json();

        // KPI medici (subito, se presente)
        updateDoctorsKPI({
            usedApi: (j?.doctors_used ?? j?.doctors ?? j?.metrics?.doctors_used ?? null)
        });

        // KPI infermieri (subito, se presente)
        if (typeof j?.nurses_used === 'number') {
            updateNursesKpi({
                nurses_used: j.nurses_used,
                nurses_total: (typeof j?.nurses_total === 'number') ? j.nurses_total : undefined
            });
        } else {
            updateNursesKpi({nurses_used: NaN});
        }

        // error handling server
        if (!j.ok) {
            alert(j.error || 'Errore valutazione');
            return false;
        }

        // percorso risultati per reloadData()
        RUN_URL = j.out_web || fixRunPath(j.out_dir || '');
        if (!RUN_URL) {
            alert('Percorso dei risultati non disponibile (out_web/out_dir).');
            return false;
        }

        // housekeeping + ricarica CSV
        LAST_RUN_KIND = 'editor';
        updateDownloadButtons();
        await reloadData();

        // firma pulita post-valutazione
        LAST_SIG = computeSignature();
        return true;

    } catch (e) {
        console.error(e);
        alert('Errore durante la valutazione.');
        return false;
    }
}


// collega i bottoni dell’editor (chiamare dopo init mappa)
function mp_bindUI() {
    // EXPLAIN RESULTS 118
    bindExplain118UI();
    const reset118Button =
        document.getElementById(
            'btnReset118'
        );


    if (
        reset118Button
        && !reset118Button.dataset.bound
    ) {

        reset118Button.dataset.bound =
            '1';


        reset118Button.addEventListener(
            'click',
            resetPlanning118
        );
    }

    // PULSANTE: svuota piano
    const btnClear =document.getElementById('mp-clear');
    if (btnClear && !btnClear.dataset.bound) {
        btnClear.dataset.bound = '1';
        btnClear.addEventListener('click',mp_clear);
    }
    bindConfigIO();
    initModeTabs();
    document.getElementById('editParamsBtn')?.addEventListener('click', () => setPanelMode('mode-algo'));
    refreshParamSummary();

    bindConfigUploadAndDrop();
    // PULSANTE: esporta PDF (EDITOR) → rivaluta se necessario, poi PDF
    const btnExp = document.getElementById('mp-export');
    if (btnExp && !btnExp.dataset.bound) {
        btnExp.dataset.bound = '1';
        btnExp.innerHTML = `<i class="fa-solid fa-file-pdf"></i> Esporta PDF`;
        btnExp.classList.remove('secondary');

        btnExp.addEventListener('click', async (e) => {
            e.preventDefault();
            btnExp.disabled = true;
            btnExp.setAttribute('aria-busy', 'true');
            try {
                await ensureFreshEvaluation();   // SOLO editor: se piano cambiato, valuta
                await generatePDFReport();      // poi genera dal RUN corrente
            } catch (err) {
                alert('Impossibile generare il PDF: ' + (err?.message || err));
            } finally {
                btnExp.disabled = false;
                btnExp.removeAttribute('aria-busy');
            }
        });
    }

    async function generatePDFReport() {
        if (!RUN_URL || !Array.isArray(LAST_CHOSEN) || LAST_CHOSEN.length === 0) {
            alert('Nessun dato da impaginare: esegui una OTTIMIZZAZIONE o una VALUTAZIONE prima di esportare il PDF.');
            return;
        }
        if (!window.jspdf || !window.jspdf.jsPDF) {
            alert('Libreria PDF non disponibile');
            return;
        }
        const {jsPDF} = window.jspdf;

        const itInt = n => (n == null || isNaN(n)) ? '–' : Math.round(Number(n)).toLocaleString('it-IT');
        const itPct = x => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(1) + '%';

        const parseDoctorsFromTxt = (txt) => {
            if (!txt) return null;
            const m = txt.match(/(?:medici\s*(?:richiesti|totali|usati)|doctors(?:\s*needed|\s*total|\s*used)?)\D+(\d+(?:[.,]\d+)?)/i);
            return m ? Number(m[1].replace(',', '.')) : null;
        };

        // usa i dati già caricati per aggiornare la pill dei medici
        const cap = Number(document.getElementById('docTotal')?.value || NaN);
        let n = parseDoctorsFromTxt(LAST_DOCTORS_TXT || '');

// fallback: se manca il TXT, prova a sommare una colonna "doctors_need" nel chosen
        if (n == null && Array.isArray(LAST_CHOSEN) && LAST_CHOSEN.length) {
            const key = ['doctors_need', 'docs_need', 'medici', 'doctors', 'doctors_required']
                .find(k => k in LAST_CHOSEN[0]);
            if (key) n = LAST_CHOSEN.reduce((a, r) => a + (+r[key] || 0), 0);
        }

        setDoctorsKPI(n, cap);


        const any = covTotals(LAST_COV_ANY);
        const doc = covTotals(LAST_COV_DOC);
        const staffNum = parseDoctorsFromTxt(LAST_DOCTORS_TXT || '');
        const {perType, totals} = prepareCosts(LAST_CHOSEN || []);

        const pdf = new jsPDF({unit: 'pt', format: 'a4'});
        const M = {l: 44, r: 44, t: 52, b: 52};
        const line = y => pdf.setLineWidth(0.6).setDrawColor(230).line(M.l, y, 595 - M.r, y);

        // Intestazione
        const title = 'Rete UOC 118 · Piano';
        const right = `ASL Benevento 118 · ${new Date().toLocaleString('it-IT')}`;
        pdf.setFont('helvetica', 'bold').setFontSize(16).text(title, M.l, M.t);
        pdf.setFont('helvetica', 'normal').setFontSize(10).text(right, 595 - M.r, M.t, {align: 'right'});
        line(M.t + 14);
        let y = M.t + 38;

        // KPI
        pdf.setFont('helvetica', 'bold').setFontSize(12).text('Indicatori di copertura', M.l, y);
        y += 16;
        pdf.setFont('helvetica', 'normal').setFontSize(11);
        pdf.text(`Copertura ANY: ${itPct(any.pct)} (${itInt(any.calls)} chiamate eq.)`, M.l, y);
        pdf.text(`Copertura con Medico (R+G): ${itPct(doc.pct)} (${itInt(doc.calls)} chiamate eq.)`, 595 / 2, y);
        y += 16;
        pdf.text(`Medici richiesti da slot attivi: ${staffNum != null ? itInt(staffNum) : '–'}`, M.l, y);

        // Costi
        line(y + 14);
        y += 28;
        pdf.setFont('helvetica', 'bold').setFontSize(12).text('Riepilogo costi', M.l, y);

        const bodyRows = (perType || []).map(r => [
            r.tipo, String(r.n), String(r.nNew),
            euro(r.cxUnit), euro(r.oxUnit), euro(r.cxTot), euro(r.oxTot),
        ]);

        pdf.autoTable({
            startY: y + 10,
            head: [['Tipo', '# Attive', '# Nuove', 'CAPEX / unità', 'OPEX / unità', 'CAPEX Totale', 'OPEX Totale']],
            body: bodyRows.length ? bodyRows : [['–', '0', '0', '0 €', '0 €', '0 €', '0 €']],
            foot: [
                ['Totale', String(totals.units || 0), String(totals.newUnits || 0), '', '', euro(totals.capex || 0), euro(totals.opex || 0)],
                [{
                    content: 'CAPEX “Acquisti” (solo nuove):',
                    colSpan: 5,
                    styles: {halign: 'right'}
                }, {content: euro(totals.capexNew || 0), colSpan: 1}],
            ],
            styles: {font: 'helvetica', fontSize: 10, cellPadding: 4},
            headStyles: {fillColor: [13, 110, 253], textColor: 255},
            footStyles: {fillColor: [245, 247, 255], textColor: 20},
            margin: {left: M.l, right: M.r}
        });


        // Unità attive (dal run corrente)
        let y3 = pdf.lastAutoTable ? pdf.lastAutoTable.finalY + 24 : (y2 + 120);
        pdf.setFont('helvetica', 'bold').setFontSize(12).text('Unità attive (run)', M.l, y3);

        const chosen = Array.isArray(LAST_CHOSEN) ? LAST_CHOSEN : [];
        const unitRows = (chosen.length ? chosen : [{tipo: '—', site_id: '—', base_comune: '—'}])
            .map((r, i) => [String(i + 1), String(r.tipo || ''), String(r.site_id || r.site || r.slot || ''), String(r.base_comune || r.base || r.comune || '')]);

        pdf.autoTable({
            startY: y3 + 10,
            head: [['#', 'Tipo', 'Site', 'Base']],
            body: unitRows,
            styles: {font: 'helvetica', fontSize: 10, cellPadding: 4},
            headStyles: {fillColor: [40, 40, 40], textColor: 255},
            margin: {left: M.l, right: M.r},
            didDrawPage: () => {
                pdf.setFont('helvetica', 'normal').setFontSize(9).setTextColor(120);
                const runInfo = `Run: ${RUN_URL || '(non salvato)'} · Data dir: ${(CONFIG && CONFIG.dataDir) || 'data'}`;
                pdf.text(runInfo, M.l, 842 - M.b + 20);
                pdf.text(String(pdf.internal.getNumberOfPages()), 595 - M.r, 842 - M.b + 20, {align: 'right'});
            }
        });

        // Download
        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const fname = `Rete_UOC_118_Report_${ts}.pdf`;
        const blob = pdf.output('blob');

        try {
            if (typeof trySaveReportOnServer === 'function') {
                const saved = await trySaveReportOnServer(blob, fname);
                if (saved) return;
            }
        } catch {
        }

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = fname;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            URL.revokeObjectURL(a.href);
            a.remove();
        }, 800);
    }

    // PULSANTE: Report (PDF) nella lista Unità attive → NON rivaluta, usa il run corrente
    const btnPdf = document.getElementById('dlPDF');
    if (btnPdf && !btnPdf.dataset.bound) {
        btnPdf.dataset.bound = '1';
        btnPdf.addEventListener('click', async (e) => {
            e.preventDefault();
            btnPdf.disabled = true;
            btnPdf.setAttribute('aria-busy', 'true');
            try {
                // niente ensureFreshEvaluation qui: evitiamo di “sostituire” il run con la mappa
                await generatePDFReport();
            } catch (err) {
                alert('Impossibile generare il PDF: ' + (err?.message || err));
            } finally {
                btnPdf.disabled = false;
                btnPdf.removeAttribute('aria-busy');
            }
        });
    }

    // PULSANTE: Valuta su mappa
    const btnEval = document.getElementById('btnEvalFromMap');
    // Esempio: click su "Valuta piano"
    document.getElementById('btnEvalFromMap')?.addEventListener('click', async () => {
        resetRunView({keepExtent: true});   // ← svuota tutto ma mantiene lo zoom
        await mp_eval();                       // poi disegna i risultati della valutazione
    });

    if (btnEval && !btnEval.dataset.bound) {
        btnEval.dataset.bound = '1';
        btnEval.addEventListener('click', mp_eval);
    }

    // Input che influenzano lo stato dei pulsanti editor
    const comuneInp = document.getElementById('mp-comune');
    ['input', 'change', 'blur'].forEach(ev => comuneInp?.addEventListener(ev, mp_updateEditorButtons));
    document.getElementById('mp-type')?.addEventListener('change', mp_updateEditorButtons);
    document.getElementById('mp-qty')?.addEventListener('input', mp_updateEditorButtons);
    document.getElementById('mp-source')?.addEventListener('change', mp_updateEditorButtons);

    mp_updateEditorButtons();
}


// ---- Utilità parsing ----
const toFixed = (x, n = 2) => Number(x).toFixed(n);

function parsePairs(str) {
    const out = {};
    if (!str) return out;
    str.split(',').map(s => s.trim()).filter(Boolean).forEach(kv => {
        const [k, v] = kv.split('=');
        if (k) out[k.trim()] = (v ?? '').toString().trim();
    });
    return out;
}


function stringifyPairs(obj) {
    if (!obj || typeof obj !== 'object') return '';
    return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join(',');
}


function itInt(n) {
    return (n == null || isNaN(n))
        ? '–'
        : Math.round(Number(n)).toLocaleString('it-IT');
}

function parseDoctorsFromTxt(txt) {
    if (!txt) return null;
    // IT: Medici richiesti/totali/usati ...
    // EN: Doctors needed/total/used/required ...
    let m = txt.match(/(?:medici\s*(?:richiesti|totali|usati)|doctors\s*(?:needed|total|used|required))\D+(\d+(?:[.,]\d+)?)/i);
    if (m) return Number(m[1].replace(',', '.'));
    // fallback: primo numero nel file
    m = txt.match(/(\d+(?:[.,]\d+)?)/);
    return m ? Number(m[1].replace(',', '.')) : null;
}

function compilePairs(obj) {
    return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join(',');
}

function parseList(str) {
    return (str || '').split(',').map(s => s.trim()).filter(Boolean);
}

// ---- Binder controlli ↔ hidden ----
function initControlsFromHidden() {
    // Toggle Avanzate
    const advToggle = document.getElementById('advToggle');
    const box = document.querySelector('.runbox');
    advToggle?.addEventListener('change', () => box?.classList.toggle('show-adv', advToggle.checked));

    // Soglie T
    const T = parsePairs(document.getElementById('paramT').value);
    const tIds = ['ROSSO', 'GIALLO', 'VERDE', 'BIANCO'];
    tIds.forEach(k => {
        const s = document.getElementById('t' + k);
        const o = document.getElementById('t' + k + '_val');
        const def = (k === 'ROSSO' ? 8 : k === 'GIALLO' ? 20 : k === 'VERDE' ? 30 : 45);
        const v = Number(T[k] ?? def);
        if (s) {
            s.value = v;
            o && (o.textContent = v);
            s.addEventListener('input', syncParamT);
        }
    });
    syncParamT();

    // Type-speed
    const TS = parsePairs(document.getElementById('typeSpeed').value);
    ['AUTO_MED', 'AMB_ALS', 'AMB_ILS', 'CMR'].forEach(k => {
        const s = document.getElementById('sp' + k);
        const o = document.getElementById('sp' + k + '_val');
        const v = Number(TS[k] ?? 1.00);
        if (s) {
            s.value = v;
            o && (o.textContent = toFixed(v, 2) + '×');
            s.addEventListener('input', () => {
                o && (o.textContent = toFixed(s.value, 2) + '×');
                syncTypeSpeed();
            });
        }
    });
    syncTypeSpeed();

    // CAPEX / OPEX
    const CX = parsePairs(document.getElementById('capex').value);
    const OX = parsePairs(document.getElementById('opex').value);
    ['AUTO_MED', 'AMB_ALS', 'AMB_ILS', 'PSAUT', 'CMR'].forEach(k => {
        const cx = document.getElementById('cx' + k);
        if (cx) {
            cx.value = Number(CX[k] ?? 0);
            cx.addEventListener('input', syncCapex);
        }
        const ox = document.getElementById('ox' + k);
        if (ox) {
            ox.value = Number(OX[k] ?? 0);
            ox.addEventListener('input', syncOpex);
        }
    });
    syncCapex();
    syncOpex();

    // Doctor-codes
    const codes = new Set(parseList(document.getElementById('docCodes').value));
    ['ROSSO', 'GIALLO', 'VERDE', 'BIANCO'].forEach(k => {
        const chk = document.getElementById('dc' + k);
        if (chk) {
            chk.checked = codes.has(k);
            chk.addEventListener('change', syncDocCodes);
        }
    });
    syncDocCodes();

    // Staff
    const ST = parsePairs(document.getElementById('staff').value);
    const defaults = {PSAUT: 6, AUTO_MED: 3, AMB_ALS: 3};
    Object.entries(defaults).forEach(([k, def]) => {
        const inp = document.getElementById('st' + k);
        if (inp) {
            inp.value = Number(ST[k] ?? def);
            inp.addEventListener('input', syncStaff);
        }
    });
    syncStaff();

    // Verbose switch → select
    const verbVal = document.getElementById('verbose')?.value || '--verbose';
    const vSw = document.getElementById('verboseSwitch');
    if (vSw) {
        vSw.checked = (verbVal === '--verbose');
        vSw.addEventListener('change', () => {
            const v = document.getElementById('verbose');
            if (v) v.value = vSw.checked ? '--verbose' : '';
        });
    }

    // === BUDGET: collega i controlli visibili agli hidden usati da buildRunBody ===
    (function wireBudgetControls() {
        const uiBT = document.getElementById('uiBudgetTotal'); // numero visibile
        const uiBM = document.getElementById('uiBudgetMode');  // select visibile
        const hBT = document.getElementById('budgetTotal');   // hidden letto da buildRunBody
        const hBM = document.getElementById('budgetMode');    // hidden letto da buildRunBody

        if (!uiBT || !uiBM || !hBT || !hBM) return;

        // inizializza UI dai hidden se ricarichi la pagina
        uiBT.value = hBT.value || '';
        // UI usa: "" | "capex" | "capex_opex"
        // Solver/CLI usa (di solito): "" | "purchase" | "all".
        // Qui lasciamo nella UI i valori "capex / capex_opex" e li mappiamo nel hidden.
        const mapUiToHidden = (v) => v === 'capex' ? 'purchase' : (v === 'capex_opex' ? 'all' : '');
        const mapHiddenToUi = (v) => v === 'purchase' ? 'capex' : (v === 'all' ? 'capex_opex' : '');
        uiBM.value = mapHiddenToUi(hBM.value || '');

        // sincronizza mentre l’utente digita/cambia
        uiBT.addEventListener('input', () => {
            hBT.value = (uiBT.value || '').trim();   // numero o vuoto per “nessun vincolo”
        });
        uiBM.addEventListener('change', () => {
            hBM.value = mapUiToHidden(uiBM.value);   // "capex"→"purchase", "capex_opex"→"all"
        });

        // esegui una prima sync ora
        hBT.value = (uiBT.value || '').trim();
        hBM.value = mapUiToHidden(uiBM.value);
    })();

}

function syncParamT() {
    const obj = {
        ROSSO: Number(document.getElementById('tROSSO')?.value || 0),
        GIALLO: Number(document.getElementById('tGIALLO')?.value || 0),
        VERDE: Number(document.getElementById('tVERDE')?.value || 0),
        BIANCO: Number(document.getElementById('tBIANCO')?.value || 0)
    };
    const setTxt = (id, val) => {
        const o = document.getElementById(id);
        if (o) o.textContent = val;
    };
    setTxt('tROSSO_val', obj.ROSSO);
    setTxt('tGIALLO_val', obj.GIALLO);
    setTxt('tVERDE_val', obj.VERDE);
    setTxt('tBIANCO_val', obj.BIANCO);
    const h = document.getElementById('paramT');
    if (h) h.value = compilePairs(obj);
}


function syncTypeSpeed() {
    const obj = {
        AUTO_MED: toFixed(document.getElementById('spAUTO_MED')?.value || 1, 2),
        AMB_ALS: toFixed(document.getElementById('spAMB_ALS')?.value || 1, 2),
        AMB_ILS: toFixed(document.getElementById('spAMB_ILS')?.value || 1, 2),
        CMR: toFixed(document.getElementById('spCMR')?.value || 1, 2)   // ← nuovo
    };
    const h = document.getElementById('typeSpeed');
    if (h) h.value = compilePairs(obj);
}

function syncCapex() {
    const obj = {
        AUTO_MED: Number(document.getElementById('cxAUTO_MED')?.value || 0),
        AMB_ALS: Number(document.getElementById('cxAMB_ALS')?.value || 0),
        AMB_ILS: Number(document.getElementById('cxAMB_ILS')?.value || 0),
        PSAUT: Number(document.getElementById('cxPSAUT')?.value || 0),
        CMR: Number(document.getElementById('cxCMR')?.value || 0)       // ← nuovo
    };
    document.getElementById('capex').value = compilePairs(obj);
}

function syncOpex() {
    const obj = {
        AUTO_MED: Number(document.getElementById('oxAUTO_MED')?.value || 0),
        AMB_ALS: Number(document.getElementById('oxAMB_ALS')?.value || 0),
        AMB_ILS: Number(document.getElementById('oxAMB_ILS')?.value || 0),
        PSAUT: Number(document.getElementById('oxPSAUT')?.value || 0),
        CMR: Number(document.getElementById('oxCMR')?.value || 0)       // ← nuovo
    };
    document.getElementById('opex').value = compilePairs(obj);
}

// Carica un GeoJSON dei comuni (prende il primo che trova)
async function loadComuniGeo() {
    const base = CONFIG.dataDir || 'data';
    const candidates = [
        `${base}/comuni_benevento.geojson`,
        `${base}/comuni.geojson`,
        `dataset/data/comuni_benevento.geojson`
    ];
    for (const url of candidates) {
        if (await fileExists(url)) {
            const geojson = await fetch(url, {cache: 'no-store'}).then(r => r.json());
            return {url, geojson};
        }
    }
    return null;
}

function syncDocCodes() {
    const parts = [];
    ['ROSSO', 'GIALLO', 'VERDE', 'BIANCO'].forEach(k => {
        if (document.getElementById('dc' + k)?.checked) parts.push(k);
    });
    const h = document.getElementById('docCodes');
    if (h) h.value = parts.join(',');
}

function syncStaff() {
    const obj = {
        PSAUT: Number(document.getElementById('stPSAUT')?.value || 0),
        AUTO_MED: Number(document.getElementById('stAUTO_MED')?.value || 0),
        AMB_ALS: Number(document.getElementById('stAMB_ALS')?.value || 0),
        CMR: Number(document.getElementById('stCMR')?.value || 0)
    };
    const h = document.getElementById('staff');
    if (h) h.value = compilePairs(obj);
}


let layersCtl;                 // controllo Leaflet layers
const CRIT_PANE = 'critPane';  // pane dedicata

function ensureCritPaneAndControl() {
    if (!map.getPane(CRIT_PANE)) {
        map.createPane(CRIT_PANE);
        map.getPane(CRIT_PANE).style.zIndex = 625; // sopra i marker standard (600)
    }
    if (!layersCtl) {
        layersCtl = L.control.layers({}, {}, {position: 'topright', collapsed: true}).addTo(map);
    }
}

// ---- Palette (basso rischio→alto rischio)
const CRIT_PALETTE = ['#e8f6e3', '#a6d97a', '#5fb164', '#f7c65a', '#f08a4b', '#e24b3b'];

let CRIT_BREAKS = null;
let CRIT_GET_FILL = v => '#e5e7eb';
let CRIT_GET_STROKE = v => '#9ca3af';

// Costruisce i quantili e funzioni colore a partire da CRIT_DATA
function updateCritScaleFromScores() {
    if (CRIT_DISPLAY_MODE === "tier") {
        CRIT_BREAKS = null;
        CRIT_GET_FILL = value => {

            const score =Number(value);
            if (score >= 0.90) {
                return "#e24b3b";
            }
            if (score >= 0.50) {
                return "#f7c65a";
            }
            return "#5fb164";
        };


        CRIT_GET_STROKE = value => {
            const score =Number(value);
            if (score >= 0.90) {
                return "#a92e27";
            }
            if (score >= 0.50) {
                return "#bd8b21";
            }
            return "#397c43";
        };

        const legend =document.getElementById("critLegend");

        if (legend) {

            legend.innerHTML = `
                <div><b>Severità territoriale</b></div>
    
                <div style="display:grid;gap:6px;margin-top:7px;">
                    <div><i style="display:inline-block;width:14px;height:14px;margin-right:7px;background:#e24b3b"></i>ALTA</div>
                    <div><i style="display:inline-block;width:14px;height:14px;margin-right:7px;background:#f7c65a;"></i>MEDIA</div>
                    <div><i style="display:inline-block;width:14px;height:14px;margin-right:7px;background:#5fb164;"></i>BASSA</div>
                </div>
            `;
        }
        return;
    }
    const vals = Array.from((CRIT_DATA || new Map()).values())
        .map(d => Number(d.score))
        .filter(x => Number.isFinite(x))
        .sort((a, b) => a - b);

    if (!vals.length) {
        CRIT_BREAKS = null;
        return;
    }

    const q = p => {
        const idx = (vals.length - 1) * p;
        const lo = Math.floor(idx), hi = Math.ceil(idx);
        if (lo === hi) return vals[lo];
        const h = idx - lo;
        return vals[lo] + h * (vals[hi] - vals[lo]);
    };

    // 5 classi → 6 break: min, q20, q40, q60, q80, max
    CRIT_BREAKS = [vals[0], q(0.2), q(0.4), q(0.6), q(0.8), vals[vals.length - 1]];

    CRIT_GET_FILL = v => {
        if (v == null || isNaN(v)) return '#e5e7eb';
        if (v <= CRIT_BREAKS[1]) return CRIT_PALETTE[0];
        if (v <= CRIT_BREAKS[2]) return CRIT_PALETTE[1];
        if (v <= CRIT_BREAKS[3]) return CRIT_PALETTE[2];
        if (v <= CRIT_BREAKS[4]) return CRIT_PALETTE[3];
        return CRIT_PALETTE[5];
    };

    // bordo un po’ più scuro per ogni classe
    const STROKES = ['#7dab5f', '#5b9956', '#3e874d', '#ce9c2e', '#c86831', '#b33a32'];
    CRIT_GET_STROKE = v => {
        if (v == null || isNaN(v)) return '#9ca3af';
        return (v <= CRIT_BREAKS[1]) ? STROKES[0]
            : (v <= CRIT_BREAKS[2]) ? STROKES[1]
                : (v <= CRIT_BREAKS[3]) ? STROKES[2]
                    : (v <= CRIT_BREAKS[4]) ? STROKES[3]
                        : STROKES[5];
    };

    // Aggiorna legenda con classi
    const Lg = document.getElementById('critLegend');
    if (Lg) {
        const fmt = x => (x == null ? '–' : (x * 100).toFixed(0) + '%');
        Lg.innerHTML = `
      <div><b>Criticità (quantili)</b></div>
      <div style="display:grid;grid-template-columns:1fr;gap:4px;margin-top:6px">
        ${[1, 2, 3, 4, 5].map(i => `
          <div style="display:flex;align-items:center;gap:8px">
            <i style="width:14px;height:14px;border:1px solid #666;background:${CRIT_GET_FILL(CRIT_BREAKS[i])}"></i>
            <span style="font-size:12px">${fmt(CRIT_BREAKS[i - 1])} – ${fmt(CRIT_BREAKS[i])}</span>
          </div>`).join('')}
      </div>`;
    }

    // Debug utile in console
    console.log('[CRIT scale]',
        {
            min: CRIT_BREAKS[0], q20: CRIT_BREAKS[1], q40: CRIT_BREAKS[2],
            q60: CRIT_BREAKS[3], q80: CRIT_BREAKS[4], max: CRIT_BREAKS[5]
        });
}


function getCriticitaDemandSource() {
    const source =(document.getElementById("severitySource") ?.value || "original").trim();
    const scenarioId =(document.getElementById("severityScenarioId") ?.value || "").trim();

    if (source === "population_health") {
        if (!scenarioId) {
            throw new Error("Population Health è selezionato, ma non è disponibile uno scenario di severità confermato.");
        }

        const params = new URLSearchParams({severity_source: "population_health", severity_scenario_id:scenarioId,});

        return {
            source,
            scenarioId,
            url:"/api/118/severity/demand.csv?" + params.toString(),
            label:"Population Health",
        };
    }
    const params =new URLSearchParams({severity_source:"original",});
    return {source: "original", scenarioId: "", url: "/api/118/severity/demand.csv?" + params.toString(), label:"Dataset originale 118",};
}


/*// === Nuova loadCriticita: robusta (tempo vs domanda) ===
async function loadCriticita() {
    if (CRIT_DATA) return CRIT_DATA;

    const base = CONFIG.dataDir || 'data';
    const candidates = [
        `${base}/weighted_demand_by_comune_code.csv`, // <- la tua
        `${base}/demand_by_comune_code.csv`
    ];
    let path = null;
    for (const p of candidates) if (await fileExists(p)) {
        path = p;
        break;
    }

    const rows = path ? await loadCSV(path) : [];
    if (!rows?.length) {
        CRIT_DATA = new Map();
        return CRIT_DATA;
    }

    const nameK = pickKeyCI(rows[0], ['comune', 'denominazione', 'nome_comune', 'name']);
    const codeK = pickKeyCI(rows[0], ['comune_code', 'istat', 'codice_istat', 'codice_comune']);
    const timeK = pickKeyCI(rows[0], ['rt_min', 'risposta_min', 'tempo_min', 'response_time', 'tempo']);
    const demandK = pickKeyCI(rows[0], [
        'weighted_demand', 'demand', 'weighted', 'calls', 'chiamate', 'peso_domanda',
        'n_missioni_pesate', 'n_missioni', 'missioni', 'n_chiamate', 'totale_missioni'
    ]);

    const toNum = v => {
        const n = Number(String(v ?? '').replace(',', '.'));
        return Number.isFinite(n) ? n : null;
    };

    // Map input -> {comune, time, demand}
    const recs = [];
    let matched = 0, skipped = 0;
    for (const r of rows) {
        // nome dal CSV o da codice istat
        let nome = '';
        if (nameK && r[nameK]) nome = normalizeComune(r[nameK]);
        else if (codeK && r[codeK] != null) {
            const code = String(r[codeK]).trim().padStart(6, '0');
            const hit = MP_BY_CODE?.get?.(code);
            if (hit) nome = hit.comune;
        }
        if (!nome) {
            skipped++;
            continue;
        }

        const t = timeK ? toNum(r[timeK]) : null;
        const d = demandK ? toNum(r[demandK]) : null;
        if (t == null && d == null) {
            skipped++;
            continue;
        }

        recs.push({comune: nome, time: t, demand: d});
        matched++;
    }
    if (!recs.length) {
        CRIT_DATA = new Map();
        return CRIT_DATA;
    }

    // --- Scelta base dello score ---
    const targetMin = 21;
    const exceed = recs.filter(x => x.time != null && x.time > targetMin);
    const hasVarTime = exceed.length >= Math.max(1, Math.round(0.2 * recs.length)) &&
        (Math.max(...exceed.map(x => x.time)) - Math.min(...exceed.map(x => x.time))) > 1e-6;

    // helper: normalizzazione 0..1 con fallback a ranking
    const norm01 = (vals) => {
        const arr = vals.slice();
        const vmin = Math.min(...arr.filter(v => v != null));
        const vmax = Math.max(...arr.filter(v => v != null));
        const span = vmax - vmin;
        if (!(span > 0)) {
            // tutti uguali → ranking uniforme per avere variazione visiva
            const uniq = Array.from(new Set(arr.filter(v => v != null))).sort((a, b) => a - b);
            const rank = new Map(uniq.map((v, i) => [v, i / (Math.max(uniq.length - 1, 1))]));
            return arr.map(v => v == null ? null : rank.get(v));
        }
        return arr.map(v => v == null ? null : (v - vmin) / span);
    };

    let basis = '';
    let scores = [];

    if (hasVarTime) {
        // usa il supero della soglia
        const exceedAmt = recs.map(x => x.time == null ? null : Math.max(0, x.time - targetMin));
        const sTime = norm01(exceedAmt);
        // opzionale: mix con domanda se disponibile
        if (recs.some(x => x.demand != null)) {
            const sDem = norm01(recs.map(x => x.demand));
            scores = sTime.map((v, i) => v == null ? (sDem[i] ?? null) : (sDem[i] == null ? v : 0.6 * v + 0.4 * sDem[i]));
            basis = 'tempo (supero) + domanda';


        } else {
            scores = sTime;
            basis = 'tempo (supero)';
        }
    } else {
        // tempi tutti sotto soglia o senza variabilità → usa domanda pesata
        scores = norm01(recs.map(x => x.demand));
        basis = 'domanda';
    }

    const mp = new Map();
    recs.forEach((x, i) => {
        const s = scores[i];
        mp.set(x.comune, {
            score: (s == null ? 0 : Math.max(0, Math.min(1, s))),
            time: x.time ?? null,
            demand: x.demand ?? null
        });
    });

    document.getElementById('critStatus')?.replaceChildren(
        `Sorgente: ${path} · Comuni mappati: ${matched} — non mappati: ${skipped} · base: ${basis}`
    );

    CRIT_DATA = mp;
    return CRIT_DATA;


}*/

async function loadCriticita(forceReload = false) {

    if (CRIT_DATA && !forceReload) {
        return CRIT_DATA;
    }
    if (forceReload) {
        CRIT_DATA = null;
    }

    let sourceInfo;
    try {
        sourceInfo =getCriticitaDemandSource();
    }catch (error) {
        CRIT_DATA = new Map();
        document.getElementById("critStatus") ?.replaceChildren(error.message);
        throw error;
    }

    const rows =await loadCSV(sourceInfo.url);
    if (!rows?.length) {
        CRIT_DATA = new Map();
        document.getElementById("critStatus") ?.replaceChildren( "Nessun dato di domanda disponibile.");
        return CRIT_DATA;
    }

    const nameK = pickKeyCI( rows[0], ["comune","denominazione","nome_comune","name",]);
    const codeK =pickKeyCI(rows[0],["comune_code","istat","codice_istat","codice_comune",]);
    const timeK =pickKeyCI(rows[0],["rt_min","risposta_min","tempo_min","response_time","tempo",]);
    const demandK =pickKeyCI(rows[0],["weighted_demand","demand","weighted","calls","chiamate","peso_domanda","n_missioni_pesate","n_missioni","missioni","n_chiamate","totale_missioni",]);
    const tierK =pickKeyCI(rows[0],["severity_tier","tier","severita","severity"]);
    const tierWeightK =pickKeyCI(rows[0],["tier_weight","severity_weight"]);
    const toNum = value => {
        const number =Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(number) ? number: null;
    };

    // ====================================================
    // AGGREGAZIONE PER COMUNE
    // ====================================================
    //
    // weighted_demand_by_comune_code.csv contiene una riga per: comune × ROSSO/GIALLO/VERDE/BIANCO
    // Per la mappa territoriale vogliamo invece UNA osservazione per comune
    // La domanda viene quindi sommata sui codici.


    const aggregated =new Map();
    let skippedRows = 0;

    for (const row of rows) {
        let comune = "";
        if (nameK && row[nameK]) {
            comune =normalizeComune(row[nameK]);
        }
        else if (codeK && row[codeK] != null) {
            const code =String(row[codeK]).trim().padStart(6,"0");
            const hit = MP_BY_CODE ?.get?.(code);
            if (hit) {
                comune = hit.comune;
            }
        }

        if (!comune) {
            skippedRows++;
            continue;
        }

        const time = timeK ? toNum(row[timeK]) : null;
        const demand = demandK ? toNum(row[demandK]) : null;
        if (time == null && demand == null) {
            skippedRows++;
            continue;
        }

        if (!aggregated.has(comune)) {
            aggregated.set(comune,{comune, demand: 0, hasDemand: false, timeSum: 0, timeCount: 0,severityTier: null,tierWeight: null});
        }
        const rec = aggregated.get(comune);
        if (demand != null) {
            rec.demand += demand;
            rec.hasDemand =true;
        }

        if (time != null) {
            rec.timeSum += time;
            rec.timeCount +=1;
        }

        if (tierK && row[tierK] != null) {

            const tier =String(row[tierK]).trim().toUpperCase();
            if (tier === "ALTA" || tier === "MEDIA" || tier === "BASSA") {
                if (rec.severityTier && rec.severityTier !== tier) {
                    console.warn("[CRIT] Tier incoerente per comune:", comune, rec.severityTier, tier);
                }
                rec.severityTier = tier;
            }
        }


        if ( tierWeightK && row[tierWeightK] != null) {

            const tierWeight = toNum(row[tierWeightK]);

            if (tierWeight != null) {
                rec.tierWeight = tierWeight;
            }
        }
    }

    const recs =Array.from(aggregated.values()).map(rec => ({
                comune:rec.comune,
                demand:rec.hasDemand ? rec.demand : null,
                time:rec.timeCount > 0 ? (rec.timeSum / rec.timeCount): null,
                severityTier:rec.severityTier,
                tierWeight: rec.tierWeight,
            }));

    if (!recs.length) {
        CRIT_DATA =new Map();
        return CRIT_DATA;
    }

    const hasSeverityTiers =recs.some(
        rec => rec.severityTier === "ALTA"  || rec.severityTier === "MEDIA" || rec.severityTier === "BASSA");

    // ====================================================
    // SCORE DI CRITICITÀ
    // ====================================================
    const targetMin = 21;
    const exceed = recs.filter( rec => rec.time != null && rec.time > targetMin);
    const hasVarTime = exceed.length>= Math.max(1,Math.round(0.2 * recs.length)) && (Math.max(...exceed.map(rec => rec.time)) - Math.min(...exceed.map(rec => rec.time))) > 1e-6;
    const norm01 = values => {
        const valid =values.filter(value =>value != null);
        if (!valid.length) {
            return values.map(() => null);
        }

        const min =Math.min(...valid);
        const max =Math.max(...valid);
        const span =max - min;

        if (!(span > 0)) {
            return values.map( value => value == null ? null : 0);
        }

        return values.map(value => value == null ? null : (value - min) / span);
    };

    let basis = "";
    let scores = [];


    if (hasSeverityTiers) {

        // Il file scenario contiene già la classificazione territoriale ufficiale per questo scenario.
        CRIT_DISPLAY_MODE ="tier";
        const tierScore = {BASSA: 0.20, MEDIA: 0.60,ALTA: 1.00,};

        scores =recs.map(rec =>tierScore[rec.severityTier] ?? null);
        basis ="tier territoriale";

    } else if (hasVarTime) {

        CRIT_DISPLAY_MODE ="quantile";
        const exceedAmount =recs.map(rec =>rec.time == null? null : Math.max(0,rec.time- targetMin));
        const timeScores =norm01(exceedAmount);

        if (recs.some(rec =>rec.demand != null)) {
            const demandScores =norm01(recs.map(rec =>rec.demand));
            scores =timeScores.map((value, index) => {
                        const demandScore =demandScores[index];
                        if (value == null) {
                            return demandScore;
                        }
                        if (demandScore== null) {
                            return value;
                        }
                        return (0.6 * value + 0.4 * demandScore);
                    }
                );
            basis ="tempo (supero) + domanda";
        }
        else {
            scores =timeScores;
            basis ="tempo (supero)";
        }
    }

    else {
        CRIT_DISPLAY_MODE = "quantile";
        scores =norm01(recs.map(rec => rec.demand));
        basis ="domanda territoriale";
    }

    const criticita =new Map();
    recs.forEach((rec, index) => {
            const score =scores[index];
            criticita.set(
                rec.comune,
                {
                    score:score == null ? 0 : Math.max(0,Math.min(1,score)),
                    time:rec.time,
                    demand:rec.demand,
                    severityTier: rec.severityTier,
                    tierWeight: rec.tierWeight
                }
            );
        }
    );

    const sourceDescription = sourceInfo.source === "population_health" ? (`Population Health · `+ `${sourceInfo.scenarioId}`) : "Dataset originale 118";
    document.getElementById("critStatus")?.replaceChildren(
            `Fonte: ${sourceDescription}`
            + ` · Comuni: ${criticita.size}`
            + ` · Righe escluse: ${skippedRows}`
            + ` · Base: ${basis}`
        );

    CRIT_DATA =criticita;
    return CRIT_DATA;
}


function critFillColor(x) {  // 0..1
    x = Math.max(0, Math.min(1, Number(x) || 0));
    const h = (1 - x) * 120;          // verde→rosso
    const s = 85;
    const l = 50 + 8 * Math.pow(x, 0.6); // leggermente più chiaro alle alte criticità
    return `hsl(${h},${s}%,${l}%)`;
}

function critStrokeColor(x) {
    x = Math.max(0, Math.min(1, Number(x) || 0));
    const h = (1 - x) * 120;
    return `hsl(${h},80%,35%)`;
}

function resetPlanning118() {

    const runId =
        current118RunId();


    const confirmed =
        window.confirm(
            'Vuoi avviare una nuova pianificazione?\n\n'
            + 'I risultati correnti e la spiegazione '
            + 'verranno rimossi dalla pagina.\n'
            + 'Gli artifact del run resteranno salvati '
            + 'per audit e riproducibilità.'
        );


    if (!confirmed) {
        return;
    }


    console.log(
        '[Planning 118] reset',
        runId
    );


    // =======================================================
    // 1. EXPLAIN RESULTS
    // =======================================================

    clearAllExplain118Cache();

    clearExplain118Content();

    setExplain118PanelOpen(
        false
    );


    // =======================================================
    // 2. ACTIVE RUN PERSISTENCE
    // =======================================================

    clearPersistedActive118Run();


    // =======================================================
    // 3. FRONTEND RUN STATE
    // =======================================================

    RUN_URL =
        null;

    LAST_RUN_KIND =
        null;


    try {

        LAST_SIG =
            null;

    } catch {
    }


    // =======================================================
    // 4. CLEAN PAGE
    //
    // Il reload impedisce che rimangano nel DOM KPI,
    // mappe o allocazioni appartenenti al vecchio run.
    // =======================================================

    window.location.reload();
}

// ---- INIT ----
async function init() {
    if (!window.L) {
        const el = document.getElementById('map');
        if (el) el.innerHTML = '<div style="padding:12px;color:#b00020">Errore: Leaflet non caricato.</div>';
        return;
    }

    map = L.map('map', {
        center: BENEVENTO_CENTER,
        zoom: 11,
        minZoom: 9,
        maxBounds: BENEVENTO_BOUNDS,
        maxBoundsViscosity: 1.0
    });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap'
    }).addTo(map);
    map.whenReady(() => map.invalidateSize());
    setTimeout(() => map.invalidateSize(), 100);
    window.addEventListener('resize', () => map.invalidateSize());

    layersByType = {
        AUTO_MED: L.layerGroup().addTo(map),
        AMB_ALS: L.layerGroup().addTo(map),
        AMB_ILS: L.layerGroup().addTo(map),
        PSAUT: L.layerGroup().addTo(map),
        CMR: L.layerGroup().addTo(map) // ⬅️ aggiungi questo
    };

    MP_FREE_LAYER = L.layerGroup().addTo(map);
    MP_PREVIEW_LAYER = L.layerGroup().addTo(map);
    ensureCritPaneAndControl();

    // Bottoni
    const btnRun = document.getElementById('btnRun');
    btnRun && (btnRun.onclick = runAlgorithm);

    // Filtri lista/mappa
    document.querySelectorAll('.flt').forEach(chk => {
        chk.addEventListener('change', () => {
            const t = chk.value;
            if (chk.checked) {
                layersByType[t] && map.addLayer(layersByType[t]);
            } else {
                layersByType[t] && map.removeLayer(layersByType[t]);
            }
            filterList();
            fitToData();
        });
    });
    document.getElementById('unitSearch')?.addEventListener('input', filterList);

    await loadConfig();
    await ensureValidDataDir();

    await mp_loadCommunes();
    await mp_loadSitesLayer();
    mp_backfillComuneCoordsFromSites();   // ⬅️ nuovo
    buildComuneIndexes();
    mp_populateComuneList();


// collega i bottoni (toggle, svuota, esporta, valuta)
    mp_bindUI();   // <— AGGIUNGI QUESTA RIGA
    // Binder controlli
    initControlsFromHidden();
    // Fonte severità territoriale
   const severitySourceEl =document.getElementById("severitySource");

    // Prima recuperiamo l'eventuale scenario
    // confermato dalla Population Health.
    restoreSeveritySelection();
    // Se arriviamo dalla Population Health con uno scenario
    // confermato, rendiamo subito visibile il layer Criticità.
    const restoredSeveritySource =(document.getElementById("severitySource") ?.value || "original").trim();
    const restoredScenarioId =(document.getElementById("severityScenarioId") ?.value || "").trim();
    const critToggle =document.getElementById("critToggle");

    if (restoredSeveritySource === "population_health" && restoredScenarioId && critToggle) {
        critToggle.checked = true;
    }

    // RESTORE LAST 118 RESULT AFTER PAGE RELOAD
    try {
        const restored =await restoreActive118Run();
        if (restored) {
            console.log('[Planning 118] last result restored');
        }

    } catch (error) {
        console.error('[Planning 118] last result restore failed', error);
    }

    if (severitySourceEl) {
        severitySourceEl.addEventListener("change", async() => {
                refreshSeveritySourceUI();
                persistSeveritySourceSelection();
                try {
                    refreshParamSummary();
                } catch {}

                try {

                    CRIT_DATA = null;
                    const critToggle =document.getElementById("critToggle");

                    if (critToggle && !critToggle.checked) {
                        critToggle.checked =true;
                    }
                    await renderCriticita(true);
                }

                catch (error) {
                    console.error("Errore aggiornamento criticità:", error);
                    document.getElementById("critStatus") ?.replaceChildren(error.message || "Impossibile aggiornare la mappa.");
                }
            }
        );
    }
    refreshSeveritySourceUI();

    // Toggle layer criticità
    const critTg = document.getElementById('critToggle');
    if (critTg) critTg.addEventListener('change', renderCriticita);


// accendi quando premi Esegui/Valuta (se presenti i bottoni)
    document.getElementById('btnRun')?.addEventListener('click', async () => {
        if (critTg && !critTg.checked) critTg.checked = true;
        await renderCriticita();
    });
    document.getElementById('btnEvalFromMap')?.addEventListener('click', async () => {
        if (critTg && !critTg.checked) critTg.checked = true;
        await renderCriticita();
    });

    document.getElementById('tab-editor').addEventListener('click', switchToValutazione);

    // Inquadra area Benevento
    try {
        map.fitBounds(BENEVENTO_BOUNDS);
    } catch (e) {}

    // Prima visualizzazione della criticità.
    //
    // Se arriviamo dalla Population Health con uno scenario valido,
    // la mappa deve essere caricata SEMPRE, anche se #critToggle
    // non è presente nella pagina.
    //
    // Per il dataset originale manteniamo invece il comportamento
    // del toggle, quando disponibile.
    try {

        const isPopulationHealthActive = restoredSeveritySource === "population_health" && Boolean(restoredScenarioId);
        const shouldRenderCriticita = isPopulationHealthActive || critToggle?.checked === true;

        if (isPopulationHealthActive && critToggle) {
            critToggle.checked = true;
        }

        if (shouldRenderCriticita) {
            await renderCriticita(true);
        }

    } catch (error) {
        console.error("Errore caricamento iniziale criticità:",error);
    }
}


function updateDoctorsKPI({usedApi = null, chosen = null} = {}) {
    const cap = Number(document.getElementById('docTotal')?.value || NaN);

    // 1) prova con dato API
    let used = (usedApi == null ? NaN : Number(usedApi));

    // 2) fallback: doctors_summary.txt
    if (!Number.isFinite(used)) {
        const parsed = parseDoctorsFromTxt((window.LAST_DOCTORS_TXT || ''));
        if (Number.isFinite(parsed)) used = parsed;
    }

    // 3) fallback: stima dai chosen
    if (!Number.isFinite(used)) {
        used = estimateDoctorsFromChosen(chosen || window.LAST_CHOSEN || []);
    }

    // 4) anti-zero: se è 0 o NaN ma nel PIANO ci sono unità “con medico”, usa la stima dal piano
    try {
        const plan = (window.MP_PLAN || []);
        const {total: estFromPlan, hasDocCapable} = estimateDoctorsFromPlan(plan);
        if ((used === 0 || !Number.isFinite(used)) && hasDocCapable && estFromPlan > 0) {
            used = estFromPlan;
        }
        console.table(window.MP_PLAN);
        console.log(estimateDoctorsFromPlan(window.MP_PLAN));

    } catch (e) {
        console.warn('plan fallback error:', e);
    }

    setDoctorsKPI(used, cap);
}


function normalizeType(t) {
    return String(t || '')
        .toUpperCase()
        .replace(/\s+/g, '')            // toglie spazi
        .replace(/[^A-Z_]/g, '')        // toglie caratteri strani
        .replace(/^AMBALS$/, 'AMB_ALS')
        .replace(/^AMBILS$/, 'AMB_ILS')
        .replace(/^AUTOMED$/, 'AUTO_MED')
        .replace(/^PSAUTO?$/, 'PSAUT'); // accetta PSAUT/PSAUTO
}

function estimateDoctorsFromPlan(plan) {
    const staffKV = parsePairs(document.getElementById('staff')?.value || '');
    // staff di default: AUTO_MED=3, AMB_ALS=3, PSAUT=6
    const staffFor = (t) => {
        const k = normalizeType(t);
        if (k === 'AUTO_MED') return Number(staffKV.AUTO_MED || 6);
        if (k === 'AMB_ALS') return Number(staffKV.AMB_ALS || 6);
        if (k === 'PSAUT') return Number(staffKV.PSAUT || 6);
        return 0; // AMB_ILS o altro → 0 medici
    };

    let tot = 0, hasDocCapable = false;
    (plan || []).forEach(r => {
        const t = normalizeType(r.tipo || r.type);
        const q = Number(r.qty || 0);
        const add = staffFor(t) * q;
        tot += add;
        if (add > 0) hasDocCapable = true; // AUTO_MED / AMB_ALS / PSAUT
    });
    return {total: tot, hasDocCapable};
}


function setRunAlgorithmStatus(state, message = '') {
    const status =document.getElementById('runAlgorithmStatus');

    if (!status) {
        return;
    }

    status.classList.remove('is-running','is-success', 'is-error');
    if (!state) {
        status.hidden = true;
        status.textContent = '';
        return;
    }

    status.hidden = false;
    if (state === 'running') {
        status.classList.add('is-running');
        status.innerHTML = '';
        const icon =document.createElement('i');
        icon.className = 'fa-solid fa-circle-notch fa-spin';
        const text =document.createElement('span');

        text.textContent = message || ('Algoritmo avviato. La pianificazione è in elaborazione.');
        status.append(icon, text);
        return;
    }

    if (state === 'success') {
        status.classList.add('is-success');
        status.textContent = message || ('Algoritmo completato. I risultati sono stati aggiornati.');
        return;
    }

    if (state === 'error') {
        status.classList.add('is-error');
        status.textContent =message || ('L’algoritmo non è stato completato.');
    }
}


function setRunAlgorithmBusy(busy) {

    const button = document.getElementById('btnRun');
    const resetButton = document.getElementById('btnReset118');
    if (!button) {
        return;
    }
    if (resetButton) {
        resetButton.disabled =!!busy;
    }

    button.disabled = !!busy;
    button.setAttribute( 'aria-busy', busy ? 'true' : 'false');

    if (busy) {
        button.innerHTML = '';
        const icon = document.createElement('i');
        icon.className ='fa-solid fa-circle-notch fa-spin';
        const text = document.createElement('span');
        text.textContent = 'Algoritmo in esecuzione';
        button.append(icon, text);
    } else {
        button.innerHTML = '';
        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-play';
        const text =document.createElement('span');
        text.textContent = 'Esegui algoritmo';
        button.append(icon, text);
    }
}

// ---- RUN ----
async function runAlgorithm() {
    resetRunView({keepExtent: true});
    const explainPreviousRunId = current118RunId();
    const log = document.getElementById('log');
    const spin = document.getElementById('spin');
    const severityCheck = validateSeveritySelection();

    if (!severityCheck.ok) {
        alert(severityCheck.message);
        if (log) {
            log.textContent = severityCheck.message;
        }
        return;
    }

    const diag = await preflightData(CONFIG.dataDir || 'data');
    if (!diag.ok) {
        renderDataStatus(diag);
        const msg = `${diag.message}\n\nMancano:\n - ${diag.missing.join('\n - ')}`;
        if (log) log.textContent = msg; else console.warn(msg);
        alert("Dati incompleti: completa i file o imposta il DATA DIR nel backend (/api/config).");
        return;
    }

    // 1) Payload base
    const body = buildRunBody();
    Object.assign(body, readNursesAndCouplingFromUI()); // ⬅️ include infermieri (anche CMR) nel POST

    // 2) Override UI → payload (infermieri & coupling)
    const v = id => (document.getElementById(id)?.value ?? '').trim();

    body.nurses_per_type =
        `PSAUT=${v('nuPSAUT') || 0},` +
        `AUTO_MED=${v('nuAUTO_MED') || 0},` +
        `AMB_ALS=${v('nuAMB_ALS') || 0},` +
        `AMB_ILS=${v('nuAMB_ILS') || 0}`;

    if (v('nurTotal')) body.nurses_total = Number(v('nurTotal'));
    else delete body.nurses_total;

    if (v('nurOpex')) body.nurse_unit_opex = Number(v('nurOpex'));
    else delete body.nurse_unit_opex;

    body.auto_med_transport = v('autoMedCoupling') || 'off';
    const delay = v('autoTransportDelay');
    if (delay) body.auto_transport_delay = Number(delay);

    // 3) Budget economico → decide lambda_cost (costo “soft”)
    const uiBudgetVal = v('uiBudgetTotal');
    const uiBudgetMode = v('uiBudgetMode'); // '' | 'capex' | 'capex_opex'
    if (uiBudgetVal && Number(uiBudgetVal) > 0) {
        body.budget_total = Number(uiBudgetVal);
        body.budget_mode = (uiBudgetMode === 'capex') ? 'purchase' : 'all';
        body.lambda_cost = 0;   // con budget, tieni una penalità al costo
    } else {
        delete body.budget_total;
        delete body.budget_mode;
        body.lambda_cost = 0;   // senza budget → massimizza solo copertura (compera se serve)
    }

  /*  // 4) Preset pro-copertura per “Ottimizza”
    body.objective = 'max_cover_budget';
    body.turnoff_doctor_families = 'on';
    body.doctor_cover = 'feasible-only';
*/
    //4) Parametri tecnici dell'ottimizzazione. objective e turnoff_doctor_families restano
    // temporaneamente gestiti internamente.doctor_cover NON viene forzato: deve rispettare il valore proveniente dalla UI.
    /*body.objective = 'max_cover_budget';
    body.turnoff_doctor_families = 'on';*/

    // assicura PSAUT in type_speed (per evitare il warning)
   /* if (typeof body.type_speed === 'string' && !/PSAUT=/.test(body.type_speed)) {
        body.type_speed += ',PSAUT =0.90';
    }*/

    // (opzionale) allarga anche lo spazio decisionale
    // body.bases = 'ALL';
    // body.reloc_psaut = 'on';

    // DEBUG: vedi esattamente cosa invii al backend
    console.log('[DEBUG /api/run payload]', body);

    // 5) Chiamata all'API
    setRunAlgorithmBusy(true);
    setRunAlgorithmStatus('running', 'Algoritmo avviato. La pianificazione è in elaborazione.');
    spin && spin.classList.add('on');
    log ? (log.textContent ='(algoritmo in esecuzione...)'): console.log('[RUN] algoritmo avviato...');

    console.log("[118] Payload finale:", structuredClone(body));
    try {
        const res = await fetch('/api/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const j = await res.json();

        let nice = (j.cmd ? j.cmd + '\n\n' : '') + (j.stdout || '');
        if (j.stderr) nice += `\n[stderr]\n${j.stderr}`;
        if (Array.isArray(j.missing) && j.missing.length) {
            nice += '\n\n[DATI MANCANTI]\n' + j.missing.map(x => ' - ' + x).join('\n');
            nice += "\n\nSuggerimento: imposta DATA DIR nel backend (/api/config) o copia i file nella cartella 'data'.";
        }
        if (j.error) nice += `\n\n[ERRORE] ${j.error}`;
        log ? (log.textContent = nice) : console.log(nice);

        if (j.ok && (j.out_web || j.out_dir)) {
            RUN_URL = j.out_web || fixRunPath(j.out_dir || '');
            const explainNewRunId =current118RunId();
            if (explainPreviousRunId && explainNewRunId && explainPreviousRunId !== explainNewRunId) {
                removeCachedExplain118(explainPreviousRunId);
            }
            EXPLAIN_118_LOADED_RUN_ID =null;

            if (!RUN_URL) {
                alert('Run completato ma non trovo il percorso web dei risultati.');
                return;
            }
            LAST_RUN_KIND = 'algo';
            persistActive118Run();
            LAST_SIG = computeSignature();
            updateDownloadButtons();
            await reloadData();
            setRunAlgorithmStatus('success', 'Algoritmo completato. I risultati della pianificazione sono disponibili.');

        } else if (!(Array.isArray(j.missing) && j.missing.length)) {
            setRunAlgorithmStatus('error', 'L’algoritmo non è stato completato.');
            alert('Errore esecuzione algoritmo');
        }

        // collega Report (PDF)
        const btnDlPDF = document.getElementById('dlPDF');
        if (btnDlPDF) {
            btnDlPDF.addEventListener('click', async (e) => {
                e.preventDefault();
                btnDlPDF.disabled = true;
                btnDlPDF.setAttribute('aria-busy', 'true');
                try {
                    await ensureFreshEvaluation();
                    await generatePDFReport();
                } finally {
                    btnDlPDF.disabled = false;
                    btnDlPDF.removeAttribute('aria-busy');
                }
            });
        }
    } catch (e) {
        const msg = 'Errore: ' + e;
        log ? (log.textContent = msg) : console.error(msg);
        setRunAlgorithmStatus('error', 'Si è verificato un errore durante l’esecuzione dell’algoritmo.');
        alert('Errore richiesta al backend');
    } finally {
        spin && spin.classList.remove('on');
        setRunAlgorithmBusy(false);
    }
}


// === NEW: leggi infermieri & coupling (UI → body-like) ===
function readNursesAndCouplingFromUI() {
    const v = id => (document.getElementById(id)?.value ?? '').trim();
    const nurses_per_type =
        `PSAUT=${v('nuPSAUT') || 0},` +
        `AUTO_MED=${v('nuAUTO_MED') || 0},` +
        `AMB_ALS=${v('nuAMB_ALS') || 0},` +
        `AMB_ILS=${v('nuAMB_ILS') || 0},` +
        `CMR=${v('nuCMR') || 0}`;

    return {
        nurses_per_type,
        nurses_total: Number(v('nurTotal') || 0),
        nurse_unit_opex: Number(v('nurOpex') || 0),
        auto_med_transport: v('autoMedCoupling'),
        auto_transport_delay: Number(v('autoTransportDelay') || 0)
    };
}


// ---- Render output run ----
function getFirstKey(obj, names) {
    for (const n of names) {
        if (Object.prototype.hasOwnProperty.call(obj, n) && obj[n] != null && String(obj[n]).length) return n;
    }
    return null;
}


function ensureCritLegend() {
    if (CRIT_LEGEND_EL) return;
    const host = document.querySelector('.map-area') || map.getContainer();
    const box = document.createElement('div');
    box.id = 'critLegend';
    box.style.position = 'absolute';
    box.style.left = '14px';
    box.style.bottom = '14px';
    box.innerHTML = `<div><b>Criticità</b></div><div class="bar" style="width:160px;height:10px;border-radius:999px;margin:6px 0;background:linear-gradient(90deg,#28a745,#f59e0b,#dc3545)"></div><div class="scale" style="display:flex;justify-content:space-between;color:#6b7280;"><span>Bassa</span><span>Alta</span></div>`;
    host.appendChild(box);
    CRIT_LEGEND_EL = box;
}


function critRadius(score01) {
    const z = map?.getZoom?.() ?? 11;                 // zoom corrente
    const base = 1200 * Math.pow(2, 11 - z);          // ~1200 m a z=11; raddoppia zoomando out
    const s = Math.max(0, Math.min(1, Number(score01) || 0));
    return base * (0.6 + 1.6 * Math.pow(s, 0.7));     // 60%..220% del base (più score, più grande)
}


// Helper: crea le pane dedicate e assicura il Layers Control
function ensureCritPanesAndControl() {
    if (!map.getPane('critCircles')) {
        map.createPane('critCircles');
        map.getPane('critCircles').style.zIndex = 450;
        map.getPane('critCircles').style.pointerEvents = 'none';
        map.getPane('critCircles').style.mixBlendMode = 'multiply'; // ⬅️ aggiungi
    }
    if (!map.getPane('critLabels')) {
        map.createPane('critLabels');
        map.getPane('critLabels').style.zIndex = 650;
    }
    if (!layersCtl) {
        layersCtl = L.control.layers({}, {}, {position: 'topright', collapsed: true}).addTo(map);
    }
}


/**
 * Disegna il layer "Criticità" usando cerchi su pane dedicata.
 * - carica (se serve) i dati di criticità
 * - calcola coordinate per ogni comune (comuni_geocoded → centroidi presìdi come fallback)
 * - disegna cerchi colorati (raggio in metri) e opzionale etichetta sopra
 * - rispetta il toggle #critToggle (on/off)
 */
async function renderCriticita(forceReload = false) {
    if (!map) return;

    if (!Array.isArray(MP_COMMUNES) || MP_COMMUNES.length === 0) {
        await mp_loadCommunes();
        buildComuneIndexes?.();
    }
    (typeof ensureCritPanesAndControl === 'function') && ensureCritPanesAndControl();
    (typeof ensureCritLegend === 'function') && ensureCritLegend();

    if (!CRIT_DATA || forceReload) await loadCriticita(forceReload);
    updateCritScaleFromScores();   // <-- costruisce i quantili e le funzioni colore


    const tg = document.getElementById('critToggle');
    const wantOn = !tg || tg.checked === true;

    // Pulisci layer precedenti
    try {
        if (CRIT_LAYER && layersCtl) layersCtl.removeLayer(CRIT_LAYER);
    } catch {
    }
    try {
        if (CRIT_POLY_LAYER && layersCtl) layersCtl.removeLayer(CRIT_POLY_LAYER);
    } catch {
    }
    try {
        if (CRIT_LAYER && map.hasLayer(CRIT_LAYER)) map.removeLayer(CRIT_LAYER);
    } catch {
    }
    try {
        if (CRIT_POLY_LAYER && map.hasLayer(CRIT_POLY_LAYER)) map.removeLayer(CRIT_POLY_LAYER);
    } catch {
    }
    CRIT_LAYER = null;
    CRIT_POLY_LAYER = null;

    if (!wantOn) {
        document.getElementById('critStatus')?.replaceChildren('Layer disattivato.');
        return;
    }

    // Prova confini in GeoJSON
    const gj = await loadComuniGeo();

    const comuneNameFromFeature = (f) => {
        const p = f.properties || {};
        let n = p.nome || p.denominazione || p.comune || p.name || '';
        if (!n) {
            let code = p.comune_code ?? p.cod_istat ?? p.codice_istat ?? p.ISTAT;
            if (code != null) {
                code = String(code).padStart(6, '0');
                n = MP_BY_CODE?.get?.(code)?.comune || '';
            }
        }
        return normalizeComune(n || '');
    };

    if (gj && gj.geojson && Array.isArray(gj.geojson.features)) {
        // ✅ COROPLETA (riempita)
        CRIT_POLY_LAYER = L.geoJSON(gj.geojson, {
            style: (feat) => {
                const n = comuneNameFromFeature(feat);
                const rec = CRIT_DATA?.get(n);
                const s = rec?.score;

                if (s == null) {
                    return {
                        stroke: false,
                        fill: true,
                        fillColor: '#e5e7eb',
                        fillOpacity: .35,
                        color: '#9ca3af',
                        weight: 1,
                        opacity: .9
                    };
                }
                return {
                    fill: true,
                    fillColor: CRIT_GET_FILL(s),    // <-- colore per classe
                    fillOpacity: 0.55,
                    color: CRIT_GET_STROKE(s),      // <-- bordo coerente
                    weight: 1.5,
                    opacity: 0.9
                };
            },

            onEachFeature: (feat, layer) => {
                const n = comuneNameFromFeature(feat) || 'Comune';

                const rec = CRIT_DATA?.get(n);
                const s = rec?.score;
                const t = rec?.time;
                const d = rec?.demand;
                const tier = rec?.severityTier;
                const tierWeight = rec?.tierWeight;
                const rows = [`<b>${n}</b>`];

                if (tier) {

                    // Scenario Population Health:
                    // viene mostrata direttamente la classificazione
                    // ALTA / MEDIA / BASSA prodotta dal service PH -> 118.
                    rows.push(`<small>Severità territoriale: <b>${tier}</b></small>`);

                    if (tierWeight != null &&Number.isFinite(Number(tierWeight))) {
                        rows.push(`<small>Peso domanda 118: ${Number(tierWeight).toFixed(2)}</small>`);
                    }

                } else {
                    // Dataset originale 118:viene mantenuta la criticità calcolata dalla logica originale.
                    rows.push(`<small>Criticità: ${s == null ? 'n.d.' : (s * 100).toFixed(0) + '%'}</small>`);
                }

                if (t != null && isFinite(t)) {
                    rows.push(`<small>Tempo medio: ${Number(t).toFixed(1)} min</small>`);
                }

                if (d != null && isFinite(d)) {
                    rows.push(`<small>Domanda pesata: ${Number(d).toLocaleString('it-IT')}</small>`);
                }

                layer.bindTooltip(rows.join('<br>'), {sticky: true});
                layer.on({
                    mouseover: e => e.target.setStyle({weight: 3, fillOpacity: 0.60}),
                    mouseout: e => CRIT_POLY_LAYER.resetStyle(e.target),
                    click: e => map.fitBounds(e.target.getBounds(), {padding: [14, 14]})
                });
            }
        }).addTo(map);

        CRIT_POLY_LAYER.bringToBack(); // icone sopra i confini
        layersCtl?.addOverlay(CRIT_POLY_LAYER, 'Comuni (coropleta criticità)');

        let severitySourceLabel = "Dataset originale 118";

        try {
            const sourceInfo =getCriticitaDemandSource();
            if (sourceInfo.source === "population_health") {
                severitySourceLabel =`Population Health · ${sourceInfo.scenarioId}`;
            }
        } catch {}

        document.getElementById('critStatus') ?.replaceChildren( `Fonte severità: ${severitySourceLabel}` + ` · Confini: ${gj.url}`+ ` · Comuni disegnati: ${CRIT_POLY_LAYER.getLayers().length}`);
        return;
    }

    // 🔁 Fallback: CERCHI se non c'è GeoJSON
    const coordsByComune = new Map(
        (MP_COMMUNES || []).filter(c => isFinite(c.lat) && isFinite(c.lon)).map(c => [c.comune, [c.lat, c.lon]])
    );
    const renderer = L.canvas({padding: 0.5});
    CRIT_LAYER = L.layerGroup();

    let drawn = 0, skipped = 0;
    for (const [name, rec] of (CRIT_DATA || new Map())) {
        const ll = coordsByComune.get(name);
        if (!ll) {
            skipped++;
            continue;
        }
        const s = Math.max(0, Math.min(1, Number(rec.score) || 0));
        L.circle(ll, {
            pane: 'critCircles', renderer,
            radius: critRadius(s),
            color: critStrokeColor(s), weight: 1, opacity: .85,
            fillColor: critFillColor(s), fillOpacity: .25,
            interactive: false
        }).addTo(CRIT_LAYER);
        drawn++;
    }
    CRIT_LAYER.addTo(map);
    layersCtl?.addOverlay(CRIT_LAYER, 'Criticità comuni (cerchi)');
    document.getElementById('critStatus')?.replaceChildren(
        `GeoJSON non trovato → cerchi. Disegnati: ${drawn}, senza coordinate: ${skipped}`
    );
}

// Bucket globali


function switchToValutazione() {
    if (!map) return;

    // 0) Pulisci lo stato del run precedente (svuota gruppi/tooltip, mantiene zoom)
    resetRunView({keepExtent: true});

    // 1) Rimuovi i gruppi del run precedente (quelli veri!)
    if (window.layersByType) {
        Object.values(layersByType).forEach(g => {
            try {
                g.clearLayers();
            } catch {
            }
            try {
                if (map.hasLayer(g)) map.removeLayer(g);
            } catch {
            }
        });
    }

    // 2) Rimuovi qualsiasi layer NON base che non vogliamo in Valutazione
    const KEEP = new Set([window.MP_FREE_LAYER, window.MP_PREVIEW_LAYER,
        window.CRIT_LAYER, window.CRIT_POLY_LAYER]);
    map.eachLayer(l => {
        const isBase = (l instanceof L.TileLayer);
        if (isBase) return;
        let keep = false;
        for (const k of KEEP) {
            if (!k) continue;
            if (l === k) {
                keep = true;
                break;
            }
            if (typeof k.hasLayer === 'function' && k.hasLayer(l)) {
                keep = true;
                break;
            }
        }
        if (!keep) {
            try {
                map.removeLayer(l);
            } catch {
            }
        }
    });

    // 3) Assicura i layer dell’editor
    if (!window.MP_FREE_LAYER) window.MP_FREE_LAYER = L.layerGroup();
    if (!window.MP_PREVIEW_LAYER) window.MP_PREVIEW_LAYER = L.layerGroup();
    if (!map.hasLayer(MP_FREE_LAYER)) MP_FREE_LAYER.addTo(map);
    if (!map.hasLayer(MP_PREVIEW_LAYER)) MP_PREVIEW_LAYER.addTo(map);

    // 4) Criticità: mostrala solo se il toggle è ON
    const critOn = document.getElementById('critToggle')?.checked;
    if (critOn) {
        renderCriticita(); // ridisegna l’overlay corretto
    } else {
        try {
            if (CRIT_LAYER && map.hasLayer(CRIT_LAYER)) map.removeLayer(CRIT_LAYER);
        } catch {
        }
        try {
            if (CRIT_POLY_LAYER && map.hasLayer(CRIT_POLY_LAYER)) map.removeLayer(CRIT_POLY_LAYER);
        } catch {
        }
    }

    // 5) Pulisci la lista UI
    const list = document.getElementById('unit-list');
    if (list) list.innerHTML = `<div class="muted" style="padding:10px">
    Mappa pronta per la <b>Valutazione</b>. Aggiungi un mezzo e premi “Valuta su mappa”.
  </div>`;
    const cnt = document.getElementById('unitCount');
    if (cnt) cnt.textContent = '0 unità';

    LAST_RUN_KIND = 'editor';
}

// === SOLO MAPPA: stima rapida medici ===
// Regola temporanea: PSAUT sempre 2 → 12 medici fissi
// +3 per ogni AUTO_MED
// +3 per ogni AMB_ALS
function doctorsFromPlanQuick(plan) {
    const arr = Array.isArray(plan) ? plan : [];
    let auto = 0, als = 0;
    for (const r of arr) {
        const t = String(r.tipo || '').toUpperCase();
        const q = Number(r.qty || 0);
        if (t === 'AUTO_MED') auto += q;
        else if (t === 'AMB_ALS') als += q;
    }
    return 12 + 3 * auto + 3 * als;  // 12 = 2 PSAUT * 6
}

// alternativa se vuoi contarle dai chosen (dopo evaluate)
function doctorsFromChosenQuick(chosen) {
    const arr = Array.isArray(chosen) ? chosen : [];
    let auto = 0, als = 0;
    for (const r of arr) {
        const t = String(r.tipo || r.type || '').toUpperCase();
        if (t === 'AUTO_MED') auto++;
        else if (t === 'AMB_ALS') als++;
    }
    return 12 + 3 * auto + 3 * als;
}

// scrive il KPI “Medici richiesti…”
function setDoctorsKPIQuick(num) {
    const el = document.querySelector('#kpi-staff');
    if (!el) return;
    const cap = Number(document.getElementById('docTotal')?.value || NaN);
    const n = Math.round(Number(num || 0));
    el.textContent = Number.isFinite(cap)
        ? `Medici richiesti da slot attivi: ${n} / ${Math.round(cap)}`
        : `Medici richiesti da slot attivi: ${n}`;
}

function mp_backfillComuneCoordsFromSites() {
    if (!Array.isArray(MP_SITES) || MP_SITES.length === 0) return;

    // raggruppa presìdi per comune
    const ptsByComune = new Map();
    for (const s of MP_SITES) {
        if (!Number.isFinite(s.lat) || !Number.isFinite(s.lon)) continue;
        const k = s.comune;
        if (!ptsByComune.has(k)) ptsByComune.set(k, []);
        ptsByComune.get(k).push([s.lat, s.lon]);
    }

    // se NON abbiamo un elenco comuni → crealo dai presìdi
    if (!Array.isArray(MP_COMMUNES) || MP_COMMUNES.length === 0) {
        MP_COMMUNES = Array.from(ptsByComune.entries()).map(([com, pts]) => {
            const n = pts.length;
            const lat = pts.reduce((a, p) => a + p[0], 0) / n;
            const lon = pts.reduce((a, p) => a + p[1], 0) / n;
            return {comune: com, lat, lon};
        });
        return;
    }

    // altrimenti: riempi lat/lon mancanti
    for (const c of MP_COMMUNES) {
        if (Number.isFinite(c.lat) && Number.isFinite(c.lon)) continue;
        const pts = ptsByComune.get(c.comune);
        if (pts && pts.length) {
            const n = pts.length;
            c.lat = pts.reduce((a, p) => a + p[0], 0) / n;
            c.lon = pts.reduce((a, p) => a + p[1], 0) / n;
        }
    }
}


let MP_BY_NAME = new Map();
let MP_BY_CODE = new Map();

function buildComuneIndexes() {
    MP_BY_NAME = new Map();
    MP_BY_CODE = new Map();

    if (!Array.isArray(MP_COMMUNES)) return;
    for (const r of MP_COMMUNES) {
        const keys = Object.keys(r || {});
        const get = (names) => {
            const low = keys.map(k => k.toLowerCase());
            for (const n of names) {
                const i = low.indexOf(n.toLowerCase());
                if (i >= 0) return r[keys[i]];
            }
            return '';
        };
        const name = normalizeComune(get(['comune', 'denominazione', 'nome_comune', 'name']) || '');
        let code = (get(['istat', 'codice_istat', 'comune_code', 'codice_comune']) || '').toString().trim();
        if (code) code = code.padStart(6, '0');

        if (name) MP_BY_NAME.set(name, {...r, comune: name});
        if (code) MP_BY_CODE.set(code, {...r, comune: name || r.comune || ''});
    }
}


async function reloadData() {
    if (!RUN_URL) return;
    const files = FILES();


    let [chosen, covAny, covDoc] = await Promise.all([
        loadCSV(files.chosen).catch(() => []),
        loadCSV(files.covAny).catch(() => []),
        loadCSV(files.covDoc).catch(() => [])
    ]);

// ↙️ Memorizza per il PDF
    LAST_CHOSEN = chosen;
    LAST_COV_ANY = covAny;
    LAST_COV_DOC = covDoc;

    updateKPIs(covAny, covDoc);

    // 🔁 SOLO MAPPA: niente TXT → calcola rapido.
// In modalità algoritmo prova il TXT, altrimenti fallback rapido.
    if (LAST_RUN_KIND === 'editor') {
        // Siamo in “Valuta su mappa”: usa i chosen per stimare i medici
        setDoctorsKPIQuick(doctorsFromChosenQuick(chosen));
    } else {
        // Siamo in “Ottimizza”: prova a leggere il TXT, se manca → stima rapida
        try {
            const t = await fetch(files.docTxt).then(r => r.text());
            LAST_DOCTORS_TXT = t;
            const n = parseDoctorsFromTxt(t);
            if (Number.isFinite(n)) {
                setDoctorsKPIQuick(n);
            } else {
                setDoctorsKPIQuick(doctorsFromChosenQuick(chosen));
            }
        } catch {
            LAST_DOCTORS_TXT = '';
            setDoctorsKPIQuick(doctorsFromChosenQuick(chosen));
        }
    }


// === KPI INFERMIERI ===
    try {
        // valore totale da UI, se presente
        let nursesTotal = Number(document.getElementById('nurTotal')?.value || NaN);
        let nursesUsed = NaN;

        // 1) prova dal CSV riassuntivo (preferito)
        if (files.runSummary) {
            const rs = await loadCSV(files.runSummary).catch(() => null);
            if (rs && rs.length) {
                const row = rs[0];
                if (row && row.nurses_used != null) nursesUsed = Number(row.nurses_used);
                if (row && row.nurses_total != null) nursesTotal = Number(row.nurses_total);
            }
        }

        // 2) fallback: estrai dal doctors_summary.txt
        if (!Number.isFinite(nursesUsed)) {
            nursesUsed = parseNursesFromTxt(window.LAST_DOCTORS_TXT || '');
        }

        // 3) fallback estremo: stima dai chosen (se presente la colonna nurses_need)
        if (!Number.isFinite(nursesUsed)) {
            const chosen = window.LAST_CHOSEN || [];
            nursesUsed = chosen.reduce((a, r) => a + (+r.nurses_need || 0), 0);
            if (!(nursesUsed > 0)) nursesUsed = NaN; // se non c'è la colonna
        }

        // Aggiorna il pill
        updateNursesKpi({
            nurses_used: nursesUsed,
            nurses_total: Number.isFinite(nursesTotal) ? nursesTotal : undefined
        });
    } catch (e) {
        console.warn('Nurses KPI error:', e);
        updateNursesKpi({nurses_used: NaN});
    }


    const geocoded = await loadGeo();
    const nameKey = geocoded.length ? (getFirstKey(geocoded[0], ['comune', 'Comune', 'name', 'site_name', 'base_comune']) || 'comune') : 'comune';
    const latKey = geocoded.length ? (getFirstKey(geocoded[0], ['lat', 'Lat', 'latitude', 'Latitude']) || 'lat') : 'lat';
    const lonKey = geocoded.length ? (getFirstKey(geocoded[0], ['lon', 'Lon', 'lng', 'Lng', 'longitude', 'Longitude']) || 'lon') : 'lon';

    const geolist = geocoded.map(r => [normalizeComune(r[nameKey]), {lat: +r[latKey], lon: +r[lonKey]}]);
    const coordsByComune = new Map(geolist);

    const list = document.querySelector('#unit-list');
    if (list) list.innerHTML = '';
    Object.values(layersByType).forEach(g => g.clearLayers());

    // svuota mapping ad ogni ricarica
    ROW_BY_KEY.clear();
    MARKER_BY_KEY.clear();

    chosen.forEach((r, i) => {
        const tipo = (r.tipo || '').toUpperCase();
        const base = normalizeComune(r.base_comune || r.base || r.comune || '');
        const site = r.site_id || `slot_${i}`;
        const key = slotKeyFromRecord(r, i);          // NEW
        const where = coordsByComune.get(base);

        // --- CARD LISTA
        const row = document.createElement('div');
        row.className = 'item';
        row.dataset.type = tipo;
        row.dataset.text = `${tipo} ${site} ${base}`.toLowerCase();
        row.dataset.key = key;                         // NEW
        row.tabIndex = 0;                               // accessibilità
        row.innerHTML = `
    <div class="icon">${iconFor(tipo).options.html}</div>
    <div>
      <div class="title">${tipo} · <span class="sub">${site}</span></div>
      <div class="sub">Base: ${base}${String(r.is_fixed) === "1" ? " · fisso" : ""}</div>
    </div>
  `;
        list && list.appendChild(row);

        // Registra la card
        ROW_BY_KEY.set(key, row);                       // NEW

        // Click/hover sulla card -> mappa
        row.addEventListener('click', () => focusMarker(key, {open: true, pan: true}));        // NEW
        row.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                focusMarker(key, {open: true, pan: true});
            }
        }); // NEW
        row.addEventListener('mouseenter', () => hoverCard(key, true));   // NEW
        row.addEventListener('mouseleave', () => hoverCard(key, false));  // NEW

        // --- MARKER MAPPA
        if (where && isFinite(where.lat) && isFinite(where.lon)) {
            const mark = L.marker([where.lat, where.lon], {icon: iconFor(tipo)})
                .bindPopup(`<b>${tipo}</b><br>${site}<br><small>Base: ${base}</small>`);

            // Registra il marker
            MARKER_BY_KEY.set(key, mark);                 // NEW

            // Click/popup sul marker -> card
            mark.on('click', () => focusCard(key, {scroll: true}));      // NEW (mobile)
            mark.on('popupopen', () => focusCard(key, {scroll: true}));      // NEW
            mark.on('popupclose', () => {/* opzionale: clearFocus(); */
            });   // facoltativo

            layersByType[tipo]?.addLayer(mark);
        }
    });


    filterList();
    fitToData();
    renderCosts(chosen);

}


function updateNursesKpi(metrics) {
    const el = document.getElementById('kpi-nurses');
    if (!el) return;

    const used = Number(metrics?.nurses_used);
    const total = metrics?.nurses_total;

    if (Number.isFinite(used)) {
        el.textContent = (total != null)
            ? `Infermieri usati: ${used.toFixed(2)} / ${Number(total).toFixed(2)}`
            : `Infermieri usati: ${used.toFixed(2)}`;
    } else {
        el.textContent = 'Infermieri usati: –';
    }
}


function fitToData() {
    const groups = Object.values(layersByType).filter(g => map.hasLayer(g));
    try {
        const layers = groups.flatMap(g => g.getLayers());
        if (layers.length) {
            const b = L.featureGroup(layers).getBounds().pad(0.12);
            map.fitBounds(b);
        } else {
            map.fitBounds(BENEVENTO_BOUNDS);
        }
    } catch (e) {
    }
}

function getFilterTypes() {
    const set = new Set();
    document.querySelectorAll('.flt').forEach(c => {
        if (c.checked) set.add(c.value);
    });
    return set;
}

function bounceMarkerOnce(m) {
    try {
        // semplice "alzata" momentanea senza plugin
        m.setZIndexOffset(1000);
        setTimeout(() => m.setZIndexOffset(0), 600);
    } catch {
    }
}

function focusMarker(key, opts) {
    const m = MARKER_BY_KEY.get(key);
    if (!m) return;
    if (opts?.pan) map.setView(m.getLatLng(), Math.max(map.getZoom(), 12), {animate: true});
    if (opts?.open && m.getPopup()) m.openPopup();
    bounceMarkerOnce(m);                    // <- qui
    focusCard(key, {scroll: true});
}


function filterList() {
    const q = (document.getElementById('unitSearch')?.value || '').toLowerCase();
    const allowed = getFilterTypes();
    const items = document.querySelectorAll('#unit-list .item');
    let visible = 0;
    items.forEach(it => {
        const okType = allowed.has(it.dataset.type);
        const okSearch = !q || (it.dataset.text || '').includes(q);
        const show = okType && okSearch;
        it.style.display = show ? '' : 'none';
        if (show) visible++;
    });
    const cnt = document.getElementById('unitCount');
    if (cnt) cnt.textContent = `${visible} unità`;
}

function normalizeComune(x) {
    return String(x || '')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // togli accenti
        .replace(/^comune di\s+/i, '')                    // es. "Comune di Benevento"
        .replace(/\s+/g, ' ')
        .replace(/’/g, "'")
        .trim()
        .split(' ')
        .map(w => w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w)
        .join(' ');
}

function setDoctorsKPI(used, cap) {
    const el = document.querySelector('#kpi-staff');
    if (!el) return;
    const u = Number(used);
    const c = Number(cap);
    if (Number.isFinite(u) && Number.isFinite(c)) {
        el.textContent = `Medici richiesti da slot attivi: ${Math.round(u)} / ${Math.round(c)}`;
    } else if (Number.isFinite(u)) {
        el.textContent = `Medici richiesti da slot attivi: ${Math.round(u)}`;
    } else {
        el.textContent = `Medici richiesti da slot attivi: –`;
    }
}

function updateKPIs(covAny, covDoc) {

    // calcolo ANY anche senza riga TOTAL
    const rows = covAny || [];
    const calls = rows.reduce((a, r) => a + (+r.chiamate || 0), 0);
    const uncov = rows.reduce((a, r) => a + (+r.uncovered || 0), 0);
    if (calls > 0) {
        const anyPct = 100 * (1 - uncov / calls);
        document.querySelector('#kpi-any').textContent =
            `Copertura ANY: ${anyPct.toFixed(1)}%`;
    }

    try {
        const rg = (covDoc || []).filter(r => {
            const code = String(r.codice || r.CODICE || '').toUpperCase();
            return code === 'ROSSO' || code === 'GIALLO';
        });
        const calls = rg.reduce((a, r) => a + (+r.chiamate || 0), 0);
        const uncov = rg.reduce((a, r) => a + (+r.uncovered_doctor || +r.uncovered || 0), 0);
        const docPct = calls > 0 ? 100 * (1 - uncov / calls) : null;
        if (docPct != null) {
            document.querySelector('#kpi-doc').textContent =
                `Copertura con Medico (R+G): ${docPct.toFixed(1)}%`;
        }
    } catch (e) {
    }

}

function findTotalRow(arr) {
    if (!Array.isArray(arr)) return null;
    const row = arr.find(r => String(r.codice || r.CODICE || '').toUpperCase() === 'TOTAL') || arr[arr.length - 1];
    if (!row) return null;
    const norm = {};
    for (const k in row) {
        norm[k.toLowerCase()] = row[k];
    }
    return {
        total_calls: +norm['chiamate'] || +norm['total_calls'] || null,
        total_uncovered: +norm['uncovered'] || +norm['uncovered_doctor'] || +norm['total_uncovered'] || null,
        total_pct: +norm['total_pct'] || null
    };
}

function pctFrom(row) {
    if (!row) return null;
    const a = row.total_calls, u = row.total_uncovered;
    if (!(a > 0)) return null;
    return 100 * (1 - (u / a));
}

/**
 * Pulisce la mappa prima di una nuova valutazione/disegno.
 * - svuota i layer temporanei registrati (layersByType, ecc.)
 * - rimuove/svuota overlay dell’editor (MP_PREVIEW_LAYER, MP_FREE_LAYER, DRAWN_ITEMS)
 * - chiude popup/tooltip
 * - azzera cache marker/righe se presenti
 * - mantiene l’estensione se keepExtent: true
 */
function resetRunView({keepExtent = false} = {}) {
    const map =
        window.MAP || window.map || globalThis.MAP || globalThis.map || null;

    // Salva i bounds se serve mantenerli
    const prevBounds =
        keepExtent && map && typeof map.getBounds === "function"
            ? map.getBounds()
            : null;

    // Helper per svuotare un gruppo/layer in modo sicuro
    const clearGroup = (g) => {
        if (!g) return;
        try {
            if (typeof g.clearLayers === "function") {
                g.clearLayers();
            } else if (typeof g.eachLayer === "function") {
                g.eachLayer((l) => {
                    try {
                        if (typeof l.remove === "function") l.remove();
                        else if (map && typeof l.removeFrom === "function") l.removeFrom(map);
                        else if (map && typeof map.removeLayer === "function") map.removeLayer(l);
                    } catch {
                    }
                });
            } else if (Array.isArray(g)) {
                g.forEach((l) => {
                    try {
                        if (typeof l.remove === "function") l.remove();
                        else if (map && typeof map.removeLayer === "function") map.removeLayer(l);
                    } catch {
                    }
                });
            }
        } catch {
        }
    };

    // 1) Svuota i layer temporanei registrati (supporta nomi diversi, se presenti)
    const registries = [
        window.layersByType,
        window.LAYERS_BY_TYPE,
        window.layers,
        globalThis.layersByType,
    ].filter(Boolean);

    registries.forEach((reg) => {
        try {
            Object.values(reg || {}).forEach((g) => clearGroup(g));
        } catch {
        }
    });

    // 2) Pulisci/rimuovi overlay dell’editor (anteprima piano + click liberi + eventuali drawn items)
    const kill = (layer) => {
        if (!layer) return;
        try {
            if (typeof layer.clearLayers === "function") layer.clearLayers();
        } catch {
        }
        try {
            if (map && typeof map.hasLayer === "function" && map.hasLayer(layer)) {
                map.removeLayer(layer);
            } else if (typeof layer.remove === "function") {
                layer.remove();
            }
        } catch {
        }
    };
    kill(window.MP_PREVIEW_LAYER);
    kill(window.MP_FREE_LAYER);
    kill(window.DRAWN_ITEMS);

    // 3) Azzera eventuali cache/registry di supporto (se esistono)
    try {
        window.ROW_BY_KEY?.clear?.();
    } catch {
    }
    try {
        window.MARKER_BY_KEY?.clear?.();
    } catch {
    }
    try {
        window.LAST_EVAL_RESULTS = undefined;
    } catch {
    }

    // 4) UI cleanup (popup/tooltip)
    try {
        map?.closePopup?.();
    } catch {
    }
    try {
        map?.closeTooltip?.();
    } catch {
    }

    // 5) Ripristina bounds se richiesto
    if (keepExtent && map && prevBounds) {
        try {
            map.fitBounds(prevBounds, {animate: false});
        } catch {
        }
    }
}

function initModeTabs() {
    const bar = document.querySelector('.mode-switch');
    if (!bar) return;

    const tabs = [...bar.querySelectorAll('[role="tab"]')];
    const getPanel = (tab) => document.getElementById(tab.getAttribute('aria-controls'));

    function activate(tabEl) {
        tabs.forEach(t => t.setAttribute('aria-selected', t === tabEl ? 'true' : 'false'));
        tabs.forEach(t => {
            const p = getPanel(t);
            if (p) p.hidden = (t !== tabEl);
        });
        try {
            localStorage.setItem('panel.mode', tabEl.getAttribute('aria-controls'));
        } catch {
        }
        if (tabEl.getAttribute('aria-controls') === 'mode-editor') {
            try {
                refreshParamSummary();
            } catch {
            }
        }

    }

    bar.addEventListener('click', (e) => {
        const b = e.target.closest('[role="tab"]');
        if (!b) return;
        activate(b);
    });

    // ripristina ultima vista
    let startId = 'mode-algo';
    try {
        startId = localStorage.getItem('panel.mode') || startId;
    } catch {
    }
    const startTab = tabs.find(t => t.getAttribute('aria-controls') === startId) || tabs[0];
    activate(startTab);
}

// Alias compatibile: se altrove chiami setPanelMode('mode-editor') ecc., manteniamolo
// Cambia scheda usando i tab ARIA (mode-algo / mode-editor / mode-config)

// Stima i medici richiesti a partire dai "chosen" (righe degli slot attivi)
function estimateDoctorsFromChosen(chosen) {
    const arr = Array.isArray(chosen) ? chosen : [];

    // leggi lo staff per tipo dalla UI (es. "PSAUT=6,AUTO_MED=6,AMB_ALS=6")
    const staffKV = parsePairs(document.getElementById('staff')?.value || '');

    // quanti medici per ciascun tipo
    const staffFor = (t) => {
        const k = normalizeType(t);
        if (k === 'AUTO_MED') return Number(staffKV.AUTO_MED || 3);
        if (k === 'AMB_ALS') return Number(staffKV.AMB_ALS || 3);
        if (k === 'PSAUT') return Number(staffKV.PSAUT || 6);
        return 0; // AMB_ILS e altri tipi non richiedono medico
    };

    let tot = 0;
    for (const r of arr) {
        const t = r.tipo || r.type || '';
        tot += staffFor(t);
    }
    return tot;
}

function paramSummaryFromBody(body) {
    const fmtKV = (s) => String(s || '').split(',').filter(Boolean).map(p => p.trim()).join(' · ');
    const euroSafe = (n) => {
        try {
            return Number(n || 0).toLocaleString('it-IT', {style: 'currency', currency: 'EUR'})
        } catch {
            return (n || 0) + ' €'
        }
    };
    const i = (v) => (v == null || v === '' ? '—' : String(v));

    // campi “classici”
    const budgetStr = body.budget_total ? `${euroSafe(body.budget_total)} (${body.budget_mode || '—'})` : '—';
    const docMode = (body.doctors_budget_mode || '').trim() || '—';
    const docCover = (body.doctor_cover || 'off');
    const docCodes = fmtKV(body.doctor_codes);
    const staffStr = fmtKV(body.staff_per_type);

    // NEW: estensioni algoritmo
    const relax = fmtKV(body.relax_weights);
    const objective = i(body.objective);
    const lambda = (body.lambda_cost == null || body.lambda_cost === '') ? '—' : String(body.lambda_cost);
    const turnoff = i(body.turnoff_doctor_families);
    const psautMin = i(body.psaut_min);
    const psautExact = i(body.psaut_exact);

    const nursesPT = fmtKV(body.nurses_per_type);
    const nursesTot = i(body.nurses_total);
    const nurseOpex = (body.nurse_unit_opex == null || body.nurse_unit_opex === '') ? '—' : euroSafe(body.nurse_unit_opex);
    const coupling = i(body.auto_med_transport);

    const T = fmtKV(body.T);
    const speeds = fmtKV(body.type_speed);
    const capex = fmtKV(body.purchase_costs);
    const opex = fmtKV(body.opex_costs);

    const rows = [
        ['Soglie T', T || '—'],
        ['Velocità relative', speeds || '—'],
        ['CAPEX unitari', capex || '—'],
        ['OPEX unitari', opex || '—'],
        ['Staff per tipo', staffStr || '—'],
        ['Vincolo medico', docCodes ? `${docCover} · ${docCodes}` : docCover],
        ['Medici totali', (body.doctors_total || '—') + (docMode !== '—' ? ` (${docMode})` : '')],
        ['Budget', budgetStr],
        ['Basi', (body.bases || '—') + ' · limit=' + (body.limit_bases || 0)],
        ['Full coverage', body.full_coverage || '—'],
        ['Reloc. PSAUT', body.reloc_psaut || 'off'],
        ['Threads / Time limit', (body.threads || '—') + ' / ' + (body.time_limit_sec || '—')],

        // === NEW: parametri aggiuntivi dell’algoritmo ===
        ['Relax weights', relax || '—'],
        ['Objective / λcost', `${objective} / ${lambda}`],
        ['Turnoff doctor families', turnoff],
        ['PSAUT vincoli', `min=${psautMin} · exact=${psautExact}`],
        ['Infermieri per tipo', nursesPT || '—'],
        ['Budget infermieri', `tot=${nursesTot} · unit=${nurseOpex}`],
        ['Trasporto automedica', coupling]
    ];

    return rows.map(([k, v]) => `<div class="k">${k}</div><div class="v">${v}</div>`).join('');
}


function refreshParamSummary() {
    const host = document.getElementById('paramSummary');
    if (!host) return;
    const body = buildRunBody();               // stessa “fonte di verità” usata da run/evaluate
    host.innerHTML = paramSummaryFromBody(body);
}


// === IMPORT CONFIG: bind input e drag&drop nella nuova scheda ===
// (riusa le tue buildConfigSnapshot / applyConfigSnapshot / importConfigFromFile / bindConfigIO se già presenti)
// Qui colleghiamo #upConfig alla nuova sezione e abilitiamo il drop.
function bindConfigUploadAndDrop() {
    const input = document.getElementById('upConfig');
    if (input && !input.dataset.bound) {
        input.dataset.bound = '1';
        input.addEventListener('change', (e) => {
            const f = e.target.files && e.target.files[0];
            if (f && typeof importConfigFromFile === 'function') importConfigFromFile(f);
            e.target.value = '';
        });
    }
    const dz = document.getElementById('configDrop');
    if (dz && !dz.dataset.bound) {
        dz.dataset.bound = '1';
        const stop = e => {
            e.preventDefault();
            e.stopPropagation();
        };
        ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => {
            stop(e);
            dz.classList.add('dragging');
        }));
        ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => {
            stop(e);
            dz.classList.remove('dragging');
        }));
        dz.addEventListener('drop', (e) => {
            const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (f && typeof importConfigFromFile === 'function') importConfigFromFile(f);
        });
    }
}


// helper: trova una chiave ignorando maiuscole/minuscole e sinonimi
function pickKeyCI(row, candidates) {
    const keys = Object.keys(row || {});
    const low = keys.map(k => k.toLowerCase());
    for (const c of candidates) {
        const i = low.indexOf(c.toLowerCase());
        if (i >= 0) return keys[i];       // restituisci la chiave originale
    }
    return null;
}


// ---- Avvio ----
window.addEventListener('DOMContentLoaded', init);


// -- expose functions used in inline HTML handlers --
try {
    Object.assign(window, {
        mp_addFromDropdown,
        mp_clear,
        mp_eval,
        mp_removeFromPlan,
        mp_updateEditorButtons,
        setPanelMode
    });
} catch (e) { /* ignore */
}
export {};
