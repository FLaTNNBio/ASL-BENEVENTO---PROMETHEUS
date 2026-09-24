# AmbulanzeASL 

Pianificazione ottima di ambulanze/presìdi su base territoriale con **OR-Tools CP-SAT**, vincoli di **budget**, **medici 24/7**, **PSAUT**, copertura per **codici ROSSO/GIALLO/VERDE/BIANCO** e interfaccia web (`index.html`).

---

## Cos’è

Questo progetto costruisce un **modello di ottimizzazione** che:

* sceglie **quali mezzi attivare/spostare/comprare** e **dove** basarli;
* massimizza la **copertura delle chiamate** entro **soglie di tempo** (per colore);
* rispetta vincoli di **medici disponibili** e **PSAUT** richiesti;
* rispetta un **budget** (CAPEX/OPEX) configurabile;
* esporta CSV e report leggibili dalla dashboard web.

Core: `allocator_cp_sat.py` (modello + CLI).
UI: `index.html` (dashboard) + eventuale `server.py` per lanciare il backend locale.

---

## Requisiti

* Python 3.9+
* Librerie: `ortools`, `numpy`, `pandas`

  ```bash
  pip install ortools numpy pandas
  ```

---

## Struttura dati (cartella `--data-dir`)

File minimi/riconosciuti (CSV):

* `comuni.csv`

  * **comune**
* `od_time_min.csv` (tempi origine→destinazione in minuti)

  * opzione A: **origin_comune**, **dest_comune**, **travel_time_min**
  * opzione B: **from_site_id**, **to_comune**, **time_min** (mappa tramite `sites.csv`)
* Domanda:

  * `weighted_demand_by_comune_code.csv` **oppure** `demand_by_comune_code.csv`
  * colonne: **comune**, **codice_invio**/**codice**, **n_missioni_pesate**/**n_missioni**
* Siti/presìdi (almeno uno fra):

  * `sites.csv` (consigliato)

    * **site_id**, **tipo**, **is_fixed** (0/1), **fixed_commune**
    * opz.: **capex**, **opex** (se non presenti, si usano i valori passati a CLI)
  * `presidi_attuali.csv` (fallback)

    * **comune**, **tipo_presidio**
  * `presidi_potenziali.csv` (fallback)

    * **comune**

**Tipi supportati**: `AUTO_MED`, `AMB_ALS`, `AMB_ILS`, `PSAUT`
(Sinonimi comuni come “AUTOMEDICA”, “ALS”, “ILS”… vengono normalizzati.)

---

## Output (cartella `--out-dir`)

* `chosen_slots.csv` – elenco slot attivi (fissi/esistenti/acquisti), base, costi.
* `coverage_summary.csv` – copertura “ANY” aggregata per codice + totale.
* `uncovered_by_comune_code.csv` – dettagli non coperti (ANY).
* `doctor_coverage_summary.csv` / `doctor_uncovered_by_comune_code.csv` – copertura con **mezzo con medico**.
* `feasibility_report.txt` – riepilogo leggibile delle violazioni (se presenti).
* `feasibility_summary.csv` – metrica numerica violazioni (slack).
* `doctors_summary.txt` – medici richiesti dagli slot attivi.
* `run_summary.csv` – KPI sintetici del run.
* (multi-case/sweep) `cases_summary.csv`.

---

## Come funziona (in breve)

1. **Costruzione slot**

   * Presìdi **fissi** (non disattivabili).
   * Presìdi **esistenti rilocabili**: si creano “famiglie” di cloni (una per possibile base).
   * Presìdi/mezzi **acquistabili**.

2. **Tempi di risposta**

   * Matrice OD (minuti) × **type-speed** per tipo (es. `AUTO_MED=0.90` per velocità/pista prioritaria).

3. **Copertura**

   * Soglie `T` per codice (**ROSSO=8**, **GIALLO=20**, **VERDE=30**, **BIANCO=45** min di default).
   * Modalità **full-coverage**:

     * `strict`: richiede copertura dove c’è domanda (se impossibile, si passa internamente a “feasible-only” per quelle coppie).
     * `feasible-only`: richiede copertura solo dove è tecnicamente raggiungibile.
     * `off`: non impone copertura come vincolo (valutata solo in obiettivo se usi `max_cover_budget`).

4. **Medici / PSAUT**

   * **staff-per-type**: medici 24/7 per slot (es.: `PSAUT=6, AUTO_MED=3, AMB_ALS=3`, ILS=0).
   * **doctors-total**: tetto totale medici.
   * **doctors-budget-mode**:

     * `absolute`: conta **tutti** gli slot attivi (fissi + esistenti + nuovi).
     * `incremental`: solo acquistabili, sottraendo fissi e una clone per famiglia (compat. vecchia).
   * **doctor-cover** + **doctor-codes**: richiedi copertura **con medico** per specifici codici.
   * **psaut-min** / **psaut-exact**: vincoli sul numero di PSAUT attivi.

5. **Budget**

   * `--budget-total`: tetto monetario.
   * `--budget-mode`:

     * `purchase`: considera **solo costi degli acquistabili** (default).
     * `all`: considera costi di **tutti** gli slot attivi (utile se hai OPEX/costi anche per esistenti).

6. **Obiettivo**

   * `min_cost`: minimizza (violazioni pesate + costo).
   * `max_cover_budget`: **massimizza copertura (domanda pesata)** − λ·costo − penalità violazioni.

     > Consigliato se vuoi “sempre massimizzare la copertura entro budget”.

