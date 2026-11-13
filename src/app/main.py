"""Application Streamlit : partie 1 « Les dérives », partie 2 « Causes et solutions » (à venir), qualité, sites sains.

Lancement : `streamlit run streamlit_app.py`. L'app n'embarque aucune donnée : elle les lit par le connecteur.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import charger_env, charger_yaml, param
from src.connecteurs import ErreurConnecteur, creer_connecteur
from src.pipeline import calculer

STATUT = {"mesuré": "🟢 mesuré", "estimé": "🟠 estimé", "ia": "🟣 généré par IA"}
TYPES = {
    "talon_permanent": "Hausse à toute heure, y compris la nuit", "hors_occupation": "Consommation hors occupation",
    "hausse_en_occupation": "Hausse pendant l'occupation", "pente_chauffage": "Chauffage en hausse à météo égale",
    "base_hors_chauffe": "Hausse aussi par temps doux (base)", "ecoulement_permanent": "Écoulement d'eau permanent",
    "surconsommation_en_occupation": "Surconsommation d'eau en occupation", "chute_production_pv": "Production solaire en chute",
    "injection_en_baisse": "Injection solaire en chute", "retour_chaud": "Retour chaud (hydraulique)", "ecart": "Écart",
}


def fr(x, dec=0, unite=""):
    if x is None or pd.isna(x):
        return "non chiffré (pas de prix dans le jeu)" if unite.startswith("CHF") else "—"
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",") + (f" {unite}" if unite else "")


@st.cache_resource(show_spinner="Lecture des données par le connecteur, contrôles et détection…")
def resultats():
    return calculer(creer_connecteur(), ecrire=False)


def graphique(table: pd.DataFrame, a: dict | None, unite: str) -> go.Figure:
    t = table[table["attendu"].notna()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t["date"], y=t["haut"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=t["date"], y=t["bas"], line=dict(width=0), fill="tonexty", fillcolor="rgba(120,120,120,0.25)", name="bande à 95 % (estimé)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=t["date"], y=t["attendu"], line=dict(color="#555", width=1.5, dash="dot"), name="attendu (estimé)"))
    j = table[table["valeur"].notna()]
    fig.add_trace(go.Scatter(x=j["date"], y=j["valeur"], line=dict(color="#0b6fa4", width=1.6), name="mesuré"))
    nj = table[table["etat"].isin(["non_juge", "periode_declaree"])]
    if len(nj):
        fig.add_trace(go.Scatter(x=nj["date"], y=[0] * len(nj), mode="markers", marker=dict(color="#999", symbol="x", size=5), name="jour non jugé"))
    if a:
        fig.add_vrect(x0=a["debut"], x1=a["fin"], fillcolor="rgba(220,60,40,0.12)", line_width=0)
        fig.add_vline(x=a["detection"], line=dict(color="#c0392b", dash="dash", width=1))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=f"{unite} par jour", legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig


def onglet_derives(res):
    alertes = [a for a in res["alertes"] if not a["masquee"]]
    m = res["meta"]
    c = st.columns(4)
    c[0].metric("Dérives retenues", len(alertes), help="Après persistance, double seuil et plancher d'enjeu.")
    c[1].metric("Surplus constaté", fr(m["total_constate"]["kwh"], 0, "kWh"), help="Estimé, « au moins » : la part antérieure au début détecté n'est pas comptée. Sans double compte PV / soutirage.")
    c[2].metric("Coût constaté (électricité)", fr(m["total_constate"]["chf"], 0, "CHF"),
                help=f"Le jeu ne donne un prix que pour l'électricité (0,27 CHF/kWh). {m['total_constate']['n_alertes_non_chiffrees_en_chf']} alertes (gaz, chaleur à distance, eau, solaire) "
                     "ne sont pas chiffrées en CHF : aucun prix n'est inventé.")
    c[3].metric("CO₂ direct constaté", fr(m["total_constate"]["t_co2_direct"], 2, "t"), help="Convention du jeu : gaz 2,086 kg/m³ ; électricité et CAD : 0 en direct sur site.")
    st.caption("Tous ces chiffres sont **estimés** par le moteur à partir de mesures ; aucun n'est généré par IA. Année 2025. "
               f"Les alertes viennent du moteur autonome (passé seulement). Le rapprochement avec le mensuel v2 ne sert qu'à vérifier après coup : "
               f"{m['n_non_confirmees']} alertes non confirmées restent affichées mais n'entrent pas dans les totaux.")
    if not alertes:
        st.info("Aucune dérive retenue.")
        return
    f1, f2, f3 = st.columns(3)
    sites = f1.multiselect("Site", sorted({f"{a['site']} · {a['nom_site']}" for a in alertes}))
    fluides = f2.multiselect("Fluide", sorted({a["fluide"] for a in alertes}))
    statuts = f3.multiselect("Statut", sorted({a["statut"] for a in alertes}))
    sel = [a for a in alertes if (not sites or f"{a['site']} · {a['nom_site']}" in sites) and (not fluides or a["fluide"] in fluides) and (not statuts or a["statut"] in statuts)]
    df = pd.DataFrame([{
        "Rang": a["rang"], "Site": f"{a['site']} · {a['nom_site']}", "Fluide": a["fluide"], "Dérive": TYPES.get(a["type"], a["type"]), "Depuis": a["debut"],
        "Jusqu'à": a["fin"], "Statut": a["statut"], "Écart %": a["ecart_pct"], "kWh (au moins)": a["constate"]["kwh"], "CHF (au moins)": a["constate"]["chf"],
        "CHF / mois": a["rythme_mensuel"]["chf"], "t CO₂ direct": a["constate"]["t_co2_direct"], "Confiance": a["confiance"], "Urgence": a["urgence"],
        "Vérification": a["rapprochement_v2"]["statut"], "id": a["id"]} for a in sel])
    st.dataframe(df.drop(columns="id"), hide_index=True, use_container_width=True)
    st.caption(f"Tri : dérives en cours d'abord, puis priorité ; les alertes sans prix dans le jeu viennent ensuite, classées par kWh par mois. {m['formule_priorite']} La confiance est un indice d'ordonnancement, pas une probabilité calibrée.")
    st.download_button("Télécharger la liste (CSV)", df.to_csv(index=False, sep=";").encode("utf-8-sig"), "derives.csv", "text/csv")
    if not sel:
        return
    choix = st.selectbox("Fiche dérive", [a["id"] for a in sel], format_func=lambda i: next(f"{a['rang']}. {a['site']} {a['nom_site']} — {a['fluide']} — {TYPES.get(a['type'], a['type'])}" for a in sel if a["id"] == i))
    a = next(x for x in sel if x["id"] == choix)
    st.subheader(f"{a['site']} · {a['nom_site']} — {a['libelle']}")
    k = st.columns(4)
    k[0].metric("Surplus constaté (au moins)", fr(a["constate"]["quantite"], 0, a["constate"]["unite"]), f"{a['ecart_pct']:+.1f} %", delta_color="inverse")
    k[1].metric("Coût constaté", fr(a["constate"]["chf"], 0, "CHF"))
    k[2].metric("Rythme constaté", fr(a["rythme_mensuel"]["chf"], 0, "CHF/mois"))
    k[3].metric("Confiance · urgence", f"{a['confiance']:.2f} · {a['urgence']}")
    st.plotly_chart(graphique(res["tables"][a["compteur"]], a, a["observe"]["unite"]), use_container_width=True)
    st.caption(f"Zone rouge : dérive du {a['debut']} au {a['fin']} ({a['statut']}, datation {a['datation']}). Trait pointillé rouge : détection ({a['detection']}). "
               f"Mesuré : {STATUT['mesuré']} · attendu et bande : {STATUT['estimé']}.")
    rv = a["rapprochement_v2"]
    message = f"**Vérification a posteriori : {rv['statut']}.** {rv['detail']}"
    if "chiffrage_de_controle" in rv:
        message += f" Chiffrage de contrôle : {fr(rv['chiffrage_de_controle']['kwh'], 0, 'kWh')}, {fr(rv['chiffrage_de_controle']['chf'], 0, 'CHF')} ({rv['chiffrage_de_controle']['definition']})."
    (st.success if rv["confirme"] else st.warning if rv["confirme"] is False else st.info)(message)
    st.markdown("**Pourquoi ce n'est pas la vie normale**")
    st.write(a["pourquoi_pas_normal"])
    g, d = st.columns(2)
    with g:
        st.markdown("**Facteurs pris en compte**")
        for f in a["facteurs_pris_en_compte"]:
            st.markdown(f"- {f}")
        st.markdown(f"**Référence** : `{a['reference']}`  \n**Détection** : {a['source_detection']}")
    with d:
        st.markdown("**Chiffrage et hypothèses**")
        st.markdown(f"- Mesuré : {fr(a['observe']['valeur'], 0, a['observe']['unite'])} ({STATUT['mesuré']})")
        st.markdown(f"- Attendu : {fr(a['attendu']['valeur'], 0, a['observe']['unite'])} ({STATUT['estimé']})")
        st.markdown(f"- Constaté : {fr(a['constate']['kwh'], 0, 'kWh')}, {fr(a['constate']['chf'], 0, 'CHF')}, {fr(a['constate']['t_co2_direct'], 3, 't CO₂ direct')} ({STATUT['estimé']}, au moins)")
        st.markdown(f"- Borne prudente (hors bande à 95 %) : {fr(a['constate']['borne_prudente']['kwh'], 0, 'kWh')}, {fr(a['constate']['borne_prudente']['chf'], 0, 'CHF')}")
        for h in a["constate"]["hypotheses"]:
            st.markdown(f"- {h}")
        if "double_compte" in a:
            st.markdown(f"- Sans double compte avec {a['double_compte']['avec']} : {fr(a['double_compte']['chf_retenu_au_total'], 0, 'CHF')} retenus au total ({a['double_compte']['regle']})")
    with st.expander("Projection sur 12 mois si rien n'est fait (hors score)"):
        p = a["projection_12_mois"]
        st.write(f"{fr(p['kwh'], 0, 'kWh')} · {fr(p['chf'], 0, 'CHF')} — hypothèse : {p['hypothese']}. Cette projection n'entre ni dans la priorité ni dans la gravité.")
    with st.expander("Indicateurs calculés et alertes liées"):
        st.json({"indicateurs": a["indicateurs"], "alertes liées (même site, même période)": a["liens"], "jours jugés": a["jours_juges"], "z moyen": a["z_moyen"]})


def bloc_mensuel(res):
    mm = res.get("mensuel")
    if not mm:
        return
    st.divider()
    st.subheader("Couche mensuelle 2021-2025 : tout le parc")
    cv = mm["couverture"]
    st.caption(f"Moteur autonome, passé seulement, rejoué mois par mois sur {mm['n_series_jugees']} séries de {cv['sites_avec_au_moins_une_serie_jugee']} sites sur {cv['sites_du_parc']} : "
               f"{cv['gaz']} gaz et {cv['chaleur_a_distance']} chaleur à distance (signature par degrés-jours), {cv['electricite']} électricité et {cv['eau']} eau "
               f"(niveau du même mois des années précédentes), {cv['cop']} pompes à chaleur (COP à température égale). Alerte = deux mois consécutifs hors bande et à plus de 10 %. "
               f"Non jugés : {cv['non_juges']}. La part 2025 de ces alertes entre dans les totaux du haut de page ; pas de second relevé pour les vérifier ; causes non proposées.")
    if mm["alertes"]:
        st.dataframe(pd.DataFrame([{"Série": a["compteur"], "Site": a["nom_site"], "Dérive": a["type"].replace("_", " "), "Du": a["debut"], "Au": a["fin"], "Statut": a["statut"],
                                    "Écart %": a["ecart_pct"], "kWh (au moins)": a["constate"]["kwh"], "CHF (au moins)": a["constate"]["chf"],
                                    "t CO₂ direct": a["constate"]["t_co2_direct"], "dont t CO₂ en 2025": a["constate_2025"]["t_co2_direct"],
                                    "COP mesuré / attendu": f"{a['cop']['mesure']} / {a['cop']['attendu']}" if "cop" in a else ""} for a in mm["alertes"]]),
                     hide_index=True, use_container_width=True)
        st.caption("CHF vide = non chiffré : le jeu ne donne un prix que pour l'électricité (0,27 CHF/kWh).")
    if mm.get("cop_par_an"):
        st.markdown("**COP annuel mesuré des pompes à chaleur équipées d'un compteur de chaleur** (chaleur produite / électricité de la PAC, 🟢 mesuré)")
        st.dataframe(pd.DataFrame(mm["cop_par_an"]).T.rename_axis("Site").reset_index(), hide_index=True)
    ex = pd.DataFrame(mm["expliques_par_la_meteo"])
    if len(ex):
        st.markdown(f"**Pourquoi la météo change la décision** : {mm['n_expliques']} mois dépassent de 20 % la médiane du même mois des années précédentes "
                    "tout en restant dans la bande une fois les degrés-jours pris en compte. Une référence seulement saisonnière les aurait signalés.")
        st.dataframe(ex.rename(columns={"compteur": "Série", "nom_site": "Site", "mois": "Mois", "ecart_mediane_meme_mois_pct": "Écart à la médiane du même mois %",
                                        "ecart_a_dj_egaux_pct": "Écart à degrés-jours égaux %", "dj_du_mois": "Degrés-jours du mois"}), hide_index=True, use_container_width=True, height=240)


def onglet_causes(res):
    from src.causes.moteur import MENTION, fiche_markdown

    alertes = [a for a in res["alertes"] if not a["masquee"]]
    if not alertes:
        st.info("Aucune dérive retenue.")
        return
    st.markdown(f"Pour chaque dérive : causes classées par plausibilité, avec les indices calculés **pour** et **contre**. **{MENTION}.** "
                "Textes produits par gabarits déterministes, sans IA.")
    choix = st.selectbox("Dérive", [a["id"] for a in alertes], key="cause",
                         format_func=lambda i: next(f"{a['rang']}. {a['site']} {a['nom_site']} — {a['fluide']} — {a.get('signature', a['type'])}" for a in alertes if a["id"] == i))
    a = next(x for x in alertes if x["id"] == choix)
    st.subheader(f"{a['site']} · {a['nom_site']} — {a.get('signature', a['type'])}")
    st.write(a["pourquoi_pas_normal"])
    for k, c in enumerate(a["causes"], 1):
        with st.container(border=True):
            g, d = st.columns([3, 1])
            g.markdown(f"**{k}. {c['cause']}**")
            d.progress(c["plausibilite"], text=f"plausibilité {c['plausibilite']:.2f}".replace(".", ","))
            if c["pour"]:
                st.markdown("✅ **Pour** : " + " ; ".join(c["pour"]))
            if c["contre"]:
                st.markdown("⚠️ **Contre** : " + " ; ".join(c["contre"]))
            if not c["pour"] and not c["contre"]:
                st.markdown("_Aucun indice calculé ne départage cette hypothèse._")
            st.markdown("**À vérifier sur place**")
            for v in c["verifications"]:
                st.checkbox(v, key=f"{a['id']}-{k}-{v}")
            st.markdown("**Action corrective** : " + " ; ".join(c["actions"]))
            st.caption(c["statut"])
    gain = a.get("gain_estime")
    if gain:
        st.markdown(f"**Gain attendu** : au plus {fr(gain['chf_par_mois'], 0, 'CHF')} par mois ({STATUT['estimé']}). {gain['definition'].capitalize()}.")
    md = fiche_markdown(a)
    c1, c2 = st.columns(2)
    c1.download_button("Fiche d'intervention (Markdown)", md.encode("utf-8"), f"fiche-{a['id']}.md", "text/markdown")
    html = "<!doctype html><html lang='fr'><meta charset='utf-8'><title>Fiche " + a["id"] + "</title><style>body{font:15px/1.5 sans-serif;max-width:46em;margin:2em auto;white-space:pre-wrap}</style><body>" \
           + md.replace("&", "&amp;").replace("<", "&lt;") + "</body></html>"
    c2.download_button("Fiche imprimable (HTML)", html.encode("utf-8"), f"fiche-{a['id']}.html", "text/html")
    with st.expander("Aperçu de la fiche"):
        st.markdown(md)


def onglet_qualite(res):
    st.markdown("Un défaut de donnée n'est **pas** une dérive : la période concernée n'est pas jugée et ne produit aucune alerte énergie.")
    d = pd.DataFrame(res["defauts"])
    if d.empty:
        st.success("Aucun défaut détecté.")
        return
    d["periodes"] = d["periodes"].map(lambda p: " ; ".join(p[:6]) + (" …" if len(p) > 6 else ""))
    lots = {"rc_v2": "Rive-Claire v2 (mensuel)", "rc_elec": "Électricité 15 min", "rc_fluides": "Fluides / PV / CAD", "rc_s04": "École du Centre S04 (sources brutes)"}
    d["lot"] = d["lot"].map(lots)
    c = st.columns(3)
    c[0].metric("Défauts de données", len(d))
    c[1].metric("Séries concernées", d["compteur"].nunique())
    c[2].metric("Dont gravité élevée", int((d["gravite"] == "élevée").sum()))
    st.dataframe(d[["lot", "compteur", "type", "gravite", "periodes", "n", "detail", "correction"]].rename(columns={
        "lot": "Lot", "compteur": "Série", "type": "Défaut", "gravite": "Gravité", "periodes": "Périodes", "n": "Nombre", "detail": "Constat (mesuré)", "correction": "Ce qu'il faut corriger"}),
        hide_index=True, use_container_width=True)


def onglet_sains(res):
    st.markdown("Séries suivies sur lesquelles le moteur **se tait** : aucun épisode retenu, aucun écart mensuel net, aucun défaut de gravité élevée.")
    s = pd.DataFrame(res["sains"])
    st.metric("Séries saines", f"{len(s)} sur {len(res['resume'])} suivies")
    if len(s):
        st.dataframe(s[["id", "nom_site", "fluide", "jours_juges", "dispersion_pct", "reference"]].rename(columns={
            "id": "Série", "nom_site": "Site", "fluide": "Fluide", "jours_juges": "Jours jugés", "dispersion_pct": "Dispersion journalière %", "reference": "Référence"}),
            hide_index=True, use_container_width=True)
        choix = st.selectbox("Voir une série saine", list(s["id"]))
        st.plotly_chart(graphique(res["tables"][choix], None, s.set_index("id").loc[choix, "unite"]), use_container_width=True)
    autres = res["autres_ecarts"]
    if autres:
        st.markdown("**Écarts dans le sens non surveillé** (baisses de consommation, hausses de production) : listés, non comptés comme dérives.")
        st.dataframe(pd.DataFrame([{"Série": a["compteur"], "Site": a["nom_site"], "Du": a["debut"], "Au": a["fin"], "Écart %": a["ecart_pct"], "Sens": a["sens"]} for a in autres]), hide_index=True)


def onglet_performance(res):
    from src.config import DOSSIER_SORTIES

    ev = res["evaluation"]
    c = st.columns(4)
    c[0].metric("Dérives de contrôle trouvées", f"{ev['trouvees']} sur {ev['n_derives_de_controle']}")
    c[1].metric("Fausses alertes", f"{len(ev['fausses_alertes'])} sur {ev['n_alertes']}")
    c[2].metric("Précision", f"{100 * ev['precision']:.0f} %")
    c[3].metric("Délai médian", "—" if ev["delai_median_jours"] is None else f"{ev['delai_median_jours']:.0f} j")
    st.markdown(res["evaluation_md"])
    f = DOSSIER_SORTIES / "evaluation_banc.md"
    if f.exists():
        st.markdown(f.read_text(encoding="utf-8"))
    else:
        st.info("Banc synthétique non exécuté sur cette machine : `python -m src.banc`.")


def onglet_methode(res):
    m = res["meta"]
    st.markdown("""
