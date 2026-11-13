"""ConnecteurLocal : lit un dossier HORS du dépôt désigné par DATA_LOCAL_DIR (développement)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import RACINE, param
from .base import Connecteur, SourceInjoignable


class ConnecteurLocal(Connecteur):
    nom = "local"

    def __init__(self, dossier: str | Path | None = None, sources: dict | None = None, autoriser_dans_depot: bool = False):
        super().__init__(sources)
        dossier = dossier or param("DATA_LOCAL_DIR")
        if not dossier:
            raise SourceInjoignable("DATA_LOCAL_DIR n'est pas défini (voir .env.example).")
        self.dossier = Path(dossier).expanduser().resolve()
        if not self.dossier.is_dir():
            raise SourceInjoignable(f"Le dossier de données n'existe pas : {self.dossier}")
        if not autoriser_dans_depot and (self.dossier == RACINE or RACINE in self.dossier.parents):
            raise SourceInjoignable("Le dossier de données doit être HORS du dépôt de code.")

    def _obtenir(self, cle: str, entree: dict) -> Path:
        chemin = (self.dossier / entree["chemin"]).resolve()
        if self.dossier not in chemin.parents:
            raise SourceInjoignable("Chemin hors du dossier de données.")
        if not chemin.is_file():
            raise SourceInjoignable(f"Fichier ouvert manquant dans DATA_LOCAL_DIR : {entree['chemin']}")
        return chemin

    def provenance(self) -> dict:
        dates = [datetime.fromtimestamp(p.stat().st_mtime) for p in self._verifies.values()]
        return {
            "connecteur": "local",
            "source": "dossier local hors dépôt (DATA_LOCAL_DIR)",
            "recuperation": max(dates).strftime("%Y-%m-%d %H:%M") if dates else None,
        }
