"""ConnecteurHTTP : télécharge les fichiers ouverts depuis DATA_SOURCE_URL, avec contrôle SHA-256.

Le cache vit dans .cache/ (ignoré par git, purgeable par `python -m src.outils purge`).
Si la source ne répond pas, une erreur claire est levée : jamais de repli sur des données cachées dans le code.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests

from ..config import DOSSIER_CACHE, param
from .base import Connecteur, SourceInjoignable, sha256_fichier


class ConnecteurHTTP(Connecteur):
    nom = "http"

    def __init__(self, url_base: str | None = None, sources: dict | None = None, cache: Path | None = None, delai_s: int = 60):
        super().__init__(sources)
        url_base = url_base or param("DATA_SOURCE_URL")
        if not url_base:
            raise SourceInjoignable("DATA_SOURCE_URL n'est pas défini (voir .env.example ou les secrets du déploiement).")
        self.url_base = url_base.rstrip("/")
        self.cache = Path(cache) if cache else DOSSIER_CACHE / "donnees"
        self.delai_s = delai_s
        self._journal = self.cache / "provenance.json"

    def _lire_journal(self) -> dict:
        if self._journal.exists():
            try:
                return json.loads(self._journal.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _obtenir(self, cle: str, entree: dict) -> Path:
        cible = self.cache / entree["chemin"]
        if cible.is_file() and sha256_fichier(cible) == entree["sha256"]:
            return cible
        url = entree.get("url") or f"{self.url_base}/{quote(entree['chemin'])}"
        cible.parent.mkdir(parents=True, exist_ok=True)
        tmp = cible.with_suffix(cible.suffix + ".part")
        try:
            with requests.get(url, stream=True, timeout=self.delai_s) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloc in r.iter_content(1 << 20):
                        f.write(bloc)
        except requests.RequestException as exc:
            tmp.unlink(missing_ok=True)
            raise SourceInjoignable(
                f"Source distante injoignable pour « {entree['chemin']} » ({type(exc).__name__}). "
                "Vérifiez DATA_SOURCE_URL ou pointez DATA_LOCAL_DIR vers un dossier local des fichiers ouverts."
            ) from exc
        tmp.replace(cible)
        journal = self._lire_journal()
        journal[cle] = {"recuperation": datetime.now().strftime("%Y-%m-%d %H:%M"), "hote": urlsplit(url).netloc}
        self._journal.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")
        return cible

    def _rejeter(self, chemin: Path) -> None:
        chemin.unlink(missing_ok=True)

    def provenance(self) -> dict:
        journal = self._lire_journal()
        dates = [v["recuperation"] for k, v in journal.items() if k in self._verifies]
        return {
            "connecteur": "http",
            "source": f"source distante ({urlsplit(self.url_base).netloc})",  # hôte seulement, jamais l'URL complète
            "recuperation": max(dates) if dates else None,
        }
