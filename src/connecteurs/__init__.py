"""Connecteurs de données : l'application n'embarque aucune donnée, elle les lit à l'exécution."""
from __future__ import annotations

from ..config import charger_env, param
from .base import Connecteur, ErreurConnecteur, FichierNonAutorise, IntegriteInvalide, SourceInjoignable
from .http import ConnecteurHTTP
from .local import ConnecteurLocal

__all__ = [
    "Connecteur", "ConnecteurHTTP", "ConnecteurLocal", "ErreurConnecteur", "FichierNonAutorise",
    "IntegriteInvalide", "SourceInjoignable", "creer_connecteur",
]


def creer_connecteur() -> Connecteur:
    """Choisit le connecteur d'après DATA_CONNECTEUR, sinon d'après ce qui est configuré."""
    charger_env()
    choix = (param("DATA_CONNECTEUR") or "").lower()
    if choix == "http" or (not choix and param("DATA_SOURCE_URL") and not param("DATA_LOCAL_DIR")):
        return ConnecteurHTTP()
    if choix in ("", "local"):
        return ConnecteurLocal()
    raise SourceInjoignable(f"DATA_CONNECTEUR inconnu : {choix} (attendu : local ou http).")
