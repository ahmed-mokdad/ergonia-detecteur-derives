"""Chaîne complète : connecteur → qualité → références → détection → impact → sorties.

Lancement : `python -m src.pipeline` (écrit outputs/, régénéré à chaque exécution, ignoré par git).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime

import numpy as np
import pandas as pd

from .causes import moteur as causes
from .config import DOSSIER_SORTIES, charger_yaml, seuils
from .connecteurs import creer_connecteur
from .detection.ancre import suivre_ancre
from .detection.journalier import suivre
from .detection.mensuel import analyser as analyser_mensuel
from .detection.series import SerieJour, preparer
from .impact import chiffrage
from .qualite import controles as Q

NOMS_FLUIDE = {"electricite": "électricité", "gaz": "gaz", "eau": "eau", "cad": "chaleur à distance", "cad_retour": "chaleur à distance (hydraulique)",
               "pv": "photovoltaïque", "injection": "injection solaire", "chaleur_pac": "chaleur PAC"}
JOURS_FERMES = ("samedi", "dimanche_ferie", "ouvre_vacances")


def _fr(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def caracteriser(s: SerieJour, table: pd.DataFrame, e: dict) -> tuple[str, list[str], dict]:
    """Décrit la forme de la dérive à partir d'indicateurs calculés. Rend (type, phrases chiffrées, indicateurs)."""
    ep = table.iloc[e["debut_i"]: e["fin_i"] + 1]
    ep = ep[np.isfinite(ep["z"])]
    avant = table.iloc[max(0, e["debut_i"] - 60): e["debut_i"]]
    avant = avant[np.isfinite(avant["z"]) & (avant["etat"] == "juge")]
    exces = ep["valeur"] - ep["attendu"]
    ind: dict = {}
    phrases: list[str] = []
    ferme = ep["classe"].isin(JOURS_FERMES)
    if s.fluide == "electricite" and s.pas is not None:
        def kw(dates, h0, h1):
            p = s.pas[s.pas["date"].isin(dates) & (s.pas["heure"] >= h0) & (s.pas["heure"] < h1)]
            return float(p["valeur"].mean() * 4) if len(p) else float("nan")
        ind = dict(nuit_avant_kw=round(kw(avant["date"], 0, 5), 2), nuit_pendant_kw=round(kw(ep["date"], 0, 5), 2),
                   jour_avant_kw=round(kw(avant["date"], 8, 18), 2), jour_pendant_kw=round(kw(ep["date"], 8, 18), 2),
                   part_exces_jours_fermes=round(float(exces[ferme].sum() / exces.sum()), 2) if exces.sum() else None,
                   part_jours_fermes=round(float(ferme.mean()), 2))
        d_nuit, d_jour = ind["nuit_pendant_kw"] - ind["nuit_avant_kw"], ind["jour_pendant_kw"] - ind["jour_avant_kw"]
        phrases.append(f"Puissance moyenne de nuit (0 h-5 h) : {_fr(ind['nuit_avant_kw'], 1)} kW sur les 60 jours précédents, {_fr(ind['nuit_pendant_kw'], 1)} kW pendant la dérive ; "
                       f"en journée (8 h-18 h) : {_fr(ind['jour_avant_kw'], 1)} kW puis {_fr(ind['jour_pendant_kw'], 1)} kW (mesuré, non corrigé de la saison).")
        if ind["part_exces_jours_fermes"] is not None and ind["part_exces_jours_fermes"] >= 0.6 and (
                ind["part_exces_jours_fermes"] > ind["part_jours_fermes"] + 0.2 or ind["part_jours_fermes"] >= 0.8):
            type_ = "hors_occupation"
            phrases.append(f"{_fr(100 * ind['part_exces_jours_fermes'])} % du surplus tombe des jours fermés (week-ends, fériés, vacances), qui ne font que {_fr(100 * ind['part_jours_fermes'])} % de la période.")
        elif d_nuit > 0 and d_nuit >= 0.6 * max(d_jour, 0.0):
            type_ = "talon_permanent"
        else:
            type_ = "hausse_en_occupation"
    elif s.fluide in ("gaz", "cad", "chaleur_pac"):
        froid = ep["hdd"] > 0
        ind = dict(exces_par_jour_froid=round(float(exces[froid].mean()), 2) if froid.any() else None,
                   exces_par_jour_doux=round(float(exces[~froid].mean()), 2) if (~froid).any() else None, jours_froids=int(froid.sum()), jours_doux=int((~froid).sum()))
        if ind["exces_par_jour_doux"] is not None and (ind["exces_par_jour_froid"] is None or ind["exces_par_jour_doux"] >= 0.6 * ind["exces_par_jour_froid"]):
            type_ = "base_hors_chauffe"
        else:
            type_ = "pente_chauffage"
        u = "m³" if s.fluide == "gaz" else "kWh"
        if ind["exces_par_jour_froid"] is not None:
            phrases.append(f"Surplus moyen de {_fr(ind['exces_par_jour_froid'], 1)} {u} par jour les {ind['jours_froids']} jours de chauffe (T < 12 °C)"
                           + (f", contre {_fr(ind['exces_par_jour_doux'], 1)} {u} les {ind['jours_doux']} jours doux." if ind["exces_par_jour_doux"] is not None else "."))
    elif s.fluide == "eau":
        ind = dict(exces_par_jour_ferme=round(float(exces[ferme].mean()), 2) if ferme.any() else None,
                   exces_par_jour_ouvert=round(float(exces[~ferme].mean()), 2) if (~ferme).any() else None,
                   minimum_avant=round(float(avant["valeur"].min()), 2) if len(avant) else None, minimum_pendant=round(float(ep["valeur"].min()), 2))
        permanent = ind["exces_par_jour_ferme"] is not None and (ind["exces_par_jour_ouvert"] is None or ind["exces_par_jour_ferme"] >= 0.6 * ind["exces_par_jour_ouvert"])
        type_ = "ecoulement_permanent" if permanent else "surconsommation_en_occupation"
        if ind["exces_par_jour_ferme"] is not None:
            phrases.append(f"Surplus moyen de {_fr(ind['exces_par_jour_ferme'], 2)} m³ par jour les jours fermés"
                           + (f" et de {_fr(ind['exces_par_jour_ouvert'], 2)} m³ les jours ouverts." if ind["exces_par_jour_ouvert"] is not None else "."))
        phrases.append("Au pas journalier, une fuite de nuit au débit horaire n'est pas observable : seul un écoulement visible sur le total du jour l'est.")
    elif s.fluide == "pv":
        type_ = "chute_production_pv"
        ind = dict(part_produite=round(float(ep["valeur"].sum() / ep["attendu"].sum()), 2), kwc=s.extra.get("kwc"))
        phrases.append(f"La production n'atteint que {_fr(100 * ind['part_produite'])} % de l'attendu à rayonnement égal.")
    elif s.fluide == "injection":
        type_ = "injection_en_baisse"
    elif s.fluide == "cad_retour":
        type_ = "retour_chaud"
        ind = dict(retour_avant_c=round(float(avant["valeur"].mean()), 1), retour_pendant_c=round(float(ep["valeur"].mean()), 1),
                   dt_avant_k=round(float(avant["dt_moy"].mean()), 1), dt_pendant_k=round(float(ep["dt_moy"].mean()), 1),
                   debit_avant_m3h=round(float(avant["debit"].mean()), 2), debit_pendant_m3h=round(float(ep["debit"].mean()), 2))
        phrases.append(f"Retour : {_fr(ind['retour_avant_c'], 1)} °C avant, {_fr(ind['retour_pendant_c'], 1)} °C pendant ; ΔT aller-retour : {_fr(ind['dt_avant_k'], 1)} K puis {_fr(ind['dt_pendant_k'], 1)} K ; "
                       f"débit moyen : {_fr(ind['debit_avant_m3h'], 2)} puis {_fr(ind['debit_pendant_m3h'], 2)} m³/h (mesuré, non corrigé de la saison).")
    else:
        type_ = "ecart"
    if len(ep) and "classe" in ep:
        ind["part_jours_vacances"] = round(float((ep["classe"] == "ouvre_vacances").mean()), 2)
    return type_, phrases, ind


