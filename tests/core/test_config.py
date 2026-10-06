"""Testes de `core/config.py` — carregam os TOML reais e TOML sintéticos em `tmp_path`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from condor.core.config import load_defaults, load_snippets, load_source_packs
from condor.core.models import MAX_DOMAINS, LocationOpt

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
DEFAULTS = CONFIG_DIR / "defaults.toml"
SOURCE_PACKS = CONFIG_DIR / "source_packs.toml"
SNIPPETS = CONFIG_DIR / "prompt_snippets.toml"


# ----------------------------------------------------------------- os 3 TOML reais


def test_os_tres_toml_reais_existem() -> None:
    for path in (DEFAULTS, SOURCE_PACKS, SNIPPETS):
        assert path.is_file(), f"falta {path.name}"


def test_carrega_defaults_real() -> None:
    """Os defaults do arquivo real têm de bater com a tabela do RF4."""
    defaults = load_defaults(DEFAULTS)
    options = defaults.options

    assert options.preset == "low"
    assert options.domain_mode == "allow"
    assert options.recency is None
    assert options.context_size == "medium"
    assert options.max_results == 15
    assert options.language == "pt-BR"
    assert options.output_format == "relatorio"
    assert options.priorities == ("primarias", "divergencias")
    assert options.location is None  # localização desligada por padrão
    assert defaults.location_shortcut == LocationOpt(country="PT", region="Lisboa", city="Lisboa")
    assert "~" not in str(defaults.output_dir)  # já expandido
    assert set(defaults.timeouts) == {"fast", "low", "medium", "high", "xhigh"}
    assert all(t > 0 for t in defaults.timeouts.values())


def test_carrega_source_packs_real() -> None:
    packs = load_source_packs(SOURCE_PACKS)
    assert len(packs) >= 7
    by_key = {p.key: p for p in packs}
    assert by_key["sem_ruido"].mode == "deny"
    assert by_key["academico"].mode == "allow"
    assert "scielo.org" in by_key["academico"].domains
    assert all(p.domains for p in packs)
    assert all(p.label for p in packs)


def test_carrega_snippets_real() -> None:
    snippets = load_snippets(SNIPPETS)
    assert {s.key for s in snippets.languages} == {"pt-BR", "pt-PT", "en", "es"}
    assert {s.key for s in snippets.formats} >= {"resposta_direta", "relatorio", "tabela"}
    assert {s.key for s in snippets.priorities} >= {"primarias", "divergencias"}
    assert all(s.text for s in snippets.formats)


def test_defaults_reais_apontam_para_snippets_existentes() -> None:
    """O default não pode citar um formato/idioma/prioridade que não existe no outro arquivo."""
    defaults = load_defaults(DEFAULTS)
    snippets = load_snippets(SNIPPETS)
    assert snippets.language(defaults.options.language)
    assert snippets.output_format(defaults.options.output_format)
    for key in defaults.options.priorities:
        assert snippets.priority(key)


def test_pacotes_default_existem_em_source_packs() -> None:
    defaults = load_defaults(DEFAULTS)
    keys = {p.key for p in load_source_packs(SOURCE_PACKS)}
    assert set(defaults.source_packs) <= keys


# ----------------------------------------------------------------- aviso dos >20 domínios


def _pack_toml(n: int) -> str:
    domains = ", ".join(f'"d{i}.pt"' for i in range(n))
    return f'[grande]\nlabel = "Grande"\ndomains = [{domains}]\n'


def test_pacote_com_mais_de_20_dominios_avisa_e_carrega(tmp_path: Path, caplog) -> None:
    """Critério de aceite da F1: >20 domínios é aviso, não erro."""
    path = tmp_path / "source_packs.toml"
    path.write_text(_pack_toml(MAX_DOMAINS + 5), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        packs = load_source_packs(path)

    assert len(packs) == 1  # carregou mesmo assim
    assert len(packs[0].domains) == MAX_DOMAINS + 5
    assert any("grande" in r.getMessage() for r in caplog.records)


def test_pacote_com_exatamente_20_dominios_nao_avisa(tmp_path: Path, caplog) -> None:
    path = tmp_path / "source_packs.toml"
    path.write_text(_pack_toml(MAX_DOMAINS), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        packs = load_source_packs(path)

    assert len(packs[0].domains) == MAX_DOMAINS
    assert not caplog.records


def test_pacote_sem_dominios_e_ignorado_com_aviso(tmp_path: Path, caplog) -> None:
    path = tmp_path / "source_packs.toml"
    path.write_text('[vazio]\nlabel = "Vazio"\ndomains = []\n\n[ok]\ndomains = ["a.pt"]\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        packs = load_source_packs(path)

    assert [p.key for p in packs] == ["ok"]
    assert caplog.records


def test_pacote_com_mode_invalido_cai_para_allow(tmp_path: Path, caplog) -> None:
    path = tmp_path / "source_packs.toml"
    path.write_text('[p]\ndomains = ["a.pt"]\nmode = "excluir"\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        packs = load_source_packs(path)

    assert packs[0].mode == "allow"
    assert caplog.records


# ----------------------------------------------------------------- erros de configuração

BASE_DEFAULTS = """\
[output]
folder = "~/Documents/CondorSearcher"

