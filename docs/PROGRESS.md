# PROGRESS — diário de bordo (mais recente embaixo)

Formato: `## AAAA-MM-DD · Fase · agente` + 3–6 bullets (feito, decisões, pendências). Não apague entradas antigas.

## 2026-10-06 · Planejamento · Claude
- Criados AGENTS.md, CLAUDE.md, TECHSPEC, PLAN, API_NOTES, config/source_packs.toml, .env.example, .gitignore.
- Decisão: Agent API com presets (Sonar Chat Completions sem suporte desde 27/09/2026).
- Decisão: PySide6 + QTextBrowser.setMarkdown (sem WebEngine).
- Decisão: opções viram "briefing" no `input`; `instructions` só no modo avançado (preserva prompt do preset).
- Pendência F0: confirmar nome do pacote pip, posição de `user_location`, campo de custo em `usage`.
- Segurança: a chave antiga estava hardcoded nos scripts `Pesquisa_*.py` → usuário deve gerar chave nova.

## 2026-10-06 · F0 Esqueleto e verificação da API · Claude
- Criados `pyproject.toml` (setuptools, src-layout, script `condor`), estrutura do TECHSPEC §7 com `__init__.py`
  vazios, `src/condor/__main__.py` (imprime versão), `README.md` e `scripts/smoke_api.py`.
- `pip install -e ".[dev]"` ok · `python -m condor` → "Condor Searcher 0.1.0" · `pytest -q` verde · `ruff` limpo.
- Decisão: `__version__` vive em `src/condor/__init__.py` (único init não vazio) e o pyproject o lê via
  `[tool.setuptools.dynamic]` — fonte única da versão. Adicionado `tests/test_skeleton.py` porque `pytest`
  sai com código 5 (não-zero) quando não coleta teste nenhum.
- Pendências F0 resolvidas contra o SDK instalado (`perplexityai==0.43.7`, sem chamar a API): `user_location`
  é campo do tool ao lado de `filters` ✔; custo existe em `usage.cost.total_cost` + `currency` ✔; nomes das
  exceções confirmados (`AuthenticationError`, `RateLimitError`, `APITimeoutError`, ...) ✔.
- Correção em `docs/API_NOTES.md`: **não existe `max_results` no tool `web_search`** (nem `search_type`);
  os campos reais são `search_context_size`, `max_tokens`, `max_tokens_per_page`. Também documentados
  `last_updated_{after,before}_filter` e a lista de tipos de item de `output`. Isso afeta a F2/F3.
- **PENDENTE (usuário):** rodar `python scripts/smoke_api.py "pergunta"` e depois com
  `--preset low --domain <dominio>` para gerar `tests/fixtures/agent_fast.json` e `agent_low_filtered.json`.
  A F3 depende dessas duas fixtures.

## 2026-10-06 · Planejamento (rev. 2) · Claude
- Novo RF7: diálogo "Chave da API" grava no `.env` (services/secrets.py na F6, ui/api_key_dialog.py na F7).
- Novo RF8: `run.bat` na raiz (cria .venv na 1ª vez, abre com pythonw; `--atualizar`, `--console`). Conferir na F0.

## 2026-10-06 · F0 (fecho): mescla da rev. 2 + smoke test real · Claude
- **Mescla do kit_v2** (sem desfazer a F0): TECHSPEC ganhou RF7 (diálogo da chave), RF8 (`run.bat`), a linha de
  segurança do §5 e os arquivos novos da árvore §7; PLAN ganhou o passo 6 da F0 e as tarefas/aceites novos de
  F6 (`services/secrets.py`), F7 (`ui/api_key_dialog.py`) e F10; AGENTS.md ganhou as 2 linhas alteradas.
  F0 segue `DONE`. `docs/API_NOTES.md` manteve a minha versão (a do kit foi descartada). `kit_v2/` apagado.
  Também restaurei `.env.example` na raiz, que havia desaparecido.
- **`run.bat` conferido** (RF8): `--console` imprime a versão; numa pasta sem `.venv` (testada numa cópia limpa)
  ele cria o ambiente, roda `pip install -e .` e executa. Nenhum ajuste foi necessário. Até a F7, o modo sem
  argumento (pythonw) não mostra nada — é esperado, ainda não há janela.
- **`scripts/smoke_api.py`**: novos `--max-results N`, `--search-type fast|web`, `--out NOME` (nome simples vai
  para `tests/fixtures/`); agora imprime versão do SDK, nº de resultados e URLs por item `search_results`,
  o `usage` inteiro, os tipos de item de `output` e, em caso de falha, status/corpo/atributos do erro.
- **4 chamadas reais** (autorizadas nesta sessão), todas exit 0, fixtures em `tests/fixtures/`:
  (a) `fast` → `agent_fast.json`, 10 resultados, US$ 0,00137, citou `[2]`;
  (b) `low --domain dglab.gov.pt` → `agent_low_filtered.json`, 15 resultados (todos do domínio), item
  `fetch_url_results` presente, US$ 0,00244, citou `[web:n]`;
  (c) `low --max-results 3` → `agent_low_maxresults.json`, **2 resultados**, US$ 0,00113;
  (d) `low --search-type web` → `agent_low_searchtype.json`, 15 resultados, US$ 0,00287.
  **Custo total da sessão: US$ 0,00781.** Nenhum 401. `grep pplx-` em `tests/fixtures` vazio (também conferi
  `authorization`/`bearer`/`api_key`).
