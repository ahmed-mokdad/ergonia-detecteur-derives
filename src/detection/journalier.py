"""Couche 2 : suivi jour par jour, sans jamais regarder le futur.

Chaque jour jugé est comparé à l'attendu appris sur le passé (réajusté chaque semaine). Les résidus
normalisés alimentent un CUSUM ; une alerte exige un biais cumulé, de la persistance ET un écart relatif
minimal. Tant qu'un épisode est ouvert, la référence est gelée à son début : une dérive qui dure ne
devient pas « normale ». Un jour non jugé est sauté : il ne casse ni ne prolonge une persistance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import seuils
from ..modeles.reference import apprendre

Z_MAX = 6.0  # un seul jour, même extrême, ne peut pas déclencher : il faut de la persistance


def suivre(d: pd.DataFrame, sens: int = 1, params: dict | None = None, modele_cfg: dict | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Suit une série journalière.

    d : colonnes date, valeur, juge, classe, niveau, mois_num, x_hdd, x_ray, x_chaud (une ligne par jour, triée).
    sens : +1 pour alerter sur une hausse (consommations), −1 sur une baisse (production PV).
    modele_cfg : additif, niveau_mois, parts, parts_classes (voir modeles.reference.apprendre).
    Rend la table enrichie (attendu, bas, haut, z, etat) et la liste des épisodes (dans les deux sens).
    """
    s = seuils()
    ref, det = dict(s["reference"]), dict(s["detection"])
    for k_, v_ in (params or {}).items():
        (ref if k_ in ref else det)[k_] = v_
    cfg = modele_cfg or {}
    k, h = det["cusum_k"], det["cusum_h"]
    n = len(d)
    y = d["valeur"].to_numpy(dtype=float)
    juge = d["juge"].to_numpy(dtype=bool) & np.isfinite(y)
    classe = d["classe"].to_numpy(dtype=object)
    niveau = d["niveau"].to_numpy(dtype=float)
    mois = d["mois_num"].to_numpy(dtype=int)
    x = {nom: d[nom].to_numpy(dtype=float) for nom in ("x_hdd", "x_ray", "x_chaud")}
    commun = np.nan_to_num(d["z_commun"].to_numpy(dtype=float)) if "z_commun" in d else np.zeros(n)
    att, sig, z = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    etat = np.where(juge, "apprentissage", "non_juge").astype(object)
    exclu = np.zeros(n, dtype=bool)
    episodes: list[dict] = []
    modele, dernier_ajustement, ouvert, calme, dernier_hors = None, -10**9, None, 0, None
    cumul = {1: 0.0, -1: 0.0}
    depart = {1: None, -1: None}

    def ajuster(i):
        """Référence apprise sur les jours sains strictement avant i."""
        sain = juge & ~exclu
        sain[i:] = False
        idx_long = np.flatnonzero(sain)
        if len(idx_long) < ref["jours_apprentissage_min"]:
            return None
        recents = []
        for c in set(classe[idx_long]):
            jc = idx_long[classe[idx_long] == c]
            fen = jc[jc >= i - ref["fenetre_recente_jours"]]
            recents.append(fen if len(fen) >= ref["jours_min_recents"] else jc[-ref["jours_min_recents"]:])
        idx_court = np.sort(np.concatenate(recents))
        return apprendre(y, niveau, mois, classe, x, idx_long, idx_court, ref["jours_min_par_type"], ref["sigma_plancher_relatif"],
                         additif=cfg.get("additif", True), niveau_mois=cfg.get("niveau_mois"), parts=cfg.get("parts"),
                         parts_classes=cfg.get("parts_classes"))

    def predire(i):
        p = modele.predire(classe[i], niveau[i], mois[i], {nom: x[nom][i] for nom in x})
        if p is None:
            att[i] = sig[i] = z[i] = np.nan
            return False
        att[i], sig[i] = p
        att[i] += commun[i] * sig[i]      # écart partagé le même jour par les compteurs pairs : météo ou saison mal modélisée, pas une dérive
        if juge[i]:
            z[i] = float(np.clip((y[i] - att[i]) / sig[i], -Z_MAX, Z_MAX))
        return juge[i]

    def remettre_a_zero():
        nonlocal cumul, depart, dernier_ajustement
        cumul, depart, dernier_ajustement = {1: 0.0, -1: 0.0}, {1: None, -1: None}, -10**9

    for i in range(n):
        if modele is None or (ouvert is None and i - dernier_ajustement >= ref["reajustement_jours"]):
            nouveau = ajuster(i)
            if nouveau is not None:
                modele, dernier_ajustement = nouveau, i
        if modele is None:
            continue
        if not predire(i):
            if juge[i]:
                etat[i] = "type_de_jour_non_appris"
            continue
        etat[i] = "juge"
        if ouvert is not None:
            exclu[i] = True
            etat[i] = "episode"
            if z[i] * ouvert["sens"] > k:
                calme, dernier_hors = 0, i
            else:
                calme += 1
            a = ouvert["debut"]
            if calme >= det["cloture_jours"]:
                ouvert.update(fin=dernier_hors, statut="résorbée")
                exclu[dernier_hors + 1: i + 1] = False
                etat[dernier_hors + 1: i + 1] = np.where(etat[dernier_hors + 1: i + 1] == "episode", "juge", etat[dernier_hors + 1: i + 1])
                episodes.append(ouvert)
                ouvert = None
                remettre_a_zero()
            elif ouvert["sens"] != sens and juge[a: i + 1].sum() >= det["acceptation_jours"]:
                # repli documenté : un changement de niveau durable dans le sens non surveillé devient la nouvelle référence
                ouvert.update(fin=i, statut="nouveau niveau accepté")
                exclu[a: i + 1] = False
                episodes.append(ouvert)
                ouvert = None
                remettre_a_zero()
            continue
        for direction in (1, -1):
            cumul[direction] = max(0.0, cumul[direction] + direction * z[i] - k)
            if cumul[direction] == 0.0:
                depart[direction] = None
            elif depart[direction] is None:
                depart[direction] = i
        for direction in (1, -1):
            if cumul[direction] <= h:
                continue
            recents = np.flatnonzero(np.isfinite(z[: i + 1]))[-det["persistance_fenetre"]:]
            if (direction * z[recents] > k).sum() < det["persistance_jours"]:
                continue
            a = depart[direction]
            fen = np.arange(a, i + 1)
            fen = fen[np.isfinite(z[fen])]
            ecart_rel = 100 * direction * np.sum(y[fen] - att[fen]) / max(np.sum(np.abs(att[fen])), 1e-9)
            if ecart_rel < det["ecart_relatif_min_pct"]:
                continue
            ouvert = dict(sens=direction, debut=a, detection=i, fin=None, statut="en cours")
            exclu[a: i + 1] = True
            regele = ajuster(a)                      # référence gelée au début de l'épisode
            if regele is not None:
                modele = regele
                for jdx in range(a, i + 1):
                    predire(jdx)
            ouvert["n_reference"] = modele.n_recent
            etat[a: i + 1] = np.where(np.isfinite(z[a: i + 1]), "episode", etat[a: i + 1])
            calme, dernier_hors = 0, i
            break
    if ouvert is not None:
        ouvert["fin"] = int(np.flatnonzero(np.isfinite(z))[-1])
        episodes.append(ouvert)

    out = d.copy()
    out["attendu"], out["sigma"], out["z"], out["etat"] = att, sig, z, etat
    out["bas"], out["haut"] = att - 1.96 * sig, att + 1.96 * sig
    dates = out["date"].to_numpy()
    for e in episodes:
        e["alerte"] = e["sens"] == sens
        for cle in ("debut", "detection", "fin"):
            e[cle + "_i"] = int(e[cle])
            e[cle] = str(dates[e[cle]])
    return out, episodes
