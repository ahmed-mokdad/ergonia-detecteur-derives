"""Couche 4 : impact et priorisation.

Seule la dérive CONSTATÉE compte : Σ (mesuré − attendu) sur les jours jugés depuis le début détecté,
affichée comme « au moins ». La projection 12 mois est calculée à part, étiquetée, et n'entre jamais
dans le score. Chaque chiffre porte son statut : mesuré, estimé (calculé par le moteur) — jamais généré par IA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import seuils, tarifs

FORMULE_PRIORITE = ("priorité = rythme mensuel constaté (CHF/mois) × confiance × urgence (Critique 3, Élevée 2, Modérée 1) "
                    "× 1,5 si risque de sinistre (eau). La projection n'y entre jamais.")
FORMULE_CONFIANCE = ("confiance = 0,35 + 0,25 × min(1, |z moyen| / 3) + 0,20 × min(1, jours jugés / 30) + 0,10 × part de jours jugés "
                     "+ 0,10 si la datation est au jour ; plafonnée à 0,95. Indice d'ordonnancement, pas une probabilité calibrée.")


def _prix(p: dict, quantite: float):
    """CHF, ou None si le jeu ne donne pas de prix : « non chiffré », jamais un prix inventé."""
    return None if p["valeur"] is None else quantite * p["valeur"]


def _txt(nom: str, p: dict) -> str:
    return f"{nom} : non chiffré en CHF ({p['source'].lower()})" if p["valeur"] is None else f"{nom} {p['valeur']} CHF par unité ({p['statut']})"


def _arr(v, dec=0):
    return None if v is None else round(v, dec) if dec else round(v)


def convertir(fluide: str, exces: pd.Series, mois: pd.Series, facteur_gaz: dict, cop_ref: float | None = None) -> dict:
    """Convertit un excès journalier (unité du compteur) en kWh, CHF et kg CO2 direct, avec ses hypothèses."""
    t = tarifs()
    px, co2 = t["prix"], t["co2_direct"]
    tot = float(exces.sum())
    if fluide == "gaz":
        f = mois.map(facteur_gaz).astype(float)
        kwh = float((exces * f).sum())
        return dict(kwh=kwh, chf=_prix(px["gaz"], kwh), kg_co2=tot * co2["gaz_kg_par_m3"], unite="m³", quantite=tot,
                    hypotheses=[f"PCS du mois (Ref_Conversion, {f.min():.2f} à {f.max():.2f} kWh/m³)", _txt("gaz", px["gaz"]),
                                f"CO₂ direct {co2['gaz_kg_par_m3']} kg/m³ (Ref_CO2)"])
    if fluide == "eau":
        return dict(kwh=0.0, chf=_prix(px["eau"], tot), kg_co2=0.0, unite="m³", quantite=tot,
                    hypotheses=[_txt("eau", px["eau"]), "pas d'équivalent kWh ni CO₂ retenu pour l'eau"])
    if fluide == "cad":
        return dict(kwh=tot, chf=_prix(px["cad"], tot), kg_co2=0.0, unite="kWh", quantite=tot,
                    hypotheses=[_txt("chaleur à distance", px["cad"]), "CO₂ direct sur site : 0 (convention du jeu)"])
    if fluide in ("pv", "injection"):
        return dict(kwh=-tot, chf=_prix(px["pv"], -tot), kg_co2=0.0, unite="kWh", quantite=-tot,
                    hypotheses=[_txt("kWh solaire non produit ou non injecté", px["pv"])])
    if fluide == "electricite":
        return dict(kwh=tot, chf=tot * px["electricite"]["valeur"], kg_co2=0.0, unite="kWh", quantite=tot,
                    hypotheses=[f"électricité {px['electricite']['valeur']} CHF/kWh ({px['electricite']['statut']})", "CO₂ direct sur site : 0 (convention du jeu)"],
                    kg_co2_cycle_de_vie=tot * t["co2_cycle_de_vie"]["electricite_g_par_kwh"] / 1000)
    if fluide == "gaz":
        f = mois.map(facteur_gaz).astype(float)
        kwh = float((exces * f).sum())
        return dict(kwh=kwh, chf=kwh * px["gaz"]["valeur"], kg_co2=tot * co2["gaz_kg_par_m3"], unite="m³", quantite=tot,
                    hypotheses=[f"PCS du mois (Ref_Conversion, {f.min():.2f} à {f.max():.2f} kWh/m³)", f"gaz {px['gaz']['valeur']} CHF/kWh PCS ({px['gaz']['statut']})",
                                f"CO₂ direct {co2['gaz_kg_par_m3']} kg/m³ (Ref_CO2)"])
    if fluide == "eau":
        return dict(kwh=0.0, chf=tot * px["eau"]["valeur"], kg_co2=0.0, unite="m³", quantite=tot,
                    hypotheses=[f"eau {px['eau']['valeur']} CHF/m³ ({px['eau']['statut']})", "pas d'équivalent kWh ni CO₂ retenu pour l'eau"])
    if fluide == "cad":
        return dict(kwh=tot, chf=tot * px["cad"]["valeur"], kg_co2=0.0, unite="kWh", quantite=tot,
                    hypotheses=[f"chaleur à distance {px['cad']['valeur']} CHF/kWh ({px['cad']['statut']})", "CO₂ direct sur site : 0 (convention du jeu)"])
    if fluide in ("pv", "injection"):
        perte = -tot
        return dict(kwh=perte, chf=perte * px["pv"]["valeur"], kg_co2=0.0, unite="kWh", quantite=perte,
                    hypotheses=[f"kWh solaire non produit ou non injecté valorisé {px['pv']['valeur']} CHF/kWh ({px['pv']['statut']})"])
    if fluide == "chaleur_pac":
        cop = cop_ref or 3.0
        kwh = tot / cop
        return dict(kwh=kwh, chf=kwh * px["chaleur_pac"]["valeur"], kg_co2=0.0, unite="kWh chaleur", quantite=tot,
                    hypotheses=[f"chaleur convertie en électricité de PAC avec un COP de {cop:.2f}" + (" (mensuel v2 2024)" if cop_ref else " (valeur par défaut)"),
                                f"électricité {px['electricite']['valeur']} CHF/kWh"])
    return dict(kwh=0.0, chf=0.0, kg_co2=0.0, unite="", quantite=tot,
                hypotheses=["pas de surconsommation mesurée : impact non chiffrable en kWh avec ces données"])


def chiffrer(table: pd.DataFrame, e: dict, fluide: str, facteur_gaz: dict, cop_ref: float | None = None) -> dict:
    """Chiffre un épisode : constaté (au moins), borne prudente, rythme mensuel, projection étiquetée, confiance, urgence, priorité."""
    s = seuils()
    fen = table.iloc[e["debut_i"]: e["fin_i"] + 1]
    fen = fen[np.isfinite(fen["z"])]
    exces = fen["valeur"] - fen["attendu"]
    mois = fen["date"].str.slice(0, 7)
    constate = convertir(fluide, exces, mois, facteur_gaz, cop_ref)
    # borne prudente : seul ce qui dépasse la bande à 95 % est compté
    prudent = (fen["valeur"] - fen["haut"]).clip(lower=0) if e["sens"] > 0 else (fen["valeur"] - fen["bas"]).clip(upper=0)
    borne = convertir(fluide, prudent, mois, facteur_gaz, cop_ref)
    dern = fen.tail(30)
    rythme = convertir(fluide, (dern["valeur"] - dern["attendu"]) * 30 / max(len(dern), 1), dern["date"].str.slice(0, 7), facteur_gaz, cop_ref)
    observe, attendu = float(fen["valeur"].sum()), float(fen["attendu"].sum())
    zmoy = float(np.abs(fen["z"]).mean()) if len(fen) else 0.0
    jours_total = max(int(e["fin_i"] - e["debut_i"] + 1), 1)
    confiance = min(0.95, 0.35 + 0.25 * min(1, zmoy / 3) + 0.20 * min(1, len(fen) / 30) + 0.10 * len(fen) / jours_total
                    + (0.10 if e.get("datation", "au jour") == "au jour" else 0.0))
    u = s["enjeu"]["urgence_chf_par_mois"]
    sinistre = fluide == "eau"
    if rythme["chf"] is None:      # pas de prix dans le jeu : ni urgence en francs, ni priorité, ni plancher ; l'alerte est classée par kWh
        chf_mois, urgence, priorite, masquee = None, "Non chiffrée", None, False
    else:
        chf_mois = abs(rythme["chf"])
        urgence = "Critique" if chf_mois >= u["critique"] else "Élevée" if chf_mois >= u["elevee"] else "Modérée"
        priorite = round(chf_mois * confiance * {"Critique": 3, "Élevée": 2, "Modérée": 1}[urgence] * (s["enjeu"]["facteur_sinistre_eau"] if sinistre else 1.0), 1)
        masquee = chf_mois < s["enjeu"]["plancher_chf_par_mois"] and not sinistre and fluide != "cad_retour"
    return dict(
        observe=dict(valeur=round(observe, 1), unite=constate["unite"] or table.attrs.get("unite", ""), statut="mesuré"),
        attendu=dict(valeur=round(attendu, 1), bande_95=[round(float(fen["bas"].sum()), 1), round(float(fen["haut"].sum()), 1)], statut="estimé"),
        ecart_pct=round(100 * (observe - attendu) / attendu, 1) if attendu else None,
        constate=dict(quantite=round(constate["quantite"], 1), unite=constate["unite"], kwh=round(constate["kwh"]), chf=_arr(constate["chf"]),
                      t_co2_direct=round(constate["kg_co2"] / 1000, 3), au_moins=True, statut="estimé", hypotheses=constate["hypotheses"],
                      borne_prudente=dict(kwh=round(borne["kwh"]), chf=_arr(borne["chf"]), definition="seul ce qui dépasse la bande à 95 %"),
                      kg_co2_cycle_de_vie=round(constate.get("kg_co2_cycle_de_vie", 0.0))),
        rythme_mensuel=dict(kwh=round(rythme["kwh"]), chf=_arr(rythme["chf"]), quantite=round(rythme["quantite"], 1), t_co2_direct=round(rythme["kg_co2"] / 1000, 3),
                            statut="estimé", definition="excès moyen par jour des 30 derniers jours jugés de la dérive, × 30"),
        projection_12_mois=dict(kwh=round(rythme["kwh"] * 12), chf=_arr(None if rythme["chf"] is None else rythme["chf"] * 12),
                                hypothese="dérive constante au rythme constaté", dans_le_score=False, statut="estimé"),
        jours_juges=int(len(fen)), z_moyen=round(zmoy, 2), confiance=round(confiance, 2), urgence=urgence, risque_sinistre=sinistre,
        priorite=priorite, masquee=bool(masquee),
    )
