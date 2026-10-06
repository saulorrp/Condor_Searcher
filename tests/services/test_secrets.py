"""Testes de `services/secrets.py` (RF7).

Nenhum teste toca no `.env` de verdade: `env_path` e `environ` são sempre injetados.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from condor.services.secrets import (
    ENV_VAR,
    MIN_KEY_LENGTH,
    SOURCE_ENV_FILE,
    SOURCE_SYSTEM,
    VISIBLE_TAIL,
    SecretStore,
    is_valid_format,
    mask,
)

CHAVE = "pplx-1234567890abcdefGHIJ"
OUTRA = "pplx-ZZZZZZZZZZ9876543210"


@pytest.fixture
def env_path(tmp_path: Path) -> Path:
    return tmp_path / ".env"


def _store(env_path: Path, **environ: str) -> SecretStore:
    return SecretStore(env_path, environ=environ)


# ----------------------------------------------------------------- is_valid_format


@pytest.mark.parametrize("chave", [CHAVE, "pplx-" + "a" * 15, "pplx-" + "x" * 100])
def test_formato_valido(chave: str) -> None:
    assert is_valid_format(chave) is True


@pytest.mark.parametrize(
    "chave",
    [
        None,
        "",
        "   ",
        "pplx-curta",  # menos de 20 caracteres
        "sk-1234567890abcdefghij",  # prefixo errado
        "PPLX-1234567890abcdefghij",  # prefixo é sensível a caixa
        "pplx-com espaco no meio 12",
        "pplx-com\ttab1234567890abc",
        "pplx-com\nquebra1234567890",
    ],
)
def test_formato_invalido(chave) -> None:
    assert is_valid_format(chave) is False


def test_minimo_de_caracteres_e_o_do_rf7() -> None:
    assert MIN_KEY_LENGTH == 20
    assert is_valid_format("pplx-" + "a" * (MIN_KEY_LENGTH - 5)) is True
    assert is_valid_format("pplx-" + "a" * (MIN_KEY_LENGTH - 6)) is False


# ----------------------------------------------------------------- mask (aceite)


def test_mask_mostra_so_os_quatro_ultimos() -> None:
    assert mask(CHAVE) == "pplx-…GHIJ"


@pytest.mark.parametrize("chave", [CHAVE, OUTRA, "pplx-" + "x" * 200, "abcdefghij", "pplx-abcde"])
def test_mask_nunca_expoe_mais_que_quatro_caracteres(chave: str) -> None:
    """Critério de aceite: nada além dos 4 finais pode aparecer."""
    mascarada = mask(chave)
    miolo = chave[len("pplx-") : -VISIBLE_TAIL] if chave.startswith("pplx-") else chave[:-VISIBLE_TAIL]
    for pedaco in (chave, miolo):
        if len(pedaco) > VISIBLE_TAIL:
            assert pedaco not in mascarada
    assert mascarada.count(chave[-VISIBLE_TAIL:]) == 1
    assert len(mascarada.replace("pplx-", "").replace("…", "")) <= VISIBLE_TAIL


def test_mask_sem_chave_tem_texto_em_portugues() -> None:
    assert mask(None) == "nenhuma chave configurada"
    assert mask("") == "nenhuma chave configurada"


def test_mask_de_chave_curtissima_nao_mostra_nada() -> None:
    assert mask("abcd") == "…"
    assert mask("pplx-") == "pplx-…"


# ----------------------------------------------------------------- prioridade (aceite)


def test_variavel_de_sistema_tem_prioridade_sobre_o_env(env_path: Path) -> None:
    env_path.write_text(f"{ENV_VAR}={OUTRA}\n", encoding="utf-8")
    store = _store(env_path, **{ENV_VAR: CHAVE})

    assert store.get_key() == CHAVE
    assert store.key_source() == SOURCE_SYSTEM
    assert store.system_overrides_file is True


def test_sem_variavel_de_sistema_usa_o_env(env_path: Path) -> None:
    env_path.write_text(f"{ENV_VAR}={CHAVE}\n", encoding="utf-8")
    store = _store(env_path)

    assert store.get_key() == CHAVE
    assert store.key_source() == SOURCE_ENV_FILE
    assert store.system_overrides_file is False


def test_sem_chave_em_lugar_nenhum(env_path: Path) -> None:
    store = _store(env_path)
    assert store.get_key() is None
    assert store.key_source() is None
    assert store.system_overrides_file is False


def test_env_inexistente_nao_quebra(tmp_path: Path) -> None:
    assert _store(tmp_path / "nao-existe" / ".env").get_key() is None


@pytest.mark.parametrize("valor", ["", "   ", "\n"])
def test_variavel_de_sistema_vazia_e_ignorada(env_path: Path, valor: str) -> None:
    env_path.write_text(f"{ENV_VAR}={CHAVE}\n", encoding="utf-8")
    store = _store(env_path, **{ENV_VAR: valor})
    assert store.get_key() == CHAVE
    assert store.key_source() == SOURCE_ENV_FILE


def test_espacos_em_volta_da_chave_sao_aparados(env_path: Path) -> None:
    assert _store(env_path, **{ENV_VAR: f"  {CHAVE}  "}).get_key() == CHAVE


# ----------------------------------------------------------------- save_key (aceite)


def test_save_key_preserva_as_outras_linhas_do_env(env_path: Path) -> None:
    """Critério de aceite: o `.env` pode ter outras coisas do usuário."""
    env_path.write_text(
        "# comentario do usuario\nOUTRA_VAR=valor\nPERPLEXITY_API_KEY=pplx-antiga00000000000000\nFIM=1\n",
        encoding="utf-8",
    )
    _store(env_path).save_key(CHAVE)

    conteudo = env_path.read_text(encoding="utf-8")
    assert "OUTRA_VAR=valor" in conteudo
    assert "FIM=1" in conteudo
    assert "# comentario do usuario" in conteudo
    assert CHAVE in conteudo
    assert "pplx-antiga00000000000000" not in conteudo
    assert conteudo.count(ENV_VAR) == 1  # atualizou, não duplicou


def test_save_key_cria_o_env_se_nao_existir(env_path: Path) -> None:
    store = _store(env_path)
    store.save_key(CHAVE)
    assert env_path.exists()
    assert store.get_key() == CHAVE


def test_save_key_cria_a_pasta_se_preciso(tmp_path: Path) -> None:
    env_path = tmp_path / "sub" / "pasta" / ".env"
    _store(env_path).save_key(CHAVE)
    assert env_path.exists()


def test_save_key_apara_espacos(env_path: Path) -> None:
    _store(env_path).save_key(f"  {CHAVE}  ")
    assert _store(env_path).get_key() == CHAVE


def test_save_key_recusa_formato_invalido_com_mensagem_em_portugues(env_path: Path) -> None:
    with pytest.raises(ValueError, match="caracteres e não conter espaços"):
        _store(env_path).save_key("pplx-curta")
    assert not env_path.exists()  # nada foi gravado


def test_save_key_nao_registra_a_chave_no_log(env_path: Path, caplog) -> None:
    import logging

    with caplog.at_level(logging.DEBUG):
        _store(env_path).save_key(CHAVE)
    tudo = "\n".join(r.getMessage() for r in caplog.records)
    assert CHAVE not in tudo
    assert "pplx-…GHIJ" in tudo  # só a versão mascarada


# ----------------------------------------------------------------- remove_key


def test_remove_key_apaga_so_a_linha_da_chave(env_path: Path) -> None:
    env_path.write_text(f"OUTRA=coisa\n{ENV_VAR}={CHAVE}\nMAIS=1\n", encoding="utf-8")
    store = _store(env_path)

    assert store.remove_key() is True
    conteudo = env_path.read_text(encoding="utf-8")
    assert "OUTRA=coisa" in conteudo and "MAIS=1" in conteudo
    assert ENV_VAR not in conteudo
    assert store.get_key() is None


def test_remove_key_sem_chave_devolve_false(env_path: Path) -> None:
    env_path.write_text("OUTRA=coisa\n", encoding="utf-8")
    assert _store(env_path).remove_key() is False


def test_remove_key_sem_env_devolve_false(env_path: Path) -> None:
    assert _store(env_path).remove_key() is False


def test_remover_nao_afeta_a_variavel_de_sistema(env_path: Path) -> None:
    """O diálogo tem de poder avisar que removeu do `.env` e a chave do sistema continua valendo."""
    env_path.write_text(f"{ENV_VAR}={OUTRA}\n", encoding="utf-8")
    store = _store(env_path, **{ENV_VAR: CHAVE})

    assert store.remove_key() is True
    assert store.get_key() == CHAVE
    assert store.key_source() == SOURCE_SYSTEM