- **DECISÃO max_results/search_type: ambos ACEITOS E COM EFEITO** → restaurados no API_NOTES; "Máx. resultados"
  permanece no RF4 e `max_results` em SearchOptions (§8). Evidência: (c) devolveu 2 resultados contra 15 em (b)
  sem o campo; em (d) o `search_web` custou US$ 0,0025 contra US$ 0,0010 das outras, provando que `search_type`
  mudou de variante (e que os presets usam `"fast"` por padrão, como diz o §7).
- **Eu estava errado na sessão anterior**: concluí "não existe" porque os campos faltam nos tipos do SDK 0.43.7.
  Esses tipos são `TypedDict`, que não validam em execução — chaves extras chegam ao servidor. Registrei o aviso
  no API_NOTES §3 para não repetir o erro.
- Outras divergências registradas no API_NOTES: `usage` traz `output_tokens_details`,
  `cost.tool_calls_cost_details` e `cost_usd` por ferramenta (**fora dos tipos do SDK**); subcampos de custo
  podem vir `null`; `queries` é lista (1–3 observadas); `date`/`last_updated` podem ser `null`; os `id` são
  contíguos **por item** `search_results`. TECHSPEC §10: 3 riscos marcados como resolvidos.
- Estado: `pytest -q` verde, `ruff check` + `format --check` limpos. Próxima sessão: F1.

## 2026-10-06 · F1 Modelos e configuração · Claude
- `core/models.py`: as dataclasses do TECHSPEC §8 (todas `frozen`), os `Literal` (`Preset`, `DomainMode`,
  `Recency`, `ContextSize`) e as constantes dos limites da API (`MAX_DOMAINS=20`, `MIN/MAX_RESULTS=1/50`),
  mais as tuplas de valores aceitos que o `config.py` usa para validar.
- `config/defaults.toml`: `[output].folder`, `[timeouts]` por preset (60/180/420/600/1800s, como no smoke da F0),
  `[search]` com os defaults exatos do RF4 e `[location]` (desligada, com o atalho Portugal–Lisboa).
- `config/prompt_snippets.toml`: 4 idiomas, 5 formatos e 5 prioridades, cada um com `label` (UI) e `text` (briefing).
  Decisão: juntar rótulo e texto no mesmo arquivo para a F8 não precisar de uma segunda fonte de rótulos.
- `core/config.py`: `load_defaults`, `load_source_packs`, `load_snippets` → `Defaults`, `tuple[SourcePack, ...]`,
  `Snippets`. Decisão de contrato: valor fora do domínio é `ValueError` em português (configuração quebrada deve
  falhar alto), mas problema que não impede o uso é `logging.warning` — pacote com >20 domínios, pacote vazio
  (ignorado) e `mode` inválido (cai para `allow`). `Snippets` tem `language/output_format/priority` que levantam
  `KeyError` listando as chaves disponíveis. `timeouts` é `MappingProxyType` (imutável, como as dataclasses).
- Nota de arquitetura: `core/config.py` faz I/O de leitura dos TOML, o que roça a regra "core não faz I/O" do
  AGENTS.md. Mantive porque a árvore do TECHSPEC §7 coloca o arquivo em `core/` e o PLAN pede `load_*(path)`.
  A mitigação é a do §7: recebe caminhos, não os descobre; nada de rede, Qt ou sqlite.
- 38 testes verdes (31 de config + 5 de models + 2 do esqueleto), `ruff` limpo. Os 3 TOML reais são carregados
  nos testes, incluindo uma checagem cruzada: os defaults não podem citar formato/idioma/prioridade/pacote
  inexistente no outro arquivo. Aceite dos >20 domínios coberto por 2 testes (25 avisa e carrega; 20 não avisa).
- Pendência para a F2: o corte da lista de domínios em 20 (união dos pacotes + extras) é do `prompt_builder`;
  aqui só avisamos. `SearchOptions.after/before` ficaram sem uso até lá.

## 2026-10-06 · F2 Prompt builder · Claude
- `core/prompt_builder.py`: `build(prompt, options, snippets, timeouts) -> AgentRequest`. Briefing no formato do
  §6 (idioma, formato, prioridades, escopo, período — linhas que não se aplicam somem), payload conforme
  API_NOTES §3 sem chaves vazias (nada de `filters: {}`), denylist com `-` em todos os domínios, datas em
  MM/DD/YYYY, `user_location` no nível do tool. `CITATION_RULES` exportado.
- Decisão de formato de data: o payload usa MM/DD/YYYY (exigência da API) e o briefing usa DD/MM/YYYY, porque
  o briefing é texto em português que o usuário relê na seção "Parâmetros da busca" do relatório (RF3 item 4).
  O exemplo do §6 trazia "01/01/2025", ambíguo; fica registrado que são dois formatos de propósito.
