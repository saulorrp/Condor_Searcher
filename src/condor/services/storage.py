"""Gravação em disco e índice do histórico (TECHSPEC §9).

O produto é o `.md`; o `.json` fica ao lado para depurar e gerar fixtures; o SQLite é só um
índice para a lista do histórico (RF5). Por isso `delete()` apaga a linha do banco e **não** o
arquivo: perder o relatório por um clique no histórico seria o pior erro possível aqui.

Cada operação abre e fecha a sua conexão. Fica mais lento e não importa — são dezenas de linhas,
e assim o `storage` pode ser chamado da thread do worker sem o `check_same_thread` do sqlite3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from condor.core.models import (
    SearchOptions,
    SearchRecord,
    SearchResult,
    options_from_dict,
    options_to_dict,
)
from condor.core.naming import MAX_BASENAME, report_basename

logger = logging.getLogger(__name__)

DB_NAME = "condor.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    prompt       TEXT    NOT NULL,
    options_json TEXT    NOT NULL,
    preset       TEXT    NOT NULL,
    md_path      TEXT    NOT NULL,
    json_path    TEXT    NOT NULL,
    cost_usd     REAL,
    response_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_searches_created_at ON searches (created_at DESC);
"""


class Storage:
    """Pasta de saída + banco do histórico. A pasta é criada na primeira gravação."""

    def __init__(self, output_dir: Path, *, db_name: str = DB_NAME) -> None:
        self.output_dir = Path(output_dir)
        self.db_path = self.output_dir / db_name

    # ------------------------------------------------------------------ gravação

    def save(
        self,
        result: SearchResult,
        md: str,
        prompt: str,
        options: SearchOptions,
        created_at: datetime | None = None,
    ) -> SearchRecord:
        """Grava `.md` + `.json`, insere a linha no banco e devolve o registro."""
        created_at = created_at or datetime.now()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        base = self._unique_basename(created_at, prompt)
        md_path = self.output_dir / f"{base}.md"
        json_path = self.output_dir / f"{base}.json"

        md_path.write_text(md, encoding="utf-8")
        json_path.write_text(json.dumps(result.raw, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._db() as conn:
            cursor = conn.execute(
                "INSERT INTO searches "
                "(created_at, prompt, options_json, preset, md_path, json_path, cost_usd, response_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    created_at.isoformat(timespec="seconds"),
                    prompt,
                    json.dumps(options_to_dict(options), ensure_ascii=False),
                    options.preset,
                    str(md_path),
                    str(json_path),
                    result.usage.cost_usd,
                    result.response_id,
                ),
            )
            novo_id = int(cursor.lastrowid or 0)

        logger.info("Busca %d salva em %s", novo_id, md_path.name)
        return SearchRecord(
            id=novo_id,
            created_at=created_at.replace(microsecond=0),
            prompt=prompt,
            options=options,
            md_path=md_path,
            cost_usd=result.usage.cost_usd,
        )

    def _unique_basename(self, created_at: datetime, prompt: str) -> str:
        """`...-2`, `...-3` quando duas buscas caem no mesmo minuto com o mesmo prompt (§9)."""
        base = report_basename(created_at, prompt)
        if not self._ocupado(base):
            return base
        for n in range(2, 1000):
            sufixo = f"-{n}"
            candidato = base[: MAX_BASENAME - len(sufixo)].rstrip("-_") + sufixo
            if not self._ocupado(candidato):
                return candidato
        raise OSError(f"Não consegui um nome livre para {base} na pasta {self.output_dir}.")

    def _ocupado(self, base: str) -> bool:
        return (self.output_dir / f"{base}.md").exists() or (self.output_dir / f"{base}.json").exists()

    # ------------------------------------------------------------------ leitura

    def list_recent(self, limit: int = 50) -> tuple[SearchRecord, ...]:
        """As buscas mais recentes primeiro. Sem banco ainda, devolve vazio."""
        if not self.db_path.exists():
            return ()
        with self._db() as conn:
            linhas = conn.execute(
                "SELECT * FROM searches ORDER BY datetime(created_at) DESC, id DESC LIMIT ?",
                (max(0, limit),),
            ).fetchall()
        return tuple(_record(linha) for linha in linhas)

    def spent_since(self, inicio: datetime) -> float:
        """Soma o custo das buscas feitas a partir de `inicio` (US$).

        Serve ao teto de gastos da linha de comando (F11): um agente buscando sem ninguém por
        perto precisa de um freio. Buscas sem custo informado contam como zero — é o que o banco
        sabe, e inventar estimativa aqui seria pior.
        """
        if not self.db_path.exists():
            return 0.0
        with self._db() as conn:
            linha = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM searches "
                "WHERE datetime(created_at) >= datetime(?)",
                (inicio.isoformat(timespec="seconds"),),
            ).fetchone()
        return float(linha["total"] or 0.0)

    def get(self, record_id: int) -> SearchRecord | None:
        if not self.db_path.exists():
            return None
        with self._db() as conn:
            linha = conn.execute("SELECT * FROM searches WHERE id = ?", (record_id,)).fetchone()
        return _record(linha) if linha else None

    def paths_of(self, record_id: int) -> tuple[Path, Path] | None:
        """Caminhos `.md` e `.json` de um registro — a UI usa para "Abrir pasta"/"Ver JSON"."""
        if not self.db_path.exists():
            return None
        with self._db() as conn:
            linha = conn.execute(
                "SELECT md_path, json_path FROM searches WHERE id = ?", (record_id,)
            ).fetchone()
        return (Path(linha["md_path"]), Path(linha["json_path"])) if linha else None

    # ------------------------------------------------------------------ remoção

    def delete(self, record_id: int) -> bool:
        """Apaga só a linha do histórico; os arquivos ficam (RF5). `False` se não existia."""
        if not self.db_path.exists():
            return False
        with self._db() as conn:
            apagadas = conn.execute("DELETE FROM searches WHERE id = ?", (record_id,)).rowcount
        return apagadas > 0

    # ------------------------------------------------------------------ interno

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(_SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()


def _record(linha: sqlite3.Row) -> SearchRecord:
    """Linha do banco → `SearchRecord`, tolerando dados escritos por versões anteriores."""
    try:
        options = options_from_dict(json.loads(linha["options_json"]))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Opções ilegíveis na busca %s; usando os padrões.", linha["id"])
        options = SearchOptions()
    return SearchRecord(
        id=int(linha["id"]),
        created_at=_parse_datetime(linha["created_at"]),
        prompt=linha["prompt"],
        options=options,
        md_path=Path(linha["md_path"]),
        cost_usd=linha["cost_usd"],
    )


def _parse_datetime(valor: str) -> datetime:
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return datetime.min
