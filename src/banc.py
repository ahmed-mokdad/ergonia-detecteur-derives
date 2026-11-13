"""Banc d'essai court : `python -m src.banc` écrit outputs/evaluation.md.

Pas d'évaluation circulaire : les scénarios partent des séries RÉELLES jugées saines (bruit, usages et saison
réels) sur lesquelles on superpose des perturbations de formes variées, sans loi commune avec le moteur.
Trois références sont comparées sur les mêmes scénarios : naïve (médiane du même mois 2021-2024), autonome
(historique + météo, passé seulement) et ancrée (mensuel v2 de l'année réparti au jour).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DOSSIER_SORTIES
from .connecteurs import creer_connecteur
from .detection.ancre import suivre_ancre
from .detection.journalier import suivre
from .detection.series import preparer

DUREE = 60
SCENARIOS = {"marche +10 %": ("marche", 0.10), "marche +20 %": ("marche", 0.20), "rampe 0 → +25 %": ("rampe", 0.25),
             "intermittente (week-ends +50 %)": ("weekend", 0.50), "saisonnière (jours froids +25 %)": ("froid", 0.25)}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def perturber(t: pd.DataFrame, forme: str, amplitude: float, debut: int, sens: int) -> pd.DataFrame:
    t = t.copy()
    fen = np.zeros(len(t), dtype=bool)
    fen[debut: debut + DUREE] = True
    f = np.zeros(len(t))
    if forme == "marche":
        f[fen] = amplitude
    elif forme == "rampe":
        f[fen] = amplitude * np.linspace(0, 1, fen.sum())
    elif forme == "weekend":
        f[fen & t["classe"].isin(["samedi", "dimanche_ferie"]).to_numpy()] = amplitude
    elif forme == "froid":
        f[fen & (t["hdd"] > 0).to_numpy()] = amplitude
    t["valeur"] = t["valeur"] * (1 + sens * f)
    return t


def naif(t: pd.DataFrame, historique: pd.Series, sens: int, seuil: float = 0.10) -> list[tuple[int, int]]:
    """Référence naïve : un mois est anormal s'il dépasse de 10 % la médiane du même mois 2021-2024, deux mois de suite."""
    m = t.groupby(t["date"].str.slice(0, 7))["valeur"].sum()
    ecart = pd.Series({k: sens * (v / historique.get(int(k[5:7]), np.nan) - 1) for k, v in m.items()})
    hors = (ecart > seuil).to_numpy()
    out, mois = [], list(m.index)
    for i in range(1, len(mois)):
        if hors[i] and hors[i - 1]:
            idx = np.flatnonzero(t["date"].str.slice(0, 7).isin([mois[i - 1], mois[i]]).to_numpy())
            out.append((int(idx[0]), int(idx[-1])))
    return out


