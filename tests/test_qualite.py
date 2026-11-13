"""Couche qualité : changement d'heure, trous, doublons, échelle, valeur figée, contrôle CAD, mensuel."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.qualite import controles as q
from tests.conftest import pas_attendus, serie_locale


def _types(defauts):
    return {d["type"] for d in defauts}


def test_changement_d_heure_92_et_100_quarts():
    att = pas_attendus("2025-03-29", "2025-04-01")
    assert att["2025-03-30"] == 92 and att["2025-03-29"] == 96
    att_oct = pas_attendus("2025-10-25", "2025-10-28")
    assert att_oct["2025-10-26"] == 100
    df = serie_locale("2025-10-25", "2025-10-28", valeur=lambda i: 1 + 0.1 * np.sin(np.arange(len(i))))
    assert df["t"].is_unique, "l'heure 2 h-3 h existe deux fois, distinguée par son décalage"
    out, defauts = q.controler_pas_fin(df, "T01-EL", att_oct, "essai", 12)
    assert not defauts
    j = q.journalier(out, att_oct)
    assert j["juge"].all() and int(j.set_index("date").loc["2025-10-26", "n_valide"]) == 100


def test_trou_jour_non_juge_et_prorata():
    att = pas_attendus("2025-02-10", "2025-02-13")
    df = serie_locale("2025-02-10", "2025-02-13", valeur=lambda i: 2 + 0.01 * np.arange(len(i)) % 0.7)
    df = df[~((df["date"] == "2025-02-11") & (df["heure"] >= 8))]        # 8 h mesurées sur 24
    df = df[~((df["date"] == "2025-02-12") & (df["heure"] >= 20))]       # 20 h mesurées sur 24
    out, defauts = q.controler_pas_fin(df, "T01-EL", att, "essai", 12)
    assert "pas_manquants" in _types(defauts)
    j = q.journalier(out, att).set_index("date")
    assert not j.loc["2025-02-11", "juge"] and np.isnan(j.loc["2025-02-11", "valeur"])
    assert j.loc["2025-02-12", "juge"]
    assert j.loc["2025-02-12", "valeur"] > j.loc["2025-02-12", "somme"], "jour partiel ramené au prorata, sans interpolation"


def test_doublons_echelle_fige_negatif():
    att = pas_attendus("2025-11-01", "2025-11-06")
    df = serie_locale("2025-11-01", "2025-11-06", valeur=lambda i: 0.6 + 0.2 * np.abs(np.sin(np.arange(len(i)) / 7.0)))
    df.loc[df["date"] == "2025-11-02", "valeur"] *= 1000          # Wh au lieu de kWh
    df.loc[(df["date"] == "2025-11-04") & (df["heure"] < 12), "valeur"] = 0.451
    df.loc[df.index[5], "valeur"] = -1.0
    df = pd.concat([df, df.iloc[[10, 11]]])
    out, defauts = q.controler_pas_fin(df, "T01-EL", att, "essai", 12)
    assert {"doublons", "echelle_ou_pic", "valeur_figee", "valeurs_negatives"} <= _types(defauts)
    ech = next(d for d in defauts if d["type"] == "echelle_ou_pic")
    assert "Wh au lieu de kWh" in ech["detail"] and ech["periodes"] == ["2025-11-02"]
    j = q.journalier(out, att).set_index("date")
    assert not j.loc["2025-11-02", "juge"] and j.loc["2025-11-03", "juge"]


def test_zero_a_midi_sur_site_pv_n_est_pas_un_defaut():
    att = pas_attendus("2025-06-01", "2025-06-04")
    df = serie_locale("2025-06-01", "2025-06-04", valeur=lambda i: np.where((i.hour >= 10) & (i.hour < 16), 0.0, 1.0 + 0.1 * np.cos(np.arange(len(i)))))
    _, defauts = q.controler_pas_fin(df, "T09-EL", att, "essai", 12)
    assert not defauts


def test_controle_physique_cad():
    n = 500
    rng = np.random.default_rng(1)
    cad = pd.DataFrame({"debit_m3_h": rng.uniform(0.5, 4, n), "t_aller_c": rng.uniform(70, 85, n), "t_retour_c": rng.uniform(45, 55, n),
                        "date": pd.date_range("2025-01-01", periods=n, freq="h").strftime("%Y-%m-%d")})
    cad["energie_kwh"] = 1.163 * cad["debit_m3_h"] * (cad["t_aller_c"] - cad["t_retour_c"]) * rng.normal(1, 0.01, n)
    ok, defauts = q.controler_cad(cad, "T01-CAD")
    assert not defauts and ok.all()
    cad.loc[:60, "energie_kwh"] *= 1.4
    ok, defauts = q.controler_cad(cad, "T01-CAD")
    assert _types(defauts) == {"relation_cad"} and (~ok).sum() == 61


def test_mensuel_doublon_manquant_negatif():
    m = pd.DataFrame({"mois": ["2024-01", "2024-02", "2024-02", "2024-03", "2024-04"], "id_compteur": "T01-GZ", "id_site": "T01",
                      "fluide": "gaz", "mesure": "consommation", "valeur": [10.0, 11.0, 11.0, np.nan, -3.0], "unite": "m3",
                      "energie_kwh": np.nan, "qualite": ["mesuré", "mesuré", "mesuré", "manquant", "mesuré"]})
    out, defauts = q.controler_mensuel(m)
    assert {"doublons", "manquant", "valeurs_negatives"} == _types(defauts)
    assert out["utilisable"].tolist() == [True, False, False, False, False]


def test_plages_lisibles():
    assert q.plages(["2025-02-11", "2025-02-12", "2025-02-14"]) == ["2025-02-11 → 2025-02-12", "2025-02-14"]
