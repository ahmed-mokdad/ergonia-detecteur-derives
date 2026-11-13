"""Couche 0 : qualité des données, avant toute détection.

Un défaut de donnée n'est jamais une dérive : les pas en défaut sont marqués invalides, les jours
insuffisamment mesurés ne sont pas jugés, et chaque défaut produit une entrée « Données » avec ce
qu'il faut corriger. Aucune interpolation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import seuils

CORRECTIONS = {
    "pas_manquants": "Redemander la courbe au distributeur pour la période ; vérifier la télérelève (communication, mémoire du compteur).",
    "doublons": "Dédoublonner à la source ; vérifier l'export (double import ou chevauchement de fichiers).",
    "valeurs_negatives": "Vérifier le sens de comptage et le registre exporté.",
    "echelle_ou_pic": "Vérifier l'unité et le facteur de l'export (Wh au lieu de kWh, rapport de transformation) ; corriger à la source.",
    "valeur_figee": "Vérifier le compteur ou la passerelle : une valeur strictement identique pendant des heures est une valeur recopiée.",
    "manquant": "Obtenir le relevé manquant ; ne pas estimer pour décider.",
    "estime": "Remplacer l'estimation du distributeur par un relevé réel dès qu'il existe.",
    "relation_cad": "Contrôler le compteur de chaleur (sondes aller/retour, débitmètre) : l'énergie ne suit pas 1,163 x débit x dT.",
    "rupture_index": "Rapprocher les index avec le distributeur : l'index de fin d'un mois doit être l'index de début du suivant.",
    "incoherence_sources": "Rapprocher les deux sources et documenter laquelle fait foi.",
}


def _defaut(compteur, type_, periodes, n, detail, lot, gravite="moyenne", correction=None):
    return dict(id=f"{compteur}-DQ-{type_}", site=compteur.split("-")[0], compteur=compteur, lot=lot, type=type_,
                periodes=periodes, n=int(n), detail=detail, correction=correction or CORRECTIONS.get(type_, ""),
                gravite=gravite)


def plages(dates) -> list[str]:
    """Regroupe des dates AAAA-MM-JJ en plages contiguës lisibles."""
    ds = sorted(set(pd.to_datetime(list(dates))))
    out, debut, prec = [], None, None
    for d in ds:
        if prec is None or (d - prec).days > 1:
            if debut is not None:
                out.append((debut, prec))
            debut = d
        prec = d
    if debut is not None:
        out.append((debut, prec))
    return [a.strftime("%Y-%m-%d") if a == b else f"{a:%Y-%m-%d} → {b:%Y-%m-%d}" for a, b in out]


def _longueurs_de_suite(v: np.ndarray) -> np.ndarray:
    """Pour chaque position, longueur de la suite de valeurs identiques qui la contient."""
    if len(v) == 0:
        return np.zeros(0, dtype=int)
    change = np.r_[True, v[1:] != v[:-1]]
    idx = np.cumsum(change) - 1
    return np.bincount(idx)[idx]


def controler_pas_fin(df: pd.DataFrame, compteur: str, attendus: dict, lot: str, figee_min: int,
                      col: str = "valeur") -> tuple[pd.DataFrame, list[dict]]:
    """Contrôle une série au quart d'heure ou à l'heure. Rend la série dédoublonnée avec `valide`, et ses défauts.

    attendus : {date locale: nombre de pas attendus} (92 / 96 / 100 quarts d'heure, ou 23 / 24 / 25 heures).
    """
    s = seuils()["qualite"]
    defauts = []
    df = df.sort_values("utc").copy()
    dup = df.duplicated("t", keep="first")
    if dup.any():
        defauts.append(_defaut(compteur, "doublons", plages(df.loc[dup, "date"]), dup.sum(),
                               f"{int(dup.sum())} horodatages en double (seule la première occurrence est gardée).", lot, "faible"))
        df = df[~dup]
    v = df[col].to_numpy(dtype=float)
    valide = ~np.isnan(v)
    neg = v < 0
    if neg.any():
        defauts.append(_defaut(compteur, "valeurs_negatives", plages(df.loc[neg, "date"]), neg.sum(),
                               f"{int(neg.sum())} valeurs négatives, marquées suspectes et exclues.", lot))
    pos = v[(v > 0) & valide]
    med = float(np.median(pos)) if len(pos) else 0.0
    pic = valide & (med > 0) & (v > s["facteur_echelle"] * med)
    if pic.any():
        rapport = float(np.median(v[pic]) / med)
        indice = " : ordre de grandeur x1000, probable Wh au lieu de kWh" if 300 < rapport < 3000 else ""
        defauts.append(_defaut(compteur, "echelle_ou_pic", plages(df.loc[pic, "date"]), pic.sum(),
                               f"{int(pic.sum())} pas à environ {rapport:.0f} fois la médiane de la série{indice}.", lot, "élevée"))
    fig = valide & (v > 0) & (_longueurs_de_suite(v) >= figee_min)
    if fig.any():
        defauts.append(_defaut(compteur, "valeur_figee", plages(df.loc[fig, "date"]), fig.sum(),
                               f"{int(fig.sum())} pas dans des suites de valeurs strictement identiques (au moins {figee_min} pas de suite).", lot))
    df["valide"] = valide & ~neg & ~pic & ~fig
    n_jour = df.groupby("date").size()
    manq = {d: n - int(n_jour.get(d, 0)) for d, n in attendus.items() if int(n_jour.get(d, 0)) < n}
    if manq:
        defauts.append(_defaut(compteur, "pas_manquants", plages(manq), sum(manq.values()),
                               f"{sum(manq.values())} pas absents sur {len(manq)} jours (comparaison au calendrier, changement d'heure compris).", lot, "élevée"))
    return df, defauts


def journalier(df: pd.DataFrame, attendus: dict, col: str = "valeur") -> pd.DataFrame:
    """Agrège au jour local. Un jour n'est jugé que si la part de pas valides atteint le seuil (18 h sur 24).

    La valeur du jour est ramenée au prorata des pas mesurés ; aucune interpolation.
    """
    part_min = seuils()["qualite"]["part_min_jour_juge"]
    ok = df[df["valide"]]
    g = ok.groupby("date")[col].agg(["sum", "size"])
    out = pd.DataFrame({"date": list(attendus), "n_attendu": list(attendus.values())}).set_index("date")
    out["n_valide"] = g["size"].reindex(out.index).fillna(0).astype(int)
    out["somme"] = g["sum"].reindex(out.index)
    out["juge"] = out["n_valide"] >= part_min * out["n_attendu"]
    out["valeur"] = np.where(out["juge"], out["somme"] * out["n_attendu"] / out["n_valide"].clip(lower=1), np.nan)
    return out.reset_index()


def controler_jour(df: pd.DataFrame, compteur: str, dates: list[str], lot: str) -> tuple[pd.DataFrame, list[dict]]:
    """Contrôle une série au jour (gaz, eau, chaleur PAC)."""
    defauts = []
    out = pd.DataFrame({"date": dates}).merge(df[["date", "valeur"]].drop_duplicates("date"), on="date", how="left")
    v = out["valeur"].to_numpy(dtype=float)
    manq = np.isnan(v)
    if manq.any():
        defauts.append(_defaut(compteur, "pas_manquants", plages(out.loc[manq, "date"]), manq.sum(), f"{int(manq.sum())} jours sans valeur.", lot))
    neg = v < 0
    if neg.any():
        defauts.append(_defaut(compteur, "valeurs_negatives", plages(out.loc[neg, "date"]), neg.sum(), f"{int(neg.sum())} valeurs négatives exclues.", lot))
    fig = ~manq & (v > 0) & (_longueurs_de_suite(v) >= 5)
    if fig.any():
        defauts.append(_defaut(compteur, "valeur_figee", plages(out.loc[fig, "date"]), fig.sum(), f"{int(fig.sum())} jours de valeur strictement identique.", lot))
    out["juge"] = ~manq & ~neg & ~fig
    out.loc[~out["juge"], "valeur"] = np.nan
    return out, defauts


def controler_mensuel(mesures: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Contrôle le mensuel v2 : doublons (compteur, mois), manquants, estimés, négatifs. Rend les mesures utilisables."""
    defauts = []
    m = mesures.copy()
    livr = m["mesure"].eq("livraison")
    dup = m.duplicated(["id_compteur", "mois"], keep=False) & ~livr
    for cpt, g in m[dup].groupby("id_compteur"):
        defauts.append(_defaut(cpt, "doublons", sorted(set(g["mois"])), len(g) - g["mois"].nunique(),
                               f"Mois en double : {', '.join(sorted(set(g['mois'])))} (valeurs {', '.join(str(x) for x in g['valeur'])}). Mois non jugé.", "rc_v2"))
    for etat, type_ in (("manquant", "manquant"), ("estimé", "estime")):
        for cpt, g in m[m["qualite"].eq(etat)].groupby("id_compteur"):
            defauts.append(_defaut(cpt, type_, sorted(g["mois"]), len(g), f"{len(g)} mois « {etat} » : {', '.join(sorted(g['mois']))}. Non jugés.", "rc_v2",
                                   "faible" if etat == "estimé" else "moyenne"))
    neg = (m["valeur"] < 0) & ~livr
    for cpt, g in m[neg].groupby("id_compteur"):
        defauts.append(_defaut(cpt, "valeurs_negatives", sorted(g["mois"]), len(g), f"Valeur négative en {', '.join(sorted(g['mois']))}. Non jugée.", "rc_v2"))
    m["utilisable"] = ~dup & m["qualite"].eq("mesuré") & ~neg & m["valeur"].notna()
    return m, defauts


def controler_cad(cad: pd.DataFrame, compteur: str, lot: str = "rc_fluides") -> tuple[pd.Series, list[dict]]:
    """Contrôle physique heure par heure : énergie ≈ 1,163 x débit x (aller − retour). Rend le masque des heures cohérentes."""
    s = seuils()["qualite"]
    calc = 1.163 * cad["debit_m3_h"] * (cad["t_aller_c"] - cad["t_retour_c"])
    ecart = (cad["energie_kwh"] - calc).abs()
    hors = (ecart > np.maximum(s["cad_tolerance_relation"] * calc.abs(), 1.0)) | (cad["t_retour_c"] > cad["t_aller_c"])
    defauts = []
    if hors.mean() > s["cad_part_heures_hors_relation"]:
        defauts.append(_defaut(compteur, "relation_cad", plages(cad.loc[hors, "date"]), hors.sum(),
                               f"{int(hors.sum())} heures ({100 * hors.mean():.1f} %) où l'énergie s'écarte de 1,163 x débit x dT de plus de {100 * s['cad_tolerance_relation']:.0f} %.",
                               lot, "élevée"))
    return ~hors, defauts


def rapprochement_v2(mensuel_fin: pd.Series, mesures: pd.DataFrame, compteur: str) -> pd.DataFrame:
    """Compare les cumuls mensuels d'une série au pas fin au mensuel v2 du même identifiant."""
    ref = mesures[(mesures["id_compteur"] == compteur) & mesures["mois"].str.startswith("2025")].drop_duplicates("mois").set_index("mois")["valeur"]
    out = pd.DataFrame({"pas_fin": mensuel_fin, "v2": ref}).dropna()
    out["ecart"] = out["pas_fin"] - out["v2"]
    out["ecart_pct"] = np.where(out["v2"].abs() > 0, 100 * out["ecart"] / out["v2"], np.nan)
    return out


def controler_s04(s04: dict) -> list[dict]:
    """École du Centre : sources brutes volontairement contradictoires. Tout part dans l'onglet Qualité."""
    d, lot = [], "rc_s04"
    sir = s04["sir"].copy()
    for (cpt, reg), g in sir.groupby(["no_compteur", "registre"]):
        nom = f"S04-SIR-{cpt}-{reg.split(' ')[0]}"
        g = g.sort_values(["periode", "date_releve"])
        dups = g[g.duplicated("periode", keep=False)]
        if len(dups):
            d.append(_defaut(nom, "doublons", sorted(set(dups["periode"])), len(dups) // 2,
                             f"Période en double dans l'export SIR ({', '.join(sorted(set(dups['periode'])))}), quantités {', '.join(f'{x:g}' for x in dups['quantite'])}.", lot))
        a, b = g.iloc[:-1], g.iloc[1:]
        rupt = (a["index_fin"].to_numpy() != b["index_debut"].to_numpy()) & (a["periode"].to_numpy() != b["periode"].to_numpy())
        if rupt.any():
            per = [f"{x} → {y}" for x, y in zip(a["periode"].to_numpy()[rupt], b["periode"].to_numpy()[rupt])]
            d.append(_defaut(nom, "rupture_index", per, rupt.sum(), f"Index de fin ≠ index de début du mois suivant ({', '.join(per)}).", lot, "élevée"))
        inc = g[(g["index_fin"] - g["index_debut"] - g["quantite"]).abs() > 0.5]
        if len(inc):
            d.append(_defaut(nom, "incoherence_sources", list(inc["periode"]), len(inc),
                             "Quantité facturée ≠ différence d'index : " + " ; ".join(f"{r.periode} : {r.quantite:g} pour un index {r.index_debut:g} → {r.index_fin:g} ({r.statut})" for r in inc.itertuples()), lot, "élevée"))
        nonreel = g[~g["statut"].eq("réel")]
        if len(nonreel):
            d.append(_defaut(nom, "estime", list(nonreel["periode"]), len(nonreel),
                             "Relevés non réels : " + " ; ".join(f"{r.periode} {r.statut} ({r.quantite:g})" for r in nonreel.itertuples()), lot, "faible"))
    # registres soutirage / injection échangés : l'index d'un registre continue celui de l'autre
    el = sir[sir["registre"].str.contains("1.8.0|2.8.0", regex=True)].sort_values("periode")
    for cpt, g in el.groupby("no_compteur"):
        so, inj = g[g["registre"].str.startswith("1.8.0")].drop_duplicates("periode", keep="last").set_index("periode"), \
                  g[g["registre"].str.startswith("2.8.0")].drop_duplicates("periode", keep="last").set_index("periode")
        per = sorted(set(so.index) & set(inj.index))
        croise = [q for p, q in zip(per[:-1], per[1:]) if so.loc[p, "index_fin"] == inj.loc[q, "index_debut"] and inj.loc[p, "index_fin"] == so.loc[q, "index_debut"]]
        if croise:
            d.append(_defaut(f"S04-SIR-{cpt}", "incoherence_sources", croise, len(croise),
                             f"Registres soutirage (1.8.0) et injection (2.8.0) échangés dans l'export à partir de {', '.join(croise)} : chaque index prolonge celui de l'autre registre.",
                             lot, "élevée", "Rétablir l'affectation des registres avant tout calcul de soutirage ou d'injection."))
    c = s04["courbe_2022"]
    for (cpt, reg), g in c.groupby(["no_compteur", "registre"]):
        v = g.sort_values("utc")["valeur"].to_numpy(dtype=float)
        fig = (v > 0) & (_longueurs_de_suite(v) >= seuils()["qualite"]["valeur_figee_pas_15min"] * 2)
        if fig.sum():
            d.append(_defaut(f"S04-courbe-{cpt}-{reg.split(' ')[0]}", "valeur_figee", plages(g.sort_values('utc').loc[fig, "date"]), fig.sum(),
                             f"{int(fig.sum())} quarts d'heure de valeur strictement identique dans la courbe de septembre 2022.", lot))
    pas = c.groupby("utc").size()
    trous = pd.date_range(pas.index.min(), pas.index.max(), freq="15min").difference(pas.index)
    if len(trous):
        d.append(_defaut("S04-courbe-2022", "pas_manquants", [f"{trous.min().tz_convert('Europe/Zurich'):%Y-%m-%d %H:%M} → {trous.max().tz_convert('Europe/Zurich'):%H:%M}"], len(trous),
                         f"{len(trous)} quarts d'heure sans aucun compteur pendant le changement de compteur.", lot))
    ond = s04["onduleur"]
    hs = ond[~ond["etat_communication"].eq("OK")]
    if len(hs):
        d.append(_defaut("S04-onduleur-PV", "pas_manquants", plages(hs["date"]), len(hs),
                         f"{len(hs)} jours « {hs['etat_communication'].iloc[0]} » sur le portail de l'onduleur (production affichée {hs['production_kwh'].sum():g} kWh sur ces jours).",
                         lot, correction="Rétablir la communication de l'onduleur ; reconstituer la production par le compteur du distributeur."))
    maz = s04["mazout"]
    av = maz[maz["quantite_litres"] < 0]
    if len(av):
        d.append(_defaut("S04-mazout", "incoherence_sources", list(av["date_livraison"]), len(av),
                         "Bon négatif : " + " ; ".join(f"{r.date_livraison} {r.quantite_litres:g} l ({r.remarque})" for r in av.itertuples()) + ". À traiter comme reprise de stock, pas comme livraison.",
                         lot, correction="Appliquer consommé = livré + stock initial − stock final ; ne pas sommer les bons sans l'avoir."))
    syn = s04["synthese"]
    cols = list(syn.columns)
    tot, gen, pav = _num_col(syn, "Total"), _num_col(syn, "Général"), _num_col(syn, "Pavillon")
    if tot is not None and gen is not None and pav is not None:
        n = int(((tot - gen - pav).abs() < 0.5).sum())
        if n:
            d.append(_defaut("S04-synthese-commune", "incoherence_sources", [f"{syn[cols[0]].iloc[0]} → {syn[cols[0]].iloc[-1]}"], n,
                             f"La feuille Synthèse additionne le sous-compteur du pavillon au compteur général sur {n} mois : double compte (le sous-compteur est déjà compris dans son parent).",
                             lot, "élevée", "Ne jamais additionner parent + enfant : total école = compteur général (+ PV − injection)."))
    return d


def _num_col(df: pd.DataFrame, debut: str):
    for c in df.columns:
        if str(c).startswith(debut):
            return pd.to_numeric(df[c], errors="coerce")
    return None