def _alerte(s: SerieJour, table: pd.DataFrame, e: dict, info: dict, jeu, cop_ref) -> dict:
    ch = chiffrage.chiffrer(table, e, s.fluide, jeu.facteur_gaz(), cop_ref)
    type_, phrases, ind = caracteriser(s, table, e)
    ancre = False
    u = ch["observe"]["unite"] or s.unite
    if s.fluide == "cad_retour":
        base = (f"Du {e['debut']} au {e['fin']}, la valeur moyenne mesurée est {_fr(ch['observe']['valeur'] / max(ch['jours_juges'], 1), 1)} {s.unite} pour "
                f"{_fr(ch['attendu']['valeur'] / max(ch['jours_juges'], 1), 1)} attendus ({ch['ecart_pct']:+.1f} %) sur {ch['jours_juges']} jours jugés, à charge égale.")
    else:
        base = (f"Du {e['debut']} au {e['fin']}, {_fr(ch['observe']['valeur'])} {u} mesurés pour {_fr(ch['attendu']['valeur'])} attendus "
                f"({ch['ecart_pct']:+.1f} %) sur {ch['jours_juges']} jours jugés. L'attendu est appris sur le passé seulement (historique mensuel 2021-2024, "
                "puis jours sains de 2025), à type de jour et météo égaux ; la référence est gelée au début de la dérive.")
    reference = s.reference + " | gelee"
    facteurs, indic = s.facteurs, {}
    if e.get("datation") == "au mois":
        base += " Dérive lente ou noyée dans le bruit du jour : datée au mois (deux mois consécutifs d'écart net), début réel possiblement antérieur."
    return dict(
        id=f"{s.id}-{e['debut'][:7]}", site=s.site, nom_site="", compteur=s.id, fluide=NOMS_FLUIDE[s.fluide], famille=s.fluide, libelle=s.libelle,
        type=type_, sens="hausse" if e["sens"] > 0 else "baisse", debut=e["debut"], detection=e["detection"], detection_regle_journaliere=e.get("detection_modele", e["detection"]),
        fin=e["fin"], statut=e["statut"], datation=e.get("datation", "au jour"),
        **{k: ch[k] for k in ("observe", "attendu", "ecart_pct", "constate", "rythme_mensuel", "projection_12_mois", "confiance", "urgence", "priorite",
                             "masquee", "jours_juges", "z_moyen", "risque_sinistre")},
        reference=reference, source_detection="croisement pas fin ↔ mensuel v2" if ancre else "moteur autonome (passé seulement)",
        pourquoi_pas_normal=" ".join([base] + phrases), facteurs_pris_en_compte=facteurs, indicateurs={**ind, **indic},
        causes=[], verifications=[], actions=[], liens=[], texte_genere_par_ia=False,
    )