- Decisão: >20 domínios é `ValueError` aqui (TECHSPEC §8 lista como validação do builder), não corte silencioso
  — corrige o que eu havia anotado no fim da F1. O limite conta a lista **já deduplicada**, e a limpeza tira
  espaços e um `-` que o usuário tenha digitado à mão. Quem impede o usuário de chegar nesse estado é a F8.
- Decisão: as buscas de snippet (`language`/`output_format`/`priority`) levantam `KeyError`, e o builder as
  converte em `ValueError` em português — a UI só mostra a mensagem, sem distinguir tipo de exceção.
- `instructions` só existe no modo avançado e sempre leva as regras de citação do API_NOTES §5 anexadas;
  texto só com espaços não conta como instrução própria.
- 40 testes novos (78 no total, `ruff` limpo), cobrindo os 7 casos do aceite: default (contra o snapshot
  `tests/fixtures/payload_default.json`), allow/deny, recency vs. datas, >20 domínios (e exatamente 20),
  localização, instruções próprias e prompt vazio. Mais: payload não leva timeout nem credencial, `options`
  não é mutado e `SearchOptions()` puro funciona (garantia para a F7).
- Conferi offline que todas as chaves do payload existem nos tipos do SDK (fora `max_results`/`search_type`,
  que a F0 provou funcionarem) — sem chamada real à API.

## 2026-10-06 · F3 Parser da resposta · Claude
- `core/response_parser.py`: `parse(raw: dict) -> SearchResult`. Junta todos os itens `search_results`,
  deduplica por URL (primeira ocorrência vence), ordena por `id`, junta as `queries` sem repetir,
  concatena o `output_text` dos itens `message` e ignora qualquer tipo de item ou bloco desconhecido.
- Princípio adotado: o parser **nunca** levanta exceção por causa da resposta. Campo ausente vira vazio/`None`,
  lixo que não é dicionário é descartado, `output`/`usage` de tipo errado são tratados como vazios.
  `parse({})` funciona. Texto vazio devolve `text=""` — decidir se isso é erro é do `services/client.py` (RF6).
- Decisão sobre o conflito de `id` que o API_NOTES §4 avisa (ids contíguos **por item**): com vários itens, o
  mesmo número pode apontar para URLs diferentes. O primeiro `id` vence e o conflito vai para o log, porque
  trocar o destino de uma citação é pior do que perder uma fonte. Resultado sem `id` utilizável entra no fim,
  numerado depois do maior `id` válido; resultado sem URL é descartado (não dá para citar nem listar).
- Decisão: `search_calls` soma as `invocation` das ferramentas cujo nome começa com "search" (ignora
  `fetch_url`); sem `tool_calls_details`, cai para a contagem de itens `search_results`. `cost_usd` vem de
  `usage.cost.total_cost` e é `None` se faltar, vier nulo ou não for número.
- Testes: 44 novos (122 no total, `ruff` limpo). As 4 fixtures reais da F0 são parseadas e as contagens de
  fontes/queries/custo batem com o que o smoke imprimiu — servem de âncora contra regressão. Criei
  `tests/fixtures/agent_estranho.json`, que junta de propósito: sem `usage`, item `advisor_result` desconhecido,
  entrada que não é objeto, resultado sem data, sem id, sem URL, id repetido em outra URL, id como texto e
  bloco de conteúdo desconhecido. Mais testes de resposta degenerada (`{}`, `output` de tipo errado).
- Para a F4: `Source.id` é único e, nas respostas reais, contíguo a partir de 1 — é esse número que o
  conversor de citações vai usar. `SearchResult.raw` é o dict recebido, intacto, para gravar o .json.

## 2026-10-06 · F4 Relatório Markdown · Claude
- `core/naming.py`: `slugify` e `report_basename(created_at, prompt)`. O slug só usa `[a-z0-9-]`, então passa
  no Windows, no macOS e no Linux de uma vez; corta na fronteira de palavra, evita os nomes reservados do
  Windows (CON, NUL, COM1...) e cai em "busca" quando o prompt não deixa nada aproveitável (só emoji, só
  pontuação). `report_basename` respeita os 80 caracteres do §9.
- `core/markdown_report.py`: `render(result, prompt, options, briefing, created_at) -> str` com as 4 partes do
  RF3 (front matter YAML · corpo com citações em link · `## Fontes` · `## Parâmetros da busca`).
  `link_citations` é pública porque a UI da F7 também vai mostrar o texto com links.
- Decisão: marcador cujo `id` não existe nas fontes fica como está. Um `[7]` órfão é melhor do que um link
  apontando para a fonte errada — mesma lógica do conflito de id resolvido na F3.
- Decisão: escrevi um emissor de YAML mínimo (uns 20 linhas) em vez de acrescentar PyYAML ao runtime; só
  usamos texto, número, data, lista e um nível de aninhamento. **Nova dependência de DEV: `pyyaml`** — serve
  só para os testes confirmarem que o front matter é YAML de verdade, inclusive com prompts hostis (aspas,
  barra invertida, dois pontos, quebra de linha). Registrado aqui conforme a regra do AGENTS.md.
