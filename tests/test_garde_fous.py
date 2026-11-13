"""Garde-fous : aucune donnée, aucun fichier restreint, aucun secret dans le dépôt."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from src.connecteurs import ConnecteurLocal, FichierNonAutorise

RACINE = Path(__file__).resolve().parents[1]
IGNORES = {".venv", ".cache", "outputs", "logs", ".git", ".pytest_cache", "__pycache__", ".streamlit"}
EXT_DONNEES = {".csv", ".xlsx", ".xls", ".parquet", ".feather", ".pkl", ".pickle"}
MOTIFS_RESTREINTS = ("ville-de-gen", "vdg", "quanthome")
SECRETS = [
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),          # jeton de type JWT
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),                            # clé d'API
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]


def fichiers_du_depot() -> list[Path]:
    if shutil.which("git") and (RACINE / ".git").exists():
        r = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True)
        suivis = [RACINE / p for p in r.stdout.splitlines() if p]
        if suivis:
            return suivis
    return [p for p in RACINE.rglob("*") if p.is_file() and not (set(p.relative_to(RACINE).parts[:-1]) & IGNORES)
            and p.name != ".env"]


def test_aucun_fichier_de_donnees_dans_le_depot():
    fautifs = [str(p.relative_to(RACINE)) for p in fichiers_du_depot() if p.suffix.lower() in EXT_DONNEES]
    assert not fautifs, f"Fichiers de données dans le dépôt : {fautifs}"


def test_aucun_fichier_de_donnees_dans_src():
    fautifs = [str(p) for p in (RACINE / "src").rglob("*") if p.is_file() and p.suffix.lower() in EXT_DONNEES | {".json"}]
    assert not fautifs, f"Données embarquées dans src/ : {fautifs}"


def test_aucun_fichier_restreint():
    fautifs = [str(p.relative_to(RACINE)) for p in fichiers_du_depot()
               if any(m in p.name.lower() for m in MOTIFS_RESTREINTS) or p.name.startswith("EIAK-")]
    assert not fautifs, f"Fichiers de lots (restreints ou bruts) dans le dépôt : {fautifs}"


def test_aucun_secret_dans_les_fichiers():
    fautifs = []
    for p in fichiers_du_depot():
        if p.suffix.lower() in {".png", ".jpg", ".pdf", ".ico"}:
            continue
        try:
            texte = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(m.search(texte) for m in SECRETS):
            fautifs.append(str(p.relative_to(RACINE)))
    assert not fautifs, f"Chaîne ressemblant à un secret dans : {fautifs}"


def test_detecteur_de_secret_fonctionne():
    faux_jeton = "ey" + "J" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    assert any(m.search(faux_jeton) for m in SECRETS)


def test_env_example_sans_valeur():
    for ligne in (RACINE / ".env.example").read_text(encoding="utf-8").splitlines():
        if ligne.strip() and not ligne.startswith("#"):
            assert ligne.strip().endswith("="), f".env.example ne doit contenir aucune valeur : {ligne}"


def test_gitignore_couvre_donnees_et_secrets():
    gi = (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines()
    for motif in (".env", ".cache/", "outputs/", "logs/", "*.csv", "*.xlsx", "*.parquet", ".streamlit/secrets.toml"):
        assert motif in gi, f".gitignore doit contenir {motif}"


def test_liste_blanche_sans_lot_restreint():
    src = yaml.safe_load((RACINE / "config" / "sources.yaml").read_text(encoding="utf-8"))
    for cle, e in src["fichiers"].items():
        bas = e["chemin"].lower()
        assert not any(m in bas for m in MOTIFS_RESTREINTS), cle
        assert "pv-15min-v1" not in bas, "Le fichier PV v1 est remplacé par la v2"
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"])


def test_connecteur_refuse_hors_liste_blanche(tmp_path):
    (tmp_path / "2-Donnees-Ville-de-Genève").mkdir()
    (tmp_path / "2-Donnees-Ville-de-Genève" / "x.txt").write_text("restreint", encoding="utf-8")
    sources = {"motifs_interdits": ["Ville-de-Gen", "Quanthome"],
               "fichiers": {"piege": {"chemin": "2-Donnees-Ville-de-Genève/x.txt", "sha256": "0" * 64},
                            "sortie": {"chemin": "../ailleurs.txt", "sha256": "0" * 64}}}
    c = ConnecteurLocal(tmp_path, sources=sources)
    with pytest.raises(FichierNonAutorise):
        c.ouvrir("inconnu")
    with pytest.raises(FichierNonAutorise):
        c.ouvrir("piege")
    with pytest.raises(FichierNonAutorise):
        c.ouvrir("sortie")
