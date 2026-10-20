# Condor Searcher — Especificação Técnica (v0.1)

Data: 06/10/2026 · Status: rascunho aprovado para implementação

## 1. Objetivo
Interface desktop mínima para a busca agêntica da Perplexity: o usuário escreve um prompt, ajusta (ou não) opções de busca,
clica **Buscar** e, ao terminar, abre-se uma aba com o resultado renderizado. **Toda busca gera um arquivo `.md`**
com a resposta, links clicáveis para cada citação e uma seção de fontes — independentemente do que o modelo escrever.

### Fora do escopo (v1)
Multiusuário, nuvem, conversa multi-turno, edição do Markdown dentro do app, upload de arquivos, empacotamento instalável
(fica para a fase opcional F10).

## 2. Decisão de API (importante)
Os scripts antigos (`Pesquisa_Lisboa_v2.py`, `Pesquisa_Matricula_ULisboa.py`) usam **Sonar Chat Completions** (`sonar-pro`).
Segundo a doc oficial, o suporte a Sonar Chat Completions terminou em 27/09/2026: requisições síncronas ainda funcionam
porque são reformuladas como Agent API, mas a recomendação é usar a **Agent API** em projetos novos.

**Decisão:** o Condor usa somente a Agent API (`client.responses.create`, endpoint `/v1/agent`) com **presets**.
Detalhes de payload e resposta em `docs/API_NOTES.md`.

| Antigo (Sonar) | Agora (Agent API) |
|---|---|
| `model="sonar-pro"` | `preset="fast"` ou `"low"` |
| `sonar-reasoning-pro` | `preset="medium"` (Perplexity sugere `low`; usamos `medium` para pesquisa) |
| `sonar-deep-research` | `preset="high"` |
| `messages=[...]` | `input=...` (+ `instructions` opcional) |
| `choices[0].message.content` | `response.output_text` |
| `citations` | item `type == "search_results"` em `response.output` |
| `search_mode="academic"` | não existe → pacote de fontes "Acadêmico" + instrução no briefing |

## 3. Stack
| Item | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.11+ | `tomllib` nativo; o usuário já usa Python |
| GUI | **PySide6** (Qt 6, LGPL) | Abas nativas; `QTextBrowser.setMarkdown()` renderiza Markdown estilo GitHub (tabelas, links) sem WebEngine |
| SDK | `perplexityai` (`from perplexity import Perplexity`) | SDK oficial; lê `PERPLEXITY_API_KEY` do ambiente |
| Config | `.env` (python-dotenv) + `config/*.toml` | Segredo fora do código; opções editáveis à mão |
| Persistência | arquivos `.md` + SQLite (`sqlite3` da stdlib) | `.md` é o produto; SQLite é só índice do histórico |
| Testes/Lint | pytest, pytest-qt (UI mínima), ruff | Padrão de mercado, leves |

Alternativas descartadas: Tkinter (não renderiza Markdown), Streamlit/NiceGUI (abas e estado por busca ficam desajeitados;
roda no navegador). Se um dia quiser versão web, `core/` e `services/` são reaproveitados integralmente.

## 4. Requisitos funcionais
**RF1 – Busca.** Caixa de texto multilinha + botão **Buscar** (atalho Ctrl+Enter). Durante a busca: botão vira **Cancelar**,
barra de status mostra preset e tempo decorrido. A UI nunca congela.

**RF2 – Resultado em aba.** Cada busca concluída abre uma aba nova (título = 40 primeiros caracteres do prompt) com:
Markdown renderizado, links abrem no navegador do sistema, rodapé com custo/tokens/nº de buscas, botões
*Abrir pasta*, *Copiar Markdown*, *Ver JSON bruto*.

**RF3 – Markdown sempre com links.** O app (não o modelo) monta o arquivo final:
1. Front matter YAML: prompt, data/hora, preset, opções usadas, custo, id da resposta.
2. Corpo: `output_text` com marcadores de citação convertidos em links (`[3]` ou `[web:3]` → `[[3]](url)`).
3. Seção `## Fontes`: lista numerada a partir de `search_results` (título, domínio, data de publicação, URL), sem duplicatas, na ordem do `id`.
4. Seção `## Parâmetros da busca`: o briefing exato enviado (transparência e reprodutibilidade).

**RF4 – Opções de busca** (painel recolhível "Opções"; todas com default; todas viram parte do payload ou do briefing):

