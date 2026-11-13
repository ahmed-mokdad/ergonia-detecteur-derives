"""Référence ancrée sur le mensuel v2 de la même année (croisement pas fin ↔ mensuel).

Le Lisez-moi des lots l'énonce : la part normale de chaque série retombe sur le total mensuel v2 ; un écart
net signifie que quelque chose a changé. Ici, le total mensuel v2 est réparti sur les jours du mois selon
le type de jour et la météo du jour (forme apprise sur les mois qui retombent sur la v2). On obtient un
attendu journalier dont la somme mensuelle est exactement la v2 : l'écart est daté au jour près et chiffré
sans hypothèse de saison.

Limite, à dire : dans un parc réel, ce second relevé « normal » n'existe pas ; le total mensuel n'est connu
qu'à la clôture du mois. La date de détection retenue est donc la fin du mois où la règle journalière se déclenche.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from ..config import seuils
from ..modeles.reference import _sigma, ajuster_robuste
from . import cusum


def _centre_relatif(t: pd.DataFrame, col: str, plancher: float) -> np.ndarray:
    moy = t.groupby("mois")[col].transform("mean")
    return ((t[col] - moy) / (moy + plancher)).to_numpy(dtype=float)


def suivre_ancre(t: pd.DataFrame, ref_mensuel: dict, sens: int = 1, params: dict | None = None) -> tuple[pd.DataFrame, list[dict], dict]:
    """t : date, valeur, juge, classe, hdd, ray_kwh, chaud, declare. ref_mensuel : {AAAA-MM: total v2}.

    Rend (table avec attendu, bande, z, etat ; épisodes ; informations sur la référence).
    """
    s = seuils()
    det = dict(s["detection"])
    det.update(params or {})
    tol = s["qualite"]["ecart_v2_net_pct"]
    t = t.copy()
    t["mois"] = t["date"].str.slice(0, 7)
    n = len(t)
    y = t["valeur"].to_numpy(dtype=float)
    ref = t["mois"].map(ref_mensuel).to_numpy(dtype=float)
    jours_mois = t["mois"].map(lambda m: calendar.monthrange(int(m[:4]), int(m[5:7]))[1]).to_numpy(dtype=float)
    base = ref / jours_mois
    declare = t["declare"].ne("").to_numpy() & np.isfinite(y)
    juge = t["juge"].to_numpy(dtype=bool) & np.isfinite(y) & np.isfinite(base) & (base > 0) & ~declare
    classe = t["classe"].to_numpy(dtype=object)
    feats = np.column_stack([_centre_relatif(t, "hdd", 3.0), _centre_relatif(t, "ray_kwh", 0.5), _centre_relatif(t, "chaud", 2.0)])
    bruts = np.column_stack([t[["hdd", "ray_kwh", "chaud"]].to_numpy(dtype=float), np.ones(n)])
    mois = t["mois"].to_numpy()
    # tendance à l'intérieur du mois : interpolation des niveaux mensuels v2 entre milieux de mois.
    # Son poids est appris : proche de 1 si la saison glisse, proche de 0 si le site change par paliers.
    rang = np.arange(n, dtype=float)
    milieux = pd.DataFrame({"m": mois, "r": rang, "b": base}).groupby("m").agg(r=("r", "mean"), b=("b", "first")).dropna()
    if len(milieux) >= 2:
        tendance = np.interp(rang, milieux["r"].to_numpy(), milieux["b"].to_numpy()) / np.where(base > 0, base, np.nan) - 1
        feats = np.column_stack([feats, np.nan_to_num(tendance)])
    else:
        feats = np.column_stack([feats, np.zeros(n)])
    conformes = set(mois)
    att = np.full(n, np.nan)
    ecart_mois = {}
    for _ in range(3):
        idx = np.flatnonzero(juge & np.isin(mois, list(conformes)))
        if len(idx) < 30:
            idx = np.flatnonzero(juge)
        if len(idx) < 30:
            break
        classes = [c for c in sorted(set(classe[idx])) if (classe[idx] == c).sum() >= s["reference"]["jours_min_par_type"]]
        g = idx[np.isin(classe[idx], classes)]
        # un effet météo n'est appris que s'il est actif au moins 40 jours parmi les jours de référence
        # (sinon, appris sur un seul mois, il déformerait la répartition des autres mois)
        cols = [k for k in range(feats.shape[1]) if np.std(feats[g, k]) > 1e-9 and (bruts[g, k] > 0).sum() >= 40]
        ech = {k: float(np.std(feats[g, k])) for k in cols}
        X = np.column_stack([(classe[g] == c).astype(float) for c in classes] + [feats[g, k] / ech[k] for k in cols])
        beta = ajuster_robuste(X, y[g] / base[g], np.r_[np.full(len(classes), 1e-6), np.full(len(cols), 1.0)])
        a = dict(zip(classes, beta[: len(classes)]))
        defaut = float(np.median(beta[: len(classes)]))
        w = np.array([a.get(c, defaut) for c in classe]) + sum(beta[len(classes) + j] * feats[:, k] / ech[k] for j, k in enumerate(cols))
        w = np.clip(w, 0.05, None)
        for m in set(mois):
            dm = mois == m
            if not np.isfinite(ref[dm][0]):
                continue
            hors = dm & declare
            reste = ref[dm][0] - np.nansum(y[hors])
            norm = dm & ~declare
            att[norm] = reste * w[norm] / w[norm].sum() if w[norm].sum() > 0 else np.nan
            att[hors] = y[hors]
            jm = dm & juge
            if jm.sum() >= 5:
                ecart_mois[m] = float(100 * np.sum(y[jm] - att[jm]) / max(np.sum(att[jm]), 1e-9))
        conformes = {m for m, e in ecart_mois.items() if abs(e) < tol}
    res = y - att
    ok = juge & np.isin(mois, list(conformes)) & np.isfinite(att)
    if ok.sum() < 20:
        ok = juge & np.isfinite(att)
    rel = res[ok] / np.maximum(np.abs(att[ok]), 1e-9)
    sigma_rel = max(_sigma(rel), s["reference"]["sigma_plancher_relatif"])
    sigma_abs = 0.25 * _sigma(res[ok])
    sig = np.maximum(sigma_rel * np.abs(att), sigma_abs)
    z = np.where(juge & np.isfinite(att), res / np.maximum(sig, 1e-12), np.nan)
    eps = cusum.episodes(z, y, att, det)
    etat = np.where(declare, "periode_declaree", np.where(np.isfinite(z), "juge", "non_juge")).astype(object)
    dates = t["date"].to_numpy()
    for e in eps:
        etat[e["debut"]: e["fin"] + 1] = np.where(np.isfinite(z[e["debut"]: e["fin"] + 1]), "episode", etat[e["debut"]: e["fin"] + 1])
        e["alerte"] = e["sens"] == sens
        e["detection_modele"] = str(dates[e["detection"]])
        fin_mois = f"{dates[e['detection']][:8]}{calendar.monthrange(int(dates[e['detection']][:4]), int(dates[e['detection']][5:7]))[1]:02d}"
        for cle in ("debut", "detection", "fin"):
            e[cle + "_i"] = int(e[cle])
            e[cle] = str(dates[e[cle]])
        e["detection"] = min(fin_mois, str(dates[-1]))   # le total mensuel n'est connu qu'à la clôture du mois
        e["n_reference"] = int(ok.sum())
    # Sobriété : un épisode journalier n'est retenu que si le total du mois s'écarte nettement de la v2 dans le même sens.
    # Sinon ce n'est qu'une répartition différente à l'intérieur du mois (pont, fin de saison de chauffe…).
    def mois_de(e):
        return sorted(set(mois[e["debut_i"]: e["fin_i"] + 1]))

    for e in eps:
        e["net"] = any(e["sens"] * ecart_mois.get(m, 0.0) >= tol for m in mois_de(e))
        if not e["net"]:
            e["alerte"], e["statut"] = False, "variation interne au mois (non retenue)"
            fen = slice(e["debut_i"], e["fin_i"] + 1)
            etat[fen] = np.where(etat[fen] == "episode", "juge", etat[fen])
    # Une alerte par cause : deux épisodes de même sens sont fusionnés si tous les mois qui les séparent
    # restent en écart net (la dérive n'a pas cessé, seul le bruit du jour l'avait fait refermer).
    nets, fusion = sorted((e for e in eps if e["net"]), key=lambda e: e["debut_i"]), []
    for e in nets:
        p = fusion[-1] if fusion else None
        if p is not None and p["sens"] == e["sens"] and all(e["sens"] * ecart_mois.get(m, 0.0) >= tol for m in set(mois[p["fin_i"]: e["debut_i"] + 1])):
            p.update(fin=e["fin"], fin_i=e["fin_i"], statut=e["statut"])
            fen = slice(p["debut_i"], p["fin_i"] + 1)
            etat[fen] = np.where(np.isfinite(z[fen]), "episode", etat[fen])
        else:
            fusion.append(e)
    eps = fusion + [e for e in eps if not e["net"]]
    # Rattrapage mensuel : au moins deux mois consécutifs d'écart net non couverts par un épisode journalier
    # (dérive lente ou noyée dans le bruit du jour). La datation est alors au mois, et c'est dit.
    liste_mois = sorted(ecart_mois)
    for direction in (1, -1):
        couverts = {m for e in eps if e["net"] and e["sens"] == direction for m in mois_de(e)}
        suite = []
        for m in liste_mois + [None]:
            if m is not None and direction * ecart_mois[m] >= tol and m not in couverts:
                suite.append(m)
                continue
            if len(suite) >= det["mensuel"]["mois_consecutifs"]:
                jm = np.flatnonzero(np.isin(mois, suite) & np.isfinite(z))
                fin_det = np.flatnonzero(mois == suite[det["mensuel"]["mois_consecutifs"] - 1])[-1]
                eps.append(dict(sens=direction, debut=str(dates[jm[0]]), detection=str(dates[fin_det]), fin=str(dates[jm[-1]]),
                                debut_i=int(jm[0]), detection_i=int(fin_det), fin_i=int(jm[-1]), net=True, datation="au mois",
                                statut="en cours" if suite[-1] == liste_mois[-1] else "résorbée", alerte=direction == sens,
                                detection_modele=str(dates[fin_det]), n_reference=int(ok.sum())))
                etat[jm] = "episode"
            suite = []
    eps.sort(key=lambda e: e["debut_i"])
    t["attendu"], t["sigma"], t["z"], t["etat"] = att, sig, z, etat
    t["bas"], t["haut"] = att - 1.96 * sig, att + 1.96 * sig
    info = dict(mois_conformes=sorted(conformes), ecart_mois_pct={m: round(v, 2) for m, v in sorted(ecart_mois.items())},
                sigma_rel=float(sigma_rel), n_jours_reference=int(ok.sum()))
    return t, eps, info
