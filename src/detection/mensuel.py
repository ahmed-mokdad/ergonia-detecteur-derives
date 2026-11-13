"""Dérives du mensuel v2 (2021-2025), moteur autonome : signature par degrés-jours et COP des pompes à chaleur.

Rejeu mois par mois, passé seulement. La signature (valeur/jour = base + pente × DJ/jour, ajustement robuste) est
réapprise chaque mois sur au moins 24 mois sains ; une alerte exige deux mois consécutifs hors bande ET à plus
de 10 % ; la référence est gelée au début de l'épisode. Ce moteur n'a pas de second relevé : il ne voit que les
écarts nets, et c'est dit (un même mois varie de 5 à 10 % d'une année à l'autre).
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from ..config import seuils, tarifs
from ..modeles.reference import _sigma, ajuster_robuste


def suivre_mensuel(df: pd.DataFrame, sens: int = 1, apprentissage_min: int | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """df : mois, y, x, utilisable (trié). Rend la table (attendu, z, ecart_pct) et les épisodes du sens surveillé."""
    det = seuils()["detection"]["mensuel"]
    n_min = apprentissage_min or det["mois_apprentissage_min"]
    y, x = df["y"].to_numpy(dtype=float), df["x"].to_numpy(dtype=float)
    ok = df["utilisable"].to_numpy(dtype=bool) & np.isfinite(y) & np.isfinite(x)
    n = len(df)
    att, z = np.full(n, np.nan), np.full(n, np.nan)
    exclu = np.zeros(n, dtype=bool)
    eps, ouvert, suite, calme = [], None, [], 0
    for i in range(n):
        tr = np.flatnonzero(ok & ~exclu & (np.arange(n) < i))
        if len(tr) < n_min or not ok[i]:
            continue
        X = np.column_stack([np.ones(len(tr)), x[tr]])
        beta = ajuster_robuste(X, y[tr], np.array([1e-9, 1e-9]))
        sigma = max(_sigma(y[tr] - X @ beta), 0.04 * float(np.median(np.abs(y[tr]))))
        att[i] = beta[0] + beta[1] * x[i]
        z[i] = (y[i] - att[i]) / sigma
        hors = sens * z[i] > 2 and att[i] > 0 and 100 * sens * (y[i] - att[i]) / att[i] >= det["ecart_relatif_min_pct"]
        if ouvert is not None:
            exclu[i] = True
            if hors:
                calme, ouvert["fin"] = 0, i
            elif att[i] > 0 and 100 * sens * (y[i] - att[i]) / att[i] < det["ecart_relatif_min_pct"] / 2:
                # mois revenu sous la moitié du seuil relatif ; un mois de faible charge encore en écart n'est pas « calme »
                calme += 1
                if calme >= det["mois_consecutifs"]:
                    ouvert["statut"] = "résorbée"
                    exclu[ouvert["fin"] + 1: i + 1] = False
                    eps.append(ouvert)
                    ouvert, suite = None, []
            continue
        suite = suite + [i] if hors else []
        if len(suite) >= det["mois_consecutifs"]:
            ouvert = dict(debut=suite[0], detection=i, fin=i, statut="en cours")
            exclu[suite[0]: i + 1] = True
            calme = 0
    if ouvert is not None:
        eps.append(ouvert)
    out = df.copy()
    out["attendu"], out["z"] = att, z
    out["ecart_pct"] = 100 * (y - att) / np.where(att > 0, att, np.nan)
    return out, eps


def analyser(mesures_ok: pd.DataFrame, compteurs: pd.DataFrame, climat: pd.DataFrame, facteur_gaz: dict, noms: dict, suivis_pas_fin: set) -> dict:
    """Applique le rejeu à tous les compteurs de gaz et de chaleur à distance, et au COP des PAC qui ont un compteur de chaleur."""
    px = tarifs()["prix"]
    co2_gaz = tarifs()["co2_direct"]["gaz_kg_par_m3"]
    cli = climat.set_index("mois")
    alertes, expliques, n_series = [], [], 0
    cop_par_an: dict = {}

    def jours(m):
        return calendar.monthrange(int(m[:4]), int(m[5:7]))[1]

    def serie(cpt):
        m = mesures_ok[mesures_ok["id_compteur"] == cpt].drop_duplicates("mois").sort_values("mois")
        return m.set_index("mois")

    def constate(exces: pd.Series, mois: pd.Series, genre: str) -> dict:
        """Excès en unité du compteur -> kWh, CHF (None si le jeu ne donne pas de prix), t CO2 direct."""
        q = float(exces.sum())
        kwh = float((exces * mois.map(facteur_gaz).astype(float)).sum()) if genre == "gaz" else 0.0 if genre == "eau" else q
        p = px[{"gaz": "gaz", "cad": "cad", "eau": "eau", "elec": "electricite"}[genre]]["valeur"]
        base = kwh if genre != "eau" else q
        return dict(quantite=round(q), unite={"gaz": "m³", "eau": "m³"}.get(genre, "kWh"), kwh=round(kwh), chf=None if p is None else round(base * p),
                    t_co2_direct=round(q * co2_gaz / 1000, 2) if genre == "gaz" else 0.0, au_moins=True, statut="estimé")

    couverture = dict(gaz=0, chaleur_a_distance=0, electricite=0, eau=0, cop=0, ecartes_evenement=[], juges_au_pas_fin_en_2025=sorted(suivis_pas_fin & set(compteurs["id_compteur"])))
    sites_juges = set()

    # ---- électricité (compteur général) et eau : niveau du même mois des années précédentes, appris sur le passé seulement
    recents = compteurs[compteurs["debut"].ge("2021-01") & compteurs["id_compteur"].str.contains("-PV|-PAC|-EL-INJ|-EL-BORNES|-EL$", regex=True)]
    sites_evenement = set(recents["id_site"])
    cible = compteurs[((compteurs["fluide"] == "électricité") & (compteurs["niveau"] == "général") & (compteurs["mesure"] == "soutirage")) | (compteurs["fluide"] == "eau")]
    for _, c in cible.iterrows():
        cpt, eau = c["id_compteur"], c["fluide"] == "eau"
        if cpt in suivis_pas_fin:
            continue                              # 2025 jugé au pas fin ; son mensuel v2 2025 est la « part normale », pas une observation
        if c["debut"] >= "2021-01" or (not eau and c["id_site"] in sites_evenement):
            couverture["ecartes_evenement"].append(cpt)   # installation ou compteur mis en service depuis 2021 : pas de référence stable
            continue
        m = serie(cpt)
        if len(m) < 50:
            continue
        j = np.array([jours(x) for x in m.index])
        y = m["valeur"].to_numpy(dtype=float) / j
        mm_ = m.index.str.slice(5, 7)
        ok_ = m["utilisable"].to_numpy(dtype=bool)
        xs = [np.median(y[:i][(mm_[:i] == mm_[i]) & ok_[:i]]) if ((mm_[:i] == mm_[i]) & ok_[:i]).sum() >= 2 else np.nan for i in range(len(m))]
        df = pd.DataFrame({"mois": m.index, "y": y, "x": xs, "utilisable": ok_, "jours": j})
        table, eps = suivre_mensuel(df, 1)
        if not np.isfinite(table["z"]).any():
            continue
        couverture["eau" if eau else "electricite"] += 1
        sites_juges.add(c["id_site"])
        for e in eps:
            fen = table.iloc[e["debut"]: e["fin"] + 1]
            fen = fen[np.isfinite(fen["z"])]
            exces = (fen["y"] - fen["attendu"]) * fen["jours"]
            genre = "eau" if eau else "elec"
            en25 = fen["mois"] >= "2025"
            alertes.append(dict(
                id=f"{cpt}-M-{fen['mois'].iloc[0]}", site=c["id_site"], nom_site=noms.get(c["id_site"], ""), compteur=cpt, fluide=c["fluide"],
                type="hausse_au_dessus_du_meme_mois_des_annees_precedentes", debut=str(fen["mois"].iloc[0]), detection=str(table["mois"].iloc[e["detection"]]),
                fin=str(fen["mois"].iloc[-1]), statut=e["statut"], mois_juges=int(len(fen)),
                ecart_pct=round(float(100 * exces.sum() / (fen["attendu"] * fen["jours"]).sum()), 1),
                constate=constate(exces, fen["mois"], genre), constate_2025=constate(exces[en25], fen["mois"][en25], genre),
                reference="meme_mois_annees_precedentes(passé seulement, ≥ 24 mois) | gelee",
                facteurs_pris_en_compte=["niveau du même mois des années précédentes", "nombre de jours du mois", "pas de correction météo ni de calendrier scolaire au pas mensuel"]))

    for _, c in compteurs[compteurs["fluide"].isin(["gaz", "chaleur à distance"])].iterrows():
        cpt, gaz = c["id_compteur"], c["fluide"] == "gaz"
        m = serie(cpt)
        if cpt in suivis_pas_fin:
            m = m[m.index < "2025"]            # 2025 est jugé au pas fin : pas de double alerte
        if len(m) < 26:
            continue
        couverture["gaz" if gaz else "chaleur_a_distance"] += 1
        sites_juges.add(c["id_site"])
        j = np.array([jours(x) for x in m.index])
        df = pd.DataFrame({"mois": m.index, "y": m["valeur"].to_numpy() / j, "x": cli["degres_jours_20_12"].reindex(m.index).to_numpy() / j,
                           "utilisable": m["utilisable"].to_numpy(), "jours": j})
        table, eps = suivre_mensuel(df, 1)
        n_series += 1
        for e in eps:
            fen = table.iloc[e["debut"]: e["fin"] + 1]
            fen = fen[np.isfinite(fen["z"])]
            exces = (fen["y"] - fen["attendu"]) * fen["jours"]
            en25 = fen["mois"] >= "2025"
            alertes.append(dict(
                id=f"{cpt}-M-{fen['mois'].iloc[0]}", site=c["id_site"], nom_site=noms.get(c["id_site"], ""), compteur=cpt, fluide=c["fluide"],
                type="chauffage_en_hausse_a_dj_egaux", debut=str(fen["mois"].iloc[0]), detection=str(table["mois"].iloc[e["detection"]]), fin=str(fen["mois"].iloc[-1]),
                statut=e["statut"], mois_juges=int(len(fen)), ecart_pct=round(float(100 * exces.sum() / (fen["attendu"] * fen["jours"]).sum()), 1),
                constate=constate(exces, fen["mois"], "gaz" if gaz else "cad"), constate_2025=constate(exces[en25], fen["mois"][en25], "gaz" if gaz else "cad"),
                reference="signature_mensuelle_DJ(passé seulement, ≥ 24 mois) | gelee", facteurs_pris_en_compte=["degrés-jours 20/12 du mois (Ref_Climat)", "nombre de jours du mois", "PCS du mois" if gaz else "—"]))
        # cas d'école : la médiane du même mois crie, la météo explique
        t = table[np.isfinite(table["z"])].copy()
        t["mm"] = t["mois"].str.slice(5, 7)
        for r in t.itertuples():
            passe = table[(table["mois"] < r.mois) & (table["mois"].str.slice(5, 7) == r.mm) & table["utilisable"]]["y"]
            if len(passe) >= 3:
                naif = 100 * (r.y / passe.median() - 1)
                if naif >= 20 and abs(r.z) < 2:
                    expliques.append(dict(compteur=cpt, nom_site=noms.get(c["id_site"], ""), mois=r.mois, ecart_mediane_meme_mois_pct=round(float(naif), 1),
                                          ecart_a_dj_egaux_pct=round(float(r.ecart_pct), 1), dj_du_mois=float(cli["degres_jours_20_12"].get(r.mois, np.nan))))

    for _, c in compteurs[compteurs["id_compteur"].str.endswith("-CH-PAC")].iterrows():
        site = c["id_site"]
        ch, el = serie(c["id_compteur"]), serie(f"{site}-PAC")
        m = ch.join(el, lsuffix="_ch", rsuffix="_el", how="inner")
        if len(m) < 20:
            continue
        j = np.array([jours(x) for x in m.index])
        charge = m["valeur_ch"].to_numpy() / j
        df = pd.DataFrame({"mois": m.index, "y": m["valeur_ch"].to_numpy() / m["valeur_el"].to_numpy(), "x": cli["temperature_moy_c"].reindex(m.index).to_numpy(),
                           "utilisable": (m["utilisable_ch"] & m["utilisable_el"]).to_numpy() & (charge >= 0.15 * np.nanmax(charge)) & (m["valeur_el"].to_numpy() > 0),
                           "ch": m["valeur_ch"].to_numpy(), "el": m["valeur_el"].to_numpy()})
        table, eps = suivre_mensuel(df, -1, apprentissage_min=12)
        n_series += 1
        couverture["cop"] += 1
        an = pd.Series(m.index.str.slice(0, 4), index=m.index)
        cop_par_an[site] = {a: round(float(m["valeur_ch"][an == a].sum() / m["valeur_el"][an == a].sum()), 2) for a in sorted(an.unique()) if m["valeur_el"][an == a].sum() > 0}
        for e in eps:
            fen = table.iloc[e["debut"]: e["fin"] + 1]
            fen = fen[np.isfinite(fen["z"])]
            surplus = fen["el"] - fen["ch"] / fen["attendu"]
            kwh, kwh25 = float(surplus.sum()), float(surplus[fen["mois"] >= "2025"].sum())
            alertes.append(dict(
                id=f"{site}-COP-M-{fen['mois'].iloc[0]}", site=site, nom_site=noms.get(site, ""), compteur=f"{site}-PAC", fluide="pompe à chaleur (COP)",
                type="cop_en_baisse_a_temperature_egale", debut=str(fen["mois"].iloc[0]), detection=str(table["mois"].iloc[e["detection"]]), fin=str(fen["mois"].iloc[-1]),
                statut=e["statut"], mois_juges=int(len(fen)), ecart_pct=round(float(100 * (fen["y"].mean() / fen["attendu"].mean() - 1)), 1),
                cop=dict(mesure=round(float(fen["ch"].sum() / fen["el"].sum()), 2), attendu=round(float(fen["attendu"].mean()), 2), statut_mesure="mesuré", statut_attendu="estimé"),
                constate=dict(quantite=round(kwh), unite="kWh él.", kwh=round(kwh), chf=round(kwh * px["electricite"]["valeur"]), t_co2_direct=0.0, au_moins=True, statut="estimé"),
                constate_2025=dict(quantite=round(kwh25), unite="kWh él.", kwh=round(kwh25), chf=round(kwh25 * px["electricite"]["valeur"]), t_co2_direct=0.0, au_moins=True, statut="estimé"),
                comparaison_pairs=f"COP annuel mesuré par site (chaleur / électricité PAC) : voir cop_par_an ; {site} est comparé aux autres PAC équipées d'un compteur de chaleur",
                reference="COP_mensuel_selon_temperature(passé seulement, mois de chauffe) | gelee",
                facteurs_pris_en_compte=["température moyenne du mois (Ref_Climat)", "mois de faible charge exclus", "électricité de la PAC = sous-compteur déjà compris dans le compteur général"]))
    alertes.sort(key=lambda a: (a["statut"] != "en cours", -a["constate"]["kwh"]))
    expliques.sort(key=lambda d: (d["mois"], d["ecart_mediane_meme_mois_pct"]), reverse=True)
    n_series += couverture["electricite"] + couverture["eau"]
    couverture["sites_avec_au_moins_une_serie_jugee"] = len(sites_juges)
    couverture["sites_du_parc"] = int(compteurs["id_site"].nunique())
    couverture["non_juges"] = ("mazout et granulés (livraisons sans stocks) ; sous-compteurs (compris dans leur parent) ; production PV et injection ; "
                               f"{len(couverture['ecartes_evenement'])} compteurs dont le site a changé d'installation depuis 2021 ; "
                               "2025 des compteurs suivis au pas fin (jugés au pas fin)")
    return dict(alertes=alertes, expliques_par_la_meteo=expliques, n_series_jugees=n_series, n_expliques=len(expliques), couverture=couverture, cop_par_an=cop_par_an)
