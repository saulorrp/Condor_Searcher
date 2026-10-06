"""Testes do esqueleto e da composição do `__main__` (F0, revisto na F7).

`main()` agora abre a janela e entra no laço do Qt, então não é chamado aqui: o que se testa é
a parte determinística — achar a pasta do projeto e carregar a configuração real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import condor
from condor.__main__ import find_project_root, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_versao_exposta() -> None:
    assert condor.__version__.count(".") == 2


def test_find_project_root_acha_a_pasta_do_projeto() -> None:
    assert find_project_root() == ROOT
    assert (find_project_root() / "config" / "defaults.toml").is_file()


def test_find_project_root_falha_com_mensagem_em_portugues(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="pasta config/"):
        find_project_root(tmp_path / "fundo" / "do" / "poco")


def test_load_config_carrega_os_tres_toml_reais() -> None:
    defaults, snippets, packs = load_config(ROOT)
    assert defaults.options.preset == "low"
    assert snippets.language(defaults.options.language)
    assert len(packs) >= 7
    assert all(p.domains for p in packs)
