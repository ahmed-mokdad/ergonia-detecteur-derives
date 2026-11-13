"""Fixtures synthétiques générées par le code : aucun fichier de données dans le dépôt."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


def serie_locale(debut: str, fin: str, freq: str = "15min", valeur=1.0, compteur: str = "T01-EL") -> pd.DataFrame:
    """Série synthétique en heure légale suisse, au format texte des jeux (décalage +01:00 / +02:00)."""
    idx = pd.date_range(debut, fin, freq=freq, tz="Europe/Zurich", inclusive="left")
    txt = idx.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d\d)(\d\d)$", r"\1:\2", regex=True)
    v = valeur(idx) if callable(valeur) else np.full(len(idx), float(valeur))
    return pd.DataFrame({"t": txt, "utc": idx.tz_convert("UTC"), "date": txt.str.slice(0, 10),
                         "heure": idx.hour, "id_compteur": compteur, "id_site": compteur.split("-")[0], "valeur": v})


def pas_attendus(debut: str, fin: str, freq: str = "15min") -> dict:
    idx = pd.date_range(debut, fin, freq=freq, tz="Europe/Zurich", inclusive="left")
    return pd.Series(1, index=idx.strftime("%Y-%m-%d")).groupby(level=0).sum().to_dict()


@pytest.fixture
def rng():
    return np.random.default_rng(42)
