"""Causes et solutions : règles déterministes sur les indicateurs calculés, puis fiche d'intervention par gabarit.

Le moteur choisit les causes de knowledge/signatures.yaml pour le type de dérive, ajuste leur plausibilité
selon les indices observés et dit aussi ce qui contredit chaque hypothèse. Aucun chiffre n'est inventé :
tous viennent de l'alerte. Toute cause est une hypothèse à vérifier sur place.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from ..config import RACINE

CHANGEMENTS_HEURE = ("2025-03-30", "2025-10-26")
MENTION = "Hypothèses à vérifier sur place avant toute intervention"


@lru_cache(maxsize=1)
def base_de_connaissances() -> dict:
    with open(RACINE / "knowledge" / "signatures.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _jours(a: str, b: str) -> int:
    from datetime import date

    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def indices(a: dict, alertes: list[dict]) -> dict[str, tuple[bool, str]]:
    """Conditions nommées -> (vraie ?, phrase d'indice chiffrée). Toutes calculées à partir de l'alerte."""
    i = a.get("indicateurs", {})
    liees = [b for b in alertes if b["id"] in a.get("liens", [])]
    apres = [c for c in CHANGEMENTS_HEURE if 0 <= _jours(c, a["debut"]) <= 14]
    mois = int(a["debut"][5:7])
    out: dict[str, tuple[bool, str]] = {}

    def pose(nom, vrai, texte):
        out[nom] = (bool(vrai), texte)

    pose("en_cours", a["statut"] == "en cours", "la dérive est toujours en cours")
    pose("resorbee", a["statut"] == "résorbée", f"la dérive s'est arrêtée d'elle-même le {a['fin']}")
    pose("debut_apres_changement_heure", apres, f"début {_jours(apres[0], a['debut'])} jours après le changement d'heure du {apres[0]}" if apres else "")
    pose("loin_d_un_changement_heure", not apres, "le début ne suit aucun changement d'heure")
    pose("saison_de_chauffe", mois >= 9 or mois <= 3, "le début tombe en saison de chauffe")
    pose("autre_fluide_meme_periode", any(b["famille"] != a["famille"] for b in liees),
         "un autre fluide du même site dérive sur la même période (" + ", ".join(b["id"] for b in liees) + ")")
    pose("pas_d_autre_fluide", not liees, "aucun autre fluide du site ne dérive en même temps")
    pose("retour_chaud_meme_site", any(b["type"] == "retour_chaud" for b in liees), "le retour du chauffage à distance du même site est chaud")
    if "nuit_avant_kw" in i:
        pose("nuit_en_hausse", i["nuit_pendant_kw"] > 1.05 * i["nuit_avant_kw"], f"puissance de nuit passée de {i['nuit_avant_kw']} à {i['nuit_pendant_kw']} kW")
        pose("jour_en_hausse", i["jour_pendant_kw"] > 1.05 * i["jour_avant_kw"], f"puissance de jour passée de {i['jour_avant_kw']} à {i['jour_pendant_kw']} kW")
    if i.get("part_exces_jours_fermes") is not None:
        p = i["part_exces_jours_fermes"]
        pose("surtout_jours_fermes", p >= 0.6, f"{round(100 * p)} % du surplus tombe des jours fermés")
        pose("pas_les_jours_fermes_seulement", p < 0.6, f"seulement {round(100 * p)} % du surplus tombe des jours fermés")
    if "part_jours_vacances" in i:
        pose("pendant_vacances", i["part_jours_vacances"] >= 0.5, f"{round(100 * i['part_jours_vacances'])} % des jours de la dérive sont des vacances scolaires")
    if i.get("exces_par_jour_froid") is not None or i.get("exces_par_jour_doux") is not None:
        f, d = i.get("exces_par_jour_froid"), i.get("exces_par_jour_doux")
        doux = d is not None and (f is None or d >= 0.6 * f)
        pose("surplus_aussi_jours_doux", doux, f"surplus de {d} par jour doux" + (f" pour {f} par jour froid" if f is not None else ""))
        pose("surplus_surtout_jours_froids", not doux, f"surplus de {f} par jour de chauffe" + (f" pour {d} par jour doux" if d is not None else " (aucun jour doux dans la période)"))
    if "part_produite" in i:
        pose("perte_forte", i["part_produite"] < 0.5, f"production à {round(100 * i['part_produite'])} % de l'attendu")
        pose("perte_partielle_stable", 0.3 <= i["part_produite"] <= 0.9, f"production à {round(100 * i['part_produite'])} % de l'attendu : une partie de l'installation produit encore")
    if a["type"] == "injection_en_baisse":
        pose("injection_nulle", a["ecart_pct"] is not None and a["ecart_pct"] <= -95, f"injection à {a['ecart_pct']:+.0f} % de l'attendu")
    if "dt_avant_k" in i:
        pose("dt_ecrase", i["dt_pendant_k"] < i["dt_avant_k"] - 3, f"ΔT passé de {i['dt_avant_k']} à {i['dt_pendant_k']} K")
        pose("debit_en_hausse", i["debit_pendant_m3h"] > 1.2 * i["debit_avant_m3h"], f"débit passé de {i['debit_avant_m3h']} à {i['debit_pendant_m3h']} m³/h")
    return out


def proposer(a: dict, alertes: list[dict]) -> dict:
    """Complète une alerte : causes classées (plausibilité, pour, contre), vérifications, actions, gain."""
    sig = base_de_connaissances().get(a["type"])
    if not sig:
        return a
    ind = indices(a, alertes)
    causes = []
    for c in sig["causes"]:
        score, pour, contre = c["base"], [], []
        for nom, poids in (c.get("pour") or {}).items():
            if ind.get(nom, (False, ""))[0]:
                score += poids
                pour.append(ind[nom][1])
        for nom, poids in (c.get("contre") or {}).items():
            if ind.get(nom, (False, ""))[0]:
                score -= poids
                contre.append(ind[nom][1])
        causes.append(dict(cause=c["cause"], plausibilite=round(min(0.95, max(0.05, score)), 2), pour=pour, contre=contre,
                           verifications=c["verifications"], actions=c["actions"], statut="hypothèse à valider par l'exploitant"))
    causes.sort(key=lambda c: -c["plausibilite"])
    a["signature"] = sig["titre"]
    a["causes"] = causes
    a["verifications"] = [v for c in causes[:2] for v in c["verifications"]]
    a["actions"] = [x for c in causes[:2] for x in c["actions"]]
    r = a["rythme_mensuel"]
    a["gain_estime"] = dict(chf_par_mois=r["chf"], kwh_par_mois=r["kwh"], statut="estimé",
                            definition="plafond : rythme constaté de la dérive ; l'économie réelle dépend de la cause confirmée sur place")
    return a


def _n(x, dec=0) -> str:
    if x is None:
        return "non chiffré"
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def fiche_markdown(a: dict) -> str:
    """Fiche d'intervention par gabarit déterministe (aucun LLM). Tous les nombres viennent de l'alerte."""
    c = a["constate"]
    lignes = [
        f"# Fiche d'intervention — {a['site']} {a['nom_site']}", "",
        f"**{a.get('signature', a['type'])}** · {a['libelle']} · priorité n° {a['rang']} · urgence {a['urgence']} · statut : {a['statut']}", "",
        "## Ce qu'on observe", "",
        a["pourquoi_pas_normal"], "",
        f"- Depuis le {a['debut']} (détection : {a['detection']}), jusqu'au {a['fin']}.",
        f"- Surplus constaté, au moins : {_n(c['quantite'])} {c['unite']}, soit {_n(c['kwh'])} kWh, {_n(c['chf'])} CHF et {_n(c['t_co2_direct'], 3)} t CO₂ direct (estimé).",
        f"- Rythme constaté : {_n(a['rythme_mensuel']['chf'])} CHF par mois (estimé). Confiance {_n(a['confiance'], 2)} (indice d'ordonnancement, pas une probabilité).",
        "- Hypothèses de chiffrage : " + " ; ".join(c["hypotheses"]) + ".",
        "- Vérification a posteriori : " + a.get("rapprochement_v2", {}).get("statut", "non faite") + ".", "",
        "## Causes probables", ""]
    for k, x in enumerate(a.get("causes", [])[:3], 1):
        lignes.append(f"{k}. **{x['cause']}** (plausibilité {_n(x['plausibilite'], 2)})")
        if x["pour"]:
            lignes.append("   - Pour : " + " ; ".join(x["pour"]) + ".")
        if x["contre"]:
            lignes.append("   - Contre : " + " ; ".join(x["contre"]) + ".")
    lignes += ["", "## À vérifier sur place, dans l'ordre", ""] + [f"- [ ] {v}" for v in a.get("verifications", [])]
    lignes += ["", "## Actions correctives envisagées", ""] + [f"- {x}" for x in a.get("actions", [])]
    g = a.get("gain_estime")
    if g:
        lignes += ["", "## Gain attendu", "", f"Au plus {_n(g['chf_par_mois'])} CHF par mois ({_n(g['kwh_par_mois'])} kWh par mois), estimé : {g['definition']}."]
    lignes += ["", f"**{MENTION}.** Texte produit par gabarit déterministe, sans IA. Statut : à valider par l'exploitant.", "",
               "Données : Energ-IA Transition, Energ-IACK 2026 (Rive-Claire, CC BY 4.0). Température et rayonnement : MétéoSuisse, station Genève-Cointrin."]
    return "\n".join(lignes)