- Bug encontrado e corrigido pelo próprio teste: eu normalizava a cerca de código para 3 caracteres, então um
  ``` fechava um bloco aberto com ````. Agora vale a regra do CommonMark — só fecha com o mesmo caractere e
  tamanho igual ou maior. Bloco não fechado protege até o fim do texto.
- Testes: 75 novos (197 no total, `ruff` limpo). Cobrem os 4 casos de citação do aceite (`[1]`, `[web:2]`,
  id inexistente, dentro de ```), mais cercas com `~~~`, com linguagem, aninhadas e não fechadas; front matter
  com 10 prompts hostis; fontes sem resultado, título vazio e com colchetes; e o golden file
  `tests/fixtures/report_expected.md`, gerado a partir da fixture real `agent_low_maxresults.json` com opções
  não-default (domínios, intervalo de datas, localização, pt-PT, dossiê) para exercitar o front matter inteiro.
- Para a F6: `report_basename` é função pura; o sufixo de desempate `-2` para buscas do mesmo minuto é do
  `storage.py`, como o PLAN prevê.

## 2026-10-06 · F5 Cliente da API · Claude
- `services/errors.py`: `CondorError` (base) + `AuthError`, `RequestError`, `RateLimitError`, `NetworkError`,
  `EmptyResponseError`, `CancelledError`. Duas classes além das 5 esboçadas no TECHSPEC §7: `RequestError`
  (4xx que não é auth — o problema é o nosso payload, não a rede) e `CancelledError` (preciso para o `cancel()`).
  Decisão: `retryable` é atributo da exceção, não tabela no cliente — a resposta a um erro novo é decidida
  onde o erro é criado.
- `services/client.py`: `AgentClient.run(req) -> dict` com até 3 tentativas, backoff 2s/4s (a constante guarda
  2/4/8 para quem subir `max_attempts`), tradução de todas as exceções do SDK e `cancel()` cooperativo.
  Continua sendo o **único** arquivo que importa `perplexity`.
- Correção de semântica durante os testes: o `run()` limpava a flag de cancelamento no início, o que **engole**
  um cancelamento pedido entre enfileirar o worker e a chamada começar — corrida real na F7. Agora o
  cancelamento vence e só `reset()` limpa; a F7 deve chamar `reset()` quando o usuário clica em Buscar.
- Limite honesto registrado na docstring: `cancel()` não aborta chamada HTTP em andamento (o SDK é bloqueante).
  O que garantimos é que nenhuma tentativa nova começa, que a espera do backoff é interrompida na hora e que
  o resultado de uma chamada cancelada é descartado.
- Achado de segurança: as mensagens genéricas interpolam o texto do erro do SDK, e erro de rede às vezes ecoa
  o cabeçalho `Authorization`. Então `CondorError.__init__` passa toda mensagem por `scrub()`, que troca
  `pplx-…` e `Bearer …` por `***`. Cumpre o TECHSPEC §5 ("nada de chave em logs ou mensagens de erro") por
  construção, e não por disciplina. O log de retry só registra o nome da classe do erro, nunca o texto.
- Testes: 78 novos (62 do cliente/erros + 16 de arquitetura). Os 4 casos do aceite estão cobertos com as **classes reais** do SDK construídas à mão
  (sucesso; 429 → sucesso na 2ª; 401 sem retry; timeout esgota 3 tentativas; nenhum log com a chave), mais
  chave ausente na criação do cliente, resposta vazia, resposta em formato inesperado, as 3 situações de
  cancelamento e a tabela inteira do API_NOTES §6.
- Extra fora do escopo da fase, mas barato: `tests/test_arquitetura.py` transforma a regra de camadas do
  AGENTS.md em teste — `core/` não importa Qt/SDK/sqlite3/httpx nem `services`/`ui`, e só `client.py` fala
  com o SDK. Protege as fases seguintes de um import de conveniência.
- 275 testes verdes, `ruff` limpo. A F6 é a próxima: storage + secrets.

## 2026-10-06 · F6 Armazenamento, configuração e chave · Claude
- `services/storage.py` (`class Storage`): `save()` grava `.md` + `.json` + linha SQLite e devolve
  `SearchRecord`; `list_recent(limit)`, `get(id)`, `delete(id)` e `paths_of(id)` (a UI precisa dos caminhos
  para "Abrir pasta"/"Ver JSON"). Tabela com as 9 colunas do §9, conferidas por teste via `PRAGMA table_info`.
- Decisão: `delete()` apaga **só** a linha do banco, nunca os arquivos — é o que o RF5 pede, e perder um
  relatório por um clique no histórico seria o pior erro possível aqui.
- Decisão: uma conexão sqlite por operação, aberta e fechada no `contextmanager`. Mais lenta e irrelevante
  (dezenas de linhas), e evita o `check_same_thread` quando o worker da F7 chamar o storage de outra thread.
- Desempate de nome: `-2`, `-3`... quando duas buscas caem no mesmo minuto com o mesmo prompt. Conta como
  ocupado também o `.json` órfão (gravação interrompida) e o nome final continua dentro dos 80 caracteres.
- `services/settings_store.py`: `load(fallback)` / `save()` / `clear()` em JSON com `version`. Nada aqui é
  essencial — arquivo ausente, corrompido, de outra versão ou editado à mão cai nos padrões e o app abre.
  `save()` devolve `False` em vez de levantar quando o disco não colabora.
