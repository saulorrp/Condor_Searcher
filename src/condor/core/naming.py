"""Nomes de arquivo seguros a partir do prompt (TECHSPEC §9).

O Windows é o chão mais estreito aqui: proíbe `<>:"/\\|?*`, não aceita nome terminando em ponto
ou espaço, reserva nomes como `CON` e `NUL`, e o caminho inteiro tem limite de tamanho. Por isso o
slug só usa `[a-z0-9-]`: o que passa por aqui é válido no Windows, no macOS e no Linux.

O sufixo de desempate (`-2`, `-3`) para buscas do mesmo minuto é do `services/storage.py` (F6);
aqui os nomes são uma função pura da data e do texto.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

#: Tamanho máximo do nome (sem extensão). Deixa folga para `-2` e para `.json`/`.md`.
MAX_BASENAME = 80

#: Usado quando o prompt não sobra nada aproveitável (só emoji, só pontuação...).
FALLBACK_SLUG = "busca"

#: Nomes de dispositivo reservados pelo Windows, em qualquer caixa e com qualquer extensão.
_RESERVADOS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_NAO_PERMITIDO = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    """Texto livre → `slug-assim`, sem acento, sem maiúscula e sem caractere proibido.

    Corta na fronteira de palavra quando dá, para o nome não terminar no meio de uma.
    """
    sem_acento = unicodedata.normalize("NFKD", text)
    ascii_only = sem_acento.encode("ascii", "ignore").decode("ascii")
    slug = _NAO_PERMITIDO.sub("-", ascii_only.lower()).strip("-")

    if len(slug) > max_len:
        slug = slug[: max_len + 1]
        corte = slug.rfind("-")
        slug = (slug[:corte] if corte > max_len // 2 else slug[:max_len]).strip("-")

    if not slug or slug in _RESERVADOS:
        return FALLBACK_SLUG
    return slug


def report_basename(created_at: datetime, prompt: str, max_len: int = MAX_BASENAME) -> str:
    """`AAAA-MM-DD_HHMM_slug-do-prompt`, sem extensão (TECHSPEC §9)."""
    prefixo = created_at.strftime("%Y-%m-%d_%H%M")
    espaco = max_len - len(prefixo) - 1  # o "_" entre a data e o slug
    slug = slugify(prompt, max_len=max(espaco, len(FALLBACK_SLUG)))
    nome = f"{prefixo}_{slug}"
    return nome[:max_len].rstrip("-_")
