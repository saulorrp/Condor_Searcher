# API_NOTES — Perplexity Agent API (verificado em 06/10/2026)

> Fonte: docs.perplexity.ai (agent-api/presets, tools/web-search, migrate-from-sonar). Agentes: usem ESTE arquivo, não a web.
> Se algo aqui divergir do comportamento real, corrija aqui e registre em PROGRESS.md.

## 1. Instalação e cliente
```bash
pip install perplexityai          # import: from perplexity import Perplexity  (confirmado na F0: 0.43.7)
```
```python
from perplexity import Perplexity
client = Perplexity()             # lê PERPLEXITY_API_KEY do ambiente
resp = client.responses.create(preset="low", input="pergunta")
print(resp.output_text)
```
HTTP equivalente: `POST https://api.perplexity.ai/v1/agent` com `Authorization: Bearer $PERPLEXITY_API_KEY`.

## 2. Presets
| Preset | Uso | Passos máx. | Observação |
|---|---|---|---|
| `fast` | fato único, resumo rápido | 1 | citações `[1]` |
| `low` | pesquisa do dia a dia | 5 | citações `[web:1]`; inclui `fetch_url` |
| `medium` | multi-hop, muitas fontes | 15 | `[web:n]` |
| `high` | pesquisa exaustiva | 15 | modelo mais forte; `[web:n]` |
| `xhigh` | tarefas abertas com sandbox | 100 | caro e lento; sem `fetch_url`, com `sandbox` |

Qualquer campo passado junto com `preset` sobrescreve o default. **Exceção:** `tools` é mesclado por ferramenta
(passar só `web_search` ajusta só ele; as outras ferramentas do preset continuam).
Passar `instructions` **substitui** o prompt de sistema do preset.

## 3. Request usado pelo Condor
```python
client.responses.create(
    preset="low",
    input="<briefing>...</briefing>\n\n<pergunta>...</pergunta>",
    # instructions="..."            # só no modo avançado
    tools=[{
        "type": "web_search",
        "search_context_size": "medium",          # low | medium | high
        "max_results": 15,                        # 1..50 — funciona (ver nota abaixo)
        # "search_type": "web",                   # "fast" (padrão dos presets) | "web" (2,5x mais caro)
        "max_tokens": 4000,                       # opcional: teto de tokens de busca
        "max_tokens_per_page": 1024,              # opcional: teto por página
        "user_location": {"country": "PT", "region": "Lisboa", "city": "Lisboa"},   # opcional, ao lado de filters
        "filters": {
            "search_domain_filter": ["ulisboa.pt", "dglab.gov.pt"],   # até 20; OU tudo com "-" (denylist), nunca misturar
            "search_recency_filter": "month",                         # hour|day|week|month|year
            # "search_after_date_filter": "01/31/2026",               # MM/DD/YYYY (excludente com recency)
            # "search_before_date_filter": "06/30/2026",
            # "last_updated_after_filter": "01/31/2026",                # idem, por data de atualização
            # "last_updated_before_filter": "06/30/2026",
        },
    }],
    timeout=180,                                   # opção do SDK; ajustar por preset
)
```
Regras:
- Omitir chaves vazias (não enviar `filters: {}` nem listas vazias).
- `user_location` fica no nível do tool, ao lado de `filters` (confirmado na F0 contra o SDK);
  aceita `city`, `country`, `region`, `latitude`, `longitude`.
- `user_location.country` é ISO-3166 alfa-2 (`PT`, `BR`). `latitude/longitude` só com `country` (não usamos na v1).
- `search_mode="academic"` **não existe** na Agent API → usar pacote de domínios + briefing.
- `max_tokens` (Sonar) virou `max_output_tokens` **no nível do request**; dentro do tool `web_search`,
  `max_tokens`/`max_tokens_per_page` limitam o conteúdo de busca (coisa diferente).
- ⚠️ **Os tipos do SDK não são a fonte da verdade.** `ToolWebSearchTool` (SDK 0.43.7) é um `TypedDict`,
  que não valida em tempo de execução: chaves fora dos tipos são repassadas ao servidor sem erro.
  Logo, "não está nos tipos do SDK" **não** significa "não existe". Confira contra a doc oficial ou com o smoke.
