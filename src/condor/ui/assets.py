"""Identidade visual do app: o ícone do condor.

Os arquivos vivem em `docs/icon/` (é lá que mora a identidade), e o app os encontra pela pasta do
projeto, do mesmo jeito que acha `config/`. Se o ícone sumir, o app abre igual — ícone que falta é
um detalhe estético, não motivo para não iniciar.

O PNG original tem mais de mil pixels. Um `QIcon` com uma única imagem desse tamanho fica mole
quando o Windows o reduz para 16px na barra de tarefas, então geramos aqui as reduções com
transformação suave e entregamos um ícone multi-tamanho.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

logger = logging.getLogger(__name__)

ICON_DIR = "docs/icon"

#: Em ordem de preferência: o PNG é a fonte de melhor qualidade.
ICON_FILES = ("icon.png", "icon.ico", "icon.svg")

#: Tamanhos que o Windows pede (barra de tarefas, Alt+Tab, janela, atalho grande).
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def icon_path(root: Path) -> Path | None:
    """Caminho do melhor arquivo de ícone disponível, ou `None` se não houver nenhum."""
    pasta = root / ICON_DIR
    for nome in ICON_FILES:
        candidato = pasta / nome
        if candidato.is_file():
            return candidato
    logger.info("Nenhum ícone encontrado em %s; seguindo sem ícone.", pasta)
    return None


def app_icon(root: Path) -> QIcon:
    """`QIcon` multi-tamanho do app. Vem vazio quando não há arquivo — o Qt lida com isso."""
    caminho = icon_path(root)
    if caminho is None:
        return QIcon()

    original = QPixmap(str(caminho))
    if original.isNull():
        logger.warning("Não consegui ler o ícone %s; seguindo sem ícone.", caminho.name)
        return QIcon()

    icone = QIcon()
    for lado in ICON_SIZES:
        icone.addPixmap(
            original.scaled(
                lado,
                lado,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icone


#: Identidade do app para o Windows. Sem isto, a barra de tarefas agrupa a janela sob o
#: executável do Python e mostra o ícone genérico da linguagem, mesmo com o ícone da janela
#: definido — o Windows decide o ícone da barra pelo AppUserModelID, não pela janela.
APP_USER_MODEL_ID = "Saulo.CondorSearcher"


def set_windows_app_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Registra o AppUserModelID no Windows. Em outros sistemas não faz nada e devolve `False`."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError) as exc:  # pragma: no cover - depende do Windows
        logger.info("Não consegui registrar o AppUserModelID (%s); ícone da barra pode variar.", exc)
        return False
    return True
