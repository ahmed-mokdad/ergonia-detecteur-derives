"""Le rapprochement v2 ne sert qu'à vérifier après coup : étiquette, chiffrage de contrôle, évaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import pipeline


def _controle(ecart):
    d = pd.date_range("2025-05-01", "2025-06-30").strftime("%Y-%m-%d")
    return dict(ecart=ecart, table=pd.DataFrame({"date": d, "valeur": 110.0, "attendu": 100.0, "z": 2.0}))


def _alerte(**k):
    return {**dict(id="T01-EL-2025-05", compteur="T01-EL", debut="2025-05-01", fin="2025-06-30", detection="2025-05-12", ecart_pct=10.0,
                   constate=dict(chf=100)), **k}


def test_confirme_non_confirme_et_sans_second_releve():
    ok = pipeline._confirmer(_alerte(), 1, _controle({"2025-05": 9.8, "2025-06": 10.1}), "electricite", {}, None, 3.0)
    assert ok["confirme"] and ok["statut"] == "confirmé par le rapprochement mensuel" and ok["chiffrage_de_controle"]["kwh"] == 610
    non = pipeline._confirmer(_alerte(), 1, _controle({"2025-05": 0.2, "2025-06": -0.1}), "electricite", {}, None, 3.0)
    assert non["confirme"] is False and "fausse alerte" in non["detail"]
    assert pipeline._confirmer(_alerte(), -1, _controle({"2025-05": 9.8}), "electricite", {}, None, 3.0)["confirme"] is False, "le sens doit concorder"
    assert pipeline._confirmer(_alerte(), 1, None, "cad_retour", {}, None, 3.0)["confirme"] is None


def test_evaluation_du_moteur_autonome_contre_la_verite_de_controle():
    verite = [dict(serie="T01-EL", fluide="electricite", debut="2025-05-01", fin="2025-06-30", statut="résorbée", datation="au jour", ecart_pct=10.0),
              dict(serie="T02-EL", fluide="electricite", debut="2025-11-01", fin="2025-12-31", statut="en cours", datation="au mois", ecart_pct=7.0)]
    alertes = [_alerte(rapprochement_v2=dict(confirme=True)),
               _alerte(id="T03-GZ-2025-10", compteur="T03-GZ", debut="2025-10-06", fin="2025-11-16", rapprochement_v2=dict(confirme=False)),
               _alerte(id="T04-CAD-RETOUR-2025-10", compteur="T04-CAD-RETOUR", rapprochement_v2=dict(confirme=None))]
    ev = pipeline.evaluer_autonome(alertes, verite, {"T01-EL", "T02-EL", "T03-GZ"})
    assert ev["trouvees"] == 1 and [x["serie"] for x in ev["manquees"]] == ["T02-EL"]
    assert ev["n_alertes"] == 2 and [f["id"] for f in ev["fausses_alertes"]] == ["T03-GZ-2025-10"]
    assert ev["precision"] == 0.5 and ev["rappel"] == 0.5 and ev["delai_median_jours"] == 11
    md = pipeline.evaluation_markdown(ev)
    assert "vérité de contrôle" in md and "**non**" in md and "T03-GZ-2025-10" in md


def test_un_ecart_partage_par_les_pairs_n_est_pas_une_derive(rng):
    """Reprise de chauffe mal modélisée : tous les compteurs montent ensemble. Seul celui qui monte plus que ses pairs est une dérive."""
    from src.detection.series import SerieJour

    d = pd.date_range("2025-01-01", "2025-12-31", freq="D")

    def serie(nom, propre):
        v = 100 + rng.normal(0, 3, len(d))
        v[270:] *= 1.20                                   # écart commun aux pairs à partir du jour 270
        v[300:] *= 1 + propre
        t = pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "valeur": v, "juge": True, "classe": "tous_les_jours", "niveau": 1.0, "mois_num": d.month,
                          "x_hdd": 0.0, "x_ray": 0.0, "x_chaud": 0.0, "ray_kwh": 3.0})
        return SerieJour(nom, nom[:3], "gaz", "m3", nom, t, cfg={"additif": False})

    series = [serie(f"T0{k}-GZ", 0.30 if k == 1 else 0.0) for k in range(1, 8)]
    communs = pipeline.mode_commun(series)
    assert communs["T02-GZ"][285] > 2, "l'écart commun est vu chez les pairs"
    par = {**pipeline.seuils()["detection"]["autonome"]}
    alertes = {s.id: [e for e in pipeline.suivre(s.table.assign(z_commun=communs[s.id]), 1, par, s.cfg)[1] if e["alerte"]] for s in series}
    assert alertes["T01-GZ"] and abs(alertes["T01-GZ"][0]["debut_i"] - 300) <= 10
    assert sum(1 for k, v in alertes.items() if k != "T01-GZ" and v) <= 1, "l'écart commun ne lève pas d'alerte sur les pairs"
    sans = sum(1 for s in series if [e for e in pipeline.suivre(s.table, 1, par, s.cfg)[1] if e["alerte"]])
    assert sans >= 5, "sans la comparaison aux pairs, presque tous les compteurs seraient en alerte"


def test_le_detecteur_ne_recoit_pas_le_mensuel_de_l_annee():
    import inspect

    from src.detection import journalier
    from src.modeles import reference

    for module in (journalier, reference):
        assert "ref_v2" not in inspect.getsource(module) and "ancre" not in inspect.getsource(module)
    assert np.isfinite(1.0)