- `services/secrets.py` (RF7): `get_key`, `key_source` ("sistema" | ".env" | None), `save_key`, `remove_key`,
  `mask`, `is_valid_format`, mais `system_overrides_file` para o aviso do diálogo. `env_path` e `environ` são
  injetáveis; nenhum teste toca no `.env` real.
- **Decisão importante para a F7: o app não deve chamar `load_dotenv()`.** Se o `.env` fosse injetado no
  ambiente, não haveria como distinguir "o usuário definiu variável de sistema" de "o app leu o próprio .env",
  e o aviso do RF7 ("o .env não terá efeito") sairia errado. `secrets.py` é o único caminho para a chave.
- Bug corrigido pelo teste: `mask("pplx-")` devolvia `pplx-…plx-` — a cauda caía dentro do próprio prefixo.
  Agora os 4 caracteres saem só do que vem **depois** do prefixo, e apenas se houver mais que eles.
- Novo em `core/models.py`: `options_to_dict`/`options_from_dict` (conversão pura, sem I/O). Storage e
  settings_store precisavam dos dois, e colocar em `services` duplicaria. Atualizei a árvore do TECHSPEC §7.
  `options_from_dict` é tolerante de propósito: valor fora do domínio, data inválida ou lixo caem no default.
- 89 testes novos (364 no total, `ruff` limpo). Aceites cobertos: tudo em `tmp_path`; duplicata no mesmo
  minuto ganha `-2` (e `-3`); `save_key` preserva comentários e outras variáveis do `.env`; `mask` nunca
  expõe mais que 4 caracteres; variável de sistema tem prioridade sobre o arquivo.

## 2026-10-06 · F7 UI mínima ponta a ponta · Claude
- `ui/worker.py`: `execute_search()` carrega o fluxo do §7 **sem Qt nenhum** (montar → enviar → interpretar →
  renderizar → gravar), e `SearchWorker` (QRunnable) só a embala em sinais. É o que deixa o fluxo testável
  sem interface. Sinais: `finished(SearchRecord)`, `failed(str)`, `progress(str)`, mais `auth_failed(str)` e
  `cancelled()`.
- `ui/search_panel.py`, `ui/result_tab.py`, `ui/main_window.py`, `ui/api_key_dialog.py` e a composição em
  `__main__.py` (caminhos → config → serviços → janela; `find_project_root()` sobe até achar `config/`).
- Decisão: `auth_failed` **substitui** o `failed` num 401, não se soma a ele. Emitir os dois abria duas caixas
  de diálogo para o mesmo erro — e foi isso que travou a suíte na primeira tentativa.
- Decisão: a janela tem `show_error()` e `ask_change_key()` próprios em vez de chamar `QMessageBox` espalhado.
  Motivo concreto: `monkeypatch` em método estático do PySide não funciona de forma confiável, e uma caixa
  modal real **trava a suíte inteira**. Com a costura própria, os testes substituem o diálogo em Python puro.
- Decisão: Ctrl+Enter é tratado no `keyPressEvent` de um `PromptEdit`, não num `QShortcut` da janela. Atalho de
  janela só dispara com a janela ativa, o que o torna dependente do gerenciador de janelas e intestável
  offscreen. Foi um teste falhando que revelou isso.
- `ui/result_tab.py` tira o front matter YAML só para exibir (`strip_front_matter`): o arquivo em disco mantém
  tudo, mas o `QTextBrowser` mostraria o bloco como texto solto no topo. Rodapé com custo/tokens/nº de buscas,
  botões Abrir pasta / Copiar Markdown / Ver JSON bruto, `setOpenExternalLinks(True)`.
- Acrescentado em `services/client.py`: `forget_client()`, para a chave nova valer sem reiniciar (RF7 pede
  "recria o cliente; não precisa reiniciar"). A janela chama depois de salvar no diálogo.
- `tests/test_skeleton.py` foi reescrito: `main()` agora abre janela e entra no laço do Qt, então o teste
  cobre a parte determinística (`find_project_root`, `load_config`).
- Testes: 24 de UI (390 no total, `ruff` limpo), em `QT_QPA_PLATFORM=offscreen`, com SDK falso e `.env` em
  `tmp_path` — nenhuma rede, nenhum arquivo do usuário. Cobrem: busca ponta a ponta abrindo aba e salvando o
  `.md`, links clicáveis, botão voltando a Buscar, Ctrl+Enter, prompt vazio, falha de rede, 401 oferecendo
  trocar a chave, sem chave não busca, e `execute_search` isolado.
- Verifiquei também a composição real: a janela sobe offscreen com os TOML e o `.env` do projeto, sem chamar
  a API. **Pendente de você:** o aceite "busca real abre aba com links clicáveis" e "janela não congela
  durante a busca" exige uma chamada paga — rode `run.bat` (ou `python -m condor`) e faça uma busca.

## 2026-10-06 · Correção pós-F7: a chave não chegava ao SDK · Claude
- **Defeito relatado pelo usuário:** "nenhuma chave da API encontrada" mesmo com a chave inserida pelo diálogo.
- **Causa:** choque entre duas decisões minhas. Na F6 resolvi que o app não chama `load_dotenv()` (para
  distinguir variável de sistema de `.env`, RF7), mas `Perplexity()` lê a chave **do ambiente**. Então o
  `secrets.py` achava a chave no `.env` — o diálogo salvava, o app abria — e o SDK não recebia nada.
