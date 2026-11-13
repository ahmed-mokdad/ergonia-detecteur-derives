"""CUSUM avec persistance et double seuil, commun aux détecteurs journaliers.

Règle d'alerte : biais cumulé (CUSUM > h) ET persistance (k jours hors tolérance sur les n derniers jugés)
ET écart relatif cumulé minimal. Un jour non jugé (z non défini) est sauté. Un pic isolé ne déclenche jamais.
"""
from __future__ import annotations

import numpy as np

Z_MAX = 6.0


def episodes(z: np.ndarray, y: np.ndarray, att: np.ndarray, det: dict) -> list[dict]:
    """Parcourt la série dans l'ordre du temps et rend les épisodes (indices début, détection, fin ; sens ±1)."""
    k, h = det["cusum_k"], det["cusum_h"]
    z = np.clip(z, -Z_MAX, Z_MAX)
    juges = np.flatnonzero(np.isfinite(z))
    out, ouvert, calme, dernier_hors = [], None, 0, None
    cumul, depart = {1: 0.0, -1: 0.0}, {1: None, -1: None}
    for pos, i in enumerate(juges):
        if ouvert is not None:
            if z[i] * ouvert["sens"] > k:
                calme, dernier_hors = 0, i
            else:
                calme += 1
            # clôture : 14 jours jugés revenus dans la tolérance, ou 14 jours dont l'écart cumulé est retombé
            # sous la moitié du seuil relatif (le bruit d'un jour ne doit pas maintenir un épisode ouvert)
            fen = juges[max(0, pos + 1 - det["cloture_jours"]): pos + 1]
            if fen[0] > ouvert["detection"]:
                rel = 100 * ouvert["sens"] * np.sum(y[fen] - att[fen]) / max(np.sum(np.abs(att[fen])), 1e-9)
                if rel < det["ecart_relatif_min_pct"] / 2:
                    avant = juges[juges < fen[0]]
                    dernier_hors, calme = int(avant[-1]), det["cloture_jours"]
            if calme >= det["cloture_jours"]:
                ouvert.update(fin=int(dernier_hors), statut="résorbée")
                out.append(ouvert)
                ouvert, cumul, depart = None, {1: 0.0, -1: 0.0}, {1: None, -1: None}
            continue
        for s in (1, -1):
            cumul[s] = max(0.0, cumul[s] + s * z[i] - k)
            if cumul[s] == 0.0:
                depart[s] = None
            elif depart[s] is None:
                depart[s] = i
        for s in (1, -1):
            if cumul[s] <= h:
                continue
            recents = juges[max(0, pos + 1 - det["persistance_fenetre"]): pos + 1]
            if (s * z[recents] > k).sum() < det["persistance_jours"]:
                continue
            fen = juges[(juges >= depart[s]) & (juges <= i)]
            # début le plus probable : point de rupture d'un saut de moyenne, estimé avec les seuls jours déjà connus
            zs = s * z[fen]
            c = np.cumsum(zs - zs.mean() / 2)
            j = int(np.argmin(c))
            if c[j] < 0 and j + 1 < len(fen):
                fen = fen[j + 1:]
            if len(fen) < det["persistance_jours"]:
                continue                         # pas encore assez de jours jugés depuis le début estimé : on attend
            if 100 * s * np.sum(y[fen] - att[fen]) / max(np.sum(np.abs(att[fen])), 1e-9) < det["ecart_relatif_min_pct"]:
                continue
            ouvert = dict(sens=s, debut=int(fen[0]), detection=int(i), fin=None, statut="en cours")
            calme, dernier_hors = 0, i
            break
    if ouvert is not None:
        ouvert["fin"] = int(juges[-1])
        out.append(ouvert)
    return out