# Pairs = compteurs qui répondent au même facteur extérieur (le froid pour le chauffage). L'électricité et l'eau n'en font
# pas partie : leurs usages sont trop différents d'un site à l'autre pour qu'une médiane serve de témoin.
FAMILLES_PAIRS = {"gaz": "chauffage", "cad": "chauffage", "chaleur_pac": "chauffage"}


def mode_commun(series: list[SerieJour], pairs_min: int = 4, lissage_jours: int = 7) -> dict:
    """Écart partagé par les compteurs pairs (même famille de fluide), jour par jour, en écarts-types.

    Une dérive est propre à un site ; un écart qui touche le même jour la médiane des AUTRES compteurs de la
    famille vient de la météo ou de la saison mal modélisée (reprise de chauffe, vacances). Il est retiré de
    l'attendu. Causal : médiane du jour, lissée sur les 7 jours précédents. Familles de moins de 5 séries : rien.
    """
    z = {}
    for s in series:
        if s.fluide in FAMILLES_PAIRS:
            # passage sans épisode ni gel : le résidu d'un pair est celui d'une référence qui continue de s'adapter,
            # comme celle du compteur jugé ; seul l'écart commun transitoire (changement de saison) est donc retiré
            t, _ = suivre(s.table, s.sens, {**seuils()["detection"]["autonome"], **s.params, "cusum_h": 1e12}, s.cfg)
            z[s.id] = (FAMILLES_PAIRS[s.fluide], t["z"].to_numpy(dtype=float))
    out = {}
    for sid, (fam, _) in z.items():
        autres = np.array([v for k, (f, v) in z.items() if f == fam and k != sid])
        if len(autres) < pairs_min:
            continue
        n_ok = np.isfinite(autres).sum(axis=0)
        med = np.where(n_ok >= pairs_min, np.nanmedian(np.where(n_ok >= 1, autres, 0.0), axis=0), 0.0)
        out[sid] = pd.Series(med).rolling(lissage_jours, min_periods=1).mean().to_numpy()
    return out


