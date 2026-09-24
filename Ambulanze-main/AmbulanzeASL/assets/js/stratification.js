"use strict";

(() => {

    const ACTIVE_STRATIFICATION_STORAGE_KEY = "prometheusActiveStratification";
    const PH118_SEVERITY_SELECTION_STORAGE_KEY = "ph118SelectedSeverityScenario";

    const state = {

        runId: null,

        page: 1,
        pageSize: 25,
        totalPages: 1,

        totalRows: 0,
        filteredRows: 0,

        rows: [],

        summary: null,
        metadata: null,

       filters: {
            search: "",
            baselineLevel: "",
            recommendationStatus: "",
            allocationStatus: "",
            municipality: "",
        },
        sortBy: "patient_id",
        sortDirection: "asc",

        geography: null,
        geographyRunId: null,
        map: null,
        geoJsonLayer: null,
        mapMetric: "patient_count",
        mapDomain: null,
        selectedMunicipality: null,
        selectedMunicipalityName: null,
        municipalityLayers: new Map(),
        severity118Preview: null,
        severity118Map: null,
        severity118Layer: null,
        severity118Index: new Map(),

        csvUploadId: null,
        csvCompatibilityReport: null,
        dataSource: "synthetic",
        isRunning: false,
        lastCompletedDataSource: null,
        lastCompletedGeography: null,
    };

    // ====================================================
    // DIZIONARI DI PRESENTAZIONE
    // ====================================================

    const RECOMMENDATION_STATUS_LABELS = {
        recommended: "Raccomandazione formulata",
        abstained: "Nessuna raccomandazione formulata",
    };

    const RECOMMENDATION_REASON_LABELS = {
        SUPPORTED_BENEFIT_STRICTLY_ABOVE_THRESHOLD: "Il beneficio atteso è supportato dai dati ed è superiore alla soglia minima.",
        NO_ELIGIBLE_SUPPORTED_PROFILE: "Non è disponibile un profilo assistenziale eleggibile con supporto empirico sufficiente.",
        BENEFIT_NOT_STRICTLY_ABOVE_THRESHOLD: "Il beneficio stimato non supera la soglia minima richiesta per proporre un cambiamento.",
        TOP_SCORE_OUTSIDE_VALIDATION_RANGE: "La migliore opportunità individuata è fuori dall'intervallo osservato nei dati di validazione.",
    };

    const ALLOCATION_STATUS_LABELS = {
        allocated_recommended_profile: "Raccomandazione attivata",
        deferred_recommended_profile: "Raccomandazione rinviata",
        no_actionable_recommendation: "Nessun cambiamento assistenziale proposto",
    };

    const ALLOCATION_REASON_LABELS = {
        RECOMMENDATION_ABSTAINED_BEFORE_ALLOCATION: "Non era presente una raccomandazione da attivare.",
        SELECTED_BY_CARDINAL_RESOURCE_OPTIMIZATION: "La raccomandazione può essere attivata nel rispetto dei vincoli di capacità e budget.",
    };

    const PROFILE_LABELS = {
        profile_ii_structured_followup: "Follow-up proattivo strutturato",
        profile_iii_chronic_management: "Gestione strutturata della cronicità",
        profile_iv_remote_monitoring: "Gestione della cronicità con monitoraggio remoto",
        profile_iv_proactive_case_management: "Case management proattivo",
        profile_v_integrated_home_support: "Assistenza domiciliare integrata ad alta intensità",
    };

    const BASELINE_REASON_LABELS = {
        MINIMAL_OR_TIME_LIMITED_COMPLEXITY: "Complessità minima o limitata nel tempo",
        CHRONICITY_OR_EARLY_FRAGILITY: "Presenza di cronicità o segnali iniziali di fragilità",
        FUNCTIONAL_LIMITATION_RECORDED: "Sono presenti limitazioni funzionali",
        MEDIUM_HIGH_MULTIDIMENSIONAL_COMPLEXITY: "Complessità multidimensionale medio-alta",
        SOCIAL_FRAGILITY_RECORDED: "Sono presenti elementi di fragilità sociale",
        HIGH_COMPLEXITY_OR_NON_SELF_SUFFICIENCY: "Elevata complessità assistenziale o rischio di non autosufficienza",
        NON_SELF_SUFFICIENCY_RECORDED: "È presente una condizione di non autosufficienza",
    };

    // ===========================================
    //HELPER
    // ===========================================
    function yesNo(value) {
        if (value === true || value === "True" || value === "true" || value === 1) {return "Sì";}
        if (value === false || value === "False" || value === "false" || value === 0) {return "No";}
        return "—";
    }
    function recommendationStatusLabel(value) {
        return (RECOMMENDATION_STATUS_LABELS[value] || humanizeCode(value));
    }
    function recommendationReasonLabel(value) {
        return (RECOMMENDATION_REASON_LABELS[value] || humanizeCode(value));
    }
    function allocationStatusLabel(value) {
        return (ALLOCATION_STATUS_LABELS[value] || humanizeCode(value));
    }

    function allocationReasonLabel(value) {
        return (ALLOCATION_REASON_LABELS[value] || humanizeCode(value));
    }
    function profileLabel(profileId, fallbackName) {

        if (!profileId) {return "Nessun profilo raccomandato";}
        return (PROFILE_LABELS[profileId] || fallbackName || humanizeCode(profileId));
    }

    function humanizeCode(value) {

        if (value === null || value === undefined || value === "") {return "—";}
        const text = String(value).replaceAll("_", " ").toLowerCase();
        return (text.charAt(0).toUpperCase() + text.slice(1));
    }
    function baselineExplanationLabel(value) {
        if (!value) {return "Nessuna motivazione aggiuntiva disponibile.";}
        return String(value).split("|").map(code => BASELINE_REASON_LABELS[code] || humanizeCode(code)).join(". ");
    }


    // ========================================================
    // DOM
    // ========================================================

    const el = {};

    function cacheElements() {
        el.form = document.getElementById("phRunForm");
        el.dataSource = document.getElementById("phDataSource");
        el.dataSourceCsvOption =document.getElementById("phDataSourceCsvOption");
        el.dataSourceHint =document.getElementById("phDataSourceHint");
        el.patients = document.getElementById("phPatients");
        el.seed = document.getElementById("phSeed");
        el.scenario = document.getElementById("phScenario");

        el.runButton = document.getElementById("phRunButton");

        el.status = document.getElementById("phStatus");
        el.statusTitle = document.getElementById("phStatusTitle");
        el.statusMessage = document.getElementById("phStatusMessage");

        el.results = document.getElementById("phResults");
        el.runId = document.getElementById("phRunId");
        el.runDataSource = document.getElementById("phRunDataSource");

        el.kpiPatients = document.getElementById("phKpiPatients");
        el.kpiRecommended = document.getElementById("phKpiRecommended");
        el.kpiAbstained = document.getElementById("phKpiAbstained");
        el.kpiAllocated = document.getElementById("phKpiAllocated");
        el.kpiDeferred = document.getElementById("phKpiDeferred");

        el.baselineDistribution = document.getElementById("phBaselineDistribution");
        el.recommendedDistribution = document.getElementById("phRecommendedDistribution");
        el.allocatedDistribution = document.getElementById("phAllocatedDistribution");
        el.tableBody = document.getElementById("phPatientsTableBody");

        el.pageLabel = document.getElementById("phPageLabel");
        el.prevPage = document.getElementById("phPrevPage");
        el.nextPage = document.getElementById("phNextPage");

        el.detail = document.getElementById("phPatientDetail");
        el.detailTitle = document.getElementById("phPatientDetailTitle");
        el.detailBody = document.getElementById("phPatientDetailBody");
        el.detailClose = document.getElementById("phPatientDetailClose");

        el.operationalOutcome = document.getElementById("phOperationalOutcome");
        el.patientFilters = document.getElementById("phPatientFilters");
        el.filterSearch = document.getElementById("phFilterSearch");
        el.filterBaseline = document.getElementById("phFilterBaseline");
        el.filterRecommendation = document.getElementById("phFilterRecommendation");
        el.filterAllocation = document.getElementById("phFilterAllocation");
        el.filterReset = document.getElementById("phFilterReset");
        el.filterSummary = document.getElementById("phFilterSummary");
        el.pageSize = document.getElementById("phPageSize");
        el.sortButtons = document.querySelectorAll("[data-ph-sort]");

        el.map =document.getElementById( "phMap");
        el.mapMetric = document.getElementById("phMapMetric");
        el.mapStatus = document.getElementById("phMapStatus");
        el.mapLegend = document.getElementById("phMapLegend");
        el.municipalityDetail = document.getElementById("phMunicipalityDetail");

        el.territorialMetricLabel = document.getElementById("phTerritorialMetricLabel");
        el.territorialPatients = document.getElementById("phTerritorialPatients");
        el.territorialMeanNeed = document.getElementById("phTerritorialMeanNeed");
        el.territorialRecommendationRate = document.getElementById("phTerritorialRecommendationRate");
        el.territorialDeferralRate = document.getElementById("phTerritorialDeferralRate");
        el.territorialRankingBody = document.getElementById("phMunicipalityRankingBody");
        el.territorialRankingDescription = document.getElementById("phTerritorialRankingDescription");

        el.configurationCard = document.getElementById("phConfigurationCard");
        el.newStratificationButton = document.getElementById("phNewStratificationButton");

        el.severity118Metric =document.getElementById("ph118Metric");
        el.severity118PreviewButton = document.getElementById("ph118PreviewButton");
        el.severity118PreviewStatus =document.getElementById("ph118PreviewStatus");
        el.severity118PreviewResults = document.getElementById("ph118PreviewResults");
        el.severity118PreviewSummary =document.getElementById("ph118PreviewSummary");
        el.severity118Map =document.getElementById("ph118SeverityMap");
        el.severity118Legend =document.getElementById("ph118SeverityLegend");
        el.severity118MunicipalityDetail = document.getElementById("ph118MunicipalityDetail");

        el.severity118UsePlanningButton = document.getElementById("ph118UsePlanningButton");
        el.severity118MaterializeStatus = document.getElementById("ph118MaterializeStatus");

        el.csvFile =document.getElementById("phCsvFile");
        el.csvValidateButton =document.getElementById("phCsvValidateButton");
        el.csvReport =document.getElementById("phCsvReport");
        el.csvReportTitle = document.getElementById("phCsvReportTitle");
        el.csvReportBody =document.getElementById("phCsvReportBody");

        el.mapDescription =document.getElementById("phMapDescription");
        el.mapGeographyProvenance =document.getElementById( "phMapGeographyProvenance");
    }

function updateDataSourceUi() {

        const csvReady =Boolean(state.csvUploadId && state.csvCompatibilityReport ?.can_run === true);
        // L'opzione CSV è selezionabile solo dopo una validazione riuscita.
        if (el.dataSourceCsvOption) {
            el.dataSourceCsvOption.disabled = !csvReady;
        }
        let source = el.dataSource?.value || "synthetic";

        // Safety frontend: non consentiamo real_csv senza un upload_id valido.
        if (source === "real_csv" && !csvReady) {
            source = "synthetic";
            if (el.dataSource) {
                el.dataSource.value = "synthetic";
            }
        }

        state.dataSource = source;
        // patients è utilizzato esclusivamente dalla modalità synthetic.
        if (el.patients) {
            el.patients.disabled = state.isRunning || source === "real_csv";
        }

        if (!el.dataSourceHint) {
            return;
        }

        if (source === "real_csv" && csvReady) {
            const report = state.csvCompatibilityReport;
            const fileName = report?.file?.name || "CSV validato";
            const patientCount =Number(report?.dataset?.patient_count|| 0);
            el.dataSourceHint.textContent =
                `${fileName} · `
                + `${patientCount.toLocaleString("it-IT")} `
                + `pazienti. `
                + `Il numero pazienti deriva dal CSV.`;
            return;
        }
        el.dataSourceHint.textContent = "Verrà generata una popolazione sintetica usando il numero di pazienti indicato.";
    }

function updateMapGeographyProvenance() {

    if (!el.mapGeographyProvenance || !el.mapDescription) {return;}

    const source = state.lastCompletedDataSource;

    // NESSUN RUN COMPLETATO
    if (!source) {
        el.mapGeographyProvenance.hidden =true;
        el.mapDescription.textContent = "Distribuzione territoriale dei pazienti utilizzata esclusivamente per l'analisi post-hoc. La geografia non entra nel causal ranker.";
        return;
    }


    // POPOLAZIONE SINTETICA
    if (source === "synthetic") {
        el.mapDescription.textContent = "Distribuzione territoriale post-hoc della popolazione sintetica. Il comune di residenza è assegnato deterministicamente dopo il ranking e non è utilizzato dal causal ranker.";
        el.mapGeographyProvenance.hidden =false;
        el.mapGeographyProvenance.className ="ph-status ph-status--success";
        el.mapGeographyProvenance.textContent ="Geografia: sintetica post-hoc · ranker_input = false";
        return;
    }


    // CSV
    const geography = state.lastCompletedGeography || {};
    const realRows = Number( geography.real_rows ?? geography.real_residence_rows?? 0);
    const syntheticRows = Number(geography.synthetic_fallback_rows ?? geography.synthetic_residence_rows ?? 0);

    // REAL + SYNTHETIC
    if (realRows > 0 && syntheticRows > 0) {
        el.mapDescription.textContent ="Distribuzione territoriale post-hoc della coorte caricata. "
            + "Le residenze reali presenti nel CSV sono preservate; solo i pazienti "
            + "senza dato geografico ricevono un fallback sintetico deterministico.";
        el.mapGeographyProvenance.hidden =false;
        el.mapGeographyProvenance.className ="ph-status ph-status--success";
        el.mapGeographyProvenance.textContent = `Geografia mista · ${realRows.toLocaleString("it-IT")} reali · `
            + `${syntheticRows.toLocaleString("it-IT")} sintetiche · ranker_input = false`;
        return;
    }

    // SOLO REAL
    if (realRows > 0 && syntheticRows === 0) {
        el.mapDescription.textContent ="Distribuzione territoriale post-hoc della coorte caricata. Le residenze provengono dal CSV e non sono utilizzate dal causal ranker.";
        el.mapGeographyProvenance.hidden =false;
        el.mapGeographyProvenance.className ="ph-status ph-status--success";
        el.mapGeographyProvenance.textContent = `Geografia reale · ${realRows.toLocaleString("it-IT")} pazienti · ranker_input = false`;
        return;
    }

    // CSV SENZA RESIDENZA
    el.mapDescription.textContent ="Distribuzione territoriale post-hoc della coorte caricata. Poiché il CSV non contiene una residenza utilizzabile, il comune viene assegnato deterministicamente dopo il ranking.";
    el.mapGeographyProvenance.hidden =false;
    el.mapGeographyProvenance.className ="ph-status ph-status--success";
    el.mapGeographyProvenance.textContent ="Geografia: fallback sintetico post-hoc · ranker_input = false";
}

    // ========================================================
    // STATUS
    // ========================================================

function showStatus(type, title, message) {
        el.status.hidden = false;
        el.status.className = `ph-status ph-status--${type}`;
        el.statusTitle.textContent = title;
        el.statusMessage.textContent = message;
    }



function setRunning(running) {

    state.isRunning =running;
    el.runButton.disabled =running;
    el.seed.disabled = running;
    el.scenario.disabled =running;

    if (el.dataSource) {
        el.dataSource.disabled = running;
    }

    if (el.csvFile) {
        el.csvFile.disabled =running;
    }

    if (el.csvValidateButton) {
        el.csvValidateButton.disabled =running;
    }
    updateDataSourceUi();
    el.runButton.textContent = running ? "PROMETHEUS in esecuzione..." : "Avvia stratificazione";
}


    // ========================================================
    // HTTP
    // ========================================================

    async function parseResponse(response) {

        let data = null;

        try {
            data = await response.json();
        } catch {
            throw new Error(`Risposta HTTP ${response.status} non valida.`);
        }

        if (!response.ok) {
            const message = ( typeof data?.error === "string" ? data.error : data?.error?.message ) || data?.message || `Errore HTTP ${response.status}`;
            const error = new Error(message);
            error.httpStatus = response.status;
            error.payload = data;
            throw error;
        }

        return data;
    }

    async function startRun(payload) {

        const response = await fetch("/api/stratification/run", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            }
        );
        return parseResponse(response);
    }

    async function validatePatientCsv(file) {
    const formData = new FormData();
    formData.append("file",file);

    const response = await fetch("/api/stratification/csv/validate", {method: "POST", body: formData});
    return parseResponse(response);
}

    async function loadResults(runId, page = 1, pageSize = state.pageSize){

        const params = new URLSearchParams();
        params.set("page", String(page));
        params.set("page_size", String(pageSize));
        params.set("sort_by", state.sortBy);
        params.set("sort_direction", state.sortDirection);

        if (state.filters.search) {
            params.set("search", state.filters.search);
        }

        if (state.filters.baselineLevel) {
            params.set("baseline_level", state.filters.baselineLevel);
        }

        if (state.filters.recommendationStatus) {
            params.set("recommendation_status", state.filters.recommendationStatus);
        }

        if (state.filters.allocationStatus) {
            params.set("allocation_status", state.filters.allocationStatus);
        }

        if (state.filters.municipality){
            params.set("municipality",state.filters.municipality)
        }

        const url = `/api/stratification/results/` + `${encodeURIComponent(runId)}` + `?${params.toString()}`;

        const response = await fetch(url);
        return parseResponse(response);
    }


    // ========================================================
    // FORMAT
    // ========================================================

    function formatNumber(value, decimals = 2) {

        if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {return "—";}
        return Number(value).toLocaleString("it-IT", {maximumFractionDigits: decimals,});
    }

    function formatPercent(value) {

        if (value === null || value === undefined) {return "—";}
        return `${(Number(value) * 100).toFixed(1)}%`;
    }

    function safeText(value) {

        if (value === null || value === undefined || value === "") {return "—";}return String(value);}

    function formatBaselineDistribution(
    distribution
) {

    if (!distribution) {
        return "—";
    }


    return [1, 2, 3, 4, 5, 6]
        .map(
            level =>
                `Livello ${level}: ${
                    Number(
                        distribution[
                            String(level)
                        ]
                        || 0
                    ).toLocaleString(
                        "it-IT"
                    )
                }`
        )
        .join(" · ");
}

function renderMunicipalityDetail(municipality) {

    state.selectedMunicipality =municipality;
    const recommendationRate = Number(municipality.recommendation_rate || 0);
    const deferredRate = Number(municipality.deferred_rate_among_recommended || 0);
    const meanNeed = Number(municipality.mean_baseline_need || 0);
    const province = getTerritorialSummary();
    const needDifference = meanNeed - province.meanNeed;
    const recommendationDifference = recommendationRate - province.recommendationRate;
    const deferralDifference = deferredRate - province.deferredRate;

    el.municipalityDetail.innerHTML = `

        <div class="ph-municipality-heading">
            <p class="ph-eyebrow">Territorio </p>
            <h4>
                ${safeText(municipality.municipality)}
            </h4>
            ${
                municipality.province ? `<span class="ph-municipality-province"> ${safeText(municipality.province)} </span>` : ""
            }
        </div>


        <dl class="ph-municipality-kv">

            <dt>
                Pazienti residenti
            </dt>

            <dd>
                ${Number(
                    municipality.patient_count
                    || 0
                ).toLocaleString("it-IT")}
            </dd>


            <dt>
                Bisogno medio
            </dt>

            <dd>
                ${meanNeed.toLocaleString(
                    "it-IT",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                    }
                )}
            </dd>


            <dt>
                Raccomandazione formulata
            </dt>

            <dd>
                ${Number(
                    municipality.recommended_count
                    || 0
                ).toLocaleString("it-IT")}
                ·
                ${(recommendationRate * 100)
                    .toLocaleString(
                        "it-IT",
                        {
                            maximumFractionDigits: 1,
                        }
                    )}%
            </dd>


            <dt>
                Raccomandazioni attivate
            </dt>

            <dd>
                ${Number(
                    municipality.allocated_count
                    || 0
                ).toLocaleString("it-IT")}
            </dd>


            <dt>
                Raccomandazioni rinviate
            </dt>

            <dd>
                ${Number(
                    municipality.deferred_count
                    || 0
                ).toLocaleString("it-IT")}
                ·
                ${(deferredRate * 100)
                    .toLocaleString(
                        "it-IT",
                        {
                            maximumFractionDigits: 1,
                        }
                    )}%
                delle raccomandazioni
            </dd>


            <dt>
                Nessuna nuova indicazione
            </dt>

            <dd>
                ${Number(
                    municipality.no_actionable_count
                    || 0
                ).toLocaleString("it-IT")}
            </dd>

        </dl>


        <div class="ph-municipality-levels">

            <strong>
                Distribuzione del bisogno
            </strong>

            <p> ${formatBaselineDistribution(municipality.baseline_level_distribution)}</p>

        </div>


        <div class="ph-geography-note">

            Residenza sintetica utilizzata esclusivamente
            per la visualizzazione territoriale.
            Non influenza la raccomandazione PROMETHEUS.

        </div>
        
       <div class="ph-territorial-comparison-detail">
        
            <strong>
                Confronto con la media provinciale
            </strong>
        
            <dl>
        
                <dt>Bisogno medio</dt>
                <dd>
                    ${needDifference >= 0 ? "+" : ""}
                    ${needDifference.toLocaleString("it-IT", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                    })}
                </dd>
        
                <dt>Tasso di raccomandazione</dt>
                <dd>
                    ${recommendationDifference >= 0 ? "+" : ""}
                    ${(recommendationDifference * 100).toLocaleString("it-IT", {
                        maximumFractionDigits: 1,
                    })} p.p.
                </dd>
        
                <dt>Tasso di rinvio</dt>
                <dd>
                    ${deferralDifference >= 0 ? "+" : ""}
                    ${(deferralDifference * 100).toLocaleString("it-IT", {
                        maximumFractionDigits: 1,
                    })} p.p.
                </dd>
        
            </dl>
        
        </div>
    `;
}

function municipalityMarkerStyle(
    selected = false
) {

    if (selected) {

        return {
            color: "#0d6efd",
            weight: 4,
            opacity: 1,

            fillColor: "#0d6efd",
            fillOpacity: 0.72,
        };
    }


    return {
        color: "#334155",
        weight: 2,
        opacity: 0.85,

        fillColor: "#64748b",
        fillOpacity: 0.48,
    };
}

async function selectMunicipality(properties) {
    state.selectedMunicipality = properties;
    state.selectedMunicipalityName = properties.municipality;
    const selectedLayer = state.municipalityLayers.get(properties.municipality);

    if (selectedLayer && typeof selectedLayer.getBounds === "function") {
        state.map.fitBounds(
            selectedLayer.getBounds(),
            {
                padding: [35, 35],
                maxZoom: 12,
            }
        );
    }

    if (state.geoJsonLayer) {
        state.geoJsonLayer.setStyle(municipalityPolygonStyle);
    }

    renderMunicipalityDetail(properties);

    state.filters.municipality = properties.municipality;

    if (!state.runId) {
        return;
    }

    try {
        await displayRun(state.runId, 1);
    } catch (error) {
        console.error(error);

        showStatus(
            "error",
            "Errore durante il filtro territoriale",
            error.message
        );
    }
}

function renderMapLegend(metric, domain) {
    const steps = CHOROPLETH_COLORS.length;
    const range = domain.max - domain.min;

    el.mapLegend.innerHTML = `
        <strong>${metric.label}</strong>
        <div class="ph-map-legend__scale">
            ${CHOROPLETH_COLORS.map((color, index) => {
                const from = domain.min + (range * index / steps);
                const to = domain.min + (range * (index + 1) / steps);

                return `
                    <span>
                        <i style="background:${color}"></i>
                        ${metric.format(from)} – ${metric.format(to)}
                    </span>
                `;
            }).join("")}
            <span>
                <i style="background:#e5e7eb"></i>
                Nessun dato
            </span>
        </div>
    `;
}

function getTerritorialSummary() {
    const features = state.geography?.features || [];

    let totalPatients = 0;
    let totalRecommended = 0;
    let totalDeferred = 0;

    let weightedNeed = 0;
    let weightedNeedPatients = 0;

    features.forEach(feature => {
        const p = feature.properties || {};

        const patients = Number(p.patient_count || 0);
        const recommended = Number(p.recommended_count || 0);
        const deferred = Number(p.deferred_count || 0);
        const meanNeed = Number(p.mean_baseline_need);

        totalPatients += patients;
        totalRecommended += recommended;
        totalDeferred += deferred;

        if (patients > 0 && Number.isFinite(meanNeed)) {
            weightedNeed += meanNeed * patients;
            weightedNeedPatients += patients;
        }
    });

    return {
        totalPatients,

        meanNeed:
            weightedNeedPatients > 0
                ? weightedNeed / weightedNeedPatients
                : 0,

        recommendationRate:
            totalPatients > 0
                ? totalRecommended / totalPatients
                : 0,

        deferredRate:
            totalRecommended > 0
                ? totalDeferred / totalRecommended
                : 0,
    };
}

function renderTerritorialComparison() {
    if (!state.geography?.features) {
        return;
    }

    const metric =
        MAP_METRICS[state.mapMetric]
        || MAP_METRICS.patient_count;

    const summary = getTerritorialSummary();

    el.territorialPatients.textContent =
        summary.totalPatients.toLocaleString("it-IT");

    el.territorialMeanNeed.textContent =
        summary.meanNeed.toLocaleString("it-IT", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });

    el.territorialRecommendationRate.textContent =
        `${(summary.recommendationRate * 100).toLocaleString("it-IT", {
            maximumFractionDigits: 1,
        })}%`;

    el.territorialDeferralRate.textContent =
        `${(summary.deferredRate * 100).toLocaleString("it-IT", {
            maximumFractionDigits: 1,
        })}%`;

    el.territorialMetricLabel.textContent = metric.label;

    el.territorialRankingDescription.textContent =
        `Ordinamento decrescente per: ${metric.label}.`;

    const ranked = state.geography.features
        .filter(feature => feature.properties?.has_population_data)
        .map(feature => ({
            feature,
            properties: feature.properties,
            value: metric.getValue(feature.properties || {}),
        }))
        .sort((a, b) => {
            const difference = b.value - a.value;

            if (difference !== 0) {
                return difference;
            }

            return String(a.properties.municipality)
                .localeCompare(String(b.properties.municipality), "it");
        })
        .slice(0, 10);

    el.territorialRankingBody.replaceChildren();

    ranked.forEach((item, index) => {
        const tr = document.createElement("tr");

        tr.className = "ph-territorial-row";
        tr.tabIndex = 0;

        appendCell(tr, String(index + 1));
        appendCell(tr, safeText(item.properties.municipality));
        appendCell(tr, metric.format(item.value));
        appendCell(
            tr,
            Number(item.properties.patient_count || 0)
                .toLocaleString("it-IT")
        );

        const select = () =>
            selectMunicipality(item.properties);

        tr.addEventListener("click", select);

        tr.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                select();
            }
        });

        el.territorialRankingBody.appendChild(tr);
    });
}

