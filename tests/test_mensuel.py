"""Rejeu mensuel autonome : la météo explique un mois froid, une dérive persistante est levée, passé seulement."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.detection.mensuel import suivre_mensuel


def cinq_ans(rng) -> pd.DataFrame:
    mois = pd.period_range("2021-01", "2025-12", freq="M").astype(str)
    k = np.arange(len(mois))
    dj = np.clip(9 + 9 * np.cos(2 * np.pi * k / 12) + rng.normal(0, 1.2, len(mois)), 0, None)
    y = (30 + 12 * dj) * np.exp(rng.normal(0, 0.03, len(mois)))
    return pd.DataFrame({"mois": mois, "y": y, "x": dj, "utilisable": True})


def test_un_mois_froid_n_est_pas_une_derive(rng):
    df = cinq_ans(rng)
    i = int(np.flatnonzero(df["mois"] == "2025-10")[0])
    df.loc[i, "x"] += 6.0                                   # octobre nettement plus froid que d'habitude
    df.loc[i, "y"] = (30 + 12 * df.loc[i, "x"]) * 1.01
    table, eps = suivre_mensuel(df, 1)
    assert eps == [] and abs(table.loc[i, "z"]) < 2
    meme_mois = df[(df["mois"].str.endswith("-10")) & (df["mois"] < "2025")]["y"].median()
    assert df.loc[i, "y"] / meme_mois > 1.3, "une médiane saisonnière aurait crié"


def test_derive_persistante_levee_sans_regarder_le_futur(rng):
    df = cinq_ans(rng)
    i = int(np.flatnonzero(df["mois"] == "2024-11")[0])
    df.loc[i:, "y"] *= 1.25
    table, eps = suivre_mensuel(df, 1)
    assert len(eps) == 1 and eps[0]["debut"] == i and eps[0]["detection"] == i + 1 and eps[0]["statut"] == "en cours"
    avant, _ = suivre_mensuel(df.iloc[: i + 1], 1)
    assert np.allclose(avant["attendu"].iloc[: i + 1], table["attendu"].iloc[: i + 1], equal_nan=True), "l'attendu d'un mois ne dépend pas des mois suivants"
    assert np.isnan(table["z"].iloc[:24]).all(), "pas de jugement avant 24 mois d'apprentissage"


def test_un_seul_mois_hors_bande_ne_suffit_pas(rng):
    df = cinq_ans(rng)
    i = int(np.flatnonzero(df["mois"] == "2024-01")[0])
    df.loc[i, "y"] *= 1.4
    assert suivre_mensuel(df, 1)[1] == []
