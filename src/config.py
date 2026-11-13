"""Configuration : fichiers YAML de config/ et paramètres d'environnement (.env, st.secrets).

Aucune clé, aucune URL et aucun chemin de données n'est écrit dans le code.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_CACHE = RACINE / ".cache"
DOSSIER_SORTIES = RACINE / "outputs"
DOSSIER_LOGS = RACINE / "logs"


def charger_env(chemin: Path | None = None) -> None:
    """Lit un fichier .env local (clé=valeur) sans écraser l'environnement existant."""
    chemin = chemin or RACINE / ".env"
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeur = valeur.strip().strip('"').strip("'")
        if valeur and cle.strip() not in os.environ:
            os.environ[cle.strip()] = valeur


def param(nom: str, defaut: str | None = None) -> str | None:
    """Paramètre lu dans l'environnement, puis dans st.secrets (déploiement en ligne)."""
    valeur = os.environ.get(nom)
    if valeur:
        return valeur
    try:  # st.secrets n'existe que sous Streamlit, et seulement s'il est configuré
        import streamlit as st

        if nom in st.secrets:
            return str(st.secrets[nom])
    except Exception:
        pass
    return defaut


@lru_cache(maxsize=None)
def charger_yaml(nom: str) -> dict:
    with open(RACINE / "config" / f"{nom}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def seuils() -> dict:
    return charger_yaml("seuils")


def tarifs() -> dict:
    return charger_yaml("tarifs")
