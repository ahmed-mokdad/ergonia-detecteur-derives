"""Connecteurs : intégrité SHA-256, cache, source injoignable. Le HTTP est testé sur un serveur local."""
from __future__ import annotations

import hashlib
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.connecteurs import ConnecteurHTTP, ConnecteurLocal, IntegriteInvalide, SourceInjoignable

RACINE = Path(__file__).resolve().parents[1]
CONTENU = "horodatage;id_compteur;energie_kwh\n2025-01-01T00:00:00+01:00;T01-EL;1.0\n".encode()


def _sources(sha=None):
    return {"motifs_interdits": [], "fichiers": {"essai": {"chemin": "lot ouvert/essai é.txt",
                                                          "sha256": sha or hashlib.sha256(CONTENU).hexdigest()}}}


def _deposer(dossier: Path) -> Path:
    p = dossier / "lot ouvert" / "essai é.txt"
    p.parent.mkdir(parents=True)
    p.write_bytes(CONTENU)
    return p


class _Silencieux(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def serveur(tmp_path):
    racine = tmp_path / "distant"
    racine.mkdir()
    _deposer(racine)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencieux, directory=str(racine)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", srv
    srv.shutdown()
    srv.server_close()


def test_local_integrite(tmp_path):
    p = _deposer(tmp_path)
    c = ConnecteurLocal(tmp_path, sources=_sources())
    assert c.ouvrir("essai") == p.resolve()
    assert c.provenance()["connecteur"] == "local"
    p.write_bytes(CONTENU + b"modifie")
    with pytest.raises(IntegriteInvalide):
        ConnecteurLocal(tmp_path, sources=_sources()).ouvrir("essai")


def test_local_refuse_un_dossier_dans_le_depot():
    with pytest.raises(SourceInjoignable):
        ConnecteurLocal(RACINE / "config", sources=_sources())


def test_local_sans_configuration(monkeypatch):
    monkeypatch.delenv("DATA_LOCAL_DIR", raising=False)
    with pytest.raises(SourceInjoignable):
        ConnecteurLocal(sources=_sources())


def test_http_telecharge_verifie_et_met_en_cache(serveur, tmp_path):
    url, srv = serveur
    cache = tmp_path / "cache"
    c = ConnecteurHTTP(url, sources=_sources(), cache=cache)
    p = c.ouvrir("essai")
    assert p.read_bytes() == CONTENU and cache in p.parents
    prov = c.provenance()
    assert prov["recuperation"] and "127.0.0.1" in prov["source"] and "essai" not in prov["source"]
    srv.shutdown()  # serveur arrêté : le cache vérifié suffit
    assert ConnecteurHTTP(url, sources=_sources(), cache=cache).ouvrir("essai").read_bytes() == CONTENU


def test_http_rejette_une_empreinte_inattendue(serveur, tmp_path):
    url, _ = serveur
    cache = tmp_path / "cache"
    with pytest.raises(IntegriteInvalide):
        ConnecteurHTTP(url, sources=_sources("f" * 64), cache=cache).ouvrir("essai")
    assert not (cache / "lot ouvert" / "essai é.txt").exists(), "un fichier non conforme ne reste pas en cache"


def test_http_source_injoignable(tmp_path):
    c = ConnecteurHTTP("http://127.0.0.1:9", sources=_sources(), cache=tmp_path / "cache", delai_s=2)
    with pytest.raises(SourceInjoignable) as e:
        c.ouvrir("essai")
    assert "DATA_LOCAL_DIR" in str(e.value)


def test_http_sans_url(monkeypatch):
    monkeypatch.delenv("DATA_SOURCE_URL", raising=False)
    with pytest.raises(SourceInjoignable):
        ConnecteurHTTP(sources=_sources())
