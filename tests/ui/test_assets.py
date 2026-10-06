"""Testes do ícone (`ui/assets.py`)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from condor.ui.assets import (
    APP_USER_MODEL_ID,
    ICON_DIR,
    ICON_SIZES,
    app_icon,
    icon_path,
    set_windows_app_id,
)

ROOT = Path(__file__).resolve().parents[2]


def test_icone_do_projeto_existe() -> None:
    caminho = icon_path(ROOT)
    assert caminho is not None
    assert caminho.name == "icon.png"
    assert caminho.parent == ROOT / ICON_DIR


def test_icone_do_projeto_carrega_em_varios_tamanhos(qtbot) -> None:
    """O PNG é único e grande; o QIcon tem de sair com um bitmap por tamanho pedido."""
    icone = app_icon(ROOT)
    assert not icone.isNull()
    assert len(icone.availableSizes()) == len(ICON_SIZES)
    for lado in ICON_SIZES:
        assert not icone.pixmap(lado, lado).isNull()


def test_maior_lado_de_cada_tamanho_bate_com_o_pedido(qtbot) -> None:
    icone = app_icon(ROOT)
    assert {max(s.width(), s.height()) for s in icone.availableSizes()} == set(ICON_SIZES)


def test_sem_pasta_de_icone_devolve_icone_vazio(qtbot, tmp_path: Path) -> None:
    assert icon_path(tmp_path) is None
    assert app_icon(tmp_path).isNull()


def test_arquivo_ilegivel_nao_quebra(qtbot, tmp_path: Path) -> None:
    pasta = tmp_path / ICON_DIR
    pasta.mkdir(parents=True)
    (pasta / "icon.png").write_text("isto não é uma imagem", encoding="utf-8")
    assert app_icon(tmp_path).isNull()  # degrada, não levanta


def test_prefere_png_mas_aceita_ico(qtbot, tmp_path: Path) -> None:
    pasta = tmp_path / ICON_DIR
    pasta.mkdir(parents=True)
    shutil.copy(ROOT / ICON_DIR / "icon.ico", pasta / "icon.ico")
    assert icon_path(tmp_path).name == "icon.ico"

    shutil.copy(ROOT / ICON_DIR / "icon.png", pasta / "icon.png")
    assert icon_path(tmp_path).name == "icon.png"


@pytest.mark.skipif(sys.platform != "win32", reason="AppUserModelID só existe no Windows")
def test_app_user_model_id_e_registrado_no_windows() -> None:
    assert set_windows_app_id() is True
    assert "." in APP_USER_MODEL_ID  # a Microsoft pede o formato Empresa.Produto


@pytest.mark.skipif(sys.platform == "win32", reason="fora do Windows deve ser inócuo")
def test_app_user_model_id_e_inocuo_fora_do_windows() -> None:
    assert set_windows_app_id() is False
