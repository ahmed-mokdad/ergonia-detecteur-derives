"""Causes et fiche d'intervention : règles déterministes, et aucun nombre qui ne vienne des faits (anti-hallucination)."""
from __future__ import annotations

import json
import re

from src.causes import moteur


def alerte(**plus) -> dict:
    a = dict(id="T01-EL-2025-04", site="T01", nom_site="Site d'essai", compteur="T01-EL", fluide="électricité", famille="electricite",
             libelle="électricité, compteur général", type="talon_permanent", debut="2025-04-02", detection="2025-04-30", fin="2025-12-31",
             statut="en cours", rang=1, urgence="Élevée", confiance=0.9, ecart_pct=16.8, liens=[],
             pourquoi_pas_normal="Du 2025-04-02 au 2025-12-31, 99 266 kWh mesurés pour 84 986 attendus (+16.8 %) sur 244 jours jugés.",
             constate=dict(quantite=14280.0, unite="kWh", kwh=14280, chf=3856, t_co2_direct=0.0, hypotheses=["électricité 0.27 CHF/kWh"]),
             rythme_mensuel=dict(kwh=1767, chf=477),
             indicateurs=dict(nuit_avant_kw=9.1, nuit_pendant_kw=11.4, jour_avant_kw=19.8, jour_pendant_kw=21.6, part_exces_jours_fermes=0.31,
                              part_jours_fermes=0.33, part_jours_vacances=0.2))
    a.update(plus)
    return a


def test_changement_d_heure_fait_monter_l_horloge():
    a = moteur.proposer(alerte(), [])
    horloge = next(c for c in a["causes"] if "Horloge" in c["cause"])
    assert any("changement d'heure du 2025-03-30" in p for p in horloge["pour"])
    loin = moteur.proposer(alerte(debut="2025-06-10"), [])
    horloge_loin = next(c for c in loin["causes"] if "Horloge" in c["cause"])
    assert horloge_loin["plausibilite"] < horloge["plausibilite"] and horloge_loin["contre"]
    assert [c["plausibilite"] for c in a["causes"]] == sorted((c["plausibilite"] for c in a["causes"]), reverse=True)


def test_chaque_cause_est_une_hypothese_avec_verifications():
    for type_ in moteur.base_de_connaissances():
        a = moteur.proposer(alerte(type=type_), [])
        assert a["causes"] and all(c["verifications"] and c["actions"] and "hypothèse" in c["statut"] for c in a["causes"]), type_
        assert all(0.05 <= c["plausibilite"] <= 0.95 for c in a["causes"])


def test_fluide_lie_renforce_l_hypothese_d_occupation():
    eau = alerte(id="T01-EAU-2025-07", famille="eau", type="ecoulement_permanent", statut="résorbée", debut="2025-07-01", fin="2025-08-20")
    el = alerte(id="T01-EL-2025-07", type="hors_occupation", statut="résorbée", debut="2025-06-30", fin="2025-08-19", liens=["T01-EAU-2025-07"],
                indicateurs=dict(part_exces_jours_fermes=0.9, part_jours_fermes=0.9, part_jours_vacances=0.8))
    a = moteur.proposer(el, [eau, el])
    travaux = next(c for c in a["causes"] if "Travaux" in c["cause"])
    assert any("T01-EAU-2025-07" in p for p in travaux["pour"])


def test_fiche_ne_contient_aucun_nombre_absent_des_faits():
    a = moteur.proposer(alerte(), [])
    fiche = moteur.fiche_markdown(a)
    assert moteur.MENTION in fiche and "sans IA" in fiche
    faits = json.dumps(a, ensure_ascii=False) + " 2026 4.0"          # attributions : millésime et version de licence
    connus = set()
    for n in re.findall(r"\d+(?:[.,]\d+)?", re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", faits)):
        v = float(n.replace(",", "."))
        connus |= {round(v, 3), round(v * 100, 3)}                    # un taux peut être affiché en pourcentage
    texte = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", fiche)                # espaces de milliers
    for n in re.findall(r"\d+(?:[.,]\d+)?", texte):
        v = round(float(n.replace(",", ".")), 3)
        assert v in connus or v <= 3, f"nombre {n} absent des faits fournis"   # 1, 2, 3 : numérotation des causes
