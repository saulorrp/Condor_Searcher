"""Monta o arquivo `.md` final (TECHSPEC RF3, API_NOTES §5).

O app monta o Markdown, não o modelo: é isso que garante que todo relatório tenha links clicáveis,
a lista de fontes e os parâmetros da busca, mesmo quando o modelo responde em prosa solta.

Estrutura: front matter YAML · corpo com as citações viradas em links · `## Fontes` ·
`## Parâmetros da busca`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from urllib.parse import urlparse

from condor.core.models import SearchOptions, SearchResult, Source

#: Marcadores de citação aceitos: `[3]` e `[web:3]` (API_NOTES §5).
_CITACAO = re.compile(r"\[(?:web:)?(\d+)\]")

#: Abertura/fechamento de bloco de código, onde as citações não devem ser tocadas.
_CERCA = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def render(
    result: SearchResult,
    prompt: str,
    options: SearchOptions,
    briefing: str,
    created_at: datetime,
) -> str:
    """Devolve o Markdown completo do relatório."""
    partes = [
        _front_matter(result, prompt, options, created_at),
        f"# {_uma_linha(prompt)}",
        link_citations(result.text, result.sources),
        _fontes(result.sources),
        _parametros(briefing),
    ]
    return "\n\n".join(p for p in partes if p).rstrip() + "\n"


# --------------------------------------------------------------------------- citações


def link_citations(text: str, sources: Iterable[Source]) -> str:
    """Troca `[3]`/`[web:3]` por `[[3]](url)`, menos dentro de blocos de código.

    Marcador cujo `id` não existe nas fontes fica como está: é melhor um `[7]` órfão do que um
    link para a fonte errada. Função pública porque a UI (F7) também mostra o texto com links.
    """
    por_id = {source.id: source.url for source in sources}
    if not por_id:
        return text

    def troca(m: re.Match[str]) -> str:
        url = por_id.get(int(m.group(1)))
        return f"[[{m.group(1)}]]({url})" if url else m.group(0)

    saida: list[str] = []
    cerca: tuple[str, int] | None = None  # (caractere, tamanho) da cerca aberta
    for linha in text.split("\n"):
        marca = _CERCA.match(linha)
        atual = (marca.group(1)[0], len(marca.group(1))) if marca else None
        if cerca is None:
            cerca = atual
        elif atual is not None and atual[0] == cerca[0] and atual[1] >= cerca[1]:
            # Só fecha com o mesmo caractere e pelo menos o mesmo tamanho (CommonMark):
            # uma cerca de 3 não fecha um bloco aberto com 4.
            cerca = None
        saida.append(linha if cerca is not None else _CITACAO.sub(troca, linha))
    return "\n".join(saida)


# --------------------------------------------------------------------------- seções


def _fontes(sources: tuple[Source, ...]) -> str:
    """`## Fontes`: título, domínio, data e URL, na ordem do `id` (RF3 item 3)."""
    if not sources:
        return "## Fontes\n\nA busca não devolveu fontes."

    linhas = ["## Fontes", ""]
    for source in sources:
        titulo = _uma_linha(source.title) or source.url
        detalhes = [d for d in (_dominio(source.url), source.date) if d]
        sufixo = f" — {' · '.join(detalhes)}" if detalhes else ""
        linhas.append(f"{source.id}. [{_escape_md(titulo)}]({source.url}){sufixo}")
    return "\n".join(linhas)


def _parametros(briefing: str) -> str:
    """`## Parâmetros da busca`: o briefing exato, em bloco de código (RF3 item 4)."""
    texto = briefing.strip()
    if not texto:
        return ""
    cerca = "~~~" if "```" in texto else "```"
    return f"## Parâmetros da busca\n\nO briefing enviado junto com a pergunta:\n\n{cerca}\n{texto}\n{cerca}"


def _dominio(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- front matter


def _front_matter(
    result: SearchResult,
    prompt: str,
    options: SearchOptions,
    created_at: datetime,
) -> str:
    """Front matter YAML válido (RF3 item 1). Tudo entre aspas duplas e escapado."""
    campos: dict[str, object] = {
        "prompt": _uma_linha(prompt),
        "created_at": created_at.isoformat(timespec="seconds"),
        "preset": options.preset,
        "model": result.model,
        "response_id": result.response_id,
        "cost_usd": result.usage.cost_usd,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "search_calls": result.usage.search_calls,
        "sources": len(result.sources),
        "options": _options_dict(options),
    }
    linhas = ["---"]
    linhas += _yaml_lines(campos, nivel=0)
    linhas.append("---")
    return "\n".join(linhas)


def _options_dict(options: SearchOptions) -> dict[str, object]:
    """As opções usadas, com as chaves vazias de fora para o front matter não virar ruído."""
    dados: dict[str, object] = {
        "domain_mode": options.domain_mode,
        "context_size": options.context_size,
        "max_results": options.max_results,
        "language": options.language,
        "output_format": options.output_format,
    }
    if options.domains:
        dados["domains"] = list(options.domains)
    if options.priorities:
        dados["priorities"] = list(options.priorities)
    if options.recency:
        dados["recency"] = options.recency
    if options.after:
        dados["after"] = options.after
    if options.before:
        dados["before"] = options.before
    if options.location is not None:
        local = {
            "country": options.location.country,
            "region": options.location.region,
            "city": options.location.city,
        }
        dados["location"] = {k: v for k, v in local.items() if v}
    if options.custom_instructions.strip():
        dados["custom_instructions"] = _uma_linha(options.custom_instructions)
    return dados


def _yaml_lines(dados: Mapping[str, object], nivel: int) -> list[str]:
    """Emissor de YAML para os poucos tipos que usamos — evita uma dependência só para isto."""
    recuo = "  " * nivel
    linhas: list[str] = []
    for chave, valor in dados.items():
        if isinstance(valor, Mapping):
            linhas.append(f"{recuo}{chave}:")
            linhas += _yaml_lines(valor, nivel + 1)
        elif isinstance(valor, (list, tuple)):
            itens = ", ".join(_yaml_scalar(v) for v in valor)
            linhas.append(f"{recuo}{chave}: [{itens}]")
        else:
            linhas.append(f"{recuo}{chave}: {_yaml_scalar(valor)}")
    return linhas


def _yaml_scalar(valor: object) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, (date, datetime)):
        return f'"{valor.isoformat()}"'
    return f'"{_escape_yaml(str(valor))}"'


def _escape_yaml(texto: str) -> str:
    """Escapa para dentro de aspas duplas do YAML: barra, aspas e quebras de linha."""
    saida = texto.replace("\\", "\\\\").replace('"', '\\"')
    return saida.replace("\n", "\\n").replace("\r", "").replace("\t", "\\t")


# --------------------------------------------------------------------------- texto


def _uma_linha(texto: str) -> str:
    """Colapsa quebras e espaços repetidos — para títulos e campos de uma linha só."""
    return " ".join(texto.split())


def _escape_md(texto: str) -> str:
    """Protege `[` e `]` dentro do rótulo de um link, que senão quebra o link."""
    return texto.replace("[", "\\[").replace("]", "\\]")
