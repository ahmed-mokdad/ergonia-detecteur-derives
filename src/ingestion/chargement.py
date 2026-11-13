"""Chargement des jeux ouverts à travers un connecteur.

Règles d'import : tout est lu en texte (identifiants, périodes AAAA-MM, horodatages), puis converti
explicitement. Les horodatages locaux (avec décalage +01:00 / +02:00) sont convertis en UTC ;
la date et l'heure locales sont tirées du texte d'origine (Europe/Zurich).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

FEUILLES_V2 = ["Batiments", "Installations", "Compteurs", "Mesures", "Ref_Climat", "Ref_Climat_Normale",
               "Ref_Conversion", "Ref_CO2"]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _csv(chemin) -> pd.DataFrame:
    return pd.read_csv(chemin, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)


def preparer_horodate(df: pd.DataFrame, col: str = "horodatage") -> pd.DataFrame:
    """Ajoute utc (instant), date et heure locales (tirées du texte), sans rien interpoler."""
    df = df.rename(columns={col: "t"})
    # instant UTC = heure locale lue − décalage lu dans le texte (+01:00 hiver, +02:00 été)
    local = pd.to_datetime(df["t"].str.slice(0, 19), format="%Y-%m-%dT%H:%M:%S", errors="coerce")
    signe = df["t"].str.slice(19, 20).map({"+": 1, "-": -1}).fillna(1)
    decalage = pd.to_timedelta(signe * (pd.to_numeric(df["t"].str.slice(20, 22), errors="coerce").fillna(0) * 60
                                        + pd.to_numeric(df["t"].str.slice(23, 25), errors="coerce").fillna(0)), unit="min")
    df["utc"] = (local - decalage).dt.tz_localize("UTC")
    df["date"] = df["t"].str.slice(0, 10)
    df["heure"] = pd.to_numeric(df["t"].str.slice(11, 13), errors="coerce")
    return df


@dataclass
class Jeu:
    batiments: pd.DataFrame
    installations: pd.DataFrame
    compteurs: pd.DataFrame
    mesures: pd.DataFrame
    climat: pd.DataFrame
    climat_normale: pd.DataFrame
    conversion: pd.DataFrame
    co2: pd.DataFrame
    calendrier: pd.DataFrame
    compteurs_elec: pd.DataFrame
    elec: pd.DataFrame
    pv: pd.DataFrame
    fluides: pd.DataFrame
    cad: pd.DataFrame
    s04: dict = field(default_factory=dict)
    catalogue: pd.DataFrame = field(default_factory=pd.DataFrame)

    def referentiel(self, nom: str) -> pd.DataFrame:
        if nom not in ("batiments", "installations", "compteurs", "climat", "climat_normale", "conversion", "co2",
                       "calendrier", "compteurs_elec"):
            raise KeyError(f"Référentiel inconnu : {nom}")
        return getattr(self, nom).copy()

    def serie(self, id_serie: str, debut: str | None = None, fin: str | None = None) -> pd.DataFrame:
        for table, col_v, col_t in ((self.elec, "valeur", "t"), (self.pv, "valeur", "t"), (self.cad, "energie_kwh", "t"),
                                    (self.fluides, "valeur", "date")):
            sel = table[table["id_compteur"] == id_serie]
            if len(sel):
                out = sel[[col_t, col_v]].rename(columns={col_t: "t", col_v: "valeur"})
                break
        else:
            sel = self.mesures[self.mesures["id_compteur"] == id_serie]
            out = sel[["mois", "valeur"]].rename(columns={"mois": "t"})
        if debut:
            out = out[out["t"] >= debut]
        if fin:
            out = out[out["t"] <= fin + "~"]
        return out.reset_index(drop=True)

    def facteur_gaz(self) -> dict:
        """kWh PCS par m3, par mois AAAA-MM (Ref_Conversion)."""
        c = self.conversion[self.conversion["vecteur"] == "gaz"]
        return dict(zip(c["mois"], c["facteur"]))


def charger_v2(chemin) -> dict:
    f = pd.read_excel(chemin, sheet_name=FEUILLES_V2, dtype=str, keep_default_na=False)
    bat, inst, cpt, mes = f["Batiments"], f["Installations"], f["Compteurs"], f["Mesures"]
    bat["sre_m2"] = _num(bat["sre_m2"])
    inst["puissance_kw"] = _num(inst["puissance_kw"])
    mes["valeur"] = _num(mes["valeur"])
    mes["energie_kwh"] = _num(mes["energie_kwh"])
    cli = f["Ref_Climat"]
    for c in cli.columns[1:]:
        cli[c] = _num(cli[c])
    nor = f["Ref_Climat_Normale"]
    for c in nor.columns:
        nor[c] = _num(nor[c])
    conv = f["Ref_Conversion"]
    conv["facteur"] = _num(conv["facteur"])
    co2 = f["Ref_CO2"]
    co2["kg_co2_par_unite"] = _num(co2["kg_co2_par_unite"])
    return dict(batiments=bat, installations=inst, compteurs=cpt, mesures=mes, climat=cli, climat_normale=nor,
                conversion=conv, co2=co2)


def charger_calendrier(chemin) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = pd.read_excel(chemin, sheet_name=["Compteurs", "Calendrier_2025"], dtype=str, keep_default_na=False)
    cal = f["Calendrier_2025"].rename(columns={"quarts_d_heure": "quarts", "temperature_moyenne_c": "t_moy",
                                               "rayonnement_global_w_m2": "ray"})
    cal["date"] = cal["date"].str.slice(0, 10)
    cal["vacances"] = cal["vacances_scolaires"].str.lower().eq("oui")
    for c in ("quarts", "t_moy", "ray"):
        cal[c] = _num(cal[c])
    cpt = f["Compteurs"]
    cpt["sre_m2"] = _num(cpt["sre_m2"])
    cpt["photovoltaique_kwc"] = _num(cpt["photovoltaique_kwc"])
    return cal[["date", "jour", "type", "vacances", "quarts", "t_moy", "ray"]], cpt


def charger_15min(chemin) -> pd.DataFrame:
    df = preparer_horodate(_csv(chemin))
    df["valeur"] = _num(df["energie_kwh"])
    return df[["t", "utc", "date", "heure", "id_compteur", "id_site", "valeur"]]


def charger_fluides(chemin) -> pd.DataFrame:
    df = _csv(chemin)
    df["valeur"] = _num(df["valeur"])
    return df


def charger_cad(chemin) -> pd.DataFrame:
    df = preparer_horodate(_csv(chemin))
    for c in ("energie_kwh", "debit_m3_h", "t_aller_c", "t_retour_c"):
        df[c] = _num(df[c])
    return df


def charger_s04(connecteur) -> dict:
    s04 = {}
    sir = _csv(connecteur.ouvrir("s04_sir"))
    for c in ("index_debut", "index_fin", "quantite"):
        sir[c] = _num(sir[c])
    s04["sir"] = sir
    s04["courbe_2022"] = preparer_horodate(_csv(connecteur.ouvrir("s04_courbe_2022")))
    s04["courbe_2022"]["valeur"] = _num(s04["courbe_2022"]["energie_kwh"])
    ond = _csv(connecteur.ouvrir("s04_onduleur"))
    ond["production_kwh"] = _num(ond["production_kwh"])
    s04["onduleur"] = ond
    maz = _csv(connecteur.ouvrir("s04_mazout"))
    maz["quantite_litres"] = _num(maz["quantite_litres"])
    s04["mazout"] = maz
    rel = pd.read_excel(connecteur.ouvrir("s04_releves"), sheet_name=["Relevés", "Synthèse"], dtype=str,
                        keep_default_na=False, header=1)
    s04["releves"], s04["synthese"] = rel["Relevés"], rel["Synthèse"]
    return s04


def _catalogue(j: Jeu) -> pd.DataFrame:
    lignes = []
    for table, pas, fluide in ((j.elec, "15 min", "électricité"), (j.pv, "15 min", None), (j.cad, "heure", "chaleur à distance")):
        for i, g in table.groupby("id_compteur"):
            fl = fluide or ("électricité solaire" if i.endswith("-PV") else "électricité (injection)")
            lignes.append(dict(id_serie=i, id_site=g["id_site"].iloc[0], fluide=fl, pas=pas, unite="kWh"))
    for i, g in j.fluides.groupby("id_compteur"):
        lignes.append(dict(id_serie=i, id_site=g["id_site"].iloc[0], fluide=g["fluide"].iloc[0], pas="jour", unite=g["unite"].iloc[0]))
    for _, c in j.compteurs.iterrows():
        lignes.append(dict(id_serie=c["id_compteur"], id_site=c["id_site"], fluide=c["fluide"], pas="mois", unite=c["unite"]))
    return pd.DataFrame(lignes)


def charger_jeu(connecteur, avec_s04: bool = True) -> Jeu:
    v2 = charger_v2(connecteur.ouvrir("rc_v2"))
    cal, cpt_elec = charger_calendrier(connecteur.ouvrir("elec_classeur"))
    j = Jeu(
        **v2,
        calendrier=cal,
        compteurs_elec=cpt_elec,
        elec=charger_15min(connecteur.ouvrir("elec_15min")),
        pv=charger_15min(connecteur.ouvrir("pv_15min")),
        fluides=charger_fluides(connecteur.ouvrir("fluides_jour")),
        cad=charger_cad(connecteur.ouvrir("cad_heure")),
    )
    if avec_s04:
        j.s04 = charger_s04(connecteur)
    j.catalogue = _catalogue(j)
    return j
