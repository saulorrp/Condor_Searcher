"""Monta o que será enviado à Agent API (TECHSPEC §6, API_NOTES §3).

`build()` é a única porta: recebe o que o usuário digitou e escolheu, devolve um `AgentRequest`
com o payload pronto, o briefing exato (que o relatório republica, RF3 item 4) e o timeout do preset.

Duas regras de formato que vale repetir, porque são fáceis de errar:
- a API quer datas em **MM/DD/YYYY**; o briefing, que é texto em português lido por humanos,
  usa **DD/MM/YYYY**. São o mesmo dia escrito para dois leitores diferentes.
- no modo denylist **todos** os domínios vão prefixados por `-`; a API não aceita misturar
  allowlist e denylist na mesma lista.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from condor.core.config import Snippets
from condor.core.models import (
    CONTEXT_SIZES,
    DOMAIN_MODES,
    MAX_DOMAINS,
    MAX_RESULTS,
    MIN_RESULTS,
    PRESETS,
    RECENCIES,
    AgentRequest,
    SearchOptions,
)

#: Trecho mínimo de regras de citação anexado às `instructions` próprias (API_NOTES §5).
#: Sem isto, instruções próprias substituem as do preset e os marcadores `[n]` desaparecem.
CITATION_RULES = (
    "Baseie cada afirmação factual nos resultados de busca numerados. Após cada frase que use "
    "uma fonte, cite o número entre colchetes, sem espaço antes, como [1] ou [1][2]. "
    "Não invente números nem crie seção de referências."
)

#: Como cada valor de `recency` é dito no briefing.
_RECENCY_TEXT: Mapping[str, str] = {
    "hour": "apenas conteúdo publicado na última hora",
    "day": "apenas conteúdo publicado nas últimas 24 horas",
    "week": "apenas conteúdo publicado na última semana",
    "month": "apenas conteúdo publicado no último mês",
    "year": "apenas conteúdo publicado no último ano",
}


def build(
    prompt: str,
    options: SearchOptions,
    snippets: Snippets,
    timeouts: Mapping[str, int],
) -> AgentRequest:
    """Valida as opções e monta o `AgentRequest`.

    Levanta `ValueError` com mensagem em português em qualquer combinação inválida.
    """
    pergunta = prompt.strip()
    if not pergunta:
        raise ValueError("Escreva a sua pergunta antes de buscar.")

    _validate_choices(options)
    domains = _clean_domains(options.domains)
    _validate_period(options)
    timeout_s = _timeout_for(options.preset, timeouts)

    briefing = _briefing(options, domains, snippets)
    payload = _payload(pergunta, briefing, options, domains)
    return AgentRequest(payload=payload, briefing=briefing, timeout_s=timeout_s)


# --------------------------------------------------------------------------- validações


def _validate_choices(options: SearchOptions) -> None:
    if options.preset not in PRESETS:
        raise ValueError(f"Profundidade desconhecida: {options.preset!r}. Use uma de {', '.join(PRESETS)}.")
    if options.domain_mode not in DOMAIN_MODES:
        raise ValueError(
            f"Modo do filtro desconhecido: {options.domain_mode!r}. "
            'Use "allow" (somente estes) ou "deny" (excluir estes).'
        )
    if options.context_size not in CONTEXT_SIZES:
        raise ValueError(
            f"Profundidade de leitura desconhecida: {options.context_size!r}. "
            f"Use uma de {', '.join(CONTEXT_SIZES)}."
        )
    if options.recency is not None and options.recency not in RECENCIES:
        raise ValueError(f"Período desconhecido: {options.recency!r}. Use um de {', '.join(RECENCIES)}.")
    if not MIN_RESULTS <= options.max_results <= MAX_RESULTS:
        raise ValueError(
            f"O máximo de resultados deve ficar entre {MIN_RESULTS} e {MAX_RESULTS} "
            f"(recebi {options.max_results})."
        )
    if options.location is not None and len(options.location.country) != 2:
        raise ValueError(
            "A localização precisa do país em duas letras (ISO-3166 alfa-2), como PT ou BR "
            f"(recebi {options.location.country!r})."
        )


def _clean_domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    """Tira espaços, o `-` que o usuário possa ter digitado e duplicatas; valida o limite da API."""
    limpos: list[str] = []
    for raw in domains:
        domain = raw.strip().lstrip("-").strip()
        if domain and domain not in limpos:
            limpos.append(domain)
    if len(limpos) > MAX_DOMAINS:
        raise ValueError(
            f"A busca aceita no máximo {MAX_DOMAINS} domínios e você escolheu {len(limpos)}. "
            "Desmarque algum pacote de fontes ou remova domínios extras."
        )
    return tuple(limpos)


def _validate_period(options: SearchOptions) -> None:
    tem_intervalo = options.after is not None or options.before is not None
    if options.recency is not None and tem_intervalo:
        raise ValueError(
            "Escolha um período OU um intervalo de datas, não os dois: a API não aceita "
            "filtro de recência junto com datas."
        )
    if options.after is not None and options.before is not None and options.after > options.before:
        raise ValueError(
            f"A data inicial ({_br(options.after)}) é posterior à final ({_br(options.before)})."
        )


def _timeout_for(preset: str, timeouts: Mapping[str, int]) -> int:
    try:
        return int(timeouts[preset])
    except KeyError as exc:
        raise ValueError(f"Falta o timeout do preset {preset!r} na configuração.") from exc


# --------------------------------------------------------------------------- briefing


def _briefing(options: SearchOptions, domains: tuple[str, ...], snippets: Snippets) -> str:
    """Bloco `<briefing>` no formato do TECHSPEC §6, sem as linhas que não se aplicam."""
    linhas: list[str] = [
        _snippet_text(snippets.language, options.language, "Idioma"),
        _snippet_text(snippets.output_format, options.output_format, "Formato"),
    ]

    if options.priorities:
        linhas.append("Prioridades:")
        linhas += [f"- {_snippet_text(snippets.priority, key, 'Prioridade')}" for key in options.priorities]

    if domains:
        lista = ", ".join(domains)
        if options.domain_mode == "deny":
            linhas.append(f"Escopo de fontes: não use estes domínios: {lista}.")
        else:
            linhas.append(f"Escopo de fontes: domínios restritos a: {lista}.")

    periodo = _periodo_texto(options)
    if periodo:
        linhas.append(periodo)

    return "\n".join(linhas)


def _periodo_texto(options: SearchOptions) -> str:
    if options.recency is not None:
        return f"Período: {_RECENCY_TEXT[options.recency]}."
    if options.after is not None and options.before is not None:
        return f"Período: publicações entre {_br(options.after)} e {_br(options.before)}."
    if options.after is not None:
        return f"Período: publicações a partir de {_br(options.after)}."
    if options.before is not None:
        return f"Período: publicações até {_br(options.before)}."
    return ""


def _snippet_text(lookup, key: str, what: str) -> str:
    """Busca o texto no `Snippets` e converte o `KeyError` em `ValueError` em português."""
    try:
        return lookup(key).text
    except KeyError as exc:
        raise ValueError(f"{what} desconhecido na configuração: {key!r}.") from exc


# --------------------------------------------------------------------------- payload


def _payload(
    pergunta: str,
    briefing: str,
    options: SearchOptions,
    domains: tuple[str, ...],
) -> dict:
    """Payload do `responses.create` (API_NOTES §3), sem chaves vazias e sem o timeout."""
    payload: dict = {
        "preset": options.preset,
        "input": f"<briefing>\n{briefing}\n</briefing>\n\n<pergunta>\n{pergunta}\n</pergunta>",
    }

    custom = options.custom_instructions.strip()
    if custom:
        # Modo avançado: substituímos o prompt do preset, então reanexamos as regras de citação.
        payload["instructions"] = f"{custom}\n\n{CITATION_RULES}"

    tool: dict = {
        "type": "web_search",
        "search_context_size": options.context_size,
        "max_results": options.max_results,
    }

    if options.location is not None:
        location = {
            "country": options.location.country.upper(),
            "region": options.location.region.strip(),
            "city": options.location.city.strip(),
        }
        tool["user_location"] = {k: v for k, v in location.items() if v}

    filters: dict = {}
    if domains:
        prefixo = "-" if options.domain_mode == "deny" else ""
        filters["search_domain_filter"] = [f"{prefixo}{d}" for d in domains]
    if options.recency is not None:
        filters["search_recency_filter"] = options.recency
    if options.after is not None:
        filters["search_after_date_filter"] = _api_date(options.after)
    if options.before is not None:
        filters["search_before_date_filter"] = _api_date(options.before)
    if filters:
        tool["filters"] = filters

    payload["tools"] = [tool]
    return payload


def _api_date(value: date) -> str:
    """MM/DD/YYYY — o formato que a API exige (API_NOTES §3)."""
    return f"{value.month:02d}/{value.day:02d}/{value.year}"


def _br(value: date) -> str:
    """DD/MM/YYYY — para o briefing e as mensagens de erro, que são em português."""
    return f"{value.day:02d}/{value.month:02d}/{value.year}"
