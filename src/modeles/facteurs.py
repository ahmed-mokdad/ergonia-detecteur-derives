"""Facteurs explicatifs d'un jour : calendrier, usage, météo, niveau historique du même mois, périodes déclarées."""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from ..config import charger_yaml

TYPOLOGIES_ECOLE = ("École primaire", "École avec piscine")


def classe_jour(type_jour: str, jour: str, vacances: bool, ecole: bool) -> str:
    """Type de jour au sens de l'usage : c'est lui qui porte horaires, week-ends, fériés et vacances."""
    if type_jour in ("dimanche", "férié"):
        return "dimanche_ferie"
    if type_jour == "samedi":
        return "samedi"
    if vacances:
        return "ouvre_vacances"
    if ecole and jour == "mercredi":
        return "mercredi_parascolaire"
    return "ouvre"


def table_jours(calendrier: pd.DataFrame, site: str, typologie: str) -> pd.DataFrame:
    """Une ligne par jour de 2025 : classe d'usage, météo du jour, période déclarée."""
    ecole = typologie in TYPOLOGIES_ECOLE
    j = calendrier[["date", "jour", "type", "vacances", "t_moy", "ray"]].copy()
    j["classe"] = [classe_jour(t, d, v, ecole) for t, d, v in zip(j["type"], j["jour"], j["vacances"])]
    j["hdd"] = np.where(j["t_moy"] < 12, 20 - j["t_moy"], 0.0)           # degrés-jours 20/12 (SIA 381/3), comme Ref_Climat
    j["chaud"] = np.clip(j["t_moy"] - 18, 0, None)
    j["ray_kwh"] = j["ray"] * 24 / 1000                                   # W/m2 moyens -> kWh/m2 par jour
    j["mois_num"] = j["date"].str.slice(5, 7).astype(int)
    j["declare"] = ""
    for p in charger_yaml("periodes_declarees").get(site, []) or []:
        j.loc[(j["date"] >= p["debut"]) & (j["date"] <= p["fin"]), "declare"] = p["motif"]
    return j


def normales_mensuelles(climat: pd.DataFrame, annees=("2021", "2022", "2023", "2024")) -> pd.DataFrame:
    """DJ et rayonnement par jour, moyennes 2021-2024 du même mois : la météo « habituelle » de l'historique."""
    c = climat[climat["mois"].str.slice(0, 4).isin(annees)].copy()
    c["mois_num"] = c["mois"].str.slice(5, 7).astype(int)
    c["jours"] = [calendar.monthrange(int(m[:4]), int(m[5:7]))[1] for m in c["mois"]]
    c["hdd_j"] = c["degres_jours_20_12"] / c["jours"]
    c["ray_j"] = c["rayonnement_kwh_m2"] / c["jours"]
    return c.groupby("mois_num")[["hdd_j", "ray_j"]].mean()


VECTEURS = {  # vecteurs des installations dont un changement rompt la référence d'un fluide
    "electricite": ("électricité", "soleil"),
    "pv": ("soleil",),
    "gaz": ("gaz",),
    "cad": ("chaleur à distance",),
    "chaleur_pac": ("électricité",),
    "eau": (),
}


def dernier_evenement(installations: pd.DataFrame, compteurs: pd.DataFrame, batiments: pd.DataFrame, site: str, ids: list[str],
                      fluide: str = "electricite") -> str:
    """Dernier événement structurel connu qui concerne ce fluide (mise en service, retrait, ouverture, début de compteur) : AAAA-MM."""
    dates = ["2020-12"]
    i = installations[(installations["id_site"] == site) & installations["vecteur"].isin(VECTEURS.get(fluide, ()))]
    dates += [d for d in list(i["mise_en_service"]) + list(i["retrait"]) if d and d >= "2021-01"]
    c = compteurs[compteurs["id_compteur"].isin(ids)]
    dates += [d for d in c["debut"] if d and d >= "2021-01"]
    b = batiments[batiments["id_site"] == site]
    dates += [d for d in b["ouverture"] if d and d >= "2021-01"]
    return max(dates)