7. **Relax/Slack (sempre attivo)**

   * Ogni vincolo ha una variabile di “sforamento” con pesi configurabili (`--relax-weights COV,DOC,PSAUT,DOCTORS,BUDGET`).
   * Pesi grandi ⇒ il solver preferisce soddisfare i vincoli prima di spendere.

8. **Famiglie che richiedono medico**

   * Opzione `--turnoff-doctor-families` (se implementi la versione “AUTO” come da discussioni):

     * `auto`: spegne automaticamente le famiglie “doctor-capable” quando i medici **non bastano** (compra solo mezzi senza medico, es. ILS).
     * `on`: spegne sempre le famiglie con medico (nessuna clone scelta).
     * `off`: comportamento originale (scegli **esattamente una** clone per famiglia).
   * **Nota importante**: assicurati che il flag arrivi fino a `solve_mip(...)`. Se chiami `run_single_case` dalla CLI, propaga il parametro (vedi “Note d’integrazione” sotto).

---

## Esempi CLI

### 1) Massimizza copertura entro budget (acquisto) — **consigliato**

```bash
python allocator_cp_sat.py ^
  --data-dir "C:\...\dataset\data" ^
  --out-dir "C:\...\runs\run_YYYYMMDD_HHMMSS" ^
  --T ROSSO=8,GIALLO=20,VERDE=30,BIANCO=45 ^
  --type-speed AUTO_MED=0.90,AMB_ALS=0.98,AMB_ILS=1.00,PSAUT=1.00 ^
  --purchase-costs AUTO_MED=500000,AMB_ALS=350000,AMB_ILS=250000,PSAUT=0 ^
  --opex-costs      AUTO_MED=250000,AMB_ALS=200000,AMB_ILS=150000,PSAUT=0 ^
  --bases ATT_POT --limit-bases 0 ^
  --full-coverage strict ^
  --doctor-cover off ^
  --staff-per-type PSAUT=6,AUTO_MED=3,AMB_ALS=3 ^
  --doctors-total 12 --doctors-budget-mode absolute ^
  --psaut-min 2 --psaut-exact 2 ^
  --budget-total 90000000 --budget-mode purchase ^
  --objective max_cover_budget ^
  --turnoff-doctor-families auto ^
  --threads 8 --verbose
```

### 2) Sweep sulla disponibilità medici

```bash
python allocator_cp_sat.py ... ^
  --sweep-doctors-total "0,6,9,12,15"
```

### 3) Multi-scenario da CSV (colonna `label` + eventuali override)

```bash
python allocator_cp_sat.py ... ^
  --cases-csv "C:\...\miei_casi.csv"
```

---

## Dashboard web (`index.html`)

* Puoi aprirla direttamente (doppio click) **oppure** servire la cartella con un server locale:

  ```bash
  # alternativa generica
  python -m http.server 8000
  # poi vai su http://localhost:8000/index.html
  ```
* La UI costruisce e lancia il comando Python (lo vedi loggato in pagina).
* **Per “massimizzare copertura entro budget”** assicurati che l’UI passi:

  * `--objective max_cover_budget`
  * `--budget-total ...` e (di solito) `--budget-mode purchase`
  * `--doctor-cover off` (se vuoi che l’assenza di medici non blocchi la copertura “ANY”)
  * `--turnoff-doctor-families auto` (se hai integrato la modalità AUTO)

> Gli output CSV generati finiscono nella cartella `--out-dir` e la dashboard li legge/visualizza (mappe, tabelle, KPI).

---

## Troubleshooting

* **`[WARN] Nessuna soluzione CP-SAT; esporto fallback...`**
  Cause tipiche:

  * `full-coverage strict` con coppie (comune, codice) **irraggiungibili** (manca OD o basi).
    → Usa `feasible-only` oppure completa `od_time_min.csv`.
  * `doctors-total` troppo basso con `doctor-cover strict` o con vincoli `psaut-exact` stringenti.
    → Aumenta medici, disattiva `doctor-cover` o abilita `turnoff-doctor-families auto`.
  * `budget-total` troppo piccolo.
    → Alza budget o riduci costi.
* **`Manca type-speed per: PSAUT` (WARN)**
  Non blocca: si usa 1.0. Aggiungi `PSAUT=1.00` se vuoi esplicitarlo.
* **`Mancano costi per tipi acquistabili` (ERROR)**
  Aggiungi CAPEX/OPEX mancanti a `--purchase-costs` e `--opex-costs` (es.: includi PSAUT=0 se non si compra).
* **Basi senza OD**
  Log: “Mancano tempi OD per queste basi: …” → completa `od_time_min.csv` per tutte le origini.

---

## Suggerimenti pratici

* Vuoi “comprare ILS se mancano medici”?

  * Metti `AMB_ILS` con **staff 0** in `--staff-per-type` e usa `--turnoff-doctor-families auto` + `doctor-cover off`.
  * L’obiettivo `max_cover_budget` selezionerà ILS finché migliorano la copertura entro budget.
* Vuoi rispettare **rigidamente** il budget/medici?

  * Tieni pesi `BUDGET`/`DOCTORS` molto alti nei `--relax-weights` (comportano penalità enorme sugli sforamenti).
* Performance: aumenta `--threads`, usa `--limit-bases` per scenari di test, e (se opportuno) un `--time-limit-sec`.

---

## Contatti

Per dubbi su dati, vincoli o UI, condividi:

* il comando completo lanciato (copiato dalla dashboard),
* `feasibility_report.txt` e `run_summary.csv`,
* eventuali warning printed (OD mancanti, costi mancanti, ecc.).

Buon lavoro! 🚑
