# -*- coding: utf-8 -*-
"""
build_presidi_dataset_static.py

Versione "config-first": le liste dei COMUNI sono scritte a mano qui sotto.
Modifica liberamente e rilancia per rigenerare i CSV.

Output:
- presidi_attuali.csv
- presidi_potenziali.csv
- presidi_dataset.csv
"""

import argparse
import os
import pandas as pd

# ======= CONFIG: Presìdi ATTUALI (modifica se necessario) =======
PSAUT = ['Cerreto Sannita', 'San Bartolomeo In Galdo']
AUTO_MED = ['Benevento', 'San Marco Dei Cavoti', 'Torrecuso']
AMB_ALS = ['Airola', 'Limatola', 'San Giorgio Del Sannio', 'San Salvatore Telesino']
AMB_ILS = ['Cerreto Sannita', 'Benevento', 'Ginestra Degli Schiavoni', 'Morcone',
           'San Bartolomeo In Galdo', 'Vitulano']

# ======= CONFIG: Comuni POTENZIALI (dalla lista che mi hai passato) =======
POTENZIALI = [
    'Limatola',
    'Castelvetere in Val Fortore',
    'Castelpagano',
    'San Bartolomeo in Galdo',
    'Santa Croce del Sannio',
    'Colle Sannita',
    'Baselice',
    'Sassinoro',
    'Pietraroja',
    'Circello',
    'Foiano di Val Fortore',
    'Morcone',
    'Cusano Mutri',
    'San Marco dei Cavoti',
    'Montefalcone di Val Fortore',
    'Molinara',
    'Faicchio',
    'Pontelandolfo',
    'Campolattaro',
    'San Lupo',
    "Fragneto l'Abate",
    'Reino',
    'Castelfranco in Miscano',
    'San Lorenzello',
    'Guardia Sanframondi',
    'San Giorgio La Molara',
    'Ginestra degli Schiavoni',
    'Casalduni',
    'San Salvatore Telesino',
    'Puglianello',
    'Castelvenere',
    'San Lorenzo Maggiore',
    'Fragneto Monforte',
    'Ponte',
    'Pesco Sannita',
    'Pago Veiano',
    'Amorosi',
    'Telese Terme',
    'Buonalbergo',
    'Paupisi',
    'Pietrelcina',
    'Solopaca',
    'Torrecuso',
    'Vitulano',
    "Sant'Arcangelo Trimonte",
    'Melizzano',
    'Foglianise',
    'Paduli',
    'Benevento',
    'Frasso Telesino',
    'Dugenta',
    'Cautano',
    'Castelpoto',
    'Apice',
    "Sant'Agata de' Goti",
    'Tocco Caudio',
    'Campoli del Monte Taburno',
    'Calvi',
    'Apollosa',
    'Bucciano',
    'San Nicola Manfredi',
    'Moiano',
    'Bonea',
    'San Leucio del Sannio',
    'San Giorgio del Sannio',
    'Montesarchio',
    'Durazzano',
    'Airola',
    'Ceppaloni',
    'San Martino Sannita',
    'San Nazzaro',
    'Arpaia',
    'Paolisi',
    'Forchia',
    "Sant'Angelo a Cupolo",
    'Arpaise',
    'Pannarano'
]


def main(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    rows_att = []
    for c in PSAUT:
        rows_att.append({"comune": c, "tipo_presidio": "PSAUT"})
    for c in AUTO_MED:
        rows_att.append({"comune": c, "tipo_presidio": "AUTO_MED"})
    for c in AMB_ALS:
        rows_att.append({"comune": c, "tipo_presidio": "AMB_ALS"})
    for c in AMB_ILS:
        rows_att.append({"comune": c, "tipo_presidio": "AMB_ILS"})
    df_att = pd.DataFrame(rows_att).drop_duplicates().sort_values(["tipo_presidio", "comune"])

    df_pot = pd.DataFrame({"comune": sorted(set(POTENZIALI))})

    df_all = pd.concat([df_att[["comune"]],
                        df_pot[["comune"]]], ignore_index=True)

    df_att.to_csv(os.path.join(out_dir, "presidi_attuali.csv"), index=False)
    df_pot.to_csv(os.path.join(out_dir, "presidi_potenziali.csv"), index=False)
    df_all.to_csv(os.path.join(out_dir, "comuni.csv"), index=False)

    print(f"[OK] Salvati CSV in: {out_dir}")
    print(f"  - presidi_attuali.csv (n={len(df_att)})")
    print(f"  - presidi_potenziali.csv (n={len(df_pot)})")
    print(f"  - presidi_dataset.csv (n={len(df_all)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="./data")
    args = ap.parse_args()
    main(args.out_dir)
