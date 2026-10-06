"""Testes de `services/settings_store.py` (RF4: lembrar a última configuração)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from condor.core.models import LocationOpt, SearchOptions
from condor.services.settings_store import SCHEMA_VERSION, SettingsStore


@pytest.fixture
def store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "settings.json")


OPCOES = SearchOptions(
    preset="medium",
    domains=("dglab.gov.pt",),
    domain_mode="deny",
    recency="week",
    location=LocationOpt("BR", "SC", "Florianópolis"),
    context_size="high",
    max_results=30,
    language="pt-PT",
    output_format="dossie",
    priorities=("primarias", "seguimento"),
    custom_instructions="seja breve",
)


def test_ida_e_volta_preserva_tudo(store: SettingsStore) -> None:
    assert store.save(OPCOES) is True
    assert store.load() == OPCOES


def test_datas_sobrevivem(store: SettingsStore) -> None:
    opcoes = SearchOptions(after=date(2026, 1, 31), before=date(2026, 6, 30))
    store.save(opcoes)
    assert store.load() == opcoes


def test_sem_arquivo_devolve_os_padroes(store: SettingsStore) -> None:
    assert store.load() == SearchOptions()


def test_sem_arquivo_respeita_o_fallback(store: SettingsStore) -> None:
    assert store.load(fallback=OPCOES) == OPCOES


def test_arquivo_corrompido_cai_no_fallback(store: SettingsStore) -> None:
    store.path.write_text("{isto nao e json", encoding="utf-8")
    assert store.load(fallback=OPCOES) == OPCOES


@pytest.mark.parametrize("conteudo", ['"texto"', "[1, 2]", "null", "42"])
def test_json_que_nao_e_objeto_cai_nos_padroes(store: SettingsStore, conteudo: str) -> None:
    store.path.write_text(conteudo, encoding="utf-8")
    assert store.load() == SearchOptions()


def test_versao_diferente_e_descartada(store: SettingsStore) -> None:
    store.path.write_text(
        json.dumps({"version": SCHEMA_VERSION + 1, "options": {"preset": "high"}}), encoding="utf-8"
    )
    assert store.load() == SearchOptions()


def test_opcoes_parciais_completam_com_os_padroes(store: SettingsStore) -> None:
    store.path.write_text(
        json.dumps({"version": SCHEMA_VERSION, "options": {"preset": "high"}}), encoding="utf-8"
    )
    carregadas = store.load()
    assert carregadas.preset == "high"
    assert carregadas.max_results == SearchOptions().max_results


def test_valor_invalido_no_arquivo_e_ignorado(store: SettingsStore) -> None:
    """Arquivo editado à mão não deve impedir o app de abrir."""
    store.path.write_text(
        json.dumps(
            {
                "version": SCHEMA_VERSION,
                "options": {"preset": "turbo", "max_results": 999, "recency": "decada"},
            }
        ),
        encoding="utf-8",
    )
    carregadas = store.load()
    assert (carregadas.preset, carregadas.max_results, carregadas.recency) == ("low", 15, None)


def test_arquivo_salvo_e_json_legivel(store: SettingsStore) -> None:
    store.save(OPCOES)
    dados = json.loads(store.path.read_text(encoding="utf-8"))
    assert dados["version"] == SCHEMA_VERSION
    assert dados["options"]["preset"] == "medium"
    assert "Florianópolis" in store.path.read_text(encoding="utf-8")  # sem escapar acento


def test_save_cria_a_pasta(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "sub" / "pasta" / "settings.json")
    assert store.save(SearchOptions()) is True
    assert store.path.exists()


def test_save_em_caminho_impossivel_devolve_false(tmp_path: Path) -> None:
    arquivo = tmp_path / "arquivo"
    arquivo.write_text("sou um arquivo", encoding="utf-8")
    store = SettingsStore(arquivo / "settings.json")  # pasta que é arquivo
    assert store.save(SearchOptions()) is False


def test_clear_esquece_a_configuracao(store: SettingsStore) -> None:
    store.save(OPCOES)
    store.clear()
    assert not store.path.exists()
    assert store.load() == SearchOptions()


def test_clear_sem_arquivo_nao_quebra(store: SettingsStore) -> None:
    store.clear()  # não deve levantar


# ----------------------------------------------------------------- pacotes de fontes (F8)


def test_pacotes_marcados_sobrevivem(store: SettingsStore) -> None:
    """Sem isto, reabrir o app mostraria os domínios do pacote soltos nos "extras"."""
    store.save(OPCOES, source_packs=("academico", "foruns"))
    assert store.load_source_packs() == ("academico", "foruns")


def test_sem_arquivo_os_pacotes_caem_no_fallback(store: SettingsStore) -> None:
    assert store.load_source_packs(fallback=("portugal_oficial",)) == ("portugal_oficial",)


def test_save_sem_pacotes_grava_lista_vazia(store: SettingsStore) -> None:
    store.save(OPCOES)
    assert store.load_source_packs(fallback=("x",)) == ()


def test_pacotes_invalidos_no_arquivo_caem_no_fallback(store: SettingsStore) -> None:
    store.path.write_text(
        json.dumps({"version": SCHEMA_VERSION, "options": {}, "source_packs": "academico"}),
        encoding="utf-8",
    )
    assert store.load_source_packs(fallback=("y",)) == ("y",)