function renderGeographyMap(fitMap = false) {
    if (!state.geography || !Array.isArray(state.geography.features)) {
        return;
    }

    ensurePopulationHealthMap();

    if (state.geoJsonLayer) {
        state.geoJsonLayer.remove();
        state.geoJsonLayer = null;
    }

    state.municipalityLayers.clear();

    const features = state.geography.features;
    const metric = MAP_METRICS[state.mapMetric] || MAP_METRICS.patient_count;

    state.mapDomain = getMetricDomain(features, metric);

    state.geoJsonLayer = L.geoJSON(features, {
        style: municipalityPolygonStyle,

        onEachFeature(feature, layer) {
            const properties = feature.properties || {};
            const value = metric.getValue(properties);

            state.municipalityLayers.set(
                properties.municipality,
                layer
            );

            layer.bindTooltip(
                `<strong>${safeText(properties.municipality)}</strong><br>${metric.label}: ${metric.format(value)}`,
                {
                    sticky: true,
                    direction: "top",
                }
            );

            layer.on("mouseover", () => {
                const selected =
                    state.selectedMunicipalityName === properties.municipality;

                layer.setStyle({
                    weight: selected ? 4 : 2.5,
                    color: selected ? "#0d6efd" : "#334155",
                });

                layer.bringToFront();
            });

            layer.on("mouseout", () => {
                if (state.geoJsonLayer) {
                    state.geoJsonLayer.resetStyle(layer);
                }
            });

            layer.on("click", event => {
                L.DomEvent.stopPropagation(event);
                selectMunicipality(properties);
            });
        },
    }).addTo(state.map);

    if (fitMap && state.geoJsonLayer.getBounds().isValid()) {
        state.map.fitBounds(
            state.geoJsonLayer.getBounds(),
            {
                padding: [18, 18],
                maxZoom: 11,
            }
        );
    }

    renderMapLegend(metric, state.mapDomain);
    renderTerritorialComparison();

    window.setTimeout(() => state.map.invalidateSize(), 0);
}