- **Correção:** `services/client.py` agora passa a chave explicitamente (`Perplexity(api_key=...)`), via novo
  parâmetro `api_key_provider`; `__main__.py` injeta `secrets.get_key`. A chave é relida a cada criação de
  cliente, então `forget_client()` continua fazendo a chave nova valer sem reiniciar. `client.py` segue sendo
  o único arquivo que importa o SDK.
- 3 testes de regressão: a chave do provider chega ao construtor do SDK; trocar a chave + `forget_client()`
  faz a busca seguinte usar a nova; sem provider, a falta de chave continua virando `AuthError`.
- Verificado com a composição real (sem chamar a API): `sdk.api_key == secrets.get_key()` é verdadeiro, e um
  `AgentClient()` sem provider reproduz a mensagem exata que o usuário viu. 393 testes verdes, `ruff` limpo.
- Lição para as fases seguintes: toda decisão de "não injetar no ambiente" precisa de um caminho explícito
  para quem dependia do ambiente. O teste de fumaça da F7 não pegou isto porque injetava um SDK falso —
  nenhum teste exercitava a criação do cliente real.

## 2026-10-06 · F8 Painel de opções + ícone no Windows · Claude
- `ui/options_form.py` (controles, rótulos e layout) + `ui/options_widget.py` (o que as escolhas significam).
  Dividi em dois porque um arquivo só passou de 500 linhas, acima do limite de 300 do AGENTS.md. Todos os
  controles do RF4, em 4 abas (Busca, Fontes, Resposta, Avançado), num painel recolhível com resumo de uma
  linha quando fechado.
- Decisão central: **a validade é decidida pelo `core/prompt_builder`**, chamado com um prompt de mentira.
  Nenhuma regra duplicada na UI — se o builder recusa, o Buscar desabilita e a dica é a própria mensagem do
  builder, em português. Mesma ideia no "Ver prompt final": o JSON exibido é o payload real.
- Decisão: `options()` lê os controles na hora; não há `SearchOptions` guardado no widget para divergir.
- Correção de persistência: os pacotes marcados agora vão para o `settings.json`
  (`SettingsStore.save(options, source_packs)` + `load_source_packs`). `SearchOptions` só conhece a lista
  final de domínios; sem isso, reabrir o app mostraria os 14 domínios do pacote "Acadêmico" soltos em
  "Domínios extras", com o pacote desmarcado.
- `xhigh` e as instruções próprias ficam atrás do "Avançado" (RF4). Desligar o avançado com `xhigh` escolhido
  devolve o preset para `low`, para não enviar o preset mais caro sem o usuário ver a opção.
- **Ícone (pedido do usuário; estava listado na F10).** `ui/assets.py` acha `docs/icon/icon.png` pela pasta do
  projeto e monta um `QIcon` multi-tamanho (16…256) com redução suave — o PNG tem 1014px e, entregue inteiro,
  fica mole nos 16px da barra de tarefas. Também `set_windows_app_id()`: sem AppUserModelID próprio, o Windows
  agrupa a janela sob o executável do Python e mostra o ícone genérico da linguagem, por mais que o ícone da
  janela esteja certo. Ícone ausente ou ilegível degrada para "sem ícone", nunca impede o app de abrir.
- **Pendência do `.ico`:** `docs/icon/icon.ico` tem uma única imagem de 29x32, pequena para atalho do Windows
  e para o executável da F10. O PNG e o SVG estão ótimos. Posso gerar um `.ico` multi-tamanho a partir do PNG
  (o Qt escreve `.ico`) quando for pedido — não sobrescrevi o arquivo do usuário sem perguntar.
- Testes: 44 novos (436 no total + 1 pulado fora do Windows, `ruff` limpo). Cobrem os dois aceites: cada opção
  muda o payload do "Ver prompt final" (preset, leitura, máx. resultados, domínios, modo excluir, pacote,
  recência, intervalo de datas, localização, idioma, formato, prioridades, instruções próprias) e combinação
  inválida desabilita o Buscar com dica. Mais: contador N/20, ida e volta `set_options`/`options`, restaurar
  padrões, e o Cancelar seguir clicável mesmo com opções inválidas.
- **⚠ `docs/TECHSPEC.md` não está mais na pasta.** Dei por falta ao tentar atualizar a árvore do §7 com os
  arquivos novos (`options_form.py`, `assets.py`). Não há git neste projeto; o caminho de recuperação é o
  histórico de versões do Yandex.Disk. Enquanto não voltar, as decisões de arquitetura seguem registradas
  aqui e em AGENTS.md. **A árvore do §7 está desatualizada em relação ao código desde a F8.**

## 2026-10-06 · F9 Histórico + .ico multi-tamanho · Claude
- `docs/TECHSPEC.md` voltou da lixeira do Yandex.Disk (versão de 13:51, com todas as edições das F0/F6 e da
  rev. 2). Atualizei a árvore do §7 com `options_form.py`, `assets.py`, `dialogs.py` e `history_panel.py`.
