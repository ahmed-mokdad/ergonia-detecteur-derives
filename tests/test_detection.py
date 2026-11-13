"""Détection et chiffrage sur séries synthétiques générées par le code (aucune donnée du jeu)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import seuils
from src.detection import cusum
from src.detection.ancre import suivre_ancre
from src.detection.journalier import suivre
from src.impact import chiffrage


def annee_synthetique(rng, niveau=100.0, bruit=0.05) -> pd.DataFrame:
    """Un an de jours : week-ends plus bas, saison marquée, bruit multiplicatif. Lois volontairement simples et distinctes du moteur."""
    d = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    j = np.arange(len(d))
    t_moy = 11 - 9 * np.cos(2 * np.pi * (j - 15) / 365) + rng.normal(0, 2.5, len(d))
    classe = np.where(d.day_of_week == 6, "dimanche_ferie", np.where(d.day_of_week == 5, "samedi", "ouvre"))
    forme = np.where(classe == "ouvre", 1.0, 0.55)
    saison = 1 + 0.35 * np.cos(2 * np.pi * (j - 20) / 365) ** 3
    v = niveau * forme * saison * np.exp(rng.normal(0, bruit, len(d)))
    return pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "valeur": v, "juge": True, "classe": classe, "t_moy": t_moy,
                         "hdd": np.where(t_moy < 12, 20 - t_moy, 0.0), "ray_kwh": 3 + 2 * np.sin(2 * np.pi * (j - 80) / 365),
                         "chaud": np.clip(t_moy - 18, 0, None), "declare": "", "mois_num": d.month})


def ref_mensuelle(t: pd.DataFrame) -> dict:
    return t.groupby(t["date"].str.slice(0, 7))["valeur"].sum().to_dict()


def test_cusum_un_pic_isole_ne_declenche_pas():
    det = seuils()["detection"]
    z = np.zeros(120)
    z[60] = 50.0
    assert cusum.episodes(z, np.ones(120) * 2, np.ones(120), det) == []


def test_cusum_derive_persistante_et_jours_non_juges_sautes():
    det = seuils()["detection"]
    z = np.zeros(200)
    att = np.full(200, 100.0)
    z[100:160] = 3.0
    y = att + z * 5
    z[110:115] = np.nan                       # jours non jugés : ni cassent ni prolongent
    eps = cusum.episodes(z, y, att, det)
    assert len(eps) == 1 and eps[0]["sens"] == 1
    assert eps[0]["debut"] == 100 and eps[0]["detection"] > 100 and eps[0]["statut"] == "résorbée"
    assert 155 <= eps[0]["fin"] <= 160


def test_ancre_serie_saine_se_tait(rng):
    t = annee_synthetique(rng)
    _, eps, info = suivre_ancre(t, ref_mensuelle(t))
    assert [e for e in eps if e["net"]] == []
    assert len(info["mois_conformes"]) == 12


def test_ancre_retrouve_date_et_chiffre_une_derive(rng):
    t = annee_synthetique(rng)
    ref = ref_mensuelle(t)                    # la part « normale »
    derive = (t["date"] >= "2025-06-10") & (t["date"] <= "2025-08-20")
    ajoute = float((t.loc[derive, "valeur"] * 0.20).sum())
    t.loc[derive, "valeur"] *= 1.20
    table, eps, _ = suivre_ancre(t, ref)
    alertes = [e for e in eps if e["alerte"]]
    assert len(alertes) == 1
    e = alertes[0]
    assert abs((pd.Timestamp(e["debut"]) - pd.Timestamp("2025-06-10")).days) <= 7
    assert e["detection"] >= e["detection_modele"] and e["detection"].endswith(("30", "31")), "détection à la clôture du mois"
    assert e["statut"] == "résorbée"
    ch = chiffrage.chiffrer(table, e, "electricite", {})
    assert 0.8 * ajoute <= ch["constate"]["kwh"] <= 1.1 * ajoute
    assert ch["constate"]["au_moins"] and ch["projection_12_mois"]["dans_le_score"] is False
    assert ch["constate"]["borne_prudente"]["kwh"] <= ch["constate"]["kwh"]


def test_ancre_decalage_interne_au_mois_n_est_pas_une_alerte(rng):
    t = annee_synthetique(rng, bruit=0.03)
    ref = ref_mensuelle(t)
    a = (t["date"] >= "2025-05-01") & (t["date"] <= "2025-05-15")
    b = (t["date"] >= "2025-05-16") & (t["date"] <= "2025-05-31")
    surplus = float((t.loc[a, "valeur"] * 0.25).sum())
    t.loc[a, "valeur"] *= 1.25
    t.loc[b, "valeur"] -= surplus / b.sum()   # même total mensuel : seule la répartition change
    _, eps, _ = suivre_ancre(t, ref)
    assert not [e for e in eps if e["alerte"]]


def test_ancre_derive_lente_rattrapee_au_mois(rng):
    t = annee_synthetique(rng, bruit=0.12)
    ref = ref_mensuelle(t)
    t.loc[t["date"] >= "2025-09-01", "valeur"] *= 1.06     # +6 % noyé dans 12 % de bruit journalier
    _, eps, info = suivre_ancre(t, ref)
    alertes = [e for e in eps if e["alerte"]]
    assert alertes and alertes[0]["debut"] <= "2025-10-01" and alertes[-1]["statut"] == "en cours"


def test_ancre_baisse_de_production_pv(rng):
    t = annee_synthetique(rng)
    t["classe"] = "tous_les_jours"
    ref = ref_mensuelle(t)
    t.loc[(t["date"] >= "2025-05-20") & (t["date"] <= "2025-09-15"), "valeur"] *= 0.6
    table, eps, _ = suivre_ancre(t, ref, sens=-1)
    al = [e for e in eps if e["alerte"]]
    assert len(al) == 1 and al[0]["sens"] == -1
    ch = chiffrage.chiffrer(table, al[0], "pv", {})
    assert ch["constate"]["kwh"] > 0, "une perte de production est comptée positivement"


def test_jours_en_defaut_ne_font_pas_d_alerte(rng):
    t = annee_synthetique(rng)
    ref = ref_mensuelle(t)
    trou = (t["date"] >= "2025-03-05") & (t["date"] <= "2025-03-20")
    t.loc[trou, "valeur"] *= 1000             # défaut d'échelle : écarté par la couche qualité
    t.loc[trou, "juge"] = False
    _, eps, _ = suivre_ancre(t, ref)
    assert not [e for e in eps if e["net"]]


def test_moteur_autonome_reference_gelee(rng):
    """Sans seconde source (retour CAD) : passé seulement, et la référence ne suit pas la dérive."""
    d = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    v = 50 + rng.normal(0, 1.0, len(d))
    v[300:] += 8.0
    t = pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "valeur": v, "juge": True, "classe": "tous_les_jours", "niveau": 1.0,
                      "mois_num": d.month, "x_hdd": rng.normal(5, 1, len(d)), "x_ray": 0.0, "x_chaud": 0.0})
    table, eps = suivre(t, 1, {"ecart_relatif_min_pct": 8.0}, {"additif": False})
    al = [e for e in eps if e["alerte"]]
    assert len(al) == 1 and abs(al[0]["debut_i"] - 300) <= 3 and al[0]["statut"] == "en cours"
    assert al[0]["detection"] > al[0]["debut"], "la détection ne précède jamais le début"
    assert abs(table["attendu"].iloc[-1] - 50) < 1.0, "référence gelée au début de l'épisode"


def test_chiffrage_gaz_eau_et_plancher():
    dates = pd.date_range("2025-11-01", periods=30).strftime("%Y-%m-%d")
    table = pd.DataFrame({"date": dates, "valeur": 110.0, "attendu": 100.0, "bas": 95.0, "haut": 105.0, "z": 2.0})
    e = dict(debut_i=0, fin_i=29, sens=1)
    gaz = chiffrage.chiffrer(table, e, "gaz", {"2025-11": 11.0})
    assert gaz["constate"]["quantite"] == 300 and gaz["constate"]["kwh"] == 3300          # m3 x PCS du mois
    assert abs(gaz["constate"]["t_co2_direct"] - 300 * 2.086 / 1000) < 1e-3
    eau = chiffrage.chiffrer(table, e, "eau", {})
    elec = chiffrage.chiffrer(table, e, "electricite", {})
    # le jeu ne donne de prix que pour l'électricité : gaz et eau sont « non chiffrés », jamais un prix inventé
    assert gaz["constate"]["chf"] is None and gaz["urgence"] == "Non chiffrée" and gaz["priorite"] is None and not gaz["masquee"]
    assert any("non chiffré" in h for h in gaz["constate"]["hypotheses"])
    assert eau["risque_sinistre"] and eau["constate"]["kwh"] == 0 and eau["constate"]["chf"] is None and eau["constate"]["quantite"] == 300
    assert not eau["masquee"]
    assert elec["rythme_mensuel"]["kwh"] == 300 and elec["constate"]["t_co2_direct"] == 0 and elec["constate"]["chf"] == 81   # 300 kWh x 0,27
    petit = table.assign(valeur=100.5)
    assert chiffrage.chiffrer(petit, e, "electricite", {})["masquee"], "sous le plancher en CHF par mois, l'alerte est masquée"