async function ensureGeographyForRun(runId) {
    if (state.geography && state.geographyRunId === runId) {
        renderGeographyMap(false);
        return;
    }

    el.mapStatus.textContent = "Caricamento distribuzione territoriale...";

    try {
        const data = await loadGeography(runId);

        state.geography = data;
        state.geographyRunId = runId;

        const geography = data.geography || {};

        const municipalities =
            Number(geography.boundary_count || data.features?.length || 0);

        const patients =
            Number(geography.joined_patient_count || geography.localized_patients || 0);

        el.mapStatus.textContent =
            `${municipalities.toLocaleString("it-IT")} comuni ISTAT · `
            + `${patients.toLocaleString("it-IT")} pazienti localizzati`;

        renderGeographyMap(true);

    } catch (error) {
        console.error(error);

        state.geography = null;
        state.geographyRunId = null;

        el.mapStatus.textContent =
            error.message || "Distribuzione territoriale non disponibile.";
    }
}


function renderCsvCompatibilityReport(payload) {

    const report = payload?.report || {};
    const dataset = report.dataset || {};
    const schema = report.schema || {};
    const geography = report.geography || {};
    const errors = Array.isArray(report.errors) ? report.errors : [];
    const warnings = Array.isArray(report.warnings) ? report.warnings : [];
    const compatible = report.can_run === true;
    state.csvUploadId = compatible ? payload.upload_id : null;
    state.csvCompatibilityReport = report;
    if (compatible) {
        // Se validazione ok --> CSV la sorgente attiva
        el.dataSourceCsvOption.disabled = false;
        el.dataSource.value ="real_csv";
    } else {
        el.dataSourceCsvOption.disabled =true;
        el.dataSource.value ="synthetic";
    }
    updateDataSourceUi();

    el.csvReport.hidden = false;
    el.csvReport.className = compatible ? "ph-status ph-status--success" : "ph-status ph-status--error";
    el.csvReportTitle.textContent = compatible ? "CSV compatibile" : "CSV non compatibile";

    const realRows =Number(geography.real_rows || 0);
    const syntheticRows =Number(geography.synthetic_fallback_rows || 0 );
    const invalidRows =Number(geography.invalid_rows || 0);
    const aliasCount = Array.isArray(schema.aliased_columns) ? schema.aliased_columns.length : 0;
    const identifyingColumns = Array.isArray( schema.identifying_columns) ? schema.identifying_columns : [];
    const rows = [
        ["Pazienti",Number(dataset.patient_count || 0 ).toLocaleString("it-IT")],
        ["Colonne obbligatorie", `${schema.present_required_count ?? 0}` + ` / ` + `${schema.required_column_count ?? 0}`],
        ["Alias riconosciuti", String(aliasCount)],
        ["Residenza reale",realRows.toLocaleString("it-IT")],
        ["Fallback geografico sintetico", syntheticRows.toLocaleString("it-IT")],
        ["Righe geografiche non valide",invalidRows.toLocaleString("it-IT")],
    ];

    const summaryHtml = rows
        .map(
            ([label, value]) =>
                `<div>`
                + `<strong>${label}:</strong> `
                + `${value}`
                + `</div>`
        )
        .join("");

    const identifyingHtml =
        identifyingColumns.length
            ? (
                `<div style="margin-top:.75rem;">`
                + `<strong>` + `Colonne identificative escluse:` + `</strong> `
                + identifyingColumns.join(", ")
                + `</div>`
            )
            : "";

    const warningsHtml =
        warnings.length
            ? (
                `<div style="margin-top:.75rem;">`
                + `<strong>Warning:</strong>`
                + `<ul>` + warnings.map(warning =>`<li>${safeText(warning.message)}</li>`).join("") + `</ul>`
                + `</div>`
            )
            : "";


    const errorsHtml =
        errors.length
            ? (
                `<div style="margin-top:.75rem;">`
                + `<strong>Errori:</strong>`
                + `<ul>` + errors.map(error =>`<li>${safeText(error.message)}</li>`).join("") + `</ul>`
                + `</div>`
            )
            : "";


    const uploadHtml =
        compatible
            ? (
                `<div style="margin-top:.75rem;">`
                + `<strong>Dataset validato.</strong> ` + `Upload ID: ` + `<code>${safeText(payload.upload_id)}</code>`
                + `</div>`
            ) : "";

    el.csvReportBody.innerHTML = summaryHtml + identifyingHtml + warningsHtml + errorsHtml + uploadHtml;
}