def _confirmer(a: dict, sens: int, controle: dict | None, fluide: str, facteur_gaz: dict, cop_ref, tol: float) -> dict:
    """Vérification a posteriori d'une alerte du moteur autonome par le rapprochement avec le mensuel v2."""
    if controle is None:
        return dict(statut="sans second relevé", confirme=None, detail="Aucun mensuel v2 pour cette grandeur : alerte non vérifiable par rapprochement.")
    mois = {m: v for m, v in controle["ecart"].items() if a["debut"][:7] <= m <= a["fin"][:7]}
    confirme = any(sens * v >= tol for v in mois.values())
    tv = controle["table"]
    fen = tv[(tv["date"] >= a["debut"]) & (tv["date"] <= a["fin"]) & np.isfinite(tv["z"])]
    c = chiffrage.convertir(fluide, fen["valeur"] - fen["attendu"], fen["date"].str.slice(0, 7), facteur_gaz, cop_ref)
    return dict(statut="confirmé par le rapprochement mensuel" if confirme else "non confirmé par le rapprochement mensuel", confirme=confirme,
                ecart_mensuel_v2_pct=mois, chiffrage_de_controle=dict(kwh=round(c["kwh"]), chf=None if c["chf"] is None else round(c["chf"]), statut="estimé",
                                                                       definition="pas fin − mensuel v2 réparti au jour, sur la même période"),
                detail=("Sur la période, le cumul du pas fin s'écarte du mensuel v2 dans le même sens (au moins un mois à 3 % ou plus)." if confirme else
                        "Sur la période, le cumul du pas fin retombe sur le mensuel v2 : l'alerte est probablement une fausse alerte du moteur autonome."))


def evaluer_autonome(alertes: list[dict], verite: list[dict], series_controlees: set) -> dict:
    """Performance du moteur autonome seul sur Rive-Claire 2025, le rapprochement v2 servant de vérité de contrôle."""
    al = [a for a in alertes if a["compteur"] in series_controlees]
    lignes = []
    for v in verite:
        touche = sorted((a for a in al if a["compteur"] == v["serie"] and a["debut"] <= v["fin"] and v["debut"] <= a["fin"]), key=lambda a: a["detection"])
        delai = (pd.Timestamp(touche[0]["detection"]) - pd.Timestamp(v["debut"])).days if touche else None
        lignes.append({**v, "trouvee": bool(touche), "alerte": touche[0]["id"] if touche else None, "delai_jours": delai,
                       "debut_autonome": touche[0]["debut"] if touche else None})
    fausses = [dict(id=a["id"], debut=a["debut"], fin=a["fin"], ecart_pct=a["ecart_pct"], chf=a["constate"]["chf"]) for a in al if not a["rapprochement_v2"]["confirme"]]
    vp = sum(1 for a in al if a["rapprochement_v2"]["confirme"])
    trouvees = sum(1 for x in lignes if x["trouvee"])
    delais = [x["delai_jours"] for x in lignes if x["delai_jours"] is not None]
    return dict(n_series=len(series_controlees), n_derives_de_controle=len(verite), trouvees=trouvees, manquees=[x for x in lignes if not x["trouvee"]],
                n_alertes=len(al), confirmees=vp, fausses_alertes=fausses, precision=round(vp / max(len(al), 1), 2), rappel=round(trouvees / max(len(verite), 1), 2),
                delai_median_jours=float(np.median(delais)) if delais else None, detail=lignes)


