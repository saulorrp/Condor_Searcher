"""Testes de `services/storage.py` (TECHSPEC §9). Tudo em `tmp_path` — nenhum arquivo do usuário."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from condor.core.models import LocationOpt, SearchOptions, SearchResult, Source, Usage
from condor.services.storage import DB_NAME, Storage

QUANDO = datetime(2026, 10, 6, 11, 49)
PROMPT = "Qual é a capital de Portugal?"


@pytest.fixture
def result() -> SearchResult:
    return SearchResult(
        response_id="resp_abc",
        model="openai/gpt-6-luna",
        text="Lisboa. [1]",
        sources=(Source(1, "https://a.pt", "A", "2026-01-01", None, "..."),),
        queries=("capital de portugal",),
        usage=Usage(input_tokens=100, output_tokens=20, search_calls=1, cost_usd=0.00137),
        raw={"id": "resp_abc", "output": [], "acentos": "ação"},
    )


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "CondorSearcher")


# ----------------------------------------------------------------- gravação


def test_save_grava_md_json_e_linha(storage: Storage, result: SearchResult) -> None:
    record = storage.save(result, "# Relatório", PROMPT, SearchOptions(), created_at=QUANDO)

    assert record.id == 1
    assert record.md_path.name == "2026-10-06_1149_qual-e-a-capital-de-portugal.md"
    assert record.md_path.read_text(encoding="utf-8") == "# Relatório"
    assert record.prompt == PROMPT
    assert record.cost_usd == pytest.approx(0.00137)
    assert record.created_at == QUANDO

    json_path = record.md_path.with_suffix(".json")
    assert json.loads(json_path.read_text(encoding="utf-8")) == result.raw


def test_pasta_e_criada_na_primeira_gravacao(tmp_path: Path, result: SearchResult) -> None:
    destino = tmp_path / "nao" / "existe" / "ainda"
    assert not destino.exists()
    Storage(destino).save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert (destino / DB_NAME).exists()


def test_json_preserva_acentos_sem_escapar(storage: Storage, result: SearchResult) -> None:
    record = storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    bruto = record.md_path.with_suffix(".json").read_text(encoding="utf-8")
    assert "ação" in bruto and "\\u00e7" not in bruto


def test_opcoes_sobrevivem_a_ida_e_volta(storage: Storage, result: SearchResult) -> None:
    """A F9 ("Repetir busca com as mesmas opções") depende disto."""
    options = SearchOptions(
        preset="high",
        domains=("dglab.gov.pt", "arquivos.pt"),
        domain_mode="deny",
        after=date(2026, 1, 31),
        location=LocationOpt("PT", "Lisboa", "Lisboa"),
        priorities=("primarias",),
        custom_instructions="seja breve",
    )
    salvo = storage.save(result, "x", PROMPT, options, created_at=QUANDO)
    assert storage.get(salvo.id).options == options


# ----------------------------------------------------------------- desempate de nomes (aceite)


def test_duplicata_no_mesmo_minuto_ganha_sufixo_2(storage: Storage, result: SearchResult) -> None:
    a = storage.save(result, "primeiro", PROMPT, SearchOptions(), created_at=QUANDO)
    b = storage.save(result, "segundo", PROMPT, SearchOptions(), created_at=QUANDO)

    assert a.md_path.name.endswith("portugal.md")
    assert b.md_path.name.endswith("portugal-2.md")
    assert a.md_path.read_text(encoding="utf-8") == "primeiro"  # o primeiro não foi sobrescrito
    assert b.md_path.read_text(encoding="utf-8") == "segundo"


def test_terceira_duplicata_vira_3(storage: Storage, result: SearchResult) -> None:
    nomes = [
        storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO).md_path.name for _ in range(3)
    ]
    assert [n.rsplit("_", 1)[-1] for n in nomes] == [
        "qual-e-a-capital-de-portugal.md",
        "qual-e-a-capital-de-portugal-2.md",
        "qual-e-a-capital-de-portugal-3.md",
    ]


def test_sufixo_respeita_o_limite_de_80_caracteres(storage: Storage, result: SearchResult) -> None:
    prompt = "palavra " * 40
    nomes = [
        storage.save(result, "x", prompt, SearchOptions(), created_at=QUANDO).md_path.stem for _ in range(2)
    ]
    assert all(len(n) <= 80 for n in nomes)
    assert nomes[1].endswith("-2") and nomes[0] != nomes[1]


def test_json_orfao_tambem_conta_como_ocupado(storage: Storage, result: SearchResult) -> None:
    """Se só o .json existir (gravação interrompida), não reaproveitamos o nome."""
    storage.output_dir.mkdir(parents=True)
    (storage.output_dir / "2026-10-06_1149_qual-e-a-capital-de-portugal.json").write_text("{}")
    record = storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert record.md_path.name.endswith("-2.md")


def test_minutos_diferentes_nao_precisam_de_sufixo(storage: Storage, result: SearchResult) -> None:
    a = storage.save(result, "x", PROMPT, SearchOptions(), created_at=datetime(2026, 10, 6, 11, 49))
    b = storage.save(result, "x", PROMPT, SearchOptions(), created_at=datetime(2026, 10, 6, 11, 50))
    assert "-2" not in b.md_path.name
    assert a.md_path != b.md_path


# ----------------------------------------------------------------- leitura


def test_list_recent_ordena_do_mais_novo_para_o_mais_velho(storage: Storage, result: SearchResult) -> None:
    for dia in (4, 6, 5):
        storage.save(result, "x", f"busca {dia}", SearchOptions(), created_at=datetime(2026, 10, dia, 10, 0))
    assert [r.prompt for r in storage.list_recent()] == ["busca 6", "busca 5", "busca 4"]


def test_list_recent_respeita_o_limite(storage: Storage, result: SearchResult) -> None:
    for i in range(5):
        storage.save(result, "x", f"b{i}", SearchOptions(), created_at=datetime(2026, 10, 6, 10, i))
    assert len(storage.list_recent(limit=2)) == 2
    assert storage.list_recent(limit=0) == ()


def test_list_recent_sem_banco_devolve_vazio(storage: Storage) -> None:
    assert storage.list_recent() == ()
    assert not storage.db_path.exists()  # consultar não cria o banco


def test_get_inexistente_devolve_none(storage: Storage, result: SearchResult) -> None:
    storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert storage.get(999) is None


def test_paths_of_devolve_md_e_json(storage: Storage, result: SearchResult) -> None:
    record = storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    md, bruto = storage.paths_of(record.id)
    assert md == record.md_path
    assert bruto == record.md_path.with_suffix(".json")
    assert storage.paths_of(999) is None


# ----------------------------------------------------------------- remoção


def test_delete_apaga_a_linha_mas_preserva_os_arquivos(storage: Storage, result: SearchResult) -> None:
    """RF5: "Excluir do histórico (não apaga o .md)"."""
    record = storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)

    assert storage.delete(record.id) is True
    assert storage.get(record.id) is None
    assert record.md_path.exists()
    assert record.md_path.with_suffix(".json").exists()


def test_delete_de_id_inexistente_devolve_false(storage: Storage, result: SearchResult) -> None:
    storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert storage.delete(999) is False


def test_delete_sem_banco_devolve_false(storage: Storage) -> None:
    assert storage.delete(1) is False


# ----------------------------------------------------------------- persistência e robustez


def test_historico_sobrevive_a_nova_instancia(tmp_path: Path, result: SearchResult) -> None:
    """Critério da F9, verificado já aqui: reabrir o app mantém o histórico."""
    pasta = tmp_path / "out"
    Storage(pasta).save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert len(Storage(pasta).list_recent()) == 1


def test_schema_tem_as_colunas_do_techspec(storage: Storage, result: SearchResult) -> None:
    storage.save(result, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    conn = sqlite3.connect(storage.db_path)
    try:
        colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(searches)")}
    finally:
        conn.close()
    assert colunas == {
        "id",
        "created_at",
        "prompt",
        "options_json",
        "preset",
        "md_path",
        "json_path",
        "cost_usd",
        "response_id",
    }


def test_custo_ausente_e_gravado_como_null(storage: Storage, result: SearchResult) -> None:
    sem_custo = SearchResult(**{**result.__dict__, "usage": Usage(1, 2, 1, None)})
    record = storage.save(sem_custo, "x", PROMPT, SearchOptions(), created_at=QUANDO)
    assert storage.get(record.id).cost_usd is None


def test_opcoes_ilegiveis_no_banco_caem_nos_padroes(storage: Storage, result: SearchResult) -> None:
    record = storage.save(result, "x", PROMPT, SearchOptions(preset="high"), created_at=QUANDO)
    conn = sqlite3.connect(storage.db_path)
    try:
        conn.execute("UPDATE searches SET options_json = ? WHERE id = ?", ("{isto nao e json", record.id))
        conn.commit()
    finally:
        conn.close()
    assert storage.get(record.id).options == SearchOptions()


def test_save_sem_created_at_usa_a_hora_atual(storage: Storage, result: SearchResult) -> None:
    antes = datetime.now().replace(microsecond=0)
    record = storage.save(result, "x", PROMPT, SearchOptions())
    assert record.created_at >= antes
