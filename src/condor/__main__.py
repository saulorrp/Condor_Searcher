"""Ponto de entrada: `python -m condor`.

Aqui, e só aqui, as peças são amarradas: caminhos → configuração → serviços → janela.
O resto do app recebe tudo pronto por injeção, o que é o que mantém os testes sem Qt nem rede.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from condor import __version__
from condor.core.config import (
    Defaults,
    Snippets,
    SourcePack,
    load_defaults,
    load_snippets,
    load_source_packs,
)

CONFIG_DIR_NAME = "config"
SETTINGS_FILE = "settings.json"


def find_project_root(start: Path | None = None) -> Path:
    """Sobe a partir deste arquivo até achar a pasta `config/` com os TOML do app.

    O app roda da própria pasta (RF8, `run.bat`), então isto basta. No executável congelado
    (PyInstaller, `scripts/build_release.py`) a raiz é a pasta do `.exe`, que leva `config/`,
    `docs/icon/` e o `.env` ao lado.
    """
    if start is None and getattr(sys, "frozen", False):
        start = Path(sys.executable)
    atual = (start or Path(__file__)).resolve()
    for pasta in (atual, *atual.parents):
        if (pasta / CONFIG_DIR_NAME / "defaults.toml").is_file():
            return pasta
    raise FileNotFoundError(
        "Não encontrei a pasta config/ com defaults.toml. Rode o app a partir da pasta do projeto."
    )


def load_config(root: Path) -> tuple[Defaults, Snippets, tuple[SourcePack, ...]]:
    """Lê os três TOML de `config/`."""
    config = root / CONFIG_DIR_NAME
    return (
        load_defaults(config / "defaults.toml"),
        load_snippets(config / "prompt_snippets.toml"),
        load_source_packs(config / "source_packs.toml"),
    )


def main() -> int:
    """Abre a janela. Devolve o código de saída do processo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("condor")
    logger.info("Condor Searcher %s", __version__)

    # Imports tardios: assim `python -m condor --version` não paga o custo de carregar o Qt.
    from PySide6.QtWidgets import QApplication, QMessageBox

    from condor.services.client import AgentClient
    from condor.services.secrets import ENV_FILE, SecretStore
    from condor.services.settings_store import SettingsStore
    from condor.services.storage import Storage
    from condor.ui.assets import app_icon, set_windows_app_id
    from condor.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Condor Searcher")
    app.setApplicationVersion(__version__)

    try:
        root = find_project_root()
        defaults, snippets, packs = load_config(root)
    except (FileNotFoundError, ValueError) as exc:
        QMessageBox.critical(None, "Configuração inválida", str(exc))
        logger.error("Configuração inválida: %s", exc)
        return 2

    set_windows_app_id()  # antes de criar janelas: é o que faz o Windows usar o nosso ícone
    app.setWindowIcon(app_icon(root))  # ícone da janela e da barra de tarefas

    storage = Storage(defaults.output_dir)
    # Nada de `load_dotenv()`: o `secrets.py` é o único caminho para a chave, e é ele que
    # distingue variável de sistema de `.env` (decisão registrada na F6).
    secrets = SecretStore(root / ENV_FILE)
    settings = SettingsStore(defaults.output_dir / SETTINGS_FILE)

    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        # A chave vem do `secrets`, não do ambiente: ver _build_sdk_client em services/client.py.
        client=AgentClient(api_key_provider=secrets.get_key),
        settings=settings,
        packs=packs,
        project_root=root,
    )
    window.show()
    window.ensure_key()  # sem chave, o diálogo abre sozinho (RF7)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