- `max_results` (1..50) **existe e funciona** — verificado na F0 com chamada real: `max_results: 3` devolveu
  2 resultados, contra 15 numa chamada igual sem o campo. Não aparece nos tipos do SDK 0.43.7, mas passa.
- `search_type` (`"fast"` | `"web"`) **existe e funciona** — verificado na F0 pelo custo: com `search_type: "web"`
  o `search_web` custou US$ 0,0025 contra US$ 0,0010 das chamadas sem o campo. Confirma que os presets usam
  `"fast"` por padrão e que `"web"` é 2,5x mais caro (bate com a tabela do §7). Também fora dos tipos do SDK.
- `temperature` é aceito pelo SDK mas ignorado em vários modelos — não usar.
- Campos do request confirmados na F0: `input`, `instructions`, `preset`, `model(s)`, `tools`, `tool_choice`,
  `max_output_tokens`, `max_steps`, `stream`, `background`, `store`, `previous_response_id`, `reasoning`,
  `response_format`, `skills`, `language_preference`, `timeout`.

## 4. Resposta
```jsonc
{
  "id": "resp_...", "model": "openai/gpt-6-luna", "status": "completed",
  "output": [
    {"type": "search_results", "queries": ["..."], "results": [
       {"id": 1, "url": "https://...", "title": "...", "snippet": "...",
        "date": "2026-05-01", "last_updated": "2026-05-01", "source": "web"}]},
    {"type": "message", "role": "assistant",
     "content": [{"type": "output_text", "text": "Resposta... [1][web:2]", "annotations": []}]}
  ],
  "usage": {"input_tokens": 11476, "output_tokens": 640, "total_tokens": 12116,
            "input_tokens_details": {"cache_creation_input_tokens": 4406, "cache_read_input_tokens": 7061,
                                     "cached_tokens": 7061},
            "output_tokens_details": {"reasoning_tokens": 0},
            "tool_calls_details": {"search_web": {"invocation": 1, "cost_usd": 0.001},
                                   "fetch_url": {"invocation": 1, "cost_usd": 0.0005}},
            "cost": {"currency": "USD", "input_cost": 0.0, "output_cost": 0.00032, "total_cost": 0.00244,
                     "cache_creation_cost": 0.00055, "cache_read_cost": 0.00007, "tool_calls_cost": 0.0015,
                     "tool_calls_cost_details": {"search_web": 0.001, "fetch_url": 0.0005}}}
}
```
- Texto final: `resp.output_text` (atalho do SDK) ou concatenar `output_text` dos itens `message`.
- Podem existir **vários** itens `search_results` (um por chamada de busca) → juntar todos, deduplicar por URL,
  manter o `id` original para mapear citações.
- Outros tipos de item podem aparecer: ignorar sem quebrar. A união do SDK 0.43.7 inclui `message`,
  `search_results`, `image_search_results`, `fetch_url_results`, `function_call`, `mcp_list_tools`, `mcp_call`,
  `tool_search`, `skill_loaded`, `advisor_result`, vários `sandbox_*`, `share_file` e `unknown`.
- **Custo:** `usage.cost.total_cost` (em `usage.cost.currency`). Campo opcional → parse defensivo, ausente = `None`.
  Nas 4 chamadas da F0 ele veio sempre preenchido. Cuidado: subcampos podem vir `null` (ex.: `cache_read_cost`),
  então não some valores sem tratar `None`. Há campos **fora dos tipos do SDK** que a API devolve de verdade:
  `usage.cost.tool_calls_cost_details`, `usage.output_tokens_details` e `cost_usd` dentro de cada
  `usage.tool_calls_details.<ferramenta>` — a F3 deve ignorar o que não conhece, não falhar.
- Campos do item `search_results`: `type`, `queries`, `results[]`; cada resultado tem
  `id`, `url`, `title`, `snippet`, `date`, `last_updated`, `source`. `date`/`last_updated` podem vir `null`.
- `queries` é uma **lista** (o agente dispara várias buscas por item). Nas chamadas da F0 veio com 1 a 3 queries.
- Observado na F0: `fast` devolveu `[search_results, message]`; `low` com `fetch_url` devolveu
  `[search_results, fetch_url_results, message]`. Os `id` dos resultados começam em 1 e são contíguos
  **dentro de cada item** `search_results` — com vários itens, cuidado para não misturar numerações.
