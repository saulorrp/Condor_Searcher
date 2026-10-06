"""Chamada REAL à Perplexity Agent API — manual, custa dinheiro.

Único ponto do projeto autorizado a falar com a API de verdade. Os testes usam as fixtures
que este script grava em `tests/fixtures/`.

Uso:
    python scripts/smoke_api.py "sua pergunta"
    python scripts/smoke_api.py "sua pergunta" --preset low --domain dglab.gov.pt
    python scripts/smoke_api.py "sua pergunta" --preset low --max-results 3 --out agent_low_mr.json
    python scripts/smoke_api.py "sua pergunta" --preset low --search-type web

`--out` aceita só o nome do arquivo (vai para `tests/fixtures/`) ou um caminho completo.
Sem `--out`, o nome sai do preset e dos filtros: agent_fast.json · agent_low_filtered.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

# Timeout (s) do SDK por preset — presets mais caros demoram muito mais.
TIMEOUTS: dict[str, int] = {"fast": 60, "low": 180, "medium": 420, "high": 600, "xhigh": 1800}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test da Agent API (chamada real).")
    p.add_argument("prompt", help="pergunta a enviar")
    p.add_argument("--preset", default="fast", choices=sorted(TIMEOUTS), help="preset da Agent API")
    p.add_argument(
        "--domain",
        action="append",
        default=[],
        metavar="DOMINIO",
        help="restringe a busca a este domínio (pode repetir; até 20)",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=None,
        metavar="N",
        help="envia max_results=N no tool web_search (a doc diz 1..50; o SDK 0.43.7 não tipa o campo)",
    )
    p.add_argument(
        "--search-type",
        default=None,
        choices=["fast", "web"],
        help="envia search_type no tool web_search (idem: documentado, não tipado no SDK)",
    )
    p.add_argument(
        "--out", default=None, metavar="NOME", help="nome do arquivo em tests/fixtures/ (ou caminho)"
    )
    return p.parse_args(argv)


def build_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    """Monta o kwargs do `responses.create` omitindo chaves vazias (API_NOTES §3)."""
    kwargs: dict[str, Any] = {"preset": args.preset, "input": args.prompt}

    tool: dict[str, Any] = {"type": "web_search"}
    if args.domain:
        tool["filters"] = {"search_domain_filter": args.domain}
    if args.max_results is not None:
        tool["max_results"] = args.max_results
    if args.search_type is not None:
        tool["search_type"] = args.search_type
    if len(tool) > 1:  # só manda o tool se houver algo além do "type"
        kwargs["tools"] = [tool]

    kwargs["timeout"] = TIMEOUTS[args.preset]
    return kwargs


def resolve_out(args: argparse.Namespace) -> Path:
    """`--out` é só um nome (vai para tests/fixtures/) ou um caminho; sem ele, deriva do preset."""
    if args.out:
        candidate = Path(args.out)
        return candidate if candidate.parent != Path(".") else FIXTURES / candidate.name
    suffix = "_filtered" if args.domain else ""
    return FIXTURES / f"agent_{args.preset}{suffix}.json"


def describe_sdk() -> None:
    """Identifica a versão do SDK e as exceções disponíveis (TECHSPEC §10)."""
    import perplexity

    print(f"[sdk] perplexity {getattr(perplexity, '__version__', '?')}")
    print(f"[sdk] exceções: {', '.join(sorted(n for n in dir(perplexity) if 'Error' in n))}")


def report_response(raw: dict[str, Any]) -> None:
    """Mostra o que a F3 vai ter de parsear: tipos de item, nº de resultados e usage."""
    output = raw.get("output") or []
    print(f"[output] {len(output)} item(ns): {[item.get('type') for item in output]}")
    for i, item in enumerate(output):
        if item.get("type") == "search_results":
            results = item.get("results") or []
            print(f"[search_results #{i}] {len(results)} resultado(s); queries={item.get('queries')}")
            for r in results:
                print(f"    id={r.get('id')} {r.get('url')}")
    usage = raw.get("usage")
    print(f"[usage] {json.dumps(usage, ensure_ascii=False, indent=2) if usage else '(ausente)'}")


def report_failure(exc: Exception) -> None:
    """Imprime o erro inteiro (status HTTP, corpo, tipo) — sem jamais tocar na chave."""
    print(f"[ERRO] {type(exc).__module__}.{type(exc).__name__}: {exc}", file=sys.stderr)
    for attr in ("status_code", "code", "param", "request_id"):
        value = getattr(exc, attr, None)
        if value is not None:
            print(f"[ERRO] {attr}={value!r}", file=sys.stderr)
    body = getattr(exc, "body", None) or getattr(getattr(exc, "response", None), "text", None)
    if body:
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)
        print(f"[ERRO] corpo da resposta:\n{text}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    load_dotenv(ROOT / ".env")

    from perplexity import Perplexity  # import tardio: só aqui a chave é necessária

    describe_sdk()
    kwargs = build_kwargs(args)
    printable = {k: v for k, v in kwargs.items() if k != "input"}
    print(f"[req] {json.dumps(printable, ensure_ascii=False)}")

    client = Perplexity()  # lê PERPLEXITY_API_KEY do ambiente; nunca imprimir a chave
    try:
        resp = client.responses.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 — queremos ver qualquer falha por inteiro
        report_failure(exc)
        return 1

    raw = resp.model_dump(mode="json")
    out = resolve_out(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    report_response(raw)
    print(f"[ok] fixture salva em {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    print("-" * 70)
    print(resp.output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
