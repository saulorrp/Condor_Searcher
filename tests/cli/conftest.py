"""Ambiente da linha de comando para os testes — disco temporário, SDK falso, sem rede."""

from __future__ import annotations

from pathlib import Path

import pytest

from condor.cli.app import Ambiente
from condor.core.config import load_defaults, load_snippets, load_source_packs
from condor.services.client import AgentClient
from condor.services.secrets import ENV_VAR, SecretStore
from condor.services.storage import Storage
from tests.fakes import SdkFalso

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
CHAVE = "pplx-chavefalsa1234567890"


class Saida:
    """Recolhe o que a CLI escreveria na tela."""

    def __init__(self) -> None:
        self.linhas: list[str] = []

    def __call__(self, texto: str) -> None:
        self.linhas.append(texto)

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)


@pytest.fixture
def raw_fast() -> dict:
    import json

    return json.loads((ROOT / "tests" / "fixtures" / "agent_fast.json").read_text(encoding="utf-8"))


@pytest.fixture
def ambiente(tmp_path: Path, raw_fast) -> Ambiente:
    """Projeto real (config/), mas saída, chave e SDK isolados."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_VAR}={CHAVE}\n", encoding="utf-8")

    sdk = SdkFalso(raw_fast)
    ambiente = Ambiente(
        root=ROOT,
        defaults=load_defaults(CONFIG / "defaults.toml"),
        snippets=load_snippets(CONFIG / "prompt_snippets.toml"),
        packs=load_source_packs(CONFIG / "source_packs.toml"),
        storage=Storage(tmp_path / "saida"),
        secrets=SecretStore(env_file, environ={}),
        client=AgentClient(lambda: sdk, sleep=lambda s: False),
        escrever=Saida(),
    )
    ambiente.sdk = sdk  # type: ignore[attr-defined]  — atalho para os testes
    return ambiente


@pytest.fixture
def sem_chave(ambiente: Ambiente, tmp_path: Path) -> Ambiente:
    ambiente.secrets = SecretStore(tmp_path / "vazio" / ".env", environ={})
    return ambiente
