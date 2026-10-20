"""Entrada da linha de comando: `condor-cli` (F11).

Existe para um agente (Claude Code) poder buscar e ler resultados sem ninguém na frente do
computador. Por isso três cuidados que a interface gráfica não precisa ter:

- **nada de Qt**: funciona em sessão remota, servidor ou terminal puro;
- **`--json` em tudo**: a saída é contrato de máquina, não texto para ler;
- **teto de gastos**: `buscar` custa dinheiro, e quem dispara pode não estar por perto.

`condor-cli buscar --so-prompt` mostra o que seria enviado sem gastar nada — é o jeito seguro de
conferir as opções antes de valer.
"""

from __future__ import annotations

import argparse
import logging
import sys

from condor import __version__
from condor.cli import app as comandos
from condor.cli.options import add_search_flags

EPILOGO = """exemplos:
  condor-cli buscar "horário da sala de leitura do AHU" --pacote linguistica_historica
  condor-cli buscar "o que mudou na lei de estrangeiros" --preset medium --periodo month --json
  condor-cli buscar "pergunta cara" --preset high --so-prompt     # não chama a API
  condor-cli historico --limite 5 --json
  condor-cli ver 12 > relatorio.md
  condor-cli gastos --dias 7
"""


def build_parser(defaults, programa: str = "condor-cli") -> argparse.ArgumentParser:
    """Monta o parser. Recebe os `defaults` porque eles viram os valores padrão das flags."""
    parser = argparse.ArgumentParser(
        prog=programa,
        description="Busca na Perplexity pela linha de comando, sem abrir a interface.",
        epilog=EPILOGO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"Condor Searcher {__version__}")
    parser.add_argument("--verbose", action="store_true", help="mostra o log detalhado em stderr")

    subs = parser.add_subparsers(dest="comando", required=True, metavar="COMANDO")

    buscar = subs.add_parser(
        "buscar",
        help="faz uma busca (CUSTA DINHEIRO) e grava o relatório",
        description="Faz uma busca de verdade na API. Use --so-prompt para conferir sem gastar.",
    )
    buscar.add_argument("pergunta", help="a pergunta da busca")
    add_search_flags(buscar, defaults)
    buscar.add_argument("--json", action="store_true", help="saída em JSON, para consumo por agente")
    buscar.add_argument(
        "--texto-completo",
        action="store_true",
        help="no JSON, devolve a resposta inteira em vez do resumo (o .md sempre tem tudo)",
    )
    buscar.add_argument(
        "--so-prompt",
        action="store_true",
        help="mostra o payload que seria enviado e sai, sem chamar a API nem gastar",
    )
    buscar.add_argument(
        "--sem-limite",
        action="store_true",
        help="ignora o teto diário de gastos desta vez",
    )
    buscar.set_defaults(funcao=comandos.cmd_buscar)

    historico = subs.add_parser("historico", help="lista as buscas já feitas")
    historico.add_argument("--limite", type=int, default=20, metavar="N", help="quantas listar (padrão: 20)")
    historico.add_argument("--json", action="store_true", help="saída em JSON")
    historico.set_defaults(funcao=comandos.cmd_historico)

    ver = subs.add_parser("ver", help="imprime o relatório de uma busca anterior")
    ver.add_argument("id", type=int, help="número da busca, como aparece no histórico")
    ver.add_argument("--json", action="store_true", help="saída em JSON (com o Markdown dentro)")
    ver.set_defaults(funcao=comandos.cmd_ver)

    gastos = subs.add_parser("gastos", help="quanto já se gastou e qual o teto")
    gastos.add_argument("--dias", type=int, default=1, metavar="N", help="janela em dias (padrão: 1 = hoje)")
    gastos.add_argument("--json", action="store_true", help="saída em JSON")
    gastos.set_defaults(funcao=comandos.cmd_gastos)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do executável `condor-cli`."""
    argumentos = list(sys.argv[1:] if argv is None else argv)

    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in argumentos else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,  # stdout fica livre para a saída útil (JSON, Markdown)
    )

    try:
        from condor.__main__ import find_project_root

        root = find_project_root()
        env = comandos.build_environment(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"erro de configuração: {exc}", file=sys.stderr)
        return comandos.ERRO_CONFIG

    parser = build_parser(env.defaults)
    args = parser.parse_args(argumentos)
    return int(args.funcao(env, args))


if __name__ == "__main__":
    raise SystemExit(main())