[timeouts]
fast = 60
low = 180
medium = 420
high = 600
xhigh = 1800

[search]
preset = "low"
domain_mode = "allow"
source_packs = []
domains = []
recency = ""
context_size = "medium"
max_results = 15
language = "pt-BR"
output_format = "relatorio"
priorities = ["primarias"]

[location]
enabled = false
country = "PT"
region = "Lisboa"
city = "Lisboa"
"""


def _defaults_with(tmp_path: Path, old: str, new: str) -> Path:
    assert old in BASE_DEFAULTS
    path = tmp_path / "defaults.toml"
    path.write_text(BASE_DEFAULTS.replace(old, new, 1), encoding="utf-8")
    return path


def test_defaults_sintetico_minimo_carrega(tmp_path: Path) -> None:
    path = tmp_path / "defaults.toml"
    path.write_text(BASE_DEFAULTS, encoding="utf-8")
    assert load_defaults(path).options.preset == "low"


@pytest.mark.parametrize(
    ("old", "new", "trecho"),
    [
        ('preset = "low"', 'preset = "turbo"', "preset"),
        ('context_size = "medium"', 'context_size = "gigante"', "context_size"),
        ('domain_mode = "allow"', 'domain_mode = "ambos"', "domain_mode"),
        ("max_results = 15", "max_results = 0", "max_results"),
        ("max_results = 15", "max_results = 51", "max_results"),
        ('recency = ""', 'recency = "decada"', "recency"),
        ("domains = []", 'domains = "a.pt"', "domains"),
        ("fast = 60", 'fast = "rapido"', "timeouts"),
        ("fast = 60", "fast = 0", "timeouts"),
    ],
)
def test_valor_invalido_em_defaults_e_value_error(tmp_path: Path, old: str, new: str, trecho: str) -> None:
    path = _defaults_with(tmp_path, old, new)
    with pytest.raises(ValueError, match=trecho):
        load_defaults(path)


def test_preset_sem_timeout_e_value_error(tmp_path: Path) -> None:
    path = _defaults_with(tmp_path, "xhigh = 1800\n", "")
    with pytest.raises(ValueError, match="xhigh"):
        load_defaults(path)


def test_secao_faltando_e_value_error(tmp_path: Path) -> None:
    path = tmp_path / "defaults.toml"
    path.write_text('[output]\nfolder = "."\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[search\]"):
        load_defaults(path)


def test_arquivo_inexistente_e_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        load_defaults(tmp_path / "nao_existe.toml")


def test_toml_invalido_e_value_error(tmp_path: Path) -> None:
    path = tmp_path / "defaults.toml"
    path.write_text("[search\npreset =", encoding="utf-8")
    with pytest.raises(ValueError, match="TOML inválido"):
        load_defaults(path)


def test_localizacao_ligada_entra_nas_opcoes(tmp_path: Path) -> None:
    path = _defaults_with(tmp_path, "enabled = false", "enabled = true")
    options = load_defaults(path).options
    assert options.location == LocationOpt(country="PT", region="Lisboa", city="Lisboa")


def test_pais_da_localizacao_vira_maiusculo(tmp_path: Path) -> None:
    path = _defaults_with(tmp_path, 'country = "PT"', 'country = "pt"')
    assert load_defaults(path).location_shortcut.country == "PT"


def test_timeouts_sao_imutaveis(tmp_path: Path) -> None:
    path = tmp_path / "defaults.toml"
    path.write_text(BASE_DEFAULTS, encoding="utf-8")
    defaults = load_defaults(path)
    with pytest.raises(TypeError):
        defaults.timeouts["fast"] = 1  # type: ignore[index]


# ----------------------------------------------------------------- snippets


def test_snippet_desconhecido_e_key_error() -> None:
    snippets = load_snippets(SNIPPETS)
    with pytest.raises(KeyError, match="Formato desconhecido"):
        snippets.output_format("inexistente")
    with pytest.raises(KeyError, match="Idioma desconhecido"):
        snippets.language("tlh")
    with pytest.raises(KeyError, match="Prioridade desconhecida|Prioridade desconhecido"):
        snippets.priority("inexistente")


def test_snippet_sem_text_e_value_error(tmp_path: Path) -> None:
    path = tmp_path / "prompt_snippets.toml"
    path.write_text(
        '[languages.pt]\ntext = "x"\n\n[formats.a]\nlabel = "A"\n\n[priorities.p]\ntext = "y"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"\[formats.a\]"):
        load_snippets(path)


def test_grupo_de_snippets_faltando_e_value_error(tmp_path: Path) -> None:
    path = tmp_path / "prompt_snippets.toml"
    path.write_text('[languages.pt]\ntext = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[formats\]"):
        load_snippets(path)


def test_label_default_e_a_propria_chave(tmp_path: Path) -> None:
    path = tmp_path / "prompt_snippets.toml"
    path.write_text(
        '[languages.pt]\ntext = "x"\n\n[formats.a]\ntext = "y"\n\n[priorities.p]\ntext = "z"\n',
        encoding="utf-8",
    )
    assert load_snippets(path).formats[0].label == "a"