**Comment une dérive est décidée.** Qualité d'abord (un jour n'est jugé que si 18 h sur 24 sont mesurées). L'attendu du jour est appris sur le passé seulement :
historique mensuel 2021-2024 (signature par degrés-jours, niveau du même mois, ratio de performance du PV), puis jours sains de 2025 sur fenêtre glissante,
à type de jour et météo égaux. Une alerte exige un biais cumulé (CUSUM), de la persistance (10 jours sur 14) **et** un écart cumulé de 10 % au moins ;
la référence est gelée au début de la dérive.

**Vérification, à part.** Le mensuel v2 de 2025 contient la part normale : il n'entre jamais dans la détection. Il sert après coup à dire si une alerte est
« confirmée par le rapprochement mensuel », à donner un chiffrage de contrôle, et à mesurer les fausses alertes du moteur (onglet Performance).
""")
    st.markdown(f"**Priorité.** {m['formule_priorite']}  \n**Confiance.** {m['formule_confiance']}")
    st.markdown("**Limites, dites honnêtement**")
    ev = res["evaluation"]
    st.markdown(f"- Le moteur autonome lève {len(ev['fausses_alertes'])} fausses alertes sur {ev['n_alertes']} (non confirmées par le rapprochement), surtout aux changements de saison : "
                "son historique porte un biais de 5 à 10 % d'une année à l'autre. Elles sont affichées comme telles, pas cachées.\n"
                "- Les dérives lentes ou inférieures à 10 % lui échappent ou sont datées tard ; la précision sur un vrai parc n'est pas mesurable ici.\n"
                "- Les causes viennent d'une base de règles écrite par l'équipe, non validée par un exploitant : ce sont des hypothèses à vérifier sur place.")
    for x in m["non_couvert"]:
        st.markdown(f"- Non couvert : {x}")
    st.markdown("**Prix et facteurs utilisés** (config/tarifs.yaml)")
    st.dataframe(pd.DataFrame([{"Vecteur": k, **v} for k, v in charger_yaml("tarifs")["prix"].items()]), hide_index=True, use_container_width=True)


def main():
    st.set_page_config(page_title="Détecteur de dérives · Ergonia", page_icon="📉", layout="wide")
    charger_env()
    st.title("Détecteur de dérives multifluides")
    st.caption("Équipe Ergonia · Energ-IACK 2026 · Défi 4 — commune fictive de Rive-Claire, année 2025")
    try:
        res = resultats()
    except ErreurConnecteur as exc:
        st.error(f"Données indisponibles : {exc}")
        st.info("L'application n'embarque aucune donnée. Configurez `DATA_SOURCE_URL` (source distante) ou `DATA_LOCAL_DIR` (dossier local des fichiers ouverts), "
                "dans `.env` en local ou dans les secrets du déploiement, puis relancez.")
        st.stop()
    m = res["meta"]
    with st.sidebar:
        st.markdown("### Données")
        st.write(f"Source : {m['provenance']['source']}")
        st.write(f"Récupération : {m['provenance']['recuperation'] or '—'}")
        st.write(f"Calcul : {m['calcule_le']}")
        st.write(f"{m['n_series_pas_fin']} séries suivies au pas fin")
        if st.button("Recalculer"):
            resultats.clear()
            st.rerun()
        st.markdown("### IA")
        st.write("LLM activé" if (param("LLM_ACTIF") or "").lower() in ("1", "true", "oui") else "LLM désactivé : textes par gabarits déterministes.")
    t1, t2, t3, t4, t6, t5 = st.tabs(["1 · Dérives", "2 · Causes et solutions", "Qualité des données", "Sites sains", "Performance", "Méthode et limites"])
    with t6:
        onglet_performance(res)
    with t1:
        onglet_derives(res)
        bloc_mensuel(res)
    with t2:
        onglet_causes(res)
    with t3:
        onglet_qualite(res)
    with t4:
        onglet_sains(res)
    with t5:
        onglet_methode(res)
    st.divider()
    att = m["attributions"]
    st.caption("Données : « " + " » · « ".join(att[k] for k in ("rc_v2", "rc_elec", "rc_fluides", "rc_s04")) + f" » · {att['meteo']}. "
               f"Licence des données : [CC BY 4.0]({charger_yaml('sources')['licence_url']}). Code sous licence MIT (Équipe Ergonia). "
               "Chiffres d'impact = surplus estimés ; causes et économies à vérifier sur le terrain.")