def evaluation_markdown(ev: dict) -> str:
    L = ["# Évaluation", "", "Générée par `python -m src.pipeline`. Tous les chiffres sortent du code.", "",
         "## Moteur autonome seul, sur Rive-Claire 2025", "",
         "Le détecteur n'utilise que le passé (historique mensuel 2021-2024, jours sains de 2025, météo, calendrier). Le rapprochement avec le mensuel v2 de 2025 "
         "ne sert qu'ici, après coup, comme **vérité de contrôle** : une dérive de contrôle est une période où le pas fin s'écarte nettement du mensuel v2.", "",
         f"- Séries contrôlables : {ev['n_series']} · dérives de contrôle : {ev['n_derives_de_controle']}",
         f"- **Dérives trouvées : {ev['trouvees']} sur {ev['n_derives_de_controle']}** (rappel {100 * ev['rappel']:.0f} %)",
         f"- **Alertes levées : {ev['n_alertes']}, dont {ev['confirmees']} confirmées et {len(ev['fausses_alertes'])} fausses alertes** (précision {100 * ev['precision']:.0f} %)",
         f"- Délai de détection médian : {ev['delai_median_jours']:.0f} jours après le début de contrôle" if ev["delai_median_jours"] is not None else "- Délai : aucune dérive trouvée",
         "", "| Dérive de contrôle | Période | Écart | Trouvée par le moteur autonome | Début estimé | Délai |", "|---|---|---|---|---|---|"]
    for x in ev["detail"]:
        L.append(f"| {x['serie']} | {x['debut']} → {x['fin']} ({x['datation']}) | {x['ecart_pct']:+.1f} % | {'oui' if x['trouvee'] else '**non**'} | "
                 f"{x['debut_autonome'] or '—'} | {str(x['delai_jours']) + ' j' if x['delai_jours'] is not None else '—'} |")
    L += ["", "**Dérives manquées** : " + (", ".join(f"{x['serie']} ({x['ecart_pct']:+.1f} %)" for x in ev["manquees"]) or "aucune") + ".",
          "", "**Fausses alertes** (non confirmées par le rapprochement) : " +
          (", ".join(f"{f['id']} ({f['debut']} → {f['fin']}, {f['ecart_pct']:+.1f} %)" for f in ev["fausses_alertes"]) or "aucune") + ".", "",
          "Limites de cette mesure : un délai négatif signifie que l'alerte autonome a commencé avant la dérive de contrôle (alerte qui recouvre la dérive sans la prouver) ; "
          "les seuils du moteur autonome ont été choisis après avoir vu ces données ; la température de retour du chauffage à distance n'a pas de vérité de contrôle ; "
          "la précision sur un parc réel n'est pas mesurable ici.", ""]
    return "\n".join(L)


def _chevauche(a: dict, b: dict) -> bool:
    return a["site"] == b["site"] and a["debut"] <= b["fin"] and b["debut"] <= a["fin"]