async function handleCsvValidation() {

    const file = el.csvFile?.files?.[0];
    if (!file) {
        el.csvReport.hidden = false;
        el.csvReport.className = "ph-status ph-status--error";
        el.csvReportTitle.textContent = "File mancante";
        el.csvReportBody.textContent = "Seleziona un file CSV prima di avviare la validazione.";
        return;
    }

    state.csvUploadId = null;
    state.csvCompatibilityReport = null;
    el.csvValidateButton.disabled = true;
    el.csvValidateButton.textContent = "Validazione in corso...";
    el.csvReport.hidden = false;
    el.csvReport.className ="ph-status ph-status--loading";
    el.csvReportTitle.textContent ="Validazione CSV";
    el.csvReportBody.textContent = "Controllo dello schema, delle covariate e della geografia...";


    try {
        const payload =await validatePatientCsv(file);
        renderCsvCompatibilityReport(payload);
    } catch (error) {
        console.error(error);
        state.csvUploadId = null;
        state.csvCompatibilityReport = null;
        el.csvReport.hidden = false;
        el.csvReport.className ="ph-status ph-status--error";
        el.csvReportTitle.textContent ="Errore durante la validazione";
        el.csvReportBody.textContent =error.message;

    } finally {
        el.csvValidateButton.disabled =false;
        el.csvValidateButton.textContent ="Valida CSV";
    }
}

