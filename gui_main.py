"""Toolbar grafica para controlar o bot sem depender de terminal."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from config import carregar_yaml, resolver_caminho_config
from services.bot_controller import BotController
from tasks.executar_fluxo import executar_bot


class BotToolbarApp:
    """UI pequena sempre no topo com start, pause e encerrar."""

    def __init__(self, root: tk.Tk, *, caminho_config: Path) -> None:
        self.root = root
        self.caminho_config = caminho_config
        self.controller = BotController()
        self.cv_profiles, self.cv_default = self._carregar_opcoes_cv()

        self.root.title('PlayGames Bot')
        self.root.attributes('-topmost', False)
        self.root.resizable(False, False)
        self.root.geometry('360x200')
        self.root.configure(bg='#f4efe6')
        self.root.protocol('WM_DELETE_WINDOW', self.encerrar_aplicacao)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Bot.TFrame', background='#f4efe6')
        style.configure('Bot.TLabel', background='#f4efe6', foreground='#3d352d')
        style.configure('BotStatus.TLabel', background='#f4efe6', foreground='#1c5d3a')
        style.configure('BotError.TLabel', background='#f4efe6', foreground='#8f2d2d')
        style.configure('Bot.TButton', padding=(10, 6))
        style.configure('Bot.TCombobox', padding=4)

        frame = ttk.Frame(self.root, style='Bot.TFrame', padding=12)
        frame.pack(fill='both', expand=True)

        self.status_var = tk.StringVar(value='Parado')
        self.error_var = tk.StringVar(value='')
        self.cv_var = tk.StringVar(value=self.cv_default)
        self.topmost_var = tk.BooleanVar(value=False)

        ttk.Label(frame, text='CV ativo', style='Bot.TLabel').pack(fill='x')
        self.cv_combo = ttk.Combobox(
            frame,
            textvariable=self.cv_var,
            values=self.cv_profiles,
            state='readonly',
            style='Bot.TCombobox',
        )
        self.cv_combo.pack(fill='x', pady=(4, 10))

        self.topmost_check = ttk.Checkbutton(
            frame,
            text='Sempre no topo',
            variable=self.topmost_var,
            command=self.alternar_topmost,
        )
        self.topmost_check.pack(fill='x', pady=(0, 10))

        botoes = ttk.Frame(frame, style='Bot.TFrame')
        botoes.pack(fill='x')

        self.start_button = ttk.Button(botoes, text='Iniciar', width=10, command=self.iniciar_ou_retomar, style='Bot.TButton')
        self.start_button.pack(side='left')

        self.pause_button = ttk.Button(botoes, text='Pausar', width=10, command=self.pausar, style='Bot.TButton')
        self.pause_button.pack(side='left', padx=8)

        self.stop_button = ttk.Button(botoes, text='Encerrar', width=10, command=self.encerrar_aplicacao, style='Bot.TButton')
        self.stop_button.pack(side='left')

        ttk.Label(frame, text='Status', style='Bot.TLabel').pack(fill='x', pady=(12, 0))
        ttk.Label(frame, textvariable=self.status_var, style='BotStatus.TLabel').pack(fill='x')
        ttk.Label(frame, textvariable=self.error_var, style='BotError.TLabel').pack(fill='x', pady=(6, 0))

        self.root.after(250, self.atualizar_estado)

    def _carregar_opcoes_cv(self) -> tuple[list[str], str]:
        """Carrega os perfis CV disponiveis no config e escolhe o default."""
        if not self.caminho_config.exists():
            return ['default'], 'default'
        cfg = carregar_yaml(self.caminho_config)
        perfis = sorted((cfg.get('cv_profiles') or {}).keys())
        default = str(cfg.get('runtime', {}).get('cv_profile') or '')
        if default and default not in perfis:
            perfis.insert(0, default)
        if not perfis:
            perfis = ['default']
        return perfis, default or perfis[0]

    def iniciar_ou_retomar(self) -> None:
        """Inicia novo worker ou retoma o worker pausado."""
        status = self.controller.snapshot()
        if status.is_paused:
            self.controller.start(self._executar_worker)
            return
        if status.is_running:
            return
        self.error_var.set('')
        iniciado = self.controller.start(self._executar_worker)
        if not iniciado:
            self.error_var.set('Nao foi possivel iniciar o worker.')

    def pausar(self) -> None:
        """Pausa o worker no próximo checkpoint seguro."""
        if not self.controller.pause():
            self.error_var.set('Nenhum worker em execucao para pausar.')

    def encerrar_aplicacao(self) -> None:
        """Solicita stop, aguarda o worker e fecha a UI."""
        self.controller.stop()
        self.controller.join(timeout=3.0)
        self.root.destroy()

    def alternar_topmost(self) -> None:
        """Liga ou desliga o modo sempre no topo da toolbar."""
        self.root.attributes('-topmost', self.topmost_var.get())

    def atualizar_estado(self) -> None:
        """Atualiza o estado visual da toolbar."""
        status = self.controller.snapshot()
        textos = {
            'idle': 'Parado',
            'running': 'Executando',
            'paused': 'Pausado',
            'stopping': 'Encerrando',
            'stopped': 'Parado',
            'error': 'Erro',
        }
        self.status_var.set(textos.get(status.state, status.state))
        self.error_var.set(status.last_error or '')

        self.start_button.configure(text='Retomar' if status.is_paused else 'Iniciar')
        self.pause_button.configure(state='normal' if status.state == 'running' else 'disabled')
        self.cv_combo.configure(state='disabled' if status.is_running else 'readonly')

        self.root.after(250, self.atualizar_estado)

    def _executar_worker(self) -> None:
        """Corpo do worker associado ao controller."""
        cv_profile = None if self.cv_var.get() == 'default' else self.cv_var.get()
        codigo_saida = executar_bot(self.caminho_config, cv_profile=cv_profile, controller=self.controller)
        if codigo_saida not in {0, 1, 2}:
            raise RuntimeError(f'Codigo de saida inesperado: {codigo_saida}')
        if codigo_saida == 2:
            raise RuntimeError('Arquivo config.yaml nao encontrado ao lado do executavel.')
        if codigo_saida == 1:
            raise RuntimeError('Execucao encerrada com erro. Consulte debug_saida/bot.log.')


def iniciar_toolbar(caminho_config: str | Path = 'config.yaml') -> None:
    """Inicializa a toolbar grafica."""
    caminho = resolver_caminho_config(caminho_config)
    root = tk.Tk()
    app = BotToolbarApp(root, caminho_config=caminho)
    if not caminho.exists():
        messagebox.showwarning('Config ausente', 'config.yaml nao encontrado ao lado do executavel ou no diretorio atual.')
        app.error_var.set('config.yaml nao encontrado.')
    root.mainloop()


if __name__ == '__main__':
    iniciar_toolbar()