def calculer(connecteur=None, ecrire: bool = True) -> dict:
    """Exécute toute la chaîne et rend les résultats (alertes, défauts, séries saines, tables journalières)."""
    connecteur = connecteur or creer_connecteur()
    jeu = connecteur.jeu()
    series, defauts, mesures_ok = preparer(jeu)
    defauts += Q.controler_s04(jeu.s04) if jeu.s04 else []
    noms = jeu.batiments.drop_duplicates("id_site").set_index("id_site")["nom_site"].to_dict()
    typo = jeu.batiments.drop_duplicates("id_site").set_index("id_site")["typologie"].to_dict()
    m24 = mesures_ok[mesures_ok["mois"].str.startswith("2024") & mesures_ok["utilisable"]]
    ch24, el24 = m24[m24["id_compteur"] == "S09-CH-PAC"]["valeur"].sum(), m24[m24["id_compteur"] == "S09-PAC"]["valeur"].sum()
    cop_ref = float(ch24 / el24) if el24 > 0 else None
    tol = seuils()["qualite"]["ecart_v2_net_pct"]
    alertes, autres, sains, tables, resume = [], [], [], {}, []
    verite, controles, ecartees = [], {}, []
    communs = mode_commun(series)
    for s in series:
        # 1. Moteur autonome : le détecteur. Passé seulement, référence gelée. Toutes les alertes affichées viennent de lui.
        entree = s.table.assign(juge=s.table["juge"] & (s.table["ray_kwh"] >= 0.5)) if s.fluide == "pv" else s.table
        if s.id in communs:
            entree = entree.assign(z_commun=communs[s.id])
        table, eps = suivre(entree, s.sens, {**seuils()["detection"]["autonome"], **s.params}, s.cfg)
        info = dict(ecart_mois_pct={}, sigma_rel=float(np.nanmedian(table["sigma"] / table["attendu"].abs())))
        table.attrs["unite"] = s.unite
        tables[s.id] = table
        # 2. Rapprochement v2 : vérification a posteriori seulement (confirmer, chiffrer en contrôle, évaluer). Jamais une source de détection.
        controle = None
        if s.ref_v2:
            tv, eps_v, info_v = suivre_ancre(s.table, s.ref_v2, s.sens, s.params)
            controle = controles[s.id] = dict(table=tv, ecart=info_v["ecart_mois_pct"])
            info["ecart_mois_pct"] = info_v["ecart_mois_pct"]
            verite += [dict(serie=s.id, fluide=s.fluide, debut=e["debut"], fin=e["fin"], statut=e["statut"], datation=e.get("datation", "au jour"),
                            ecart_pct=round(float(100 * (tv["valeur"] - tv["attendu"]).iloc[e["debut_i"]: e["fin_i"] + 1].sum() / tv["attendu"].iloc[e["debut_i"]: e["fin_i"] + 1].sum()), 1))
                       for e in eps_v if e["net"] and e["alerte"]]
        retenus = eps
        for e in retenus:
            a = _alerte(s, table, e, info, jeu, cop_ref)
            a["nom_site"], a["typologie"] = noms.get(s.site, s.site), typo.get(s.site, "")
            a["rapprochement_v2"] = _confirmer(a, e["sens"], controle, s.fluide, jeu.facteur_gaz(), cop_ref, tol)
            # Filtre de sobriété, causal : l'écart cumulé de l'épisode doit rester au-dessus du seuil relatif du moteur.
            seuil_rel = {**seuils()["detection"]["autonome"], **s.params}["ecart_relatif_min_pct"]
            if a["ecart_pct"] is None or e["sens"] * a["ecart_pct"] < seuil_rel:
                ecartees.append(dict(id=a["id"], debut=a["debut"], fin=a["fin"], ecart_pct=a["ecart_pct"], seuil_pct=seuil_rel,
                                     rapprochement=a["rapprochement_v2"]["statut"]))
                continue
            (alertes if e["alerte"] else autres).append(a)
        isoles = {}
        dq = [d for d in defauts if d["compteur"] == s.id]
        juges = int(np.isfinite(table["z"]).sum())
        ligne = dict(id=s.id, site=s.site, nom_site=noms.get(s.site, s.site), fluide=NOMS_FLUIDE[s.fluide], famille=s.fluide, libelle=s.libelle, unite=s.unite,
                     jours_juges=juges, jours_non_juges=int(len(table) - juges), dispersion_pct=round(100 * info["sigma_rel"], 1),
                     ecart_mensuel_v2_pct=info["ecart_mois_pct"], ecarts_isoles=isoles, n_alertes=sum(1 for e in retenus if e["alerte"]),
                     n_defauts=len(dq), reference="mensuel v2 2025 réparti au jour" if s.ref_v2 else s.reference)
        resume.append(ligne)
        if not retenus and not isoles and not any(d["gravite"] == "élevée" for d in dq):
            sains.append(ligne)

    # ---------------------------------------------- une alerte par cause et par site, sans double compte
    garde = []
    for a in alertes:
        if a["famille"] == "injection":
            pv = next((b for b in alertes if b["famille"] == "pv" and _chevauche(a, b)), None)
            if pv is not None:      # l'injection baisse parce que la production baisse : même cause, une seule alerte
                continue
            a["pourquoi_pas_normal"] += (" Production et soutirage du site retombent sur le mensuel v2 pendant cette période : l'énergie produite a été consommée sur place "
                                         "ou n'a pas été comptée par le registre d'injection. Dérive visible seulement en croisant injection, production et soutirage.")
        garde.append(a)
    alertes = garde
    for a in alertes:
        a["liens"] = [b["id"] for b in alertes if b is not a and _chevauche(a, b)]
        if a["famille"] == "pv" and f"{a['site']}-EL-INJ" in tables:
            ti = tables[f"{a['site']}-EL-INJ"]
            fen = ti[(ti["date"] >= a["debut"]) & (ti["date"] <= a["fin"]) & np.isfinite(ti["z"])]
            a["indicateurs"]["injection_perdue_kwh"] = round(float(-(fen["valeur"] - fen["attendu"]).sum()))
            a["indicateurs"]["injection_jours_juges"] = int(len(fen))
        if a["famille"] == "pv":
            el = next((b for b in alertes if b["famille"] == "electricite" and _chevauche(a, b)), None)
            if el is not None and "injection_perdue_kwh" in a["indicateurs"]:
                prix = charger_yaml("tarifs")["prix"]["pv"]["valeur"]
                a["double_compte"] = dict(avec=el["id"], kwh_retenu_au_total=a["indicateurs"]["injection_perdue_kwh"],
                                          chf_retenu_au_total=None if prix is None else round(a["indicateurs"]["injection_perdue_kwh"] * prix),
                                          regle="perte PV = injection perdue + autoconsommation perdue ; cette dernière est déjà dans le surplus de soutirage du même site")
    # en cours d'abord ; alertes chiffrées par priorité ; alertes non chiffrées (pas de prix dans le jeu) ensuite, par kWh par mois
    alertes.sort(key=lambda a: (a["statut"] != "en cours", a["priorite"] is None, -(a["priorite"] or 0), -abs(a["rythme_mensuel"]["kwh"])))
    for rang, a in enumerate(alertes, 1):
        a["rang"] = rang
        causes.proposer(a, alertes)
    evaluation = evaluer_autonome(alertes, verite, set(controles))
    visibles = [a for a in alertes if not a["masquee"]]
    retenues_total = [a for a in visibles if a["rapprochement_v2"]["confirme"] is not False]   # une alerte non confirmée n'entre pas dans le total
    total_chf = sum(a["constate"]["chf"] or 0 for a in retenues_total if "double_compte" not in a)
    mensuel = analyser_mensuel(mesures_ok, jeu.compteurs, jeu.climat, jeu.facteur_gaz(), noms, {s.id for s in series})
    m25 = [a["constate_2025"] for a in mensuel["alertes"]]
    meta = dict(calcule_le=datetime.now().strftime("%Y-%m-%d %H:%M"), provenance=connecteur.provenance(),
                n_series_pas_fin=len(series), n_alertes=len(visibles), n_alertes_masquees=len(alertes) - len(visibles), n_defauts=len(defauts), n_sains=len(sains),
                n_non_confirmees=len(visibles) - len(retenues_total),
                total_constate=dict(kwh=round(sum(a["constate"]["kwh"] for a in retenues_total if "double_compte" not in a) + sum(x["kwh"] for x in m25)),
                                    chf=round(total_chf + sum(x["chf"] or 0 for x in m25)),
                                    t_co2_direct=round(sum(a["constate"]["t_co2_direct"] for a in retenues_total) + sum(x["t_co2_direct"] for x in m25), 2),
                                    statut="estimé", au_moins=True,
                                    n_alertes_non_chiffrees_en_chf=sum(1 for a in retenues_total if a["constate"]["chf"] is None) + sum(1 for x in m25 if x["chf"] is None),
                                    composition="alertes du pas fin confirmées ou sans second relevé + part 2025 des alertes de la couche mensuelle"),
                formule_priorite=chiffrage.FORMULE_PRIORITE, formule_confiance=chiffrage.FORMULE_CONFIANCE, cop_reference_s09=cop_ref,
                attributions=charger_yaml("sources")["attributions"], licence_donnees=charger_yaml("sources")["licence_donnees"],
                non_couvert=["dérives du mensuel v2 2021-2024 (signature par degrés-jours, COP mensuel) : étape suivante",
                             "fuite d'eau de nuit au débit horaire : impossible au pas journalier",
                             "mazout et granulés : livraisons sans stocks, consommation mensuelle inconnue",
                             "COP journalier de la PAC S09 : pas de sous-compteur PAC au jour"])
    meta["non_couvert"][0] = "couche mensuelle : " + mensuel["couverture"]["non_juges"]
    res = dict(alertes=alertes, autres_ecarts=autres, defauts=defauts, sains=sains, resume=resume, meta=meta, tables=tables, mensuel=mensuel,
               evaluation=evaluation, evaluation_md=evaluation_markdown(evaluation) + "\n## Épisodes écartés par le filtre de sobriété\n\n"
               + f"{len(ecartees)} épisodes ouverts par le CUSUM puis retombés sous le seuil d'écart cumulé, non affichés : "
               + (", ".join(f"{x['id']} ({x['ecart_pct']:+.1f} %, {x['rapprochement']})" for x in ecartees) or "aucun") + ".\n")
    if ecrire:
        ecrire_sorties(res)
    return res


