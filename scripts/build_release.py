"""Gera a pasta `release/` com o app compilado (PyInstaller, Windows) + documentação + zip.

Uso:  python scripts/build_release.py

Resultado:
    release/CondorSearcher-<versão>-win64/
        CondorSearcher.exe  _internal/      <- app compilado
        config/  docs/                      <- lidos pelo app ao lado do .exe
        README.md  LICENSE  AGENTS.md  .env.example  LEIAME.txt
    release/CondorSearcher-<versão>-win64.zip   <- anexar à Release do GitHub

Nunca copia o `.env` real.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from condor import __version__  # noqa: E402

APP_NAME = "CondorSearcher"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"
PACKAGE_NAME = f"{APP_NAME}-{__version__}-win64"

LEIAME = """Condor Searcher {versao}
=========================

Pequena ferramenta vibecoded para pesquisa agêntica (Perplexity Agent API).

Como usar
---------
1. Dê duplo clique em CondorSearcher.exe.
2. Na primeira vez o app pede a sua chave da Perplexity (pplx-...); ela é gravada
   num arquivo .env ao lado do .exe. Nunca compartilhe esse arquivo.
   (Alternativa: copie .env.example para .env e preencha.)
3. Os relatórios em Markdown são gravados na pasta de saída configurada em
   config/defaults.toml.

Cada busca consome créditos da API (paga) da sua conta.

Documentação: README.md e a pasta docs/.
Licença: MIT (arquivo LICENSE).
"""


def run_pyinstaller() -> Path:
    """Compila o app em modo onedir e devolve a pasta resultante."""
    dist = BUILD_DIR / "dist"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "src" / "condor" / "__main__.py"),
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        str(ROOT / "docs" / "icon" / "icon.ico"),
        "--paths",
        str(ROOT / "src"),
        "--collect-submodules",
        "condor",
        "--collect-all",
        "perplexity",
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD_DIR / "work"),
        "--specpath",
        str(BUILD_DIR),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT)
    return dist / APP_NAME


def assemble(app_dir: Path) -> Path:
    """Monta `release/<pacote>/` com o app, a config e a documentação."""
    target = RELEASE_DIR / PACKAGE_NAME
    if target.exists():
        shutil.rmtree(target)
    RELEASE_DIR.mkdir(exist_ok=True)
    shutil.copytree(app_dir, target)
    shutil.copytree(ROOT / "config", target / "config")
    shutil.copytree(ROOT / "docs", target / "docs")
    for nome in ("README.md", "LICENSE", "AGENTS.md", ".env.example"):
        arquivo = ROOT / nome
        if arquivo.is_file():
            shutil.copy2(arquivo, target / nome)
    (target / "LEIAME.txt").write_text(LEIAME.format(versao=__version__), encoding="utf-8")
    return target


def make_zip(target: Path) -> Path:
    """Compacta a pasta do pacote em `release/<pacote>.zip`."""
    arquivo = shutil.make_archive(str(RELEASE_DIR / PACKAGE_NAME), "zip", RELEASE_DIR, target.name)
    return Path(arquivo)


def main() -> int:
    app_dir = run_pyinstaller()
    target = assemble(app_dir)
    zip_path = make_zip(target)
    print(f"Pasta: {target}")  # noqa: T201 - script de build
    print(f"Zip:   {zip_path} ({zip_path.stat().st_size / 1_048_576:.0f} MB)")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
