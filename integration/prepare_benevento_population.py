from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


# ============================================================
# PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ISTAT_FILE = (
    PROJECT_ROOT
    / "integration"
    / "Data"
    / "Population"
    / "ISTAT_2025_Benevento"
    / "POSAS_2025_it_062_Benevento.csv"
)

AMBULANZE_DATA_DIR = (
    PROJECT_ROOT
    / "Ambulanze-main"
    / "AmbulanzeASL"
    / "dataset"
    / "data"
)

COMUNI_FILE = (
    AMBULANZE_DATA_DIR
    / "comuni.csv"
)

OUTPUT_FILE = (
    AMBULANZE_DATA_DIR
    / "population_by_comune.csv"
)


# ============================================================
# NORMALIZZAZIONE
# ============================================================

def normalize_comune(value: str) -> str:
    """
    Normalizzazione usata solo per confrontare i nomi
    tra ISTAT e dataset Ambulanze.
    """

    text = str(value).strip()
    text = (text.replace("’", "'").replace("`", "'"))
    text = re.sub( r"\s+", " ", text,)
    return text.casefold()

# ============================================================
# LOAD ISTAT
# ============================================================


def load_istat_population() -> pd.DataFrame:

    if not ISTAT_FILE.exists():
        raise FileNotFoundError(f"File ISTAT non trovato: {ISTAT_FILE}")

    # L'intestazione reale è la seconda riga.
    df = pd.read_csv(ISTAT_FILE, sep=";", encoding="utf-8-sig", skiprows=1, dtype={"Codice comune": "string", }, )
    required = {"Codice comune", "Comune", "Età", "Totale", }
    missing = (required - set(df.columns))

    if missing:
        raise ValueError("Colonne ISTAT mancanti: " + ", ".join(sorted(missing)))

    df["Totale"] = pd.to_numeric(df["Totale"], errors="coerce", ).fillna(0)


    # POPOLAZIONE RESIDENTE TOTALE
    # Nel file ISTAT:
    # - età 0..100 = dettaglio per singola età
    # - età 999 = totale ufficiale del comune

    total_rows = df[pd.to_numeric(df["Età"], errors="coerce", ) == 999].copy()
    if total_rows.empty:
        raise ValueError("Nel file ISTAT non sono state trovate le righe con Età = 999.")

    # Deve esserci esattamente una riga totale per comune.
    duplicates = total_rows.duplicated(subset=["Codice comune"], keep=False, )
    if duplicates.any():
        problematic = (total_rows.loc[duplicates, ["Codice comune", "Comune", "Età", "Totale", ], ])
        raise ValueError("Sono presenti più righe Età=999 per lo stesso comune:\n"+ problematic.to_string(index=False))

    population = (total_rows[["Codice comune", "Comune", "Totale", ]].rename(columns={"Codice comune": "istat_code", "Comune": "comune", "Totale": "resident_population", }).copy())
    population["resident_population"] = (pd.to_numeric(population["resident_population"], errors="coerce", ))
    if population["resident_population"].isna().any():
        raise ValueError("Sono presenti valori di popolazione non numerici nelle righe ISTAT Età=999.")
    population["resident_population"] = (population["resident_population"].round().astype(int))
    population["_comune_key"] = (population["comune"].map(normalize_comune))
    return population

# ============================================================
# LOAD COMUNI PIATTAFORMA 118
# ============================================================

def load_ambulance_communes() -> pd.DataFrame:

    if not COMUNI_FILE.exists():
        raise FileNotFoundError(f"File comuni non trovato: {COMUNI_FILE}")

    df = pd.read_csv(COMUNI_FILE)
    if "comune" not in df.columns:
        raise ValueError("comuni.csv deve contenere la colonna 'comune'.")

    out = pd.DataFrame({"comune": (df["comune"].astype(str).str.strip())})
    out["_comune_key"] = (out["comune"].map(normalize_comune))

    # comuni.csv contiene 82 righe grezze,ma alcuni comuni compaiono più volte.
    # la chiave normalizzata identifica il comune rale
    duplicated = out[out.duplicated("_comune_key",keep=False,)].sort_values("_comune_key")

    if not duplicated.empty:

        print("\n[INFO] Duplicati trovati in comuni.csv:")
        for key, group in duplicated.groupby("_comune_key"):
            names = (group["comune"].drop_duplicates().tolist())
            print(f" - {key}: {names}")

    # Una sola riga per comune reale.
    out = (out.drop_duplicates(subset="_comune_key", keep="first",).reset_index(drop=True))
    return out
# ============================================================
# VALIDAZIONE + EXPORT
# ============================================================

def main():

    istat = load_istat_population()
    ambulance = load_ambulance_communes()
    EXPECTED_MUNICIPALITIES = 78

    if len(istat) != EXPECTED_MUNICIPALITIES:
        raise SystemExit(f"ISTAT: attesi {EXPECTED_MUNICIPALITIES} comuni, trovati {len(istat)}.")

    if len(ambulance) != EXPECTED_MUNICIPALITIES:
        raise SystemExit(
            f"Piattaforma 118: attesi {EXPECTED_MUNICIPALITIES} comuni dopo la deduplicazione, trovati {len(ambulance)}.")
    print(f"[INFO] Comuni ISTAT: {len(istat)}")
    print(f"[INFO] Comuni piattaforma 118: {len(ambulance)}")

    merged = ambulance.merge(istat[["_comune_key", "istat_code", "resident_population", ]], on="_comune_key", how="left", validate="one_to_one", )
    missing = merged[merged["resident_population"].isna()]

    if not missing.empty:
        print("\n[ERRORE] Comuni 118 senzacorrispondenza ISTAT:")
        for comune in missing["comune"]:
            print(f" - {comune}")
        raise SystemExit("Join ISTAT ↔ Ambulanze incompleto.")

    # --------------------------------------------------------
    # Controllo inverso:
    # comuni ISTAT non presenti nella piattaforma.
    # --------------------------------------------------------

    ambulance_keys = set(ambulance["_comune_key"])
    extra_istat = istat[~istat["_comune_key"].isin(ambulance_keys)]

    if not extra_istat.empty:
        print("\n[WARNING] Comuni ISTAT non presenti in comuni.csv:")
        for comune in extra_istat["comune"]:
            print(f" - {comune}")

    output = merged[["comune", "istat_code", "resident_population", ]].copy()
    output["resident_population"] = output["resident_population"].astype(int)
    output = output.sort_values("comune").reset_index(drop=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True,)
    output.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig", )

    print()
    print(f"[OK] Salvato: {OUTPUT_FILE}")
    print(f"[OK] Comuni esportati: {len(output)}")
    print(f"[OK] Popolazione totale provincia: {output['resident_population'].sum():,}".replace(",", "."))

    print()
    print(output.head(10).to_string(index=False))

if __name__ == "__main__":
    main()