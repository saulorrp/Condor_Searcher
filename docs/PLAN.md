# PLAN — Fases de implementação

Regras: uma fase por sessão · leia só os "Arquivos" listados (+ AGENTS.md) · ao terminar, marque `DONE` e escreva em PROGRESS.md.
Status possíveis: `TODO` · `DOING` · `DONE` · `BLOCKED (motivo)`.

---

## F0 — Esqueleto e verificação da API · `DONE`
**Objetivo:** projeto instalável, chave fora do código, 1 chamada real salva como fixture.
**Arquivos:** AGENTS.md, docs/API_NOTES.md, docs/TECHSPEC.md §3 e §7.
**Tarefas**
1. `pyproject.toml` (setuptools, `src/` layout, nome `condor-searcher`, pacote `condor`, Python ≥3.11).
   Deps: `PySide6`, `perplexityai`, `python-dotenv`. Dev: `pytest`, `pytest-qt`, `ruff`.
   Script: `condor = "condor.__main__:main"`.
2. Estrutura de pastas do TECHSPEC §7 com `__init__.py` vazios; `src/condor/__main__.py` com `main()` que só imprime a versão.
3. `.gitignore` (já existe; conferir), `.env.example` (já existe), `README.md` curto (instalar, configurar `.env`, rodar).
4. `scripts/smoke_api.py`: carrega `.env`, faz `client.responses.create(preset="fast", input=argv[1])`,
   salva `resp.model_dump()` em `tests/fixtures/agent_fast.json` e imprime `output_text`.
   Repetir manualmente com `--preset low` e um domínio em `filters` → `tests/fixtures/agent_low_filtered.json`.
5. Conferir na prática os itens de TECHSPEC §10 e corrigir `docs/API_NOTES.md` se necessário.
6. `run.bat` já existe (RF8): conferir que funciona com o `pyproject.toml` criado; ajustar só se necessário.
**Aceite:** `pip install -e ".[dev]"` ok · `python -m condor` imprime versão · `pytest -q` roda (0 testes ok) ·
duplo clique no `run.bat` numa pasta sem `.venv` cria o ambiente e executa ·
2 fixtures JSON salvas e **sem a chave dentro** (`grep pplx- tests/fixtures` vazio).
**Atenção:** passo 4 é o usuário quem roda (custa dinheiro). O agente escreve o script e para.

