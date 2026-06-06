# Play Games App QA Visual Bot

Bot visual para testar app proprio/autorizado rodando no Google Play Games.
Ele trabalha por captura de tela, reconhecimento de botoes por imagem, OCR opcional e cliques configuraveis.

## Estrutura

```text
playgames_app_qa_visual_bot/
|- main.py
|- config.py
|- playgames_app_bot.py
|- calibrar_mouse.py
|- screenshot_grade.py
|- crop_asset.py
|- services/
|  \- automacao_service.py
|- clients/
|  \- window_client.py
|- tasks/
|  \- executar_fluxo.py
|- utils/
|  \- image_utils.py
|- assets/
|- config.example.yaml
|- config.yaml
```

- `main.py`: novo ponto de entrada principal.
- `config.py`: carregamento de YAML, merge de perfis CV e resolucao de caminhos.
- `services/`: regras e orquestracao do bot.
- `clients/`: integracao com a janela do Play Games.
- `tasks/`: fluxo executavel do bot.
- `utils/`: funcoes auxiliares de imagem.
- `playgames_app_bot.py`: wrapper de compatibilidade com o comando antigo.

## Instalacao

```cmd
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
```

## Uso basico

Configure a janela no `config.yaml`:

```yaml
window:
  title_contains: "Google Play Games"
```

Comandos principais:

```cmd
python main.py --config config.yaml
python main.py --config config.yaml --cv cv_13
python main.py --config config.yaml --preliminary
python main.py --config config.yaml --deploy-now
```

Compatibilidade:

```cmd
python playgames_app_bot.py --config config.yaml
```

Toolbar grafica:

```cmd
python gui_main.py
```

O app abre uma janelinha sempre no topo com `Iniciar`, `Pausar` e `Encerrar`. Se `runtime.require_target_focus: true`, ao retomar o bot ele volta a tentar ativar a janela do Clash of Clans/Play Games antes de seguir.

## Gerar EXE

Instale o PyInstaller no ambiente e rode:

```cmd
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

O `config.yaml` e a pasta `assets\` devem ficar ao lado do executavel gerado para permitir ajustes sem recompilar.

## Utilitarios

Descobrir coordenadas relativas:

```cmd
python calibrar_mouse.py --config config.yaml
```

Gerar screenshot com grade:

```cmd
python screenshot_grade.py --config config.yaml
```

Recortar asset:

```cmd
python crop_asset.py --input debug_saida\screenshot_grade_20260602-120000.png --output assets\start_button.png --x 100 --y 500 --w 150 --h 60
```

## Assets e fluxo

No `config.yaml`, cada asset precisa existir em `assets:` com a mesma chave usada no fluxo:

```yaml
assets:
  start_button: "assets/start_button.png"
  start_button_2: "assets/start_button_2.png"
  search_button: "assets/search_button.png"
```

Fluxo inicial:

```yaml
flow:
  target_mode: direct_attack
  pre_search_steps:
    - start_button
    - start_button_2
    - search_button
```

O bot valida esses caminhos ao iniciar. Se algum asset estiver faltando, ele informa a chave e o caminho esperado.