- `ui/history_panel.py`: QDockWidget à esquerda com tabela (data, pergunta, profundidade, custo), duplo clique
  e o menu de contexto do RF5. O painel não decide nada — emite sinais e a janela age; excluir precisa de
  confirmação, e caixa de diálogo é assunto da janela.
- Na janela: `open_record` (relê o `.md` salvo e reativa a aba se já estiver aberta, em vez de duplicar),
  `repeat_record`, `open_record_file` e `delete_record`. Menu *Exibir* com o toggle do painel.
- Decisão: `repeat_record` usa `set_options_inferring_packs`, que remarca os pacotes de fontes inteiramente
  contidos na lista de domínios — senão "Repetir" jogaria 14 domínios soltos na caixa de extras com o pacote
  desmarcado. Se a remarcação mudar a **ordem** dos domínios, o método volta atrás e usa só os extras: o
  aceite exige opções idênticas, e ordem faz parte da identidade.
- Decisão: "Repetir" preenche e para. Não dispara a busca sozinho — repetir por engano custa dinheiro.
- Reorganização obrigada pelo limite de 300 linhas do AGENTS.md: `load_result_tab` foi para `result_tab.py`
  (ler o `.md`/`.json` é assunto da aba), `summary_text` para `options_form.py` (é apresentação) e as caixas
  de diálogo para `ui/dialogs.py` (`DialogMixin`). Todos os arquivos voltaram a caber no limite.
- Rodapé tolerante: se o `.json` ao lado sumir, a aba abre mostrando o custo que o histórico conhece, em vez
  de recusar. Sem o `.md` não há aba — ele é o produto — e a mensagem diz qual arquivo faltou.
- **`.ico` refeito** (`scripts/make_icon.py`): 9 tamanhos (16…256) gerados do `icon.png` com redução suave.
  O escritor de ICO do Qt grava uma imagem por arquivo, então o contêiner (ICONDIR + ICONDIRENTRY + PNGs) é
  montado no script. O `.ico` anterior tinha uma só imagem de 29x32. Conferido lendo de volta: `QImageReader`
  encontra as 9 imagens e o condor continua legível a 16px. Cópia do original guardada fora do projeto.
  Armadilha registrada: `QBuffer(QByteArray())` com o array como temporário derruba o processo — guarde o
  `QByteArray` numa variável.
- Testes: 24 novos (460 no total + 1 pulado fora do Windows, `ruff` limpo). Cobrem os dois aceites — o
  histórico sobrevive a fechar e reabrir a janela, e "Repetir" devolve prompt e opções idênticos (incluindo
  datas, localização, prioridades e instruções próprias) — além de: ordem por data, custo ausente, menu de
  contexto, reabrir sem duplicar aba, `.md` ausente, `.json` ausente, excluir preservando os arquivos e o
  cancelar da exclusão.

## 2026-10-06 · F10 (item 1): streaming do texto · Claude
- Item escolhido pelo usuário entre os da F10. `AgentClient.run(req, sink)`: com `sink`, a chamada vai com
  `stream=True` e o texto chega em pedaços; **o valor de retorno é o mesmo nos dois modos**, para parser,
  relatório e storage não precisarem saber da diferença.
- `StreamSink` é um `Protocol` com `delta`, `restart` e `note`. O `restart` existe por um caso concreto: se
  uma tentativa falha no meio do fluxo, o texto já exibido não vale mais e a tela precisa apagá-lo antes de
  a próxima tentativa recomeçar do zero. Coberto por teste.
- `ui/result_tab.py` ganhou `StreamingTab`: aba temporária que mostra **texto puro** enquanto chega.
  Renderizar Markdown a cada pedaço custa caro, faz piscar e o texto parcial está quase sempre no meio de uma
  marcação. Terminada a busca, ela é substituída pela `ResultTab` com o Markdown de verdade, citações em link
  e lista de fontes. Falha, 401 ou cancelamento também removem a aba temporária — nada de aba órfã.
- Interruptor em *Exibir → Mostrar a resposta enquanto chega*, ligado por padrão e lembrado entre sessões
  (`SettingsStore.load_flag`/`save(..., ui=...)`). Existe porque não consegui verificar o streaming contra a
  API real (custa dinheiro): se o fluxo se comportar diferente do que os tipos do SDK dizem, um clique
  devolve o app ao modo que já funciona.
- Nova seção **API_NOTES §8** com a tabela de eventos do fluxo, os campos de cada um e as regras adotadas.
  Marcada como verificada só contra os tipos do SDK 0.43.7 — **não** contra uma chamada real.
- Dois arquivos passaram de 300 linhas por causa deste item, e foram divididos: `services/error_mapping.py`
  (tradução SDK → nossos erros, saiu do `client.py`) e `ui/history_actions.py` (`HistoryActionsMixin`, saiu do
  `main_window.py`).
- **Regra do AGENTS.md alterada, com justificativa:** o teste de arquitetura pegou que `error_mapping.py`
  também importa o SDK, violando "só `client.py` importa o SDK". Duas regras do projeto colidiram (essa e a
  das 300 linhas). Resolvi mantendo a divisão e redefinindo a regra como "a fronteira do SDK são
  `client.py` + `error_mapping.py`", ambos na mesma camada; o teste agora fixa esse conjunto e um teste novo
  garante que a `ui/` nunca importa o SDK.
