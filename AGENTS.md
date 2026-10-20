# AGENTS.md — Condor Searcher

> Contexto mínimo para agentes de código. Leia ESTE arquivo inteiro; os demais docs só quando a fase pedir.

## O que é
App desktop (Python + PySide6) que envia uma busca à **Perplexity Agent API** (`/v1/agent`, `client.responses.create`)
e grava/mostra o resultado como **Markdown com links das fontes**. Usuário único, Windows 11 (deve rodar também em macOS/Linux).

## Onde está cada coisa
| Preciso de... | Leia |
|---|---|
| Requisitos, arquitetura, modelos de dados | `docs/TECHSPEC.md` |
| Formato exato da API (request/response) | `docs/API_NOTES.md` — **não pesquise a doc na web, use este arquivo** |
| O que fazer agora | `docs/PLAN.md` → primeira fase com status `TODO` |
| O que já foi feito / decisões recentes | `docs/PROGRESS.md` (últimas 30 linhas bastam) |
| Pacotes de fontes (domínios) | `config/source_packs.toml` |

## Comandos
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
python -m condor                                     # roda o app (usuário final: duplo clique em run.bat)
pytest -q                                            # testes (NUNCA chamam a API real)
ruff check src tests && ruff format src tests        # lint + format
python scripts/smoke_api.py "pergunta"               # ÚNICO ponto que chama a API real (manual, custa dinheiro)
python scripts/make_icon.py                          # regera docs/icon/icon.ico a partir do icon.png
condor-cli --help                                    # busca pela linha de comando (ver seção abaixo)
```

## Buscar pela linha de comando (é assim que um agente usa este projeto)
`condor-cli` faz tudo o que a janela faz, **sem Qt** — serve em terminal puro, sessão remota ou servidor.

```bash
condor-cli buscar "pergunta" --json                 # BUSCA REAL: custa dinheiro
condor-cli buscar "pergunta" --so-prompt            # mostra o payload e NÃO chama a API (grátis)
condor-cli buscar "pergunta" --preset medium --pacote academico --periodo month --json
condor-cli historico --limite 10 --json             # buscas já feitas
condor-cli ver 12                                   # imprime o relatório .md de uma busca anterior
condor-cli gastos --json                            # quanto já se gastou hoje e qual o teto
```

Regras para quem roda isto sem o usuário por perto:
- **`buscar` gasta dinheiro de verdade.** Confira antes com `--so-prompt`, que é grátis e mostra o payload.
- Há **teto diário** (`[limits].daily_usd` em `config/defaults.toml`, padrão US$ 1,00). Estourou, `buscar`
  recusa com código 4 e explica. `--sem-limite` passa por cima — use só se o usuário pediu.
- `--json` em qualquer comando devolve objeto estável; os campos são contrato (ver `cli/output.py`).
- Códigos de saída: `0` ok · `1` opção inválida · `2` config quebrada · `3` falha de API · `4` teto atingido ·
  `5` chave ausente/recusada · `6` id inexistente.
- O relatório fica em `md_path` (Markdown com as fontes em link); o JSON bruto da API, ao lado.
- A chave nunca aparece na saída. Continua valendo: não leia nem imprima o `.env`.

## Arquitetura em camadas (regra rígida)
```
ui/ (Qt)  ─┐
           ├──►  services/  ──►  core/
cli/ ──────┘      (rede, disco)   (puro: dataclasses, prompt, markdown)
```
- `core/` não importa Qt, `perplexity`, `sqlite3` nem faz I/O. Tudo testável com dados em memória.
- `services/client.py` e `services/error_mapping.py` são os **únicos** arquivos que importam o SDK
  `perplexity` (o segundo nasceu na F10, quando o primeiro passou das 300 linhas).
- `ui/` nunca monta payload nem Markdown: chama `core`/`services`.
- `cli/` **não importa Qt** (teste garante). O fluxo de uma busca mora em `services/search_runner.py`,
  compartilhado pela janela e pela linha de comando.
- Chamadas de rede rodam fora da thread da UI (`ui/worker.py`).

## Convenções
- Python 3.11+, type hints em tudo, `dataclasses` (frozen quando possível), `pathlib`, f-strings.
- Nomes de código em inglês; textos visíveis ao usuário e docstrings em português.
- Funções pequenas; arquivo > 300 linhas = dividir.
- Erros da API viram exceções próprias de `services/errors.py`; a UI só mostra a mensagem.
- Logs via `logging` (nunca `print` fora de `scripts/`).
- Testes: `tests/` espelha `src/condor/`; fixtures JSON em `tests/fixtures/`.

## Proibido
- Ler, imprimir ou commitar `.env` / a chave da API. Só `services/secrets.py` toca no `.env` (o usuário grava a chave pelo app).
- Chamar a API real em testes ou "para conferir". Use as fixtures.
- Adicionar dependência sem registrar o motivo em `docs/PROGRESS.md`.
- Mudar a camada de outra fase "de passagem". Se achar um bug fora do escopo, anote em PROGRESS.md.
- Reescrever arquivos inteiros quando um Edit pontual resolve.

## Fluxo de trabalho por sessão (economia de contexto)
1. Leia `docs/PLAN.md` e pegue **uma** fase `TODO`. Leia só os arquivos listados em "Arquivos" dessa fase.
2. Implemente. Rode `pytest -q` e `ruff check`.
3. Cumpra todos os "Critérios de aceite" da fase.
4. Marque a fase como `DONE` no PLAN.md e acrescente 3–6 linhas em `docs/PROGRESS.md` (o que fez, decisões, pendências).
5. Pare. A próxima fase começa em sessão nova (`/clear`).

## Definição de pronto
Testes verdes, lint limpo, critérios de aceite cumpridos, PROGRESS.md atualizado, nenhum segredo no diff.