def main(tirages: int = 3, graine: int = 2026) -> None:
    rng = np.random.default_rng(graine)
    jeu = creer_connecteur().jeu()
    series, _, mesures_ok = preparer(jeu)
    saines = []
    for s in series:
        if not s.ref_v2 or s.fluide == "injection":
            continue
        _, eps, info = suivre_ancre(s.table, s.ref_v2, s.sens, s.params)
        if not [e for e in eps if e["net"]] and all(abs(v) < 3 for v in info["ecart_mois_pct"].values()):
            saines.append(s)

    def historique(s):
        m = mesures_ok[(mesures_ok["id_compteur"] == s.id) & mesures_ok["utilisable"] & (mesures_ok["mois"] < "2025")]
        return m.groupby(m["mois"].str.slice(5, 7).astype(int))["valeur"].median()

    def intervalles(nom, s, t):
        if nom == "naïve":
            return naif(t, historique(s), s.sens), None
        if nom == "autonome":
            _, eps = suivre(t, s.sens, s.params, s.cfg)
            return [(e["debut_i"], e["fin_i"]) for e in eps if e["alerte"]], [e["detection_i"] for e in eps if e["alerte"]]
        _, eps, _ = suivre_ancre(t, s.ref_v2, s.sens, s.params)
        al = [e for e in eps if e["alerte"]]
        return [(e["debut_i"], e["fin_i"]) for e in al], [int(np.flatnonzero(t["date"].to_numpy() == e["detection_modele"])[0]) for e in al]

    moteurs = ("naïve", "autonome", "ancrée")
    fausses = {nom: sum(1 for s in saines if intervalles(nom, s, s.table)[0]) for nom in moteurs}
    lignes, total = [], {nom: [0, 0, 0, []] for nom in moteurs}
    for libelle, (forme, amp) in SCENARIOS.items():
        res = {nom: [0, 0, 0, []] for nom in moteurs}            # détectés, essais, alertes hors fenêtre, délais
        for s in saines:
            if forme == "froid" and s.fluide not in ("gaz", "cad", "chaleur_pac"):
                continue
            for _ in range(tirages):
                debut = int(rng.integers(150 if forme == "froid" else 60, 240)) if forme != "froid" else int(rng.integers(270, 300))
                t = perturber(s.table, forme, amp, debut, s.sens)
                for nom in moteurs:
                    inter, det = intervalles(nom, s, t)
                    touche = [k for k, (a, b) in enumerate(inter) if a <= debut + DUREE + 14 and b >= debut]
                    res[nom][1] += 1
                    res[nom][0] += bool(touche)
                    res[nom][2] += len(inter) - len(touche)
                    if touche and det:
                        res[nom][3].append(det[touche[0]] - debut)
        for nom in moteurs:
            k, n, hors, delais = res[nom]
            for j in range(3):
                total[nom][j] += res[nom][j]
            total[nom][3] += delais
            bas, haut = wilson(k, n)
            lignes.append(f"| {libelle} | {nom} | {k}/{n} | {100 * k / max(n, 1):.0f} % [{100 * bas:.0f} ; {100 * haut:.0f}] | {hors} | "
                          + (f"{np.median(delais):.0f} j" if delais else "au mois" if nom == "naïve" and k else "—") + " |")
    synth = []
    for nom in moteurs:
        k, n, hors, delais = total[nom]
        bas, haut = wilson(k, n)
        fp = hors + 0
        precision = k / max(k + fp, 1)
        rappel = k / max(n, 1)
        f1 = 2 * precision * rappel / max(precision + rappel, 1e-9)
        synth.append(f"| {nom} | {fausses[nom]} sur {len(saines)} | {100 * rappel:.0f} % [{100 * bas:.0f} ; {100 * haut:.0f}] | {100 * precision:.0f} % | {f1:.2f} | "
                     + (f"{np.median(delais):.0f} j" if delais else "au mois") + " |")
    texte = "\n".join([
        "# Évaluation (banc d'essai court)", "",
        f"Généré par `python -m src.banc` (graine {graine}, {tirages} tirages par série et par scénario). Tous les chiffres sortent du code.", "",
        f"**Matériau** : {len(saines)} séries réelles de Rive-Claire jugées saines ({', '.join(s.id for s in saines)}). "
        f"Chaque scénario superpose une perturbation de {DUREE} jours à une date tirée au hasard. Pour la référence ancrée, le mensuel v2 n'est pas modifié : "
        "il joue le rôle de la « part normale ».", "",
        "## Synthèse", "",
        "| Référence | Séries saines avec au moins une alerte (sans perturbation) | Rappel [Wilson 95 %] | Précision sur les scénarios | F1 | Délai médian |",
        "|---|---|---|---|---|---|", *synth, "",
        "Précision = dérives injectées retrouvées / (retrouvées + alertes hors de la fenêtre injectée). Délai = du début injecté au jour où la règle journalière se déclenche "
        "(pour la référence ancrée, le total mensuel n'est connu qu'à la clôture du mois : compter jusqu'à un mois de plus).", "",
        "## Par scénario", "",
        "| Scénario | Référence | Détectées | Rappel [Wilson 95 %] | Alertes hors fenêtre | Délai médian |", "|---|---|---|---|---|---|", *lignes, "",
        "## Ce que ce banc ne dit pas", "",
        "- Les séries « saines » sont celles où la référence ancrée se tait : son zéro fausse alerte sans perturbation est acquis par construction, pas démontré. "
        "Il faudrait des séries saines désignées par un tiers.",
        "- La référence ancrée dispose d'un second relevé « normal » de l'année ; les deux autres non. La comparaison montre ce qu'apporte ce second relevé, "
        "pas une supériorité de méthode à information égale.",
        "- Un délai négatif signifie que l'alerte comptée existait avant la perturbation : c'est une fausse alerte qui recouvre la fenêtre, et le rappel "
        "de la référence concernée est alors surestimé.",
        "- Un score de 100 % ici ne vaut pas preuve : il tient au second relevé et au choix des séries, voir les deux points ci-dessus.",
        "- Perturbations multiplicatives de 60 jours seulement ; pas d'essai de lacunes, de bruit amplifié ni d'historique court.",
        "- La précision sur un parc réel n'est pas mesurable ici.", ""])
    DOSSIER_SORTIES.mkdir(exist_ok=True)
    (DOSSIER_SORTIES / "evaluation_banc.md").write_text(texte.replace("# Évaluation (banc d'essai court)", "## Banc d'essai synthétique court"), encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main()
