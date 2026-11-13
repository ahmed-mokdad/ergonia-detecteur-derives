"""Prépare les séries journalières à suivre, fluide par fluide, à partir du jeu et de la couche qualité.

Règles physiques appliquées ici :
- site avec PV : consommation = soutirage + production − injection (le soutirage nul à midi est normal) ;
- un sous-compteur est compris dans son parent : seul le compteur général est suivi au pas fin ;
- CAD : seules les heures qui respectent énergie ≈ 1,163 × débit × ΔT comptent ;
- gaz suivi en m³ (converti en kWh PCS avec le facteur du mois au moment du chiffrage).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import seuils
from ..modeles import facteurs as F
from ..qualite import controles as Q

SITES_PV = {"S09": 100.0, "S26": 150.0, "S32": 200.0}


@dataclass
class SerieJour:
    id: str
    site: str
    fluide: str            # electricite | gaz | eau | cad | cad_retour | pv | chaleur_pac
    unite: str
    libelle: str
    table: pd.DataFrame    # une ligne par jour, prête pour detection.journalier.suivre
    sens: int = 1
    reference: str = ""
    facteurs: list = field(default_factory=list)
    pas: pd.DataFrame | None = None        # pas fin valide (électricité) pour caractériser un épisode
    rapprochement: pd.DataFrame | None = None
    extra: dict = field(default_factory=dict)
    ref_v2: dict = field(default_factory=dict)     # total mensuel v2 2025 du même périmètre
    cfg: dict = field(default_factory=dict)        # configuration du modèle de référence
    params: dict = field(default_factory=dict)     # seuils propres à la série (documentés dans METHODS.md)


def _typologie(jeu, site: str) -> str:
    b = jeu.batiments[jeu.batiments["id_site"] == site]
    return b["typologie"].iloc[0] if len(b) else ""


def _nom_site(jeu, site: str) -> str:
    b = jeu.batiments[jeu.batiments["id_site"] == site]
    return b["nom_site"].iloc[0] if len(b) else site


def _assembler(jeu, mesures_ok, normales, site, jour: pd.DataFrame, composantes, fluide: str) -> tuple[pd.DataFrame, str, list, dict]:
    """Ajoute calendrier, météo et niveau historique à une table journalière (date, valeur, juge).

    Rend (table, mode de référence, facteurs pris en compte, configuration du modèle).
    """
    t = F.table_jours(jeu.calendrier, site, _typologie(jeu, site)).merge(jour[["date", "valeur", "juge"]], on="date", how="left")
    t["juge"] = t["juge"].fillna(False).astype(bool) & t["declare"].eq("")
    ids = [c for c, _ in composantes]
    depuis = F.dernier_evenement(jeu.installations, jeu.compteurs, jeu.batiments, site, ids, fluide)
    evt = "" if depuis < "2021-01" else f", après le dernier événement connu ({depuis})"
    facteurs = ["type de jour : ouvré, mercredi parascolaire, samedi, dimanche/férié, vacances scolaires"]
    cfg: dict = {"additif": True}
    t["x_ray"] = t["ray_kwh"] - t["mois_num"].map(normales["ray_j"])
    sig = F.signature_chauffage(mesures_ok, jeu.climat, ids[0], depuis) if fluide in ("gaz", "cad", "chaleur_pac") else None
    niveau, annees = (None, []) if sig else F.niveau_historique(mesures_ok, composantes, depuis)
    if sig:
        t["niveau"] = sig["base"] + sig["pente"] * t["hdd"]
        t["x_hdd"], t["x_chaud"] = 0.0, 0.0
        reference = f"signature_mensuelle_DJ({sig['periode']})+fenetre_recente_2025"
        facteurs += [f"signature de chauffage du mensuel v2 ({sig['periode']}{evt}) : base {sig['base']:.3g} + {sig['pente']:.3g} par degré-jour, R² {sig['r2']:.2f}",
                     "degrés-jours 20/12 du jour (MétéoSuisse Cointrin)", "rayonnement du jour (apports solaires)"]
        cfg["signature"] = sig
    elif niveau is not None:
        classes = sorted(t["classe"].unique())
        parts = pd.crosstab(t["mois_num"], t["classe"], normalize="index").reindex(index=range(1, 13), columns=classes).fillna(0.0).to_numpy()
        cfg.update(niveau_mois=niveau.reindex(range(1, 13)).to_numpy(), parts=parts, parts_classes=classes)
        t["niveau"] = t["mois_num"].map(niveau)
        t["x_hdd"] = t["hdd"] - t["mois_num"].map(normales["hdd_j"])
        t["x_chaud"] = t["chaud"]
        reference = f"meme_mois_annees_precedentes({annees[0]}-{annees[-1]})+fenetre_recente_2025"
        facteurs += [f"niveau du même mois, {annees[0]}-{annees[-1]} (mensuel v2{evt}), corrigé de la part de jours de vacances du mois",
                     "écart des degrés-jours du jour à la normale du mois", "rayonnement du jour", "chaleur (T > 18 °C)"]
    else:
        t["niveau"], t["x_hdd"], t["x_chaud"] = 1.0, t["hdd"], t["chaud"]
        t["x_ray"] = t["ray_kwh"]
        reference = "periode_anterieure_2025"
        facteurs += [f"pas d'historique mensuel comparable{evt}", "degrés-jours 20/12 du jour", "rayonnement du jour", "chaleur (T > 18 °C)"]
    if (t["declare"] != "").any():
        facteurs.append("période déclarée (non jugée) : " + "; ".join(sorted(set(t.loc[t["declare"] != "", "declare"]))))
    return t, reference, facteurs, cfg


def preparer(jeu) -> tuple[list[SerieJour], list[dict], pd.DataFrame]:
    """Rend (séries journalières, défauts de données, mesures mensuelles contrôlées)."""
    sq = seuils()["qualite"]
    mesures_ok, defauts = Q.controler_mensuel(jeu.mesures)
    normales = F.normales_mensuelles(jeu.climat)
    quarts = dict(zip(jeu.calendrier["date"], jeu.calendrier["quarts"].astype(int)))
    heures = {d: n // 4 for d, n in quarts.items()}
    dates = list(quarts)
    series: list[SerieJour] = []

    # ------------------------------------------------ PV et injection (contrôlés d'abord, utilisés ensuite)
    pv_ok = {}
    for cpt, g in jeu.pv.groupby("id_compteur"):
        pv_ok[cpt], d = Q.controler_pas_fin(g, cpt, quarts, "rc_fluides", sq["valeur_figee_pas_15min"] * 2)
        defauts += d

    # ------------------------------------------------ électricité 15 min
    for cpt, g in jeu.elec.groupby("id_compteur"):
        site = g["id_site"].iloc[0]
        ok, d = Q.controler_pas_fin(g, cpt, quarts, "rc_elec", sq["valeur_figee_pas_15min"] * 2)
        defauts += d
        brut = ok.groupby(ok["date"].str.slice(0, 7))["valeur"].sum()
        composantes = [(cpt, 1)]
        libelle = "électricité, compteur général (soutirage)"
        conso = None
        if site in SITES_PV:
            # Site avec PV : consommation = soutirage + production − injection. Le soutirage nul à midi est normal.
            # Le soutirage est suivi contre son propre mensuel v2 ; production et injection ont chacune leur série.
            p, i = pv_ok[f"{site}-PV"], pv_ok[f"{site}-EL-INJ"]
            m = ok.merge(p[["utc", "valeur", "valide"]], on="utc", suffixes=("", "_pv")).merge(
                i[["utc", "valeur", "valide"]].rename(columns={"valeur": "valeur_inj", "valide": "valide_inj"}), on="utc")
            tous = m["valide"] & m["valide_pv"] & m["valide_inj"]
            m["conso"] = m["valeur"] + m["valeur_pv"] - m["valeur_inj"]
            neg = tous & (m["conso"] < -1e-6)
            if neg.any():
                defauts.append(Q._defaut(cpt, "incoherence_sources", Q.plages(m.loc[neg, "date"]), neg.sum(),
                                         f"{int(neg.sum())} pas où injection > soutirage + production (consommation reconstituée négative).", "rc_fluides"))
            conso = m.loc[tous & ~neg, ["date", "heure", "conso", "valeur", "valeur_pv", "valeur_inj"]]
            libelle = "électricité soutirée au réseau (site avec PV : soutirage nul à midi = normal)"
        jour = Q.journalier(ok, quarts)
        t, reference, facteurs, cfg = _assembler(jeu, mesures_ok, normales, site, jour, composantes, "electricite")
        horaires = jeu.compteurs_elec.loc[jeu.compteurs_elec["id_compteur"] == cpt, "horaires"]
        if len(horaires):
            facteurs.append("horaires déclarés : " + horaires.iloc[0])
        series.append(SerieJour(cpt, site, "electricite", "kWh", libelle, t, 1, reference, facteurs,
                                pas=ok.loc[ok["valide"], ["date", "heure", "valeur"]],
                                rapprochement=Q.rapprochement_v2(brut, mesures_ok, cpt), cfg=cfg, extra={"conso_pv": conso}))

    # ------------------------------------------------ production PV : ratio de performance
    for site, kwc in SITES_PV.items():
        cpt = f"{site}-PV"
        ok = pv_ok[cpt]
        jour = Q.journalier(ok, quarts)
        t = F.table_jours(jeu.calendrier, site, "").merge(jour[["date", "valeur", "juge"]], on="date", how="left")
        t["classe"] = "tous_les_jours"
        depuis = F.dernier_evenement(jeu.installations, jeu.compteurs, jeu.batiments, site, [cpt], "pv")
        pr, annees = F.ratio_performance_historique(mesures_ok, jeu.climat, cpt, kwc, depuis)
        t["niveau"] = kwc * t["ray_kwh"] * (t["mois_num"].map(pr) if pr is not None else 1.0)
        t["juge"] = t["juge"].fillna(False).astype(bool)
        t["x_hdd"], t["x_ray"], t["x_chaud"] = t["t_moy"], t["ray_kwh"], 0.0
        mode = f"physique(kWc×rayonnement×ratio_de_performance_du_meme_mois_{annees[0]}-{annees[-1]})" if pr is not None else "physique(kWc×rayonnement)"
        series.append(SerieJour(cpt, site, "pv", "kWh", f"production photovoltaïque ({kwc:g} kWc)", t, -1,
                                mode + "+fenetre_recente_2025",
                                [f"puissance installée {kwc:g} kWc", "rayonnement global du jour (MétéoSuisse Cointrin)",
                                 "ratio de performance du même mois, années précédentes (mensuel v2)", "température du jour",
                                 "jours à moins de 0,5 kWh/m² non jugés"],
                                rapprochement=Q.rapprochement_v2(ok.groupby(ok["date"].str.slice(0, 7))["valeur"].sum(), mesures_ok, cpt),
                                extra={"kwc": kwc}, cfg={"additif": False}))
        inj = pv_ok[f"{site}-EL-INJ"]
        ti, ref_inj, fact_inj, cfg_inj = _assembler(jeu, mesures_ok, normales, site, Q.journalier(inj, quarts), [(f"{site}-EL-INJ", 1)], "pv")
        ti["x_hdd"], ti["x_chaud"] = 0.0, 0.0
        series.append(SerieJour(f"{site}-EL-INJ", site, "injection", "kWh", "électricité solaire injectée au réseau", ti, -1, ref_inj, fact_inj, cfg=cfg_inj,
                                rapprochement=Q.rapprochement_v2(inj.groupby(inj["date"].str.slice(0, 7))["valeur"].sum(), mesures_ok, f"{site}-EL-INJ")))

    # ------------------------------------------------ fluides au jour : gaz, eau, chaleur PAC
    for cpt, g in jeu.fluides.groupby("id_compteur"):
        site, fl = g["id_site"].iloc[0], g["fluide"].iloc[0]
        fluide = "gaz" if fl == "gaz" else "eau" if fl == "eau" else "chaleur_pac"
        jour, d = Q.controler_jour(g, cpt, dates, "rc_fluides")
        defauts += d
        t, reference, facteurs, cfg = _assembler(jeu, mesures_ok, normales, site, jour, [(cpt, 1)], fluide)
        libelle = {"gaz": "gaz naturel (m³ par jour)", "eau": "eau (m³ par jour)", "chaleur_pac": "chaleur produite par la pompe à chaleur"}[fluide]
        series.append(SerieJour(cpt, site, fluide, "m3" if fluide != "chaleur_pac" else "kWh", libelle, t, 1, reference, facteurs,
                                rapprochement=Q.rapprochement_v2(g.groupby(g["date"].str.slice(0, 7))["valeur"].sum(), mesures_ok, cpt), cfg=cfg))

    # ------------------------------------------------ chauffage à distance à l'heure : énergie + hydraulique
    for cpt, g in jeu.cad.groupby("id_compteur"):
        site = g["id_site"].iloc[0]
        ok, d = Q.controler_pas_fin(g, cpt, heures, "rc_fluides", sq["valeur_figee_pas_heure"] * 4, col="energie_kwh")
        defauts += d
        coherent, d = Q.controler_cad(ok, cpt)
        defauts += d
        ok["valide"] = ok["valide"] & coherent.to_numpy()
        jour = Q.journalier(ok, heures, col="energie_kwh")
        t, reference, facteurs, cfg = _assembler(jeu, mesures_ok, normales, site, jour, [(cpt, 1)], "cad")
        facteurs.append("contrôle physique horaire : énergie ≈ 1,163 × débit × (aller − retour)")
        series.append(SerieJour(cpt, site, "cad", "kWh", "chaleur à distance (énergie livrée)", t, 1, reference, facteurs,
                                rapprochement=Q.rapprochement_v2(g.groupby(g["date"].str.slice(0, 7))["energie_kwh"].sum(), mesures_ok, cpt), cfg=cfg))
        v = ok[ok["valide"] & (ok["energie_kwh"] > 0)]
        w = v["energie_kwh"]
        hyd = pd.DataFrame({"date": v["date"], "w": w, "retour": v["t_retour_c"] * w, "dt": (v["t_aller_c"] - v["t_retour_c"]) * w,
                            "debit": v["debit_m3_h"]}).groupby("date").agg(w=("w", "sum"), retour=("retour", "sum"), dt=("dt", "sum"), debit=("debit", "mean"), n=("w", "size"))
        hyd["valeur"] = hyd["retour"] / hyd["w"]
        hyd["dt_moy"] = hyd["dt"] / hyd["w"]
        hyd = hyd.reset_index()
        hyd["juge"] = hyd["n"] >= 18
        th = F.table_jours(jeu.calendrier, site, "").merge(hyd[["date", "valeur", "juge", "dt_moy", "debit", "w"]], on="date", how="left")
        th["juge"] = th["juge"].fillna(False).astype(bool)
        th["classe"], th["niveau"] = "tous_les_jours", 1.0
        th["x_hdd"], th["x_ray"], th["x_chaud"] = np.log(th["w"].clip(lower=1.0)).fillna(0.0), 0.0, 0.0
        series.append(SerieJour(f"{cpt}-RETOUR", site, "cad_retour", "°C", "chaleur à distance : température de retour (hydraulique)", th, 1,
                                "periode_anterieure_2025",
                                ["température de retour pondérée par l'énergie", "charge du jour (énergie livrée)", "ΔT aller-retour et débit suivis en indicateurs"],
                                extra={"compteur": cpt}, cfg={"additif": False}, params={"ecart_relatif_min_pct": seuils()["detection"]["ecart_relatif_min_pct_retour_cad"]}))
    # ------------------------------------------------ mensuel v2 2025 du même périmètre (croisement pas fin ↔ mensuel)
    for s_ in series:
        if s_.fluide == "cad_retour":
            continue
        s_.ref_v2 = _ref_v2(mesures_ok, [(s_.id, 1)])
    return series, defauts, mesures_ok


def _ref_v2(mesures_ok: pd.DataFrame, composantes: list[tuple[str, int]]) -> dict:
    """Total mensuel v2 2025 d'un périmètre ; un mois n'est retenu que si toutes ses composantes sont utilisables."""
    total = None
    for cpt, signe in composantes:
        m = mesures_ok[(mesures_ok["id_compteur"] == cpt) & mesures_ok["utilisable"] & mesures_ok["mois"].str.startswith("2025")]
        v = m.set_index("mois")["valeur"] * signe
        total = v if total is None else total.add(v, fill_value=np.nan)
    return {} if total is None else total.dropna().to_dict()
