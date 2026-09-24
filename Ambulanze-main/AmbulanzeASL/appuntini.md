# Riassunto dei documenti che abbiamo a disposizione
## Tempi lea regioni tablet 
  - Il documento introduce e inquadra l’indicatore NSG D09Z “Intervallo Allarme-Target dei mezzi di soccorso”, che misura il tempo tra l’inizio della chiamata al 118 e l’arrivo del primo mezzo sul luogo; obiettivo ≤ 21 minuti
  - Forte disomogeneità tra centrali operative: una quota dal 3% all’81% delle comunicazioni del tempo di arrivo avviene per telefono (anziché via tablet) e ciò aumenta di ~2 minuti il tempo rilevato. La Regione dispone quindi che tutte le trasmissioni avvengano via tablet e che tutti i mezzi ne siano dotati.
  - L’allegato riporta tabelle 2022–2023 con tempi REALI, SIMULATI, TABLET e TELEFONICI per Regione e per ciascuna Centrale (Avellino, Benevento, Caserta, Napoli, Napoli Est, Napoli Ovest, Salerno) con numero di interventi. Esempio 2023 (Campania): Reale 20:09; Simulato 19:35; Tablet 19:42; Telefonica 21:33 su 53.908 interventi. 
  - Esempi per centrale 2023: Napoli Ovest Tablet 15:51 vs Telefonica 17:36; Napoli Est Tablet 21:41 vs Telefonica 23:19; Salerno Tablet 20:52 vs Telefonica 22:08.
## Rete UOC 118
- **Che cos’è:** elenco ufficiale della rete UOC 118 ed Emergenza dell’ASL Benevento, con recapiti e indirizzi di tutte le postazioni operative: Centrale Operativa (COT 118), CMR, PSAUT, Auto Mediche, Ambulanze medicalizzate e infermieristiche. Data: 13/01/2025. 
- **Cosa contiene di utile per te**: nomi delle sedi e indirizzi puntuali (base per geocoding e analisi di copertura); distingue le tipologie di mezzo/presidio (utile per vincoli di capacità/skill mix).


## Come usarli per l’ottimizzazione delle sedi SAUT
A seconda dell’obiettivo operativo, puoi formulare due classici modelli di localizzazione:
- Maximal Coverage Location Problem (MCLP) (massimizza la quota coperta entro 21’):
- Considera coperta una zona se il tempo stimato ≤ 21 minuti (coerente con D09Z).
- Ottimo quando il KPI principale è rispettare il target NSG.

## Parere su impiego di automedica nel SET 118
- Automedica baricentrica: collocare un’equipe medico–infermieristica in posizione baricentrica rispetto a più postazioni con ambulanze senza medico (assetto India/Victor) per garantire rapidamente il livello avanzato di cura (assetto Mike). Può arrivare prima o subito dopo l’ambulanza e subentrare nella gestione del paziente. 
- Riduzione dei trasporti (codici gialli): nella loro esperienza, il trattamento tempestivo sul posto consente in una quota 30–40% dei casi di lasciare il paziente a domicilio (niente trasporto). 
- Più veloce e agile dell’ambulanza: soprattutto con traffico, strade strette o viabilità tortuosa.
- Uso ottimale dei medici: soluzione utile con carenza di organico medico (consente di “spalmare” l’equipe medico–infermieristica su più richieste). 
- Raccomandazione operativa: automediche H24, medico+infermiere, baricentriche rispetto ad aree coperte in prima battuta da ambulanze assetto India. 




certo! ecco “MCLP” spiegato in modo pratico, con cosa serve, come si modella e come si risolve.

# Cos’è il MCLP

**MCLP = Maximal Covering Location Problem** (Church & ReVelle).
Dato un insieme di **punti di domanda** (es. comuni) e un insieme di **siti candidati** (postazioni), vuoi scegliere al massimo **p** siti in modo da **massimizzare la domanda coperta** entro una **soglia di tempo** (T) (es. 21 minuti).

In parole semplici: “con un numero limitato di basi, dove le metto per coprire più popolazione/chiamate possibili in T minuti?”.

# Dati in ingresso tipici

* **Domanda** per punto (j): quante chiamate attese/pesate (w_j) (puoi pesare ROSSO>GIALLO>VERDE>BIANCO).
* **Siti candidati** (i) (posizioni possibili).
* **Tempi** o distanze (d_{ij}) tra sito (i) e punto (j).
* **Soglia** (T) (coperto se (d_{ij} \le T)).
* **Budget** (p) (quanti siti attivabili).

# Formulazione (versione classica)

Costruisci la matrice di copertura (a_{ij} = 1) se (d_{ij}\le T), altrimenti 0.

Variabili:

* (x_i \in {0,1}): apro il sito (i)?
* (z_j \in {0,1}): il punto (j) è coperto da almeno un sito aperto?

Obiettivo:
[
\max \sum_{j} w_j, z_j
]
Vincoli:
[
\sum_{i: a_{ij}=1} x_i ;\ge; z_j \quad \forall j
]
[
\sum_{i} x_i \le p,\qquad x_i, z_j \in {0,1}
]

