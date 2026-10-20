# Condor Searcher

> 🇧🇷 Pequena ferramenta *vibecoded* para **pesquisa agêntica**. · 🇬🇧 A small vibe-coded tool for **agentic research**.

Condor Searcher é um app desktop (Python + PySide6) que envia uma busca à
**[Perplexity Agent API](https://docs.perplexity.ai/)** e grava/mostra o resultado como
**Markdown com os links das fontes**.

## Sobre o projeto

Este é um projeto pessoal, pequeno e **vibecoded**: foi construído em conversa com agentes de código
(ver `AGENTS.md` e o diário em `docs/PROGRESS.md`), sem pretensão de ser um produto polido.
Funciona para o meu uso — pesquisa agêntica com fontes citáveis — e está público caso seja útil a
alguém. Use por sua conta e risco; issues e PRs são bem-vindos, mas sem promessa de suporte.

> ⚠️ **A API da Perplexity é paga.** Cada busca consome créditos da *sua* chave.

## Instalar

Requer Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

## Configurar

Copie `.env.example` para `.env` e preencha a sua chave:

```
PERPLEXITY_API_KEY=pplx-...
```

O `.env` está no `.gitignore` — nunca o commite. A chave é lida apenas da variável de ambiente
`PERPLEXITY_API_KEY`; nenhum arquivo do código a contém.

## Rodar

```bash
python -m condor        # ou: condor
```

No Windows, também dá para dar duplo clique em `run.bat`.

## Linha de comando

Além da janela, há o `condor-cli`, que faz buscas sem abrir interface — útil para scripts e para
um agente rodar sem ninguém na frente do computador:

```bash
condor-cli buscar "sua pergunta" --json        # busca real (custa dinheiro)
condor-cli buscar "sua pergunta" --so-prompt   # mostra o que seria enviado, sem gastar
condor-cli historico --limite 10
condor-cli ver 12 > relatorio.md
condor-cli gastos                              # quanto já se gastou hoje e qual o teto
```

Há um teto diário de gastos em `config/defaults.toml` (`[limits].daily_usd`, padrão US$ 1,00).
`condor-cli --help` lista todas as opções.

## Desenvolvimento

```bash
pytest -q                               # testes (nunca chamam a API real)
ruff check src tests                    # lint
ruff format src tests                   # format
python scripts/smoke_api.py "pergunta"  # ÚNICA chamada real à API (manual, custa dinheiro)
```

Documentação do projeto em `docs/`: `TECHSPEC.md` (arquitetura), `API_NOTES.md` (formato da API),
`PLAN.md` (fases) e `PROGRESS.md` (diário de bordo). Para agentes de código, comece por `AGENTS.md`.

## Licença

[MIT](LICENSE)
