"""Commandes utilitaires (remplacent make) : `python -m src.outils purge | verifier | demo`."""
from __future__ import annotations

import shutil
import subprocess
import sys

from .config import DOSSIER_CACHE, DOSSIER_LOGS, DOSSIER_SORTIES, RACINE


def purge() -> None:
    """Supprime le cache des données et les résultats calculés."""
    for d in (DOSSIER_CACHE, DOSSIER_SORTIES, DOSSIER_LOGS):
        if d.exists():
            shutil.rmtree(d)
            print(f"supprimé : {d.name}/")


def verifier() -> None:
    """Vérifie que la source configurée fournit bien tous les fichiers ouverts attendus (empreintes SHA-256)."""
    from .connecteurs import creer_connecteur

    c = creer_connecteur()
    for cle in c.cles():
        c.ouvrir(cle)
        print(f"ok  {cle}")
    print(c.provenance())


def demo() -> None:
    """Récupère les données par le connecteur, calcule, puis lance l'application (sans LLM)."""
    from .pipeline import main as calculer

    calculer()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(RACINE / "streamlit_app.py")], check=False)


if __name__ == "__main__":
    commandes = {"purge": purge, "verifier": verifier, "demo": demo}
    if len(sys.argv) != 2 or sys.argv[1] not in commandes:
        sys.exit("usage : python -m src.outils [purge|verifier|demo]")
    commandes[sys.argv[1]]()
