"""Couche 1 : la référence « attendue » d'un jour, avec sa bande de prédiction.

attendu(jour) = niveau(jour) × effet du type de jour + effets météo

- `niveau` porte ce que l'historique sait déjà : signature de chauffage (base + pente × degrés-jours du jour),
  niveau du même mois des années précédentes (corrigé du mélange école / vacances), ou kWc × rayonnement ×
  ratio de performance historique pour le PV. Sans historique, niveau = 1.
- les effets météo sont appris sur tout le passé disponible (ils ne s'oublient pas d'une saison à l'autre) ;
- l'effet du type de jour est recalé sur la fenêtre récente (les ~90 derniers jours sains), pour suivre le
  niveau réel du bâtiment sans jamais utiliser le futur.
La bande vient des résidus de la fenêtre récente (dispersion robuste), jamais d'une valeur unique.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METEO = ("x_hdd", "x_ray", "x_chaud")


def _sigma(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def ajuster_robuste(X: np.ndarray, y: np.ndarray, penal: np.ndarray, iterations: int = 5) -> np.ndarray:
    """Moindres carrés repondérés (Huber) avec pénalité ridge sur les colonnes météo."""
    w = np.ones(len(y))
    beta = np.zeros(X.shape[1])
    for _ in range(iterations):
        A = X.T @ (w[:, None] * X) + np.diag(penal)
        beta = np.linalg.lstsq(A, X.T @ (w * y), rcond=None)[0]
        res = y - X @ beta
        s = _sigma(res) + 1e-9
        u = np.abs(res) / (1.5 * s)
        w = np.where(u <= 1, 1.0, 1.0 / u)
    return beta


@dataclass
class Reference:
    a: dict                      # effet de chaque type de jour appris
    meteo: list
    centre: dict
    echelle: dict
    beta: np.ndarray
    additif: bool
    indice_mois: np.ndarray | None   # indice saisonnier corrigé du mélange des types de jour (12 valeurs)
    sigma_rel: float
    sigma_abs: float
    n: int
    n_recent: int

    def predire(self, classe: str, niveau: float, mois: int, x: dict) -> tuple[float, float] | None:
        """Rend (attendu, écart-type) pour un jour, ou None si son type de jour n'a pas été appris."""
        niv = self.indice_mois[mois - 1] if self.indice_mois is not None else niveau
        if classe not in self.a or not np.isfinite(niv) or niv <= 0:
            return None
        r = self.a[classe]
        for k, nom in enumerate(self.meteo):
            f = x[nom] / niv if self.additif else x[nom]
            r += self.beta[k] * (f - self.centre[nom]) / self.echelle[nom]
        att = float(niv * r)
        return att, max(self.sigma_rel * abs(att), self.sigma_abs)


def apprendre(y, niveau, mois, classe, x: dict, idx_long, idx_court, jours_min_par_type: int, sigma_plancher: float,
              additif: bool = True, niveau_mois=None, parts=None, parts_classes=None,
              jours_min_chaud: int = 20, ridge: float = 0.5) -> Reference | None:
    """Ajuste la référence. idx_long : tout le passé sain ; idx_court : la fenêtre récente par type de jour."""
    if len(idx_long) == 0:
        return None
    cl = classe[idx_long]
    classes = [c for c in sorted(set(cl)) if (cl == c).sum() >= jours_min_par_type]
    g = idx_long[np.isin(cl, classes)]
    if not classes or len(g) < 2 * len(classes):
        return None
    niv = np.asarray(niveau, dtype=float).copy()
    indice, a_norm = None, None
    correction = parts is not None and niveau_mois is not None
    beta, meteo, centre, echelle = None, [], {}, {}
    for _ in range(4 if correction else 1):
        if correction:
            a_vec = np.array([a_norm.get(c, 1.0) if a_norm else 1.0 for c in parts_classes])
            indice = np.asarray(niveau_mois, dtype=float) / np.maximum(parts @ a_vec, 1e-9)
            niv = indice[mois - 1]
        r = y[g] / niv[g]
        meteo, centre, echelle, cols = [], {}, {}, []
        for nom in METEO:
            f = x[nom][g] / niv[g] if additif else x[nom][g]
            if np.std(f) < 1e-9 or (nom == "x_chaud" and (x[nom][g] > 0).sum() < jours_min_chaud):
                continue
            meteo.append(nom)
            centre[nom], echelle[nom] = float(np.mean(f)), float(np.std(f))
            cols.append((f - centre[nom]) / echelle[nom])
        X = np.column_stack([(classe[g] == c).astype(float) for c in classes] + cols)
        penal = np.r_[np.full(len(classes), 1e-6), np.full(len(meteo), ridge)]
        beta = ajuster_robuste(X, r, penal)
        if correction:
            poids = np.array([parts[:, parts_classes.index(c)].sum() for c in classes])
            moyenne = float(np.sum(poids * beta[: len(classes)]) / max(poids.sum(), 1e-9))
            a_norm = {c: float(beta[k] / moyenne) for k, c in enumerate(classes)} if moyenne > 0 else None
    a = {c: float(beta[k]) for k, c in enumerate(classes)}
    b_meteo = beta[len(classes):]

    def part_meteo(idx):
        tot = np.zeros(len(idx))
        for k, nom in enumerate(meteo):
            f = x[nom][idx] / niv[idx] if additif else x[nom][idx]
            tot += b_meteo[k] * (f - centre[nom]) / echelle[nom]
        return tot

    # recalage des types de jour sur la fenêtre récente
    rc = idx_court[np.isin(classe[idx_court], classes)]
    reste = y[rc] / niv[rc] - part_meteo(rc)
    for c in classes:
        v = reste[classe[rc] == c]
        if len(v) >= min(jours_min_par_type, 5):
            a[c] = float(np.median(v))
    att = niv[rc] * (np.array([a[c] for c in classe[rc]]) + part_meteo(rc))
    res = y[rc] - att
    rel = res / np.maximum(np.abs(att), 1e-9)
    return Reference(a, meteo, centre, echelle, b_meteo, additif, indice,
                     sigma_rel=max(_sigma(rel), sigma_plancher), sigma_abs=0.25 * _sigma(res), n=len(g), n_recent=len(rc))
