"""Emplacement d'un futur ConnecteurAPI (API d'un distributeur ou d'un EDM communal).

Pour brancher ses propres données, une commune implémente les trois méthodes de l'interface
(`lister_series`, `lire_serie`, `lire_referentiel`) au-dessus de son système de télérelève :
le moteur de détection et l'application ne changent pas.
"""
from __future__ import annotations

from .base import Connecteur, SourceInjoignable


class ConnecteurAPI(Connecteur):
    nom = "api"

    def __init__(self, *args, **kwargs):
        raise SourceInjoignable("ConnecteurAPI n'est pas encore implémenté : c'est le point de branchement prévu pour la Ville.")

    def _obtenir(self, cle, entree):  # pragma: no cover
        raise NotImplementedError

    def provenance(self):  # pragma: no cover
        raise NotImplementedError
