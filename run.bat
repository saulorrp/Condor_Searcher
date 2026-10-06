@echo off
rem ==========================================================
rem  Condor Searcher - inicializador para Windows
rem  Uso:  run.bat              abre o app
rem        run.bat --atualizar  reinstala dependencias e abre
rem        run.bat --console    abre com console (ver erros)
rem ==========================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"

if not exist "%VENV_PY%" goto :criar_venv
if /i "%~1"=="--atualizar" goto :instalar
goto :abrir

:criar_venv
echo [Condor] Primeira execucao: criando ambiente Python...
where py >nul 2>nul
if errorlevel 1 goto :tentar_python
py -3 -m venv .venv
goto :checar_venv

:tentar_python
where python >nul 2>nul
if errorlevel 1 goto :sem_python
python -m venv .venv

:checar_venv
if not exist "%VENV_PY%" goto :sem_python
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :python_antigo

:instalar
echo [Condor] Instalando/atualizando dependencias (pode levar alguns minutos)...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -e . --quiet
if errorlevel 1 goto :falha_pip
echo [Condor] Pronto.

:abrir
if /i "%~1"=="--console" goto :abrir_console
start "" "%VENV_PYW%" -m condor
goto :fim

:abrir_console
"%VENV_PY%" -m condor
pause
goto :fim

:sem_python
echo.
echo [ERRO] Python nao encontrado.
echo Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
pause
exit /b 1

:python_antigo
echo.
echo [ERRO] O Condor precisa de Python 3.11 ou mais novo.
echo Apague a pasta .venv, instale um Python mais novo e rode de novo.
pause
exit /b 1

:falha_pip
echo.
echo [ERRO] Falha ao instalar as dependencias. Verifique a internet e tente:
echo        run.bat --atualizar
pause
exit /b 1

:fim
endlocal