def niveau_historique(mesures: pd.DataFrame, composantes: list[tuple[str, int]], depuis: str, jusqu_a: str = "2024-12"):
    """Niveau moyen par jour du même mois, années précédentes (médiane), après le dernier événement structurel.

    composantes : [(id_compteur, signe)] ; ex. consommation d'un site PV = EL (+1), PV (+1), EL-INJ (−1).
    Rend (série indexée par mois 1..12, liste des années utilisées) ou (None, []) si un mois manque.
    """
    total = None
    for cpt, signe in composantes:
        m = mesures[(mesures["id_compteur"] == cpt) & mesures["utilisable"]].set_index("mois")["valeur"] * signe
        total = m if total is None else total.add(m, fill_value=np.nan)
    if total is None:
        return None, []
    total = total[(total.index > depuis) & (total.index <= jusqu_a)].dropna()
    if total.empty:
        return None, []
    df = total.to_frame("v")
    df["an"] = df.index.str.slice(0, 4)
    df["mois_num"] = df.index.str.slice(5, 7).astype(int)
    df["par_jour"] = [v / calendar.monthrange(int(a), m)[1] for v, a, m in zip(df["v"], df["an"], df["mois_num"])]
    niveau = df.groupby("mois_num")["par_jour"].median()
    if len(niveau) < 12 or (niveau <= 0).any():
        return None, []
    return niveau, sorted(df["an"].unique())


def signature_chauffage(mesures: pd.DataFrame, climat: pd.DataFrame, compteur: str, depuis: str, jusqu_a: str = "2024-12",
                        mois_min: int = 6, r2_min: float = 0.6):
    """Signature énergétique mensuelle (type IPMVP option C, 2 paramètres) : valeur/jour = base + pente × DJ/jour.

    Ajustée (robuste) sur le mensuel v2 après le dernier événement connu et jusqu'à fin 2024.
    Rend dict(base, pente, r2, n, periode) ou None si l'historique est trop court ou la relation trop faible.
    """
    from .reference import ajuster_robuste

    m = mesures[(mesures["id_compteur"] == compteur) & mesures["utilisable"] & (mesures["mois"] > depuis) & (mesures["mois"] <= jusqu_a)]
    m = m.merge(climat[["mois", "degres_jours_20_12"]], on="mois")
    if len(m) < mois_min:
        return None
    jours = np.array([calendar.monthrange(int(x[:4]), int(x[5:7]))[1] for x in m["mois"]])
    yj, dj = m["valeur"].to_numpy(dtype=float) / jours, m["degres_jours_20_12"].to_numpy(dtype=float) / jours
    if np.ptp(dj) < 5:
        return None
    X = np.column_stack([np.ones(len(dj)), dj])
    beta = ajuster_robuste(X, yj, np.array([1e-9, 1e-9]))
    res = yj - X @ beta
    r2 = 1 - np.sum(res ** 2) / max(np.sum((yj - yj.mean()) ** 2), 1e-9)
    base, pente = float(max(beta[0], 0.02 * yj.mean())), float(beta[1])
    if pente <= 0 or r2 < r2_min:
        return None
    return dict(base=base, pente=pente, r2=float(r2), n=len(m), periode=f"{m['mois'].min()} à {m['mois'].max()}")


def ratio_performance_historique(mesures: pd.DataFrame, climat: pd.DataFrame, compteur: str, kwc: float, depuis: str, jusqu_a: str = "2024-12"):
    """Ratio de performance PV par mois calendaire : production / (kWc × rayonnement), médiane des années précédentes."""
    m = mesures[(mesures["id_compteur"] == compteur) & mesures["utilisable"] & (mesures["mois"] > depuis) & (mesures["mois"] <= jusqu_a)]
    m = m.merge(climat[["mois", "rayonnement_kwh_m2"]], on="mois")
    if m.empty:
        return None, []
    m = m.assign(pr=m["valeur"] / (kwc * m["rayonnement_kwh_m2"]), mois_num=m["mois"].str.slice(5, 7).astype(int))
    pr = m.groupby("mois_num")["pr"].median()
    if len(pr) < 12 or (pr <= 0).any():
        return None, []
    return pr, sorted(m["mois"].str.slice(0, 4).unique())
