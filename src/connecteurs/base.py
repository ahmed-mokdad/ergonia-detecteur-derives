"""Interface unique des connecteurs de données.

Un connecteur ne donne accès qu'aux fichiers de la liste blanche (config/sources.yaml),
après vérification de leur empreinte SHA-256. Tout autre nom ou chemin est refusé.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import charger_yaml


class ErreurConnecteur(Exception):
    """Erreur générique d'accès aux données."""


class FichierNonAutorise(ErreurConnecteur):
    """Le fichier demandé n'est pas dans la liste blanche des jeux ouverts."""


class IntegriteInvalide(ErreurConnecteur):
    """L'empreinte SHA-256 ne correspond pas à celle attendue."""


class SourceInjoignable(ErreurConnecteur):
    """La source de données ne répond pas ou n'est pas configurée."""


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class Connecteur(ABC):
    nom = "base"

    def __init__(self, sources: dict | None = None):
        self.sources = sources or charger_yaml("sources")
        self._verifies: dict[str, Path] = {}
        self._jeu = None

    # ----------------------------------------------------------- liste blanche
    def entree(self, cle: str) -> dict:
        fichiers = self.sources.get("fichiers", {})
        if cle not in fichiers:
            raise FichierNonAutorise(f"« {cle} » n'est pas dans la liste blanche des fichiers ouverts.")
        e = fichiers[cle]
        chemin = str(e["chemin"])
        for motif in self.sources.get("motifs_interdits", []):
            if motif.lower() in chemin.lower():
                raise FichierNonAutorise(f"« {chemin} » correspond à un motif interdit ({motif}).")
        if ".." in Path(chemin).parts or Path(chemin).is_absolute():
            raise FichierNonAutorise(f"Chemin non relatif refusé : {chemin}")
        return e

    def cles(self) -> list[str]:
        return list(self.sources.get("fichiers", {}))

    @abstractmethod
    def _obtenir(self, cle: str, entree: dict) -> Path:
        """Rend un chemin local lisible pour ce fichier (sans vérifier l'empreinte)."""

    def ouvrir(self, cle: str) -> Path:
        """Chemin local d'un fichier de la liste blanche, empreinte vérifiée."""
        if cle in self._verifies:
            return self._verifies[cle]
        e = self.entree(cle)
        chemin = self._obtenir(cle, e)
        empreinte = sha256_fichier(chemin)
        if empreinte != e["sha256"]:
            self._rejeter(chemin)
            raise IntegriteInvalide(
                f"Empreinte SHA-256 inattendue pour « {e['chemin']} » : le fichier n'est pas celui du jeu ouvert."
            )
        self._verifies[cle] = chemin
        return chemin

    def _rejeter(self, chemin: Path) -> None:
        """Appelé quand un fichier échoue au contrôle d'intégrité (le cache HTTP le supprime)."""

    @abstractmethod
    def provenance(self) -> dict:
        """Source et date de récupération, affichées dans l'application."""

    # ------------------------------------------------------- interface métier
    def jeu(self):
        if self._jeu is None:
            from ..ingestion.chargement import charger_jeu

            self._jeu = charger_jeu(self)
        return self._jeu

    def lister_series(self):
        """Table des séries disponibles (identifiant, site, fluide, pas, unité)."""
        return self.jeu().catalogue.copy()

    def lire_serie(self, id_serie: str, debut: str | None = None, fin: str | None = None):
        """Série au pas le plus fin disponible : colonnes t (texte local), valeur."""
        return self.jeu().serie(id_serie, debut, fin)

    def lire_referentiel(self, nom: str):
        """Référentiel : batiments, installations, compteurs, climat, calendrier, conversion, co2…"""
        return self.jeu().referentiel(nom)