## F1 — Modelos e configuração · `DONE`
**Arquivos:** TECHSPEC §4 (RF4), §8; config/*.toml.
**Tarefas:** `core/models.py` (dataclasses do §8); `config/defaults.toml` e `config/prompt_snippets.toml`;
`core/config.py` com `load_defaults(path)`, `load_source_packs(path)`, `load_snippets(path)` → dataclasses.
**Aceite:** testes carregam os 3 TOML reais; pacote com >20 domínios gera aviso (não erro) no carregamento.

## F2 — Prompt builder · `DONE`
**Arquivos:** TECHSPEC §6, §8; API_NOTES §3, §5; `core/models.py`, `core/config.py`.
**Tarefas:** `core/prompt_builder.py`: `build(prompt, options, snippets, timeouts) -> AgentRequest`.
Briefing no formato do §6; payload conforme API_NOTES §3; omitir chaves vazias; denylist prefixa `-`;
datas → MM/DD/YYYY; modo avançado adiciona `instructions` + trecho de citação. `ValueError` com mensagem em PT nas validações.
**Aceite:** ≥10 testes (default; allow/deny; recency vs. datas; >20 domínios; localização; instruções próprias; prompt vazio).
Snapshot do payload default em `tests/fixtures/payload_default.json`.

## F3 — Parser da resposta · `DONE`
**Arquivos:** API_NOTES §4; `core/models.py`; fixtures da F0.
**Tarefas:** `core/response_parser.py`: `parse(raw: dict) -> SearchResult`. Juntar múltiplos `search_results`,
dedupe por URL, tolerar campos ausentes, ignorar tipos desconhecidos, `cost_usd=None` se não houver.
**Aceite:** testes com as 2 fixtures reais + 1 fixture sintética "esquisita" (sem usage, item desconhecido, resultado sem data).

## F4 — Relatório Markdown · `DONE`
**Arquivos:** TECHSPEC RF3; API_NOTES §5; `core/models.py`.
**Tarefas:** `core/markdown_report.py`: `render(result, prompt, options, briefing, created_at) -> str`;
`core/naming.py`: `slugify` e `report_basename(created_at, prompt)` seguros no Windows (sem `<>:"/\|?*`, ≤80 chars).
Citações → links (fora de blocos de código); seção Fontes; seção Parâmetros; front matter YAML válido (escapar aspas).
**Aceite:** testes de citação (`[1]`, `[web:2]`, id inexistente, dentro de ``` não muda); golden file `tests/fixtures/report_expected.md`.

## F5 — Cliente da API · `DONE`
**Arquivos:** API_NOTES §1, §3, §6; `core/models.py`.
**Tarefas:** `services/errors.py`; `services/client.py`: `class AgentClient` com `run(req: AgentRequest) -> dict`,
retries com backoff (2/4/8s), `cancel()` cooperativo (flag checada entre tentativas), mensagens em PT.
O SDK é injetável (`client_factory`) para testes.
**Aceite:** testes com SDK falso: sucesso; 429→sucesso na 2ª; 401 sem retry; timeout esgota 3 tentativas; nenhum log contém a chave.

## F6 — Armazenamento · `DONE`
**Arquivos:** TECHSPEC §9; `core/models.py`, `core/naming.py`.
**Tarefas:** `services/storage.py`: `save(result, md, prompt, options) -> SearchRecord` (grava .md, .json, linha SQLite);
`list_recent(limit)`, `get(id)`, `delete(id)`; pasta de saída configurável; `services/settings_store.py` (última config em JSON).
`services/secrets.py` (TECHSPEC RF7): `get_key()`, `key_source()` ("sistema" | ".env" | None), `save_key(k)`, `remove_key()`,
`mask(k) -> "pplx-…AB12"`, `is_valid_format(k)`. Caminho do `.env` injetável para testes.
**Aceite:** testes com `tmp_path`; nomes duplicados no mesmo minuto ganham sufixo `-2`;
`save_key` preserva outras linhas do `.env`; `mask` nunca devolve mais que 4 caracteres finais; variável de sistema tem prioridade.

## F7 — UI mínima ponta a ponta · `DONE` (falta o seu teste com busca real)
**Arquivos:** TECHSPEC RF1, RF2, §7 (fluxo); assinaturas públicas de core/services (não ler implementações).
**Tarefas:** `ui/worker.py` (QRunnable + sinais `finished(SearchRecord)`, `failed(str)`, `progress(str)`);
`ui/main_window.py` (QTabWidget + status bar); `ui/search_panel.py` (QPlainTextEdit + Buscar/Cancelar, Ctrl+Enter);
`ui/result_tab.py` (QTextBrowser `setOpenExternalLinks(True)`, rodapé, botões Abrir pasta/Copiar/Ver JSON).
`ui/api_key_dialog.py` (TECHSPEC RF7) + menu *Configurações → Chave da API…*; abre sozinho se não houver chave;
erro 401 oferece "Trocar chave…". Usa só `SearchOptions()` default. `__main__.main()` abre a janela.
**Aceite:** busca real abre aba com links clicáveis e salva .md; janela não congela (dá para arrastar durante a busca);
sem chave → diálogo aparece, salvar → busca funciona sem reiniciar; teste pytest-qt de fumaça com client falso.

## F8 — Painel de opções · `DONE`
**Arquivos:** TECHSPEC RF4, §6; `ui/search_panel.py`; `core/config.py` (assinaturas).
**Tarefas:** `ui/options_widget.py` com todos os controles do RF4 (recolhível); contador "N/20 domínios";
botões *Ver prompt final* (diálogo com JSON) e *Restaurar padrões*; carregar/salvar última config via settings_store.
**Aceite:** cada opção altera o payload mostrado em "Ver prompt final"; combinações inválidas desabilitam o Buscar com dica.

## F9 — Histórico · `DONE`
**Arquivos:** TECHSPEC RF5; `services/storage.py` (assinaturas); `ui/main_window.py`.
**Tarefas:** `ui/history_panel.py` (QDockWidget com lista/tabela); duplo clique reabre; menu de contexto (Repetir, Abrir arquivo, Excluir).
**Aceite:** histórico sobrevive a reiniciar o app; "Repetir" preenche prompt e opções idênticos.

## F10 — Polimento (opcional) · `TODO`
Escolher itens isolados, um por sessão. Feitos: ~~ícone~~ (F8), ~~streaming do texto~~ (F10 — falta a
verificação com busca real paga). Restam:
modo background para `high`/`xhigh`; tema escuro; empacotar com PyInstaller
(`--windowed`, usar `docs/icon/icon.ico` — ver pendência do .ico no PROGRESS);
exportar para PDF/DOCX; importar os prompts dos scripts antigos como "modelos de busca";
atalho na área de trabalho para o `run.bat`; guardar a chave no Gerenciador de Credenciais do Windows (`keyring`) em vez do `.env`.
