@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERRO] Python da virtualenv nao encontrado em ".venv\Scripts\python.exe".
    echo Crie a virtualenv e instale as dependencias antes de rodar este build.
    exit /b 1
)

echo [1/3] Verificando PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller nao encontrado. Instalando...
    "%PYTHON_EXE%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar PyInstaller.
        exit /b 1
    )
)

echo [2/3] Gerando executavel unico...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --onefile --windowed --name playgames-bot-toolbar --add-data "config.yaml;." --add-data "assets;assets" gui_main.py
if errorlevel 1 (
    echo [ERRO] Falha ao gerar o executavel.
    exit /b 1
)

echo [3/3] Build concluido.
echo Executavel unico gerado em: "%ROOT_DIR%dist\playgames-bot-toolbar.exe"
echo O config.yaml e os assets estao embutidos no proprio exe.

endlocal