function handleCsvFileChange() {
    state.csvUploadId = null;
    state.csvCompatibilityReport =null;
    if (el.dataSourceCsvOption) {
        el.dataSourceCsvOption.disabled =true;
    }
    if (el.dataSource) {
        el.dataSource.value ="synthetic";
    }

    updateDataSourceUi();

    if (el.csvReport) {
        el.csvReport.hidden = true;
        el.csvReportBody.replaceChildren();
    }
}



    // ========================================================
    // KPI
    // ========================================================

    function renderSummary(summary) {
        state.summary = summary;
        const recommendation = summary.recommendation || {};
        const allocation = summary.allocation || {};
        el.kpiPatients.textContent = formatNumber(summary.patient_count, 0);
        el.kpiRecommended.textContent = `${formatNumber(recommendation.recommended_count, 0)} (${formatPercent(recommendation.recommendation_rate)})`;
        el.kpiAbstained.textContent = `${formatNumber(recommendation.abstained_count, 0)} (${formatPercent(recommendation.abstention_rate)})`;
        el.kpiAllocated.textContent = formatNumber(allocation.allocated_count, 0);
        el.kpiDeferred.textContent = `${formatNumber(allocation.deferred_count, 0)} (${formatPercent(allocation.conditional_deferral_rate)})`;
        renderLevelDistribution(el.baselineDistribution, summary.baseline_level_distribution);
        renderLevelDistribution(el.recommendedDistribution, summary.recommended_only_level_distribution || summary.recommended_level_distribution);
        renderLevelDistribution(el.allocatedDistribution, summary.allocated_level_distribution);
        renderOperationalOutcome(el.operationalOutcome, allocation);
    }

    function renderLevelDistribution(container, distribution) {
        container.replaceChildren();
        const values = [];
        for (let level = 1; level <= 6; level++) {
                values.push(Number(distribution?.[String(level)] || 0));
        }

        const maxValue = Math.max(...values, 1);
        values.forEach((count, index) => {
                const level = index + 1;
                const row = document.createElement("div");
                row.className = "ph-distribution-row";
                const label = document.createElement("span");
                label.className = "ph-distribution-label";
                label.textContent = `Livello ${level}`;
                const barContainer = document.createElement("div");
                barContainer.className = "ph-distribution-bar-container";
                const bar = document.createElement("div");
                bar.className = "ph-distribution-bar";
                bar.style.width = `${(count / maxValue) * 100}%`;
                const value = document.createElement("strong");
                value.textContent = count.toLocaleString("it-IT");
                barContainer.appendChild(bar);
                row.append(label, barContainer, value);
                container.appendChild(row);
            }
        );
    }

    function renderOperationalOutcome(container, allocation) {

    container.replaceChildren();
    const items = [
        {
            label: "Raccomandazione attivata",
            count: Number(allocation.allocated_count || 0),
        },
        {
            label: "Raccomandazione rinviata",
            count: Number(allocation.deferred_count || 0
            ),
        },
        {
            label: "Nessuna raccomandazione",
            count: Number(allocation.no_actionable_recommendation_count || 0),
        },
    ];

    const maxValue = Math.max(...items.map(item => item.count), 1);
    items.forEach(item => {
        const row = document.createElement("div");
        row.className = "ph-distribution-row ph-distribution-row--wide";
        const label = document.createElement("span");
        label.className = "ph-distribution-label";
        label.textContent = item.label;
        const barContainer = document.createElement("div");
        barContainer.className = "ph-distribution-bar-container";
        const bar = document.createElement("div");
        bar.className = "ph-distribution-bar";
        bar.style.width = `${(item.count / maxValue) * 100}%`;
        barContainer.appendChild(bar);
        const value = document.createElement("strong");
        value.textContent = item.count.toLocaleString("it-IT");
        row.append(label, barContainer, value);
        container.appendChild(row);
    });
}


    // ========================================================
    // TABLE
    // ========================================================

    function renderPatients(rows) {

        state.rows = rows;
        el.tableBody.replaceChildren();
        rows.forEach(row => {

            const tr = document.createElement("tr");
            tr.className = "ph-patient-row";
            tr.tabIndex = 0;
            appendCell(tr, safeText(row.patient_id));
            appendCell(tr, safeText(row.residence_municipality));
            appendCell(tr, formatNumber(row.age, 0));
            appendCell(tr, safeText(row.baseline_need_level));
            appendCell(tr, safeText(row.current_care_profile_level));
            appendCell(tr, safeText(row.recommended_actionable_level));
            appendCell(tr, formatNumber(row.calibrated_incremental_benefit, 2));
            appendCell(tr, recommendationStatusLabel(row.recommendation_status));
            appendCell(tr, safeText(row.allocated_care_level));
            appendCell(tr, allocationStatusLabel(row.allocation_status));

            tr.addEventListener("click", () => showPatientDetail(row));
            tr.addEventListener("keydown", event => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        showPatientDetail(row);
                    }
                }
            );
            el.tableBody.appendChild(tr);
        });
    }


    function appendCell(row, value) {
        const td = document.createElement("td");
        td.textContent = value;
        row.appendChild(td);
    }

    function renderFilterSummary(pagination) {

            const total = Number(pagination.total_rows || 0);
            const filtered = Number(pagination.filtered_rows ?? total);
            const returned = Number(pagination.returned_rows || 0);
            let message;
            if (filtered === total) {
                el.filterSummary.textContent = `${total.toLocaleString("it-IT")} ` + `pazienti nel run · ` + `${returned.toLocaleString("it-IT")} ` + `mostrati in questa pagina`;
                return;
            }

            el.filterSummary.textContent =
                `${filtered.toLocaleString("it-IT")} `
                + `pazienti corrispondono ai filtri · `
                + `${returned.toLocaleString("it-IT")} `
                + `mostrati · `
                + `${total.toLocaleString("it-IT")} `
                + `pazienti totali`;

            if (state.filters.municipality){
                el.filterSummary.textContent= el.filterSummary.textContent += `· Comune:` + state.filters.municipality
            }
        }

    // ========================================================
    // PATIENT DETAIL
    // ========================================================

    function showPatientDetail(row) {

            el.detail.hidden = false;
            el.detailTitle.textContent = `Paziente ${safeText(row.patient_id)}`;
            el.detailBody.replaceChildren();
            const sections = [
        {
            title: "Quadro di bisogno",
            fields: [
                ["Livello di bisogno", `Livello ${safeText(row.baseline_need_level)}`,],
                ["Descrizione", safeText(row.baseline_need_label),],
                ["Elementi che hanno contribuito", baselineExplanationLabel(row.baseline_need_explanation),],
                ["Percorso assistenziale protetto", yesNo(row.baseline_need_protected_pathway),],
            ],
        },

        {
            title: "Assistenza attuale",
            fields: [
                ["Profilo assistenziale", profileLabel(row.current_care_profile, row.current_care_profile_name),],
                ["Livello attuale", `Livello ${safeText(row.current_care_profile_level)}`,],
            ],
        },

        {
            title: "Indicazione PROMETHEUS",
            fields: [
                ["Esito", recommendationStatusLabel(row.recommendation_status),],
                ["Motivazione", recommendationReasonLabel(row.recommendation_reason),],
                ["Profilo proposto", profileLabel(row.recommended_profile_id, row.recommended_profile_name),],
                ["Livello associato", row.recommendation_status === "recommended" ? `Livello ${safeText(row.recommended_actionable_level)}` : "Nessuna nuova raccomandazione",],
                ["Priorità relativa", row.recommendation_status === "recommended" ? formatNumber(row.recommended_raw_priority_score, 3) : "Non applicabile",],
                ["Beneficio incrementale stimato", row.recommendation_status === "recommended" ? `${formatNumber(row.calibrated_incremental_benefit, 2)} giorni` : "Non applicabile",],
                ["Supporto empirico sufficiente", yesNo(row.selected_patient_empirical_support),],
            ],
        },

        {
            title: "Esito operativo",
            fields: [
                ["Stato", allocationStatusLabel(row.allocation_status),],
                ["Motivazione", allocationReasonLabel(row.allocation_reason),],
                ["Profilo effettivamente attivato", row.allocated_profile_id ? profileLabel(row.allocated_profile_id, row.allocated_profile_name) : (row.deferred_recommendation ? "Rimane temporaneamente l'assistenza corrente" : "Assistenza corrente invariata"),],
                ["Livello assistenziale operativo", `Livello ${safeText(row.allocated_care_level)}`,],
                ["Raccomandazione rinviata per vincoli operativi", yesNo(row.deferred_recommendation),],
            ],
        },
    ];

        sections.forEach(section => {

            const block = document.createElement("section");
            block.className = "ph-detail-section";
            const heading = document.createElement("h4");
            heading.textContent = section.title;
            block.appendChild(heading);
            const dl = document.createElement("dl");
            section.fields.forEach(([label, value]) => {
                    const dt = document.createElement("dt");
                    const dd = document.createElement("dd");
                    dt.textContent = label;
                    dd.textContent = safeText(value);
                    dl.append(dt, dd);
                }
            );

            block.appendChild(dl);
            el.detailBody.appendChild(block);
        });
    }


    function hidePatientDetail() {
        el.detail.hidden = true;
        el.detailBody.replaceChildren();
    }

    // ========================================================
    // ACTIVE STRATIFICATION
    // ========================================================

    function persistActiveStratification() {

        if (!state.runId) {
            return;
        }
        const payload = {
            runId: state.runId,
            patients: Number(el.patients.value),
            seed: Number(el.seed.value),
            scenario: el.scenario.value.trim(),
        };
        localStorage.setItem(ACTIVE_STRATIFICATION_STORAGE_KEY,JSON.stringify(payload));
    }


    function getPersistedStratification() {

        const raw = localStorage.getItem(ACTIVE_STRATIFICATION_STORAGE_KEY);

        if (!raw) {
            return null;
        }

        try {
            const parsed = JSON.parse(raw);
            if (!parsed || !parsed.runId) {
                return null;
            }
            return parsed;

        } catch {
            localStorage.removeItem(ACTIVE_STRATIFICATION_STORAGE_KEY);
            return null;
        }
    }


    function clearPersistedStratification() {
        localStorage.removeItem(ACTIVE_STRATIFICATION_STORAGE_KEY);
    }


    function showActiveStratificationMode() {

        if (el.configurationCard) {
            el.configurationCard.hidden = true;
        }

        if (el.results) {
            el.results.hidden = false;
        }
    }


    function showNewStratificationMode() {

        if (el.configurationCard) {
            el.configurationCard.hidden = false;
        }

        if (el.results) {
            el.results.hidden = true;
        }
    }

    // ========================================================
    // POPULATION HEALTH -> 118 SEVERITY PREVIEW
    // ========================================================

    function severity118MetricLabel(metric) {
        const labels = {patient_count: "Pazienti per 1000 residenti", mean_baseline_need: "Bisogno medio baseline",};
        return labels[metric] || metric || "Indicatore";
    }


    function severity118FormatValue(value, metric) {
        const number = Number(value);
        if (!Number.isFinite(number)) {
            return "—";
        }
        if (metric === "patient_count") {
            return number.toFixed(2);
        }
        if (metric === "mean_baseline_need") {
            return number.toFixed(3);
        }
        return String(number);
    }


    function resetSeverity118Preview() {
        state.severity118Preview = null;
        state.severity118Index.clear();

        if (state.severity118Layer) {
            state.severity118Layer.remove();
            state.severity118Layer = null;
        }

        if (el.severity118PreviewResults) {
            el.severity118PreviewResults.hidden =true;
        }

        if (el.severity118PreviewSummary) {
            el.severity118PreviewSummary.textContent ="";
        }

        if (el.severity118MunicipalityDetail) {
            el.severity118MunicipalityDetail.textContent ="Seleziona un comune sulla mappa per visualizzare il dettaglio.";
        }

        if (el.severity118PreviewStatus) {
            el.severity118PreviewStatus.textContent ="Seleziona un indicatore e genera l'anteprima.";
        }

        if (el.severity118UsePlanningButton) {
            el.severity118UsePlanningButton.disabled =true;
        }

        if (el.severity118MaterializeStatus) {
            el.severity118MaterializeStatus.textContent ="";
        }
    }


    async function loadSeverity118Preview(runId, metric) {

        const response = await fetch("/api/ph-118/severity/preview",
            {
                method: "POST",
                headers: {"Content-Type": "application/json",},
                body: JSON.stringify({
                    run_id: runId,
                    metric: metric,
                }),
            }
        );

        return parseResponse(response);
    }


    function renderSeverity118Preview(data) {
    state.severity118Preview = data;
    if (el.severity118UsePlanningButton) {
        el.severity118UsePlanningButton.disabled =false;
    }

    if (el.severity118MaterializeStatus) {
        el.severity118MaterializeStatus.textContent = "";
    }

    const counts =data.tier_counts || {};
    if (el.severity118PreviewSummary) {
        el.severity118PreviewSummary.textContent = `${data.municipality_count} comuni · ` + `ALTA: ${counts.ALTA || 0} · `+ `MEDIA: ${counts.MEDIA || 0} · `+ `BASSA: ${counts.BASSA || 0}`;
    }

    el.severity118PreviewStatus.textContent = "Anteprima costruita sul run " + `${data.run_id} utilizzando `  + `${severity118MetricLabel(data.metric)}.`;
    el.severity118PreviewResults.hidden = false;
    if (el.severity118MunicipalityDetail) {
        el.severity118MunicipalityDetail.textContent ="Seleziona un comune sulla mappa per visualizzare il dettaglio.";
    }
    renderSeverity118Map(data);
}


    async function handleSeverity118Preview() {

        if (!state.runId) {
            alert("Non è presente una stratificazione Population Health attiva.");
            return;
        }

        const metric =(el.severity118Metric?.value || "").trim();

        if ( metric !== "patient_count" && metric !== "mean_baseline_need") {
            alert("Indicatore Population Health non valido.");
            return;
        }

        el.severity118PreviewButton.disabled = true;
        el.severity118PreviewStatus.textContent = "Costruzione della severità territoriale 118...";
        el.severity118PreviewResults.hidden = true;

        try {
            const preview =await loadSeverity118Preview(state.runId,metric);
            renderSeverity118Preview(preview);
        }catch (error) {

            console.error(error);
            state.severity118Preview = null;
            el.severity118PreviewResults.hidden = true;
            el.severity118PreviewStatus.textContent = error.message || "Impossibile costruire la preview 118.";
        }
        finally {
            el.severity118PreviewButton.disabled = false;
        }
    }

    function normalizeSeverityMunicipality(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[’`´]/g, "'")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
    }

    function buildSeverity118Index(preview) {
        const index = new Map();
        (preview.municipalities || []).forEach(row => {
            const key =normalizeSeverityMunicipality(row.comune);
            if (key) {
                index.set(key, row);
            }
        });
        return index;
    }

    const PH118_TIER_COLORS = {
        ALTA: "#e24b3b",
        MEDIA: "#f7c65a",
        BASSA: "#5fb164",
    };

    const PH118_TIER_STROKES = {
        ALTA: "#a92e27",
        MEDIA: "#bd8b21",
        BASSA: "#397c43",
    };


    function ensureSeverity118Map() {

        if (state.severity118Map) {
            return;
        }

        if ( typeof L === "undefined" || !el.severity118Map) {
            throw new Error("Leaflet non disponibile per la mappa 118.");
        }
        state.severity118Map = L.map(el.severity118Map,{zoomControl: true,});
        L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 18,
                attribution: "&copy; OpenStreetMap contributors",
            }
        ).addTo(state.severity118Map);
    }

    function severity118PolygonStyle(feature) {

        const properties =feature?.properties || {};
        const municipality = properties.municipality || properties.comune || "";
        const key = normalizeSeverityMunicipality(municipality);
        const row = state.severity118Index.get(key);
        const tier = row?.severity_tier || null;

        if (!tier) {
            return {
                color: "#94a3b8",
                weight: 1.5,
                opacity: 0.8,
                fillColor: "#e5e7eb",
                fillOpacity: 0.45,
            };
        }

        return {
            color: PH118_TIER_STROKES[tier] || "#64748b",
            weight: 2,
            opacity: 0.9,
            fillColor:PH118_TIER_COLORS[tier] || "#e5e7eb",
            fillOpacity: 0.72,
        };
    }

    function renderSeverity118Legend() {

        if (!el.severity118Legend) {
            return;
        }
        el.severity118Legend.innerHTML = `
            <strong>Severità territoriale 118</strong>
            <div style=" display:grid; gap:7px; margin-top:8px;">
                <span> <i style=" display:inline-block; width:14px; height:14px; margin-right:7px; background:${PH118_TIER_COLORS.ALTA};"></i> ALTA · peso 1.30 </span>
                <span><i style=" display:inline-block; width:14px; height:14px; margin-right:7px; background:${PH118_TIER_COLORS.MEDIA};"></i> MEDIA · peso 1.10</span>
                <span> <i style=" display:inline-block; width:14px; height:14px; margin-right:7px;background:${PH118_TIER_COLORS.BASSA};"></i>BASSA · peso 1.00</span>
            </div>
        `;
    }

    function renderSeverity118MunicipalityDetail( row, metric) {

        if (!el.severity118MunicipalityDetail) {
            return;
        }
        if (!row) {
            el.severity118MunicipalityDetail.textContent = "Nessun dato Population Health disponibile per questo comune.";
            return;
        }

        el.severity118MunicipalityDetail.innerHTML = `
            <strong>${safeText(row.comune)}</strong>
            <div style="display:grid; grid-template-columns: repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-top:10px;">
                <div>
                    <small>Indicatore</small><br>
                    <strong>${severity118MetricLabel(metric)}</strong>
                </div>
                <div>
                    <small>Valore</small><br>
                    <strong> ${severity118FormatValue(row.ph_value,metric)}</strong>
                </div>
                <div>
                    <small>Tier territoriale</small><br>
                    <strong>${safeText(row.severity_tier)}</strong>
                </div>
                <div>
                    <small>Peso domanda 118</small><br>
                    <strong>${Number(row.tier_weight).toFixed(2)}</strong>
                </div>
            </div>
        `;
    }


    function renderSeverity118Map(preview) {
        if (!state.geography || !Array.isArray(state.geography.features)) {
            throw new Error("Geografia Population Health non disponibile.");
        }

        ensureSeverity118Map();
        state.severity118Index =buildSeverity118Index(preview);
        if (state.severity118Layer) {
            state.severity118Layer.remove();
            state.severity118Layer = null;
        }


        state.severity118Layer =L.geoJSON(state.geography.features,
                                            {
                                                style:severity118PolygonStyle,onEachFeature( feature, layer) {
                                                    const properties= feature.properties || {};
                                                    const municipality = properties.municipality || properties.comune || "";
                                                    const key = normalizeSeverityMunicipality(municipality);
                                                    const row = state.severity118Index.get(key);

                                                    if (row) {
                                                        layer.bindTooltip(
                                                            `
                                                            <strong>${safeText(row.comune)}</strong>
                                                            <br>
                                                            ${severity118MetricLabel(preview.metric)}:
                                                            ${severity118FormatValue(row.ph_value, preview.metric)}
                                                            <br>
                                                            Severità:
                                                            <strong>${safeText(row.severity_tier)}</strong>
                                                            <br>
                                                            Peso: ${Number(row.tier_weight).toFixed(2)}
                                                            `,
                                                            {
                                                                sticky: true,
                                                                direction: "top",
                                                            }
                                                        );
                                                    }

                                                    layer.on("mouseover",() => {
                                                            layer.setStyle({weight: 3, opacity: 1,});
                                                            layer.bringToFront();
                                                        }
                                                    );

                                                    layer.on("mouseout", () => {
                                                            if (state.severity118Layer) {
                                                                state.severity118Layer.resetStyle(layer);
                                                            }
                                                        }
                                                    );

                                                    layer.on("click",() => {
                                                            renderSeverity118MunicipalityDetail(row,preview.metric);
                                                        }
                                                    );
                                                },
                                            }
                                        ).addTo(state.severity118Map);


        const bounds =state.severity118Layer.getBounds();
        if (bounds.isValid()) {
            state.severity118Map.fitBounds(bounds,{padding: [18, 18], maxZoom: 11,});
        }

        renderSeverity118Legend();
        window.setTimeout(() => {state.severity118Map ?.invalidateSize();},0);
    }

    async function materializeSeverity118Scenario(
    runId,
    metric
) {

    const response = await fetch(
        "/api/ph-118/severity/materialize",
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
            },

            body: JSON.stringify({
                run_id: runId,
                metric: metric,
            }),
        }
    );

    return parseResponse(response);
}


function persistSeverity118Selection(data) {

    const severity = data.severity || {};

    const selection = {
        severity_source: "population_health",

        severity_scenario_id:
            data.scenario_id,

        source_run_id:
            severity.source_run_id,

        metric:
            severity.metric,

        municipality_count:
            severity.municipality_count,

        created_at:
            severity.created_at,
    };

    localStorage.setItem(
        PH118_SEVERITY_SELECTION_STORAGE_KEY,
        JSON.stringify(selection)
    );
}


async function handleUseSeverity118InPlanning() {

    const preview =state.severity118Preview;

    if (!preview || !state.runId) {
        alert("Genera prima una preview della severità territoriale.");
        return;
    }


    const metric =(el.severity118Metric?.value || "").trim();

    // Evito di confermare una preview vecchia dopo che l'indicatore è stato cambiato.
    if (preview.run_id !== state.runId || preview.metric !== metric) {
        alert("La preview visualizzata non corrisponde più alla stratificazione o all'indicatore selezionato. Rigenera prima l'anteprima.");
        return;
    }

    const confirmed = window.confirm(
        "Confermare l'utilizzo di questa severità nella Pianificazione 118?\n\n"
        + `Run PROMETHEUS: ${state.runId}\n`
        + `Indicatore: ${severity118MetricLabel(metric)}\n\n`
    );


    if (!confirmed) {
        return;
    }

    el.severity118UsePlanningButton.disabled = true;

    if (el.severity118MaterializeStatus) {
        el.severity118MaterializeStatus.textContent ="Creazione dello scenario 118...";
    }

    try {
        const result =await materializeSeverity118Scenario(state.runId, metric);
        persistSeverity118Selection(result);

        if (el.severity118MaterializeStatus) {
            el.severity118MaterializeStatus.textContent ="Scenario confermato. Apertura della Pianificazione 118...";
        }

        // La Planning 118 reale è la route "/".
        window.location.assign("/");
    }

    catch (error) {
        console.error(error);
        if (el.severity118MaterializeStatus) {
            el.severity118MaterializeStatus.textContent = error.message || "Impossibile creare lo scenario 118.";
        }
        el.severity118UsePlanningButton.disabled =
            false;
    }
}


    // ========================================================
    // RESULT LOAD
    // ========================================================

    async function displayRun(runId, page = 1) {

        showStatus("loading", "Caricamento risultati", `Lettura del run ${runId}...`);
        const data = await loadResults(runId, page, state.pageSize);
        state.runId = data.run_id;
        state.page = data.pagination.page;
        state.totalPages = data.pagination.total_pages;
        state.totalRows = data.pagination.total_rows;
        state.filteredRows = data.pagination.filtered_rows ?? data.pagination.total_rows;
        state.metadata = data.metadata;
        el.runId.textContent = data.run_id;
        persistActiveStratification();
        showActiveStratificationMode();

        renderSummary(data.summary);
        renderPatients(data.rows);
        renderFilterSummary(data.pagination);

        el.pageLabel.textContent = `Pagina ${state.page} di ${state.totalPages}`;
        el.prevPage.disabled = state.page <= 1;
        el.nextPage.disabled = state.page >= state.totalPages;
        el.results.hidden = false;

        const completedSource = data?.metadata?.source;
        if (el.runDataSource) {
        if (completedSource === "real_csv") {
            el.runDataSource.textContent = "Dataset CSV esterno · ambiente causale semisintetico";
        } else if (completedSource === "synthetic") {
            el.runDataSource.textContent ="Popolazione sintetica";
        } else {
            el.runDataSource.textContent = "Sorgente non disponibile";
        }
    }
        state.lastCompletedDataSource =completedSource === "real_csv" || completedSource === "synthetic" ? completedSource : null;
        state.lastCompletedGeography = data?.metadata?.geography || null;

        updateMapGeographyProvenance();
        await ensureGeographyForRun(state.runId);
        showStatus("success", "Stratificazione completata", `${data.pagination.total_rows} pazienti disponibili.`);
    }

    async function restoreActiveStratification() {

        const saved = getPersistedStratification();

        if (!saved) {
            showNewStratificationMode();
            return;
        }

        if (Number.isFinite(Number(saved.patients))) {
            el.patients.value = String(saved.patients);
        }

        if (Number.isFinite(Number(saved.seed))) {
            el.seed.value = String(saved.seed);
        }

        if (saved.scenario) {
            el.scenario.value = saved.scenario;
        }

        try {
            showStatus("loading", "Ripristino stratificazione", `Caricamento del run ${saved.runId}...` );
            await displayRun(saved.runId, 1);
        } catch (error) {

            console.error(error);
            clearPersistedStratification();
            state.runId = null;
            showNewStratificationMode();
            showStatus("error","Stratificazione non più disponibile", "Il run precedentemente selezionato non è più disponibile. Configura una nuova stratificazione.");
        }
    }


    async function loadGeography(runId) {
    const response = await fetch(`/api/stratification/geography/${encodeURIComponent(runId)}/geojson`);
    return parseResponse(response);
    }

    // ========================================================
    // FORM
    // ========================================================

    async function handleSubmit(event) {

        event.preventDefault();
        hidePatientDetail();
        resetSeverity118Preview();

        state.filters = {
            search: "",
            baselineLevel: "",
            recommendationStatus: "",
            allocationStatus: "",
            municipality: "",
        };
        state.pageSize = 25;
        state.sortBy = "patient_id";
        state.sortDirection = "asc";

        el.pageSize.value = "25";
        updateSortIndicators();

        el.filterSearch.value = "";
        el.filterBaseline.value = "";
        el.filterRecommendation.value = "";
        el.filterAllocation.value = "";

        state.geography = null;
        state.geographyRunId = null;
        state.selectedMunicipality = null;
        state.selectedMunicipalityName = null;
        state.mapMetric = "patient_count";
        el.mapMetric.value = "patient_count";
        state.municipalityLayers.clear();

        if (state.geoJsonLayer) {
            state.geoJsonLayer.remove();
            state.geoJsonLayer = null;
        }

        // Ripristina il pannello di dettaglio territoriale
        if (el.municipalityDetail) {
            el.municipalityDetail.innerHTML = `
                <div class="ph-municipality-placeholder">
                    <strong>Dettaglio territoriale</strong>
                    <p> Seleziona un comune sulla mappa per visualizzarne gli indicatori.</p>
                </div>
            `;
        }

        const useCsv = el.dataSource.value  === "real_csv";

        if (useCsv && !state.csvUploadId) {
            showStatus( "error", "Dataset CSV non disponibile", "Valida nuovamente il CSV prima di avviare PROMETHEUS.");
            return;
        }

        const payload = {
            seed:Number(el.seed.value),
            scenario: el.scenario.value.trim(),
        };

        if (useCsv) {
            payload.patient_csv_upload_id = state.csvUploadId;
        } else {
            payload.patients = Number(el.patients.value);
        }

        state.lastCompletedDataSource =null;
        state.lastCompletedGeography =null;
        updateMapGeographyProvenance();

        setRunning(true);
        el.results.hidden = true;

        const runSourceMessage = useCsv ? ("Uso del dataset CSV validato, causal supervision semisintetica, ranking, calibrazione e allocation...") : ("Generazione popolazione sintetica, causal supervision, ranking, calibrazione e allocation...");
        showStatus("loading", "PROMETHEUS in esecuzione", runSourceMessage);

        try {
            const run = await startRun(payload);
            showStatus(
                "loading",
                "Run completato",
                "Caricamento degli artifact..."
            );

            // displayRun:
            // 1. carica risultati
            // 2. mostra KPI
            // 3. mostra tabella
            // 4. rende visibile phResults
            // 5. carica la geografia
            // 6. crea i marker sulla mappa

            await displayRun(run.run_id, 1);

        }

        catch (error) {
            console.error(error);
            const apiError =error?.payload?.error || null;
            const isScientificFeasibilityError = error.httpStatus === 422 && apiError?.type === "scientific_feasibility_error";
            if (isScientificFeasibilityError) {
                const message = useCsv
                    ? (
                        "Il dataset CSV è formalmente compatibile, ma questa specifica coorte non fornisce "
                        + "supporto empirico sufficiente per completare l'addestramento del causal ranker. "
                        + "PROMETHEUS ha quindi interrotto correttamente il run senza modificare le soglie scientifiche."
                    )
                    : (
                        "La configurazione della popolazione è formalmente valida, ma il run non dispone di supporto empirico sufficiente "
                        + "per completare l'addestramento del causal ranker. PROMETHEUS ha quindi interrotto l'esecuzione senza rilassare le soglie scientifiche."
                    );

                showStatus("error","Supporto causale insufficiente",message);
                return;
            }

            let title ="Errore di stratificazione";
            if (error.httpStatus === 400) {
                title = "Parametri non validi";
            }
            showStatus( "error", title, error.message);
        }
        finally {
            setRunning(false);
        }
    }

    function handleNewStratification() {

        clearPersistedStratification();

        state.runId = null;
        state.summary = null;
        state.metadata = null;

        state.geography = null;
        state.geographyRunId = null;
        state.selectedMunicipality = null;
        state.selectedMunicipalityName = null;

        state.lastCompletedDataSource = null;
        state.lastCompletedGeography = null;

        state.csvUploadId = null;
        state.csvCompatibilityReport = null;
        state.dataSource = "synthetic";

        state.filters = {
            search: "",
            baselineLevel: "",
            recommendationStatus: "",
            allocationStatus: "",
            municipality: "",
        };

        if (el.csvFile) {
            el.csvFile.value = "";
        }

        if (el.csvReport) {
            el.csvReport.hidden = true;
            el.csvReport.className = "ph-status";
        }

        if (el.csvReportTitle) {
            el.csvReportTitle.textContent = "";
        }

        if (el.csvReportBody) {
            el.csvReportBody.replaceChildren();
        }

        if (el.dataSourceCsvOption) {
            el.dataSourceCsvOption.disabled = true;
        }

        if (el.dataSource) {
            el.dataSource.value = "synthetic";
        }

        if (el.runDataSource) {
            el.runDataSource.textContent = "—";
        }

        updateDataSourceUi();
        updateMapGeographyProvenance();
        resetSeverity118Preview();

        hidePatientDetail();
        showNewStratificationMode();
        showStatus("success", "Nuova stratificazione", "Configura i parametri e avvia un nuovo run PROMETHEUS.");
    }

    async function handlePatientFilters(event) {
        event.preventDefault();
        if (!state.runId) {
            return;
        }

        state.filters.search = el.filterSearch.value.trim();
        state.filters.baselineLevel = el.filterBaseline.value;
        state.filters.recommendationStatus = el.filterRecommendation.value;
        state.filters.allocationStatus = el.filterAllocation.value;

        try {
            await displayRun(state.runId, 1);
        } catch (error) {
            console.error(error);
            showStatus("error", "Errore durante il filtraggio", error.message);
        }
    }

    async function handleSort(column) {
        if (!state.runId) {return;}
        if (state.sortBy === column) {
            state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
            state.sortBy = column;
            state.sortDirection = "asc";
        }
        updateSortIndicators();
        try {
            await displayRun(state.runId, 1);
        } catch (error) {
            console.error(error);
            showStatus("error", "Errore durante l'ordinamento", error.message);
        }
    }

    async function handlePageSizeChange() {

        if (!state.runId) {return;}
        state.pageSize = Number(el.pageSize.value);
        try {
            await displayRun(state.runId, 1);
        } catch (error) {
            console.error(error);
            showStatus("error", "Errore durante il cambio pagina", error.message);
        }
    }

    function updateSortIndicators() {

        el.sortButtons.forEach(button => {

                const column = button.dataset.phSort;
                const indicator = button.querySelector(".ph-sort-indicator");
                button.classList.toggle("is-active", column === state.sortBy);

                if (!indicator) {return;}

                if (column !== state.sortBy) {
                    indicator.textContent = "";
                    return;
                }

                indicator.textContent = state.sortDirection === "asc" ? "↑" : "↓";
            }
        );
    }

    async function resetPatientFilters() {
        if (!state.runId) {
            return;
        }

        el.filterSearch.value = "";
        el.filterBaseline.value = "";
        el.filterRecommendation.value = "";
        el.filterAllocation.value = "";


        state.filters = {
            search: "",
            baselineLevel: "",
            recommendationStatus: "",
            allocationStatus: "",
            municipality: ""
        };

        state.selectedMunicipality = null;
        state.selectedMunicipalityName =null;
        state.filters.municipality = "";
        if (state.geoJsonLayer) {
            state.geoJsonLayer.setStyle(municipalityPolygonStyle);
        }
        state.municipalityMarkers.forEach(marker => {
                marker.setStyle(municipalityMarkerStyle(   false));
            }
        );

        try {
            await displayRun(state.runId, 1);
        } catch (error) {
            console.error(error);
            showStatus("error", "Errore durante il ripristino", error.message);
        }
    }


    function handleMapMetricChange() {
    state.mapMetric = el.mapMetric.value;
    renderGeographyMap(false);
    }


    // ========================================================
    // PAGINATION
    // ========================================================

    async function changePage(newPage) {

        if (!state.runId || newPage < 1 || newPage > state.totalPages) {
            return;
        }try {
            await displayRun(state.runId, newPage);
        } catch (error) {
            console.error(error);
            showStatus("error", "Errore caricamento pagina", error.message);
        }
    }

    // =======================================================
    // CONFIG
    // ======================================================

    function ensurePopulationHealthMap() {

        if (state.map) {
            state.map.invalidateSize();
            return;
        }


        if (typeof L === "undefined"|| !el.map) {
            throw new Error(
                "Il componente cartografico non è disponibile."
            );
        }
        state.map = L.map(el.map, {zoomControl: true,});

        state.map.on("click", async () => {
        const hadMunicipalityFilter = Boolean(state.filters.municipality);

        state.selectedMunicipality = null;
        state.selectedMunicipalityName = null;
        state.filters.municipality = "";

        if (state.geoJsonLayer) {
            state.geoJsonLayer.setStyle(municipalityPolygonStyle);
        }

        el.municipalityDetail.innerHTML = `
            <div class="ph-municipality-placeholder">
                <strong>Dettaglio territoriale</strong>
                <p>Seleziona un comune sulla mappa per visualizzarne gli indicatori.</p>
            </div>
        `;

        if (hadMunicipalityFilter && state.runId) {
            try {
                await displayRun(state.runId, 1);
            } catch (error) {
                console.error(error);

                showStatus(
                    "error",
                    "Errore durante il ripristino territoriale",
                    error.message
                );
            }
        }
    });


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 18,

            attribution:
                "&copy; OpenStreetMap contributors",
        }
    ).addTo(
        state.map
    );


    state.mapLayer =
        L.layerGroup().addTo(
            state.map
        );
}

    const MAP_METRICS = {
        patient_count: {
            label: "Numero di pazienti",
            getValue: p => Number(p.patient_count || 0),
            min: 0,
            format: v => Number(v).toLocaleString("it-IT"),
        },

        mean_baseline_need: {
            label: "Bisogno assistenziale medio",
            getValue: p => Number(p.mean_baseline_need || 0),
            min: 1,
            max: 6,
            format: v => Number(v).toLocaleString("it-IT", {minimumFractionDigits: 2, maximumFractionDigits: 2}),
        },

        recommendation_rate: {
            label: "Tasso di raccomandazione",
            getValue: p => Number(p.recommendation_rate || 0),
            min: 0,
            max: 1,
            format: v => `${(Number(v) * 100).toLocaleString("it-IT", {maximumFractionDigits: 1})}%`,
        },

        deferred_count: {
            label: "Raccomandazioni rinviate",
            getValue: p => Number(p.deferred_count || 0),
            min: 0,
            format: v => Number(v).toLocaleString("it-IT"),
        },

        deferred_rate_among_recommended: {
            label: "Pressione operativa · tasso di rinvio",
            getValue: p => Number(p.deferred_rate_among_recommended || 0),
            min: 0,
            max: 1,
            format: v => `${(Number(v) * 100).toLocaleString("it-IT", {maximumFractionDigits: 1})}%`,
        },
    };
    const CHOROPLETH_COLORS = [
    "#eff6ff",
    "#bfdbfe",
    "#60a5fa",
    "#2563eb",
    "#1e3a8a",
    ];

    function getMetricDomain(features, metric) {
        const values = features
            .map(feature => metric.getValue(feature.properties || {}))
            .filter(Number.isFinite);

        const min = metric.min ?? 0;
        let max = metric.max ?? Math.max(...values, min + 1);

        if (max <= min) {
            max = min + 1;
        }

        return {min, max};
    }

    function choroplethColor(value, min, max, hasData = true) {
        if (!hasData) {
            return "#e5e7eb";
        }

        const normalized = Math.max(0, Math.min(1, (value - min) / (max - min)));
        const index = Math.min(CHOROPLETH_COLORS.length - 1, Math.floor(normalized * CHOROPLETH_COLORS.length));

        return CHOROPLETH_COLORS[index];
    }

    function municipalityPolygonStyle(feature) {
        const properties = feature.properties || {};
        const metric = MAP_METRICS[state.mapMetric] || MAP_METRICS.patient_count;
        const domain = state.mapDomain || {min: 0, max: 1};

        const value = metric.getValue(properties);
        const selected = state.selectedMunicipalityName === properties.municipality;

        return {
            color: selected ? "#0d6efd" : "#ffffff",
            weight: selected ? 4 : 1.3,
            opacity: 1,

            fillColor: choroplethColor(
                value,
                domain.min,
                domain.max,
                properties.has_population_data !== false
            ),

            fillOpacity: selected ? 0.92 : 0.76,
        };
    }



    function markerRadius(value,maximum) {
    if (maximum <= 0|| value <= 0) {
        return 6;
    }


    const normalized =
        Math.sqrt(
            value / maximum
        );


    return (
        6
        + normalized * 18
    );
}



    // ========================================================
    // INIT
    // ========================================================

    function init() {

        cacheElements();

        if (!el.form) {
            return;
        }

        el.form.addEventListener("submit", handleSubmit);
        el.csvValidateButton?.addEventListener("click", handleCsvValidation);
        el.csvFile?.addEventListener("change", handleCsvFileChange);
        el.patientFilters.addEventListener("submit", handlePatientFilters);
        el.filterReset.addEventListener("click", resetPatientFilters);
        el.prevPage.addEventListener("click", () => changePage(state.page - 1));
        el.nextPage.addEventListener("click", () => changePage(state.page + 1));
        el.detailClose.addEventListener("click", hidePatientDetail);
        el.pageSize.addEventListener("change", handlePageSizeChange);
        el.sortButtons.forEach(button => {button.addEventListener("click", () => handleSort(button.dataset.phSort));});
        el.mapMetric.addEventListener("change", handleMapMetricChange);
        el.dataSource?.addEventListener("change",updateDataSourceUi);

        if (el.newStratificationButton) {
            el.newStratificationButton.addEventListener("click", handleNewStratification);
        }
        if (el.severity118PreviewButton) {
            el.severity118PreviewButton.addEventListener("click",handleSeverity118Preview);
        }
        if (el.severity118Metric) {
            el.severity118Metric.addEventListener("change",resetSeverity118Preview);
        }

        if (el.severity118UsePlanningButton) {
            el.severity118UsePlanningButton.addEventListener("click",handleUseSeverity118InPlanning);
        }
        updateSortIndicators();
        restoreActiveStratification();
        updateDataSourceUi();
        updateMapGeographyProvenance();
    }

    document.addEventListener("DOMContentLoaded", init);
})();