| Opção | Valores | Default | Vai para |
|---|---|---|---|
| Profundidade (preset) | Rápida `fast` · Padrão `low` · Aprofundada `medium` · Exaustiva `high` · (Agente `xhigh`, oculto atrás de "Avançado") | `low` | `preset` |
| Pacotes de fontes | multiseleção de `config/source_packs.toml` | nenhum | `filters.search_domain_filter` (união, máx. 20) |
| Domínios extras | texto livre, um por linha | vazio | idem |
| Modo do filtro | Somente estes (allowlist) · Excluir estes (denylist, prefixo `-`) | allowlist | idem |
| Período | qualquer · última hora/dia/semana/mês/ano · intervalo de datas | qualquer | `search_recency_filter` ou `search_after/before_date_filter` (MM/DD/YYYY) |
| Localização | desligada · país (ISO-2) + região + cidade | desligada (atalho "Portugal – Lisboa") | `user_location` no tool |
| Profundidade de leitura | baixa · média · alta | média | `search_context_size` |
| Máx. resultados | 1–50 | 15 | `max_results` |
| Idioma da resposta | pt-BR · pt-PT · en · es | pt-BR | briefing |
| Formato | Resposta direta · Relatório estruturado · Tabela comparativa · Bibliografia anotada · Dossiê tático | Relatório estruturado | briefing |
| Prioridades (checkboxes) | Fontes primárias/oficiais · Relatos de fóruns · Apontar divergências entre fontes · Indicar nível de confiança · Terminar com perguntas de seguimento | 1ª e 3ª marcadas | briefing |
| Instruções de sistema próprias | texto (campo avançado) | vazio | `instructions` (substitui as do preset — ver §6) |

Botão **Ver prompt final** mostra exatamente o que será enviado (payload JSON sem a chave). Botão **Restaurar padrões**.
Última configuração usada é lembrada entre sessões.

**RF5 – Histórico.** Painel lateral com buscas anteriores (data, prompt, preset, custo). Duplo clique reabre a aba a partir
do `.md` salvo; menu de contexto: *Repetir busca com as mesmas opções*, *Abrir arquivo*, *Excluir do histórico* (não apaga o `.md`).

**RF6 – Erros.** Chave ausente/inválida, rede, timeout, rate limit (429) e resposta vazia geram mensagem clara em português.
Rede/timeout/429 têm até 3 tentativas com backoff (2s, 4s, 8s). Erro de autenticação não repete.
Erro 401 mostra o botão **Trocar chave…** (abre o diálogo do RF7).

**RF7 – Chave da API pela interface.** Menu *Configurações → Chave da API…* abre um diálogo com:
- campo mascarado (`QLineEdit.EchoMode.Password`) + botão "mostrar" (olho) enquanto digita;
- texto "Chave atual: pplx-…AB12" (só os 4 últimos caracteres; nunca a chave inteira) ou "nenhuma chave configurada";
- validação de formato (`pplx-` + ≥ 20 caracteres, sem espaços) antes de salvar;
- botão **Salvar**: grava/atualiza `PERPLEXITY_API_KEY` no arquivo `.env` da pasta do app (`dotenv.set_key`),
  aplica na hora (recria o cliente; não precisa reiniciar);
- botão **Testar chave** (opcional, avisa que custa uma fração de centavo): busca mínima com `preset="fast"`;
- botão **Remover chave**: apaga a linha do `.env` (com confirmação).
Na primeira execução, se não houver chave, o diálogo abre sozinho antes da janela principal ficar utilizável.
Ordem de leitura da chave: variável de ambiente do sistema já definida → `.env` da pasta do app.
Se a chave vier de variável de sistema, o diálogo avisa que o `.env` não terá efeito.

**RF9 – Linha de comando (`condor-cli`).** Tudo o que a janela faz, sem Qt, para uso por script ou agente:
- `buscar` (todas as opções do RF4 como flags), `historico`, `ver <id>`, `gastos`;
- `--so-prompt` mostra o payload sem chamar a API; `--json` devolve objeto estável para consumo por máquina;
- **teto diário de gastos** (`[limits].daily_usd`), porque quem dispara pode não estar por perto;
- códigos de saída distinguem uso, configuração, API, teto, chave e "não encontrado".
O fluxo de uma busca vive em `services/search_runner.py` e é o mesmo nos dois caminhos.

**RF8 – Execução com duplo clique (`run.bat`).** Na raiz do projeto:
- 1ª execução: localiza Python ≥ 3.11 (`py -3` ou `python`), cria `.venv`, instala o app (`pip install -e .`) e abre;
- execuções seguintes: só abre, via `pythonw.exe` (sem janela preta de console);
- `run.bat --atualizar` reinstala dependências (usar depois de `git pull` ou de uma fase nova);
- `run.bat --console` abre com console visível, para ver erros/logs;
- se algo falhar, a janela do console fica aberta com a mensagem (`pause`).
Opcional: atalho na área de trabalho apontando para o `run.bat` (F10).

