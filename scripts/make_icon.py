"""Gera `docs/icon/icon.ico` multi-tamanho a partir de `docs/icon/icon.png`.

Por que existe: o Windows escolhe a imagem do `.ico` pelo tamanho pedido (16px na barra de
tarefas, 32px no Explorer, 256px no painel de visualização). Um `.ico` com uma única imagem
obriga o Windows a redimensionar, e o resultado fica serrilhado nos tamanhos pequenos.

Por que não é só `QImage.save("icon.ico")`: o escritor de ICO do Qt grava **uma** imagem por
arquivo. O contêiner com várias é montado aqui — cabeçalho ICONDIR + uma ICONDIRENTRY por
tamanho + os PNGs. Entradas em PNG são aceitas pelo Windows desde o Vista.

Uso:
    python scripts/make_icon.py                # docs/icon/icon.png -> docs/icon/icon.ico
    python scripts/make_icon.py --dry-run      # só mostra o que faria
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_app = None  # instância do Qt, criada em main()
ICON_DIR = ROOT / "docs" / "icon"

#: Tamanhos que o Windows pede. 256 é o limite do formato (gravado como 0 no cabeçalho).
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(source: Path, lado: int) -> bytes:
    """Reduz a imagem para um quadrado `lado`x`lado` e devolve o PNG em memória."""
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter

    original = QImage(str(source))
    if original.isNull():
        raise SystemExit(f"Não consegui ler {source}.")

    escalada = original.scaled(
        lado,
        lado,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # O ícone precisa ser quadrado: centralizamos a imagem num quadro transparente.
    quadro = QImage(lado, lado, QImage.Format.Format_ARGB32)
    quadro.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(quadro)
    pintor.drawImage((lado - escalada.width()) // 2, (lado - escalada.height()) // 2, escalada)
    pintor.end()

    # O QByteArray fica numa variável própria: entregue como temporário ao QBuffer, ele pode
    # ser liberado antes da hora e derrubar o processo.
    destino = QByteArray()
    buffer = QBuffer(destino)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    quadro.save(buffer, "PNG")
    buffer.close()
    return bytes(destino)


def build_ico(imagens: list[tuple[int, bytes]]) -> bytes:
    """Monta o arquivo .ico: ICONDIR + uma ICONDIRENTRY por imagem + os dados."""
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))  # reservado, tipo 1 = ícone, quantidade
    deslocamento = len(cabecalho) + 16 * len(imagens)

    entradas = b""
    for lado, dados in imagens:
        entradas += struct.pack(
            "<BBBBHHII",
            0 if lado >= 256 else lado,  # largura (0 significa 256)
            0 if lado >= 256 else lado,  # altura
            0,  # cores da paleta (0 = sem paleta)
            0,  # reservado
            1,  # planos de cor
            32,  # bits por pixel
            len(dados),
            deslocamento,
        )
        deslocamento += len(dados)

    return cabecalho + entradas + b"".join(dados for _, dados in imagens)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gera o .ico multi-tamanho do Condor.")
    p.add_argument("--source", type=Path, default=ICON_DIR / "icon.png")
    p.add_argument("--out", type=Path, default=ICON_DIR / "icon.ico")
    p.add_argument("--dry-run", action="store_true", help="não grava nada")
    args = p.parse_args(list(sys.argv[1:] if argv is None else argv))

    if not args.source.is_file():
        raise SystemExit(f"Imagem de origem não encontrada: {args.source}")

    from PySide6.QtGui import QGuiApplication

    global _app  # mantido vivo até o fim do processo: o Qt não gosta de perder a instância
    _app = QGuiApplication.instance() or QGuiApplication(["make_icon"])

    imagens = [(lado, png_bytes(args.source, lado)) for lado in SIZES]
    conteudo = build_ico(imagens)
    print(f"[origem] {args.source.relative_to(ROOT)}")
    for lado, dados in imagens:
        print(f"  {lado:>3}x{lado:<3} {len(dados):>6} bytes")

    if args.dry_run:
        print(f"[dry-run] geraria {len(conteudo)} bytes em {args.out.relative_to(ROOT)}")
        return 0

    args.out.write_bytes(conteudo)
    print(f"[ok] {args.out.relative_to(ROOT)} — {len(imagens)} tamanhos, {len(conteudo)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