# Che “tipo” di problema è

È un **problema di ottimizzazione combinatoria** su grafi, **NP-hard**.
Traduzione: non esiste (in generale) un algoritmo veloce che garantisca la soluzione ottima per istanze grandi; si usano:

* **Metodi esatti (MILP)**: risolto come **programmazione lineare intera** (branch-and-bound/branch-and-cut). Ottimo garantito ma più lento al crescere di (|I|,|J|).
* **Euristiche/metaeuristiche**: più veloci, trovano soluzioni molto buone:

  * **Greedy** (aggiungi il sito col maggior guadagno residuo),
  * **Local search / swap** (prova a sostituire un sito per migliorare),
  * **GRASP, Tabu, Simulated Annealing, Genetic**, ecc.

# Il greedy (quello che stai usando)

Idea: costruisci la soluzione passo-passo.

1. Calcola, per ogni sito (i), quali comuni copre (entro (T)).
2. Inizia con insieme selezionato vuoto e tutta la domanda “scoperta”.
3. **Itera (p) volte**: scegli il sito che aggiunge più domanda nuova (non coperta finora), aggiungilo; segna i comuni coperti come “coperti”.
4. Stop: hai (p) siti e una copertura totale.

### Pro e contro del greedy

* **Pro**: semplice, molto veloce, spesso dà soluzioni vicine all’ottimo.
* **Contro**: non garantisce l’ottimo; può “fossilizzarsi” su scelte iniziali non perfette (si migliora con una fase di **swap** finale).

### Complessità (indicativa)

* Costruire la mappa di copertura: (O(|I||J|)).
* Greedy puro: (O(p,|I|,|J|)) se valuti il guadagno da zero ogni volta.
  (Si ottimizza con strutture bitset/aggiornamenti incrementali.)

# Confronto con altri modelli

* **p-Median**: minimizza il **tempo medio/pesato** verso la base più vicina (non usa soglia (T)).
* **p-Center**: minimizza il **massimo** tempo al peggiore punto (logica “minimax”).
* **MCLP**: massimizza **quanta domanda sta sotto (T)** (coerente con KPI tipo LEA ≤ 21’).

# Varianti utili nell’emergenza sanitaria

* **Backup/MEXCLP**: considera la **probabilità che un mezzo sia occupato** (busy fraction) e massimizza la **copertura attesa** con ridondanze (2°, 3° mezzo).
* **Capacitated**: limiti di carico/numero interventi per sito.
* **Multi-periodo**: replica per fasce orarie e cerca un assetto **robusto** o uno per turno.
* **Tipi di mezzo**: tempi diversi per **AMB** vs **AUTO_MED** (auto medica spesso più rapida); pesi diversi per codici.
* **Penalità oltre soglia**: se vuoi “non buttare” la domanda oltre (T), usa una funzione obiettivo che penalizza gli sforamenti invece del taglio secco.

# Come leggere i tuoi output

* **Selected sites**: la lista dei siti scelti (ordine = contributo marginale).
* **Covered fraction**: quota di domanda **pesata** coperta (0–1).
* **Coverage report**: per comune, domanda totale, coperto sì/no, **gap** (domanda rimasta fuori).

# Consigli pratici

* **T** realistico: deve riflettere il KPI che misuri (es. LEA 21’ corretti dal bias telefono).
* **Pesi**: dai più peso a ROSSO/GIALLO per spingere copertura critica.
* **Distanze**: usa **tempi di viaggio** (non distanza euclidea), con fattore stradale/congestione.
* **Validazione**: confronta la soluzione greedy con un **MILP** su istanze ridotte: ti dà un’idea del **gap**.
* **Swap** finale: dopo il greedy, prova qualche scambio sito-dentro/sito-fuori: spesso migliora la copertura.

Se vuoi, posso aggiungere al tuo runner una **fase di miglioramento “1-swap”** (post-greedy) e un flag `--reopt-swaps` per spremere qualche punto percentuale in più di copertura.



https://github.com/GIScience/openrouteservice-py


conda activate ninonino
cd C:\Users\aless\Desktop\Ambulanze\AmbulanzeASL\dataset

# dipendenze base
conda install -c conda-forge pandas openpyxl xlrd requests

# variabili comode
$SRC  = "C:\Users\aless\Desktop\Ambulanze\AmbulanzeASL\documenti_segretii"   # dove stanno gli Excel
$DATA = "C:\Users\aless\Desktop\Ambulanze\AmbulanzeASL\dataset\data"         # output

python .\build_presidi_dataset.py `
  --out-dir "$DATA"


python .\od_matrices_builder.py `
  --data-dir "$DATA" `
  --osrm-url http://router.project-osrm.org


python .\simulate_demand_and_severity.py `
  --comuni-csv "$DATA\comuni.csv" `
  --out-dir    "$DATA" `
  --seed 118 `
  --total-missions 20000



numero massimo di mezzi 
esempio di algoritmo: con cui copro tutte le areee
un caso in cui non riesco a soddisfare le cose e compra dei mezzi 
quando viene daniele un altra call, idea della dashboard 