## 5. Requisitos não funcionais
- UI responsiva: nenhuma chamada de rede ou disco pesado na thread principal.
- Timeouts por preset: fast 90s · low 180s · medium 420s · high 900s · xhigh 1800s (configurável em `config/defaults.toml`).
- Chave da API só via `PERPLEXITY_API_KEY` (variável de sistema ou `.env`, que está no `.gitignore`), gravada pelo diálogo do RF7.
  Nada de chave no código, logs, JSON salvo ou mensagens de erro. O `.env` é texto puro: protegido apenas pelas permissões
  da sua conta do Windows (aceitável para uso pessoal; ver F10 para cofre do sistema).
- UTF-8 em todos os arquivos; nomes de arquivo seguros no Windows.
- `core/` com ≥ 90% de cobertura; `services/` testado com fixtures; UI com 1–2 testes de fumaça (pytest-qt).

## 6. Como o prompt é montado (o "briefing")
Os presets da Perplexity trazem `instructions` próprias, afinadas pela empresa (regras de citação, busca, formato).
Enviar `instructions` **substitui** essas regras. Por isso:

- **Padrão:** não enviamos `instructions`. As opções do usuário viram um **bloco de briefing** colocado antes da pergunta no `input`.
- **Avançado:** se o usuário preencher "Instruções de sistema próprias", elas vão em `instructions` e o app acrescenta
  automaticamente o trecho mínimo de regras de citação (ver API_NOTES §5) para não perder os marcadores `[n]`.

Formato do `input` gerado por `core/prompt_builder.py`:
```
<briefing>
Idioma da resposta: português do Brasil.
Formato: relatório estruturado com seções ## e conclusão curta.
Prioridades:
- Prefira fontes primárias e oficiais; cite a fonte de cada afirmação.
- Quando as fontes divergirem, diga explicitamente onde e por quê.
Escopo de fontes: domínios restritos a: ulisboa.pt, dglab.gov.pt, ...
Período: publicações após 01/01/2025.
</briefing>

<pergunta>
{texto digitado pelo usuário}
</pergunta>
```
Os textos de cada formato/prioridade ficam em `config/prompt_snippets.toml` (editáveis sem mexer no código).

## 7. Arquitetura
```
condor-searcher/
├─ AGENTS.md · CLAUDE.md · README.md · pyproject.toml · .env.example · .gitignore
├─ run.bat                   # duplo clique no Windows (RF8)
├─ config/
│  ├─ defaults.toml          # defaults da UI, timeouts, pasta de saída
│  ├─ source_packs.toml      # pacotes de domínios
│  └─ prompt_snippets.toml   # textos do briefing por formato/prioridade/idioma
├─ docs/  TECHSPEC.md · PLAN.md · API_NOTES.md · PROGRESS.md
├─ scripts/smoke_api.py      # chamada real manual; salva JSON em tests/fixtures/
├─ src/condor/
│  ├─ __main__.py            # python -m condor
│  ├─ core/                  # PURO
│  │  ├─ models.py           # dataclasses + options_to_dict/options_from_dict
│  │  ├─ config.py           # lê TOML → objetos (recebe caminhos, não acha sozinho)
│  │  ├─ prompt_builder.py   # SearchOptions → AgentRequest (payload dict + briefing)
│  │  ├─ response_parser.py  # dict da resposta → SearchResult
│  │  ├─ markdown_report.py  # SearchResult → str Markdown
│  │  └─ naming.py           # slug/nome de arquivo
│  ├─ services/
│  │  ├─ errors.py           # CondorError, AuthError, NetworkError, RateLimitError, EmptyResponseError
│  │  ├─ client.py           # único import do SDK; retries/timeouts
│  │  ├─ storage.py          # grava .md/.json, SQLite do histórico
│  │  ├─ search_runner.py    # o fluxo de uma busca (§7), compartilhado por ui/ e cli/
│  │  ├─ settings_store.py   # lembra última configuração (JSON na pasta de dados)
│  │  └─ secrets.py          # lê/grava/remove a chave no .env; mascara para exibição (RF7)
│  ├─ cli/                   # linha de comando (RF9), sem Qt
│  │  ├─ main.py             # parser e entrada do `condor-cli`
│  │  ├─ app.py              # os comandos e os códigos de saída
│  │  ├─ options.py          # flags -> SearchOptions
│  │  └─ output.py           # texto para humano, JSON para agente
│  └─ ui/
│     ├─ main_window.py      # janela, abas, menu, status bar
│     ├─ search_panel.py     # prompt + botão + painel de opções
│     ├─ options_widget.py   # significado das opções do RF4
│     ├─ options_form.py     # os controles em si (layout e rótulos)
│     ├─ assets.py           # ícone do app (lido de docs/icon/)
│     ├─ api_key_dialog.py   # diálogo da chave (RF7)
│     ├─ dialogs.py          # caixas de diálogo da janela (costura para os testes)
│     ├─ result_tab.py       # QTextBrowser + rodapé
│     ├─ history_panel.py    # painel lateral do histórico (RF5)
│     └─ worker.py           # QThread/QRunnable + sinais
└─ tests/  (espelha src/condor; fixtures/*.json)
```

