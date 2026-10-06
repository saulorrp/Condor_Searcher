"""Leitura e gravação da chave da API (TECHSPEC RF7).

**Único módulo autorizado a tocar no `.env`.** Ninguém mais lê, escreve ou imprime esse arquivo,
e nada aqui registra a chave em log — nem truncada, a não ser pelo `mask()`, que é feito para
aparecer na tela.

Ordem de leitura (RF7): variável de ambiente do sistema → `.env` da pasta do app. Por isso o app
**não** deve chamar `load_dotenv()`: se o `.env` fosse injetado no ambiente, não haveria como
distinguir "o usuário definiu uma variável de sistema" de "o app leu o próprio .env", e o aviso
de que o `.env` não terá efeito ficaria errado.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values, set_key, unset_key

logger = logging.getLogger(__name__)

ENV_VAR = "PERPLEXITY_API_KEY"
ENV_FILE = ".env"

#: Formato exigido pelo RF7: prefixo `pplx-` e pelo menos 20 caracteres, sem espaço.
KEY_PREFIX = "pplx-"
MIN_KEY_LENGTH = 20

#: Quantos caracteres finais o `mask()` mostra. Nunca mais do que isto.
VISIBLE_TAIL = 4

#: Valores de `key_source()`.
SOURCE_SYSTEM = "sistema"
SOURCE_ENV_FILE = ".env"


def is_valid_format(key: str | None) -> bool:
    """Confere o formato antes de salvar — não confirma que a chave funciona."""
    if not key:
        return False
    texto = key.strip()
    if len(texto) != len(key.strip()) or any(c.isspace() for c in texto):
        return False
    return texto.startswith(KEY_PREFIX) and len(texto) >= MIN_KEY_LENGTH


def mask(key: str | None) -> str:
    """`pplx-…AB12`: prefixo conhecido + os 4 últimos caracteres, nunca mais (RF7)."""
    if not key:
        return "nenhuma chave configurada"
    texto = key.strip()
    prefixo = KEY_PREFIX if texto.startswith(KEY_PREFIX) else ""
    corpo = texto[len(prefixo) :]
    # Só mostra a cauda se houver mais que ela depois do prefixo: assim nem uma chave
    # absurdamente curta aparece inteira, e a cauda nunca invade o prefixo.
    cauda = corpo[-VISIBLE_TAIL:] if len(corpo) > VISIBLE_TAIL else ""
    return f"{prefixo}…{cauda}"


class SecretStore:
    """Acesso à chave. `env_path` e `environ` são injetáveis para os testes."""

    def __init__(self, env_path: Path, *, environ: Mapping[str, str] | None = None) -> None:
        self.env_path = Path(env_path)
        self._environ = environ if environ is not None else os.environ

    # ------------------------------------------------------------------ leitura

    def get_key(self) -> str | None:
        """A chave em uso, seguindo a ordem do RF7. `None` se não houver nenhuma."""
        return self._from_system() or self._from_file()

    def key_source(self) -> str | None:
        """`"sistema"`, `".env"` ou `None` — o diálogo usa isto para avisar o usuário."""
        if self._from_system():
            return SOURCE_SYSTEM
        if self._from_file():
            return SOURCE_ENV_FILE
        return None

    @property
    def system_overrides_file(self) -> bool:
        """`True` quando há variável de sistema e o `.env` não terá efeito (aviso do RF7)."""
        return bool(self._from_system()) and bool(self._from_file())

    def _from_system(self) -> str | None:
        return _clean(self._environ.get(ENV_VAR))

    def _from_file(self) -> str | None:
        if not self.env_path.exists():
            return None
        try:
            return _clean(dotenv_values(self.env_path).get(ENV_VAR))
        except OSError as exc:
            logger.warning("Não consegui ler o %s (%s).", ENV_FILE, exc)
            return None

    # ------------------------------------------------------------------ gravação

    def save_key(self, key: str) -> None:
        """Grava/atualiza a chave no `.env`, preservando as outras linhas (`dotenv.set_key`).

        `ValueError` com mensagem em português se o formato não passar.
        """
        texto = (key or "").strip()
        if not is_valid_format(texto):
            raise ValueError(
                f"A chave precisa começar com {KEY_PREFIX!r}, ter ao menos {MIN_KEY_LENGTH} "
                "caracteres e não conter espaços."
            )
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.touch(exist_ok=True)
        set_key(str(self.env_path), ENV_VAR, texto, quote_mode="never")
        logger.info("Chave da API gravada em %s (%s).", ENV_FILE, mask(texto))

    def remove_key(self) -> bool:
        """Apaga a linha da chave no `.env`. `False` se não havia nada para apagar."""
        if not self.env_path.exists() or self._from_file() is None:
            return False
        unset_key(str(self.env_path), ENV_VAR)
        logger.info("Chave da API removida do %s.", ENV_FILE)
        return True


def _clean(valor: str | None) -> str | None:
    texto = (valor or "").strip()
    return texto or None
