"""Os comandos da linha de comando (F11).

Cada comando devolve um código de saída que distingue o tipo de falha — é o que permite a um
agente decidir sozinho se tenta de novo, corrige as opções ou desiste:

| código | significado                                    |
|--------|------------------------------------------------|
| 0      | deu certo                                       |
| 1      | erro de uso: opção inválida, pacote inexistente |
| 2      | configuração do projeto quebrada                |
| 3      | falha na API (rede, 5xx, limite de taxa)        |
| 4      | teto de gastos atingido                         |
| 5      | chave da API ausente ou recusada                |
| 6      | nada encontrado (id inexistente no histórico)   |
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from condor.cli import output
from condor.cli.options import options_from_args
from condor.core.config import Defaults, Snippets, SourcePack
from condor.core.models import SearchRecord
from condor.core.prompt_builder import build
from condor.core.response_parser import parse
from condor.services.client import AgentClient
from condor.services.errors import AuthError, CondorError
from condor.services.search_runner import SearchContext, execute_search
from condor.services.secrets import ENV_FILE, SecretStore
from condor.services.storage import Storage

logger = logging.getLogger(__name__)

OK = 0
ERRO_USO = 1
ERRO_CONFIG = 2
ERRO_API = 3
ERRO_TETO = 4
ERRO_CHAVE = 5
NAO_ENCONTRADO = 6


@dataclass
class Ambiente:
    """O que os comandos precisam. Montado em `cli/main.py` e trocável nos testes."""

    root: Path
    defaults: Defaults
    snippets: Snippets
    packs: tuple[SourcePack, ...]
    storage: Storage
    secrets: SecretStore
    client: AgentClient
    escrever: Callable[[str], None]  # `print` em produção; lista nos testes

    def diz(self, texto: str) -> None:
        self.escrever(texto)


def build_environment(root: Path, client: AgentClient | None = None) -> Ambiente:
    """Monta o ambiente real a partir da pasta do projeto."""
    from condor.__main__ import load_config

    defaults, snippets, packs = load_config(root)
    secrets = SecretStore(root / ENV_FILE)
    return Ambiente(
        root=root,
        defaults=defaults,
        snippets=snippets,
        packs=packs,
        storage=Storage(defaults.output_dir),
        secrets=secrets,
        client=client or AgentClient(api_key_provider=secrets.get_key),
        escrever=print,
    )


# --------------------------------------------------------------------------- buscar


def cmd_buscar(env: Ambiente, args: argparse.Namespace) -> int:
    """Roda uma busca de verdade — **custa dinheiro** — e grava o relatório."""
    try:
        options = options_from_args(args, env.packs, env.defaults)
        req = build(args.pergunta, options, env.snippets, env.defaults.timeouts)
    except ValueError as exc:
        return _falha(env, args, str(exc), "uso", ERRO_USO)

    if args.so_prompt:
        if args.json:
            env.diz(output.dump({"ok": True, "timeout_s": req.timeout_s, "payload": req.payload}))
        else:
            env.diz(f"timeout: {req.timeout_s}s\n\n{output.dump(req.payload)}")
        return OK

    if env.secrets.get_key() is None:
        return _falha(
            env,
            args,
            f"Nenhuma chave da API configurada. Grave-a no {ENV_FILE} da pasta do projeto "
            "ou defina a variável de ambiente PERPLEXITY_API_KEY.",
            "chave",
            ERRO_CHAVE,
        )

    excedido = _teto_excedido(env, args)
    if excedido is not None:
        return _falha(env, args, excedido, "teto", ERRO_TETO)

    ctx = SearchContext(
        client=env.client,
        storage=env.storage,
        snippets=env.snippets,
        timeouts=env.defaults.timeouts,
    )
    progresso = (lambda texto: logger.info("%s", texto)) if args.json else env.diz

    try:
        record = execute_search(ctx, args.pergunta, options, progresso)
    except AuthError as exc:
        return _falha(env, args, str(exc), "chave", ERRO_CHAVE)
    except CondorError as exc:
        return _falha(env, args, str(exc), "api", ERRO_API)

    result = parse(_raw_de(record))
    if args.json:
        env.diz(output.dump(output.search_payload(record, result, texto_completo=args.texto_completo)))
    else:
        env.diz(output.human_search(record, result))
    return OK


def _teto_excedido(env: Ambiente, args: argparse.Namespace) -> str | None:
    """Mensagem do teto diário, ou `None` se pode buscar."""
    limite = env.defaults.limits
    if args.sem_limite or not limite.enabled:
        return None
    gasto = env.storage.spent_since(_inicio_do_dia())
    if gasto < limite.daily_usd:
        return None
    return (
        f"Teto diário atingido: já foram gastos US$ {gasto:.5f} hoje, e o limite é "
        f"US$ {limite.daily_usd:.2f}. Use --sem-limite para passar por cima, ou ajuste "
        "[limits].daily_usd em config/defaults.toml."
    )


def _inicio_do_dia() -> datetime:
    agora = datetime.now()
    return agora.replace(hour=0, minute=0, second=0, microsecond=0)


def _raw_de(record: SearchRecord) -> dict:
    """Relê o `.json` salvo ao lado do relatório, para montar o resumo da saída."""
    caminho = record.md_path.with_suffix(".json")
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------- histórico


def cmd_historico(env: Ambiente, args: argparse.Namespace) -> int:
    registros = env.storage.list_recent(args.limite)
    if args.json:
        env.diz(
            output.dump(
                {
                    "ok": True,
                    "total": len(registros),
                    "searches": [output.record_payload(r) for r in registros],
                }
            )
        )
    else:
        env.diz(output.human_history(registros))
    return OK


def cmd_ver(env: Ambiente, args: argparse.Namespace) -> int:
    """Imprime o relatório salvo de uma busca anterior — não chama a API."""
    record = env.storage.get(args.id)
    if record is None:
        return _falha(env, args, f"Não há busca #{args.id} no histórico.", "nao_encontrado", NAO_ENCONTRADO)

    try:
        markdown = record.md_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _falha(
            env, args, f"Não consegui ler {record.md_path}: {exc}", "nao_encontrado", NAO_ENCONTRADO
        )

    if args.json:
        dados = output.record_payload(record)
        dados.update({"ok": True, "markdown": markdown})
        env.diz(output.dump(dados))
    else:
        env.diz(markdown)
    return OK


def cmd_gastos(env: Ambiente, args: argparse.Namespace) -> int:
    """Quanto já se gastou hoje (ou nos últimos N dias) e qual o teto."""
    inicio = _inicio_do_dia()
    if args.dias > 1:
        inicio -= timedelta(days=args.dias - 1)
    gasto = env.storage.spent_since(inicio)
    limite = env.defaults.limits

    if args.json:
        env.diz(
            output.dump(
                {
                    "ok": True,
                    "since": inicio.isoformat(timespec="seconds"),
                    "spent_usd": round(gasto, 6),
                    "daily_limit_usd": limite.daily_usd if limite.enabled else None,
                    "blocked": bool(limite.enabled and gasto >= limite.daily_usd),
                }
            )
        )
    else:
        teto = f"teto de US$ {limite.daily_usd:.2f}/dia" if limite.enabled else "sem teto configurado"
        env.diz(f"Gasto desde {inicio.strftime('%d/%m/%Y %H:%M')}: US$ {gasto:.5f} ({teto}).")
    return OK


# --------------------------------------------------------------------------- apoio


def _falha(env: Ambiente, args: argparse.Namespace, mensagem: str, codigo: str, saida: int) -> int:
    """Erro no formato pedido (texto ou JSON) e o código de saída correspondente."""
    if getattr(args, "json", False):
        env.diz(output.dump(output.error_payload(mensagem, codigo)))
    else:
        env.diz(f"erro: {mensagem}")
    return saida