- Para converter o objeto do SDK em dict: `resp.model_dump()` (pydantic) — salvar isso como JSON bruto.

## 5. Citações
- Formatos possíveis no texto: `[3]`, `[3][4]`, `[web:3]`, `[web:3][web:7]`.
  Confirmado na F0: `preset="fast"` citou `[2]`; `preset="low"` citou `[web:2]` e `[web:8][web:9]`.
- Regex sugerida: `\[(?:web:)?(\d+)\]` → `[[n]](url_do_id_n)`. Se o `id` não existir nos resultados, deixar o marcador como está.
- Não converter dentro de blocos de código (``` ... ```).
- Trecho mínimo a anexar quando houver `instructions` próprias:
  > Baseie cada afirmação factual nos resultados de busca numerados. Após cada frase que use uma fonte, cite o número
  > entre colchetes, sem espaço antes, como [1] ou [1][2]. Não invente números nem crie seção de referências.

## 6. Erros (mapear em services/errors.py)
| Situação | Exceção do SDK (provável) | Ação |
|---|---|---|
| chave inválida | `AuthenticationError` (401) | `AuthError`, sem retry |
| limite de taxa | `RateLimitError` (429) | retry com backoff |
| rede / timeout | `APIConnectionError`, `APITimeoutError` | retry |
| 5xx | `InternalServerError` / `APIStatusError` | retry |
| texto vazio | — | `EmptyResponseError` |
Nomes confirmados na F0 (`dir(perplexity)`, SDK 0.43.7): `PerplexityError`, `APIError`, `APIStatusError`,
`APIConnectionError`, `APITimeoutError`, `APIResponseValidationError`, `AuthenticationError`, `BadRequestError`,
`PermissionDeniedError`, `NotFoundError`, `ConflictError`, `UnprocessableEntityError`, `RateLimitError`,
`InternalServerError`. Todas importáveis direto de `perplexity`.

## 7. Preço de referência (para exibir estimativa, não para cobrança)
`web_search`: US$ 2,50 / 1.000 chamadas (US$ 1,00 com `search_type: "fast"`, que os presets fast→high já usam) + tokens do modelo.

## 8. Streaming (`stream=True`)
Verificado na F10 contra os tipos do SDK 0.43.7 (`perplexity.types.ResponseStreamChunk`), **sem chamada real**:
o fluxo precisa ser conferido na prática numa busca de verdade.

```python
fluxo = client.responses.create(**payload, stream=True, timeout=180)
for evento in fluxo:          # o objeto também é context manager e tem .close()
    if evento.type == "response.output_text.delta":
        print(evento.delta, end="")
```

Eventos da união `ResponseStreamChunk` (todos têm `type` e `sequence_number`):

| `type` | Campos úteis | Para que serve |
|---|---|---|
| `response.created` / `response.in_progress` | `response` | início; ignorados pelo Condor |
| `response.reasoning.search_results` | `results[]`, `thought`, `usage` | quantas fontes já apareceram (barra de status) |
| `response.output_text.delta` | `delta` (str), `item_id`, `output_index` | o pedaço de texto |
| `response.output_text.done` | `text` (texto completo do item) | fim de um item de texto |
| `response.completed` | `response` (resposta inteira, `Optional`) | **é daqui que sai o mesmo dict do modo normal** |
| `response.failed` | `error` (`code`, `message`, `type`) | falha avisada dentro do fluxo |
| outros | — | `reasoning.*`, `image_search_*`, `fetch_url_*`, `skill_loaded`: ignorar |

Regras adotadas no Condor (`services/client.py`):
- o valor de retorno é **igual** nos dois modos: `response.completed.response.model_dump()`. Se o fluxo acabar
  sem esse evento (ou com ele vazio), é erro — não vale montar uma resposta pela metade.
- retry com streaming precisa avisar quem está exibindo (`StreamSink.restart()`): a tentativa nova recomeça o
  texto do zero, e o pedaço da tentativa falha não pode continuar na tela.
- o cancelamento é verificado a cada evento, e o fluxo é fechado no `finally`.