### Fluxo de uma busca
```
SearchPanel ─(SearchOptions)─► prompt_builder.build() ─► AgentRequest
     │                                                       │
     └─► Worker (thread) ─► client.run(AgentRequest) ─► dict bruto
                                    │
            response_parser.parse() ─► SearchResult ─► markdown_report.render() ─► str
                                    │
            storage.save(result, md) ─► caminho .md + linha no SQLite
                                    │
     ◄── sinal finished(SearchRecord) ── MainWindow abre ResultTab
```

## 8. Modelos de dados (`core/models.py`)
```python
Preset = Literal["fast", "low", "medium", "high", "xhigh"]

@dataclass(frozen=True)
class LocationOpt:   country: str; region: str = ""; city: str = ""

@dataclass(frozen=True)
class SearchOptions:
    preset: Preset = "low"
    domains: tuple[str, ...] = ()          # já sem o "-"
    domain_mode: Literal["allow", "deny"] = "allow"
    recency: Literal["hour","day","week","month","year"] | None = None
    after: date | None = None; before: date | None = None
    location: LocationOpt | None = None
    context_size: Literal["low","medium","high"] = "medium"
    max_results: int = 15
    language: str = "pt-BR"
    output_format: str = "relatorio"
    priorities: tuple[str, ...] = ("primarias", "divergencias")
    custom_instructions: str = ""

@dataclass(frozen=True)
class AgentRequest:  payload: dict; briefing: str; timeout_s: int

@dataclass(frozen=True)
class Source:        id: int; url: str; title: str; date: str | None; last_updated: str | None; snippet: str

@dataclass(frozen=True)
class Usage:         input_tokens: int; output_tokens: int; search_calls: int; cost_usd: float | None

@dataclass(frozen=True)
class SearchResult:  response_id: str; model: str; text: str; sources: tuple[Source, ...]; queries: tuple[str, ...]; usage: Usage; raw: dict

@dataclass(frozen=True)
class SearchRecord:  id: int; created_at: datetime; prompt: str; options: SearchOptions; md_path: Path; cost_usd: float | None
```
Validações em `prompt_builder`: prompt não vazio; ≤ 20 domínios; recency e intervalo de datas são mutuamente exclusivos;
latitude/longitude não são usadas na v1.

## 9. Saída em disco
Pasta padrão: `Documentos/CondorSearcher/` (configurável).
- `AAAA-MM-DD_HHMM_slug-do-prompt.md` — o produto.
- `AAAA-MM-DD_HHMM_slug-do-prompt.json` — resposta bruta (para depurar e gerar fixtures).
- `condor.db` — SQLite: tabela `searches(id, created_at, prompt, options_json, preset, md_path, json_path, cost_usd, response_id)`.

## 10. Riscos e pontos a verificar na F0
- ~~Nome do pacote pip e versão do SDK que aceita `search_type`/`user_location` no tool.~~ **Resolvido na F0:**
  `perplexityai==0.43.7`; os tipos do SDK são `TypedDict` (não validam), então `max_results` e `search_type`
  passam e funcionam mesmo sem estar tipados. Ver `docs/API_NOTES.md` §3.
- ~~Posição de `user_location`.~~ **Resolvido na F0:** é campo do tool, ao lado de `filters`.
- ~~Campos de custo em `usage`.~~ **Resolvido na F0:** `usage.cost.total_cost` + `currency`; subcampos podem vir `null`.
- `QTextBrowser` não renderiza LaTeX: aceitável na v1 (fica como texto).
- Presets são dinâmicos (a Perplexity muda o modelo por trás); custo/latência podem variar levemente.