- Rede de segurança nos testes de UI: fixture `sem_caixas_modais` substitui os diálogos por padrão. Sem ela,
  um erro inesperado abre uma caixa modal real e **trava a suíte inteira** — foi o que aconteceu quando o SDK
  falso ainda não falava streaming, e custou um bom tempo de diagnóstico.
- `tests/ui/fakes.py`: SDK falso compartilhado que fala os dois modos e emite os eventos reais do fluxo.
- Testes: 20 novos de streaming (481 no total + 1 pulado, `ruff` limpo): payload com e sem `stream`, texto
  montado dos deltas, notas de progresso, evento desconhecido ignorado, fluxo fechado no fim, ausência do
  evento final, `response.failed` comum e de chave, retry apagando o texto, cancelamento no meio, aba
  temporária aparecendo e sendo substituída, interruptor desligado e preferência persistida.
- **PENDENTE (usuário):** uma busca real para confirmar que o fluxo da API se comporta como os tipos do SDK
  indicam. Se der errado, desligue em *Exibir → Mostrar a resposta enquanto chega* e me diga a mensagem.

## Release 0.1.0 (empacotamento)
- Novo `scripts/build_release.py`: PyInstaller (onedir, `--windowed`) -> `release/CondorSearcher-<versão>-win64/` (+ `.zip`) com `config/`, `docs/`, README, LICENSE, `.env.example` e LEIAME.txt. Nunca copia o `.env`.
- `find_project_root` (`__main__.py`): no executável congelado a raiz é a pasta do `.exe`.
- Dependência nova (só build): `pyinstaller` -> extra `[build]` no pyproject, para gerar o executável.
- Smoke test: o .exe abre e permanece rodando; build não chama a API.

## 2026-10-20 · F11 Linha de comando (busca sem interface) · Claude
- Pedido do usuário: poder mandar prompts pelo app do Claude e ter o Claude Code gerando buscas e lendo os
  resultados sem ele presente. O que faltava no projeto era um caminho **sem Qt** — a janela não serve a
  sessão remota nem a terminal puro. Registrei como fase F11 no PLAN e implementei.
- `services/search_runner.py`: `SearchContext` e `execute_search` saíram de `ui/worker.py` (que importava Qt
  no topo e por isso era inutilizável pela CLI). O worker passou a importar de lá; nenhum teste mudou de
  comportamento. Agora janela e linha de comando percorrem **o mesmo** fluxo do §7.
- `src/condor/cli/`: `main.py` (parser), `app.py` (comandos e códigos de saída), `options.py` (flags →
  `SearchOptions`), `output.py` (texto para humano, JSON para agente). Entry point `condor-cli` no pyproject.
- Comandos: `buscar` (todas as opções do RF4), `historico`, `ver <id>`, `gastos`. `--so-prompt` mostra o
  payload **sem chamar a API** — é o jeito grátis de conferir antes de gastar.
- Decisão: **teto diário de gastos** (`[limits].daily_usd` em `defaults.toml`, padrão US$ 1,00), com
  `Storage.spent_since()` somando o custo do dia. Não estava no pedido, mas um agente disparando buscas sem
  ninguém por perto precisa de um freio; estourado, `buscar` recusa com código 4 e explica. `--sem-limite`
  libera. A janela não aplica o teto: lá o usuário vê o custo de cada busca antes de repetir.
- Decisão: `--json` é **contrato**, com códigos de saída que distinguem uso (1), configuração (2), API (3),
  teto (4), chave (5) e id inexistente (6) — é o que permite ao agente decidir sozinho se repete, corrige ou
  desiste. Acrescentar campo ao JSON é seguro; renomear quebra quem já depende.
- Documentação: seção nova no **AGENTS.md** (é o primeiro arquivo que um agente lê, então os comandos, o
  aviso de custo e os códigos de saída ficam lá), **RF9** no TECHSPEC, árvore do §7 atualizada e uma seção no
  README. `tests/ui/fakes.py` virou `tests/fakes.py`, compartilhado por UI e CLI.
- Testes: 45 novos (526 no total + 1 pulado, `ruff` limpo). Cobrem o mapeamento de todas as flags, datas e
  localização inválidas, pacote inexistente, o contrato do JSON, `--so-prompt` não chamando a API, chave
  ausente, falha de API, as cinco situações do teto (bloqueia, libera abaixo, ignora gasto de ontem,
  `--sem-limite`, teto zero) e os comandos de histórico/ver/gastos. Dois testes novos de arquitetura garantem
  que `cli/` nunca importa Qt e que o fluxo da busca não volta para dentro da UI.
- Conferido contra o projeto real, **sem chamar a API**: `--so-prompt`, `gastos` e `historico` (que listou as
  4 buscas de verdade já feitas pelo usuário).
- **PENDENTE (usuário):** rodar uma `condor-cli buscar` de verdade para confirmar ponta a ponta — e decidir
  onde o Claude Code vai rodar para operar sem você (ver resumo da sessão).