def ecrire_sorties(res: dict) -> None:
    """Écrit outputs/ (régénéré à chaque exécution, ignoré par git)."""
    for sous in ("series", "fiches"):
        shutil.rmtree(DOSSIER_SORTIES / sous, ignore_errors=True)
    (DOSSIER_SORTIES / "series").mkdir(parents=True)
    for nom in ("alertes", "autres_ecarts", "defauts", "sains", "resume", "meta", "mensuel"):
        (DOSSIER_SORTIES / f"{nom}.json").write_text(json.dumps(res[nom], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (DOSSIER_SORTIES / "evaluation.md").write_text(res["evaluation_md"], encoding="utf-8")
    (DOSSIER_SORTIES / "fiches").mkdir()
    for a in res["alertes"]:
        (DOSSIER_SORTIES / "fiches" / f"{a['id']}.md").write_text(causes.fiche_markdown(a), encoding="utf-8")
    for cle, t in res["tables"].items():
        cols =[c for c in ("date", "valeur", "attendu", "bas", "haut", "z", "etat", "classe", "t_moy", "dt_moy", "debit") if c in t.columns]
        t[cols].to_csv(DOSSIER_SORTIES / "series" / f"{cle}.csv", sep=";", index=False, float_format="%.4f")


def main() -> None:
    res = calculer()
    m = res["meta"]
    print(f"{m['n_series_pas_fin']} séries suivies | {m['n_alertes']} alertes ({m['n_alertes_masquees']} masquées sous le plancher) | "
          f"{m['n_defauts']} défauts de données | {m['n_sains']} séries saines")
    print(f"Constaté (au moins) : {m['total_constate']['kwh']} kWh, {m['total_constate']['chf']} CHF, {m['total_constate']['t_co2_direct']} t CO2 direct")
    for a in res["alertes"]:
        print(f" {a['rang']:2d} {a['id']:20s} {a['type']:28s} {a['debut']} → {a['fin']} {a['statut']:9s} {a['ecart_pct']:+6.1f} % "
              f"{a['constate']['kwh']:8d} kWh {str(a['constate']['chf']):>7s} CHF rythme {str(a['rythme_mensuel']['chf']):>6s} CHF/mois conf {a['confiance']:.2f} {a['urgence']}"
              + (" [masquée]" if a["masquee"] else "") + " | " + a["rapprochement_v2"]["statut"][:13])
    ev = res["evaluation"]
    print(f"Autonome vs contrôle v2 : {ev['trouvees']}/{ev['n_derives_de_controle']} dérives trouvées, {len(ev['fausses_alertes'])} fausses alertes sur {ev['n_alertes']}, "
          f"délai médian {ev['delai_median_jours']} j ; manquées : {[x['serie'] for x in ev['manquees']]}")
    mm = res["mensuel"]
    print(f"Mensuel 2021-2025 (autonome) : {mm['n_series_jugees']} séries rejouées, {len(mm['alertes'])} alertes, {mm['n_expliques']} mois expliqués par la météo")
    for a in mm["alertes"]:
        print(f"    {a['id']:22s} {a['debut']} → {a['fin']} {a['statut']:9s} {a['ecart_pct']:+6.1f} % {a['constate']['kwh']:8d} kWh {str(a['constate']['chf']):>6s} CHF "
              f"{a['constate']['t_co2_direct']} t CO2 | dont 2025 : {a['constate_2025']}")
    print("    couverture :", mm["couverture"])
    print("    COP par an :", mm["cop_par_an"])
    for d in mm["expliques_par_la_meteo"][:6]:
        print(f"    expliqué : {d['compteur']} {d['mois']} médiane {d['ecart_mediane_meme_mois_pct']:+.0f} % → à DJ égaux {d['ecart_a_dj_egaux_pct']:+.0f} %")
    print("Sorties écrites dans outputs/")


if __name__ == "__main__":
    main()
