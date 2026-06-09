"""Janela principal do app desktop."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.settings.entities import RatioRegion, UserSettings
from presentation.desktop.widgets.image_preview import ImagePreviewWidget


class MainWindow(QMainWindow):
    """UI principal com setup, diagnostico visual e controles do bot."""

    def __init__(self, *, setup_service, automation_service) -> None:
        super().__init__()
        self.setup_service = setup_service
        self.automation_service = automation_service
        self.settings = self.setup_service.load_settings()
        self.setWindowTitle('PlayGames Bot Desktop')
        self.resize(1240, 820)
        self._last_error_message = ''

        self._build_ui()
        self._load_settings_into_form(self.settings)
        self._refresh_status()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(500)

    def _build_ui(self) -> None:
        container = QWidget()
        self.setCentralWidget(container)
        root = QHBoxLayout(container)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()
        root.addLayout(left_panel, stretch=0)
        root.addLayout(right_panel, stretch=1)

        left_panel.addWidget(self._build_window_group())
        left_panel.addWidget(self._build_bottom_region_group())
        left_panel.addWidget(self._build_battle_bar_group())
        left_panel.addWidget(self._build_actions_group())
        left_panel.addStretch(1)

        self.preview = ImagePreviewWidget()
        right_panel.addWidget(self.preview, stretch=3)

        self.slot_list = QListWidget()
        right_panel.addWidget(self.slot_list, stretch=1)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        right_panel.addWidget(self.log_output, stretch=1)

        self.status_label = QLabel('Parado')
        right_panel.addWidget(self.status_label)

    def _build_window_group(self) -> QGroupBox:
        group = QGroupBox('Janela Alvo')
        form = QFormLayout(group)

        self.window_title_edit = QLineEdit()
        self.match_mode_combo = QComboBox()
        self.match_mode_combo.addItems(['contains', 'starts_with', 'exact'])
        self.activate_window_check = QCheckBox('Ativar janela antes de clicar')
        self.dry_run_check = QCheckBox('Dry-run')

        form.addRow('Titulo da janela', self.window_title_edit)
        form.addRow('Modo de comparacao', self.match_mode_combo)
        form.addRow('', self.activate_window_check)
        form.addRow('', self.dry_run_check)
        return group

    def _build_bottom_region_group(self) -> QGroupBox:
        group = QGroupBox('Regiao Inferior')
        layout = QGridLayout(group)
        self.bottom_region_x = self._ratio_spin()
        self.bottom_region_y = self._ratio_spin()
        self.bottom_region_w = self._ratio_spin(default=1.0)
        self.bottom_region_h = self._ratio_spin(default=0.22)

        layout.addWidget(QLabel('x_ratio'), 0, 0)
        layout.addWidget(self.bottom_region_x, 0, 1)
        layout.addWidget(QLabel('y_ratio'), 0, 2)
        layout.addWidget(self.bottom_region_y, 0, 3)
        layout.addWidget(QLabel('w_ratio'), 1, 0)
        layout.addWidget(self.bottom_region_w, 1, 1)
        layout.addWidget(QLabel('h_ratio'), 1, 2)
        layout.addWidget(self.bottom_region_h, 1, 3)
        return group

    def _build_battle_bar_group(self) -> QGroupBox:
        group = QGroupBox('Battle Bar')
        layout = QGridLayout(group)

        self.bar_x = self._ratio_spin(default=0.296)
        self.bar_y = self._ratio_spin(default=0.824)
        self.bar_w = self._ratio_spin(default=0.648)
        self.bar_h = self._ratio_spin(default=0.070)
        self.slot_count = QSpinBox()
        self.slot_count.setRange(1, 20)
        self.slot_width = QSpinBox()
        self.slot_width.setRange(1, 300)
        self.slot_height = QSpinBox()
        self.slot_height.setRange(1, 300)
        self.slot_spacing = QSpinBox()
        self.slot_spacing.setRange(0, 100)
        self.variance_threshold = QDoubleSpinBox()
        self.variance_threshold.setRange(1.0, 10000.0)
        self.variance_threshold.setDecimals(2)

        widgets = [
            ('bar_x', self.bar_x),
            ('bar_y', self.bar_y),
            ('bar_w', self.bar_w),
            ('bar_h', self.bar_h),
            ('slot_count', self.slot_count),
            ('slot_width', self.slot_width),
            ('slot_height', self.slot_height),
            ('slot_spacing', self.slot_spacing),
            ('variance_threshold', self.variance_threshold),
        ]
        for index, (label, widget) in enumerate(widgets):
            row = index // 2
            col = (index % 2) * 2
            layout.addWidget(QLabel(label), row, col)
            layout.addWidget(widget, row, col + 1)
        return group

    def _build_actions_group(self) -> QGroupBox:
        group = QGroupBox('Acoes')
        layout = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()

        self.detect_window_button = QPushButton('Detectar janela')
        self.capture_region_button = QPushButton('Testar captura da regiao inferior')
        self.detect_slots_button = QPushButton('Testar deteccao dos slots')
        self.save_button = QPushButton('Salvar configuracao')
        self.start_button = QPushButton('Iniciar automacao')
        self.pause_button = QPushButton('Pausar')
        self.stop_button = QPushButton('Parar')

        self.detect_window_button.clicked.connect(self._handle_detect_window)
        self.capture_region_button.clicked.connect(self._handle_capture_bottom_region)
        self.detect_slots_button.clicked.connect(self._handle_detect_slots)
        self.save_button.clicked.connect(self._handle_save_settings)
        self.start_button.clicked.connect(self._handle_start)
        self.pause_button.clicked.connect(self._handle_pause)
        self.stop_button.clicked.connect(self._handle_stop)

        row1.addWidget(self.detect_window_button)
        row1.addWidget(self.capture_region_button)
        row2.addWidget(self.detect_slots_button)
        row2.addWidget(self.save_button)
        row3.addWidget(self.start_button)
        row3.addWidget(self.pause_button)
        row3.addWidget(self.stop_button)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)
        return group

    def _ratio_spin(self, *, default: float = 0.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.01)
        spin.setValue(default)
        return spin

    def _load_settings_into_form(self, settings: UserSettings) -> None:
        self.window_title_edit.setText(settings.window_title)
        self.match_mode_combo.setCurrentText(settings.window_match_mode)
        self.activate_window_check.setChecked(settings.activate_window)
        self.dry_run_check.setChecked(settings.dry_run)
        self.bottom_region_x.setValue(settings.bottom_region.x_ratio)
        self.bottom_region_y.setValue(settings.bottom_region.y_ratio)
        self.bottom_region_w.setValue(settings.bottom_region.w_ratio)
        self.bottom_region_h.setValue(settings.bottom_region.h_ratio)
        self.bar_x.setValue(settings.battle_bar.bar_roi.x_ratio)
        self.bar_y.setValue(settings.battle_bar.bar_roi.y_ratio)
        self.bar_w.setValue(settings.battle_bar.bar_roi.w_ratio)
        self.bar_h.setValue(settings.battle_bar.bar_roi.h_ratio)
        self.slot_count.setValue(settings.battle_bar.slot_count)
        self.slot_width.setValue(settings.battle_bar.slot_width)
        self.slot_height.setValue(settings.battle_bar.slot_height)
        self.slot_spacing.setValue(settings.battle_bar.slot_spacing)
        self.variance_threshold.setValue(settings.battle_bar.variance_threshold)

    def _read_settings_from_form(self) -> UserSettings:
        battle_bar = replace(
            self.settings.battle_bar,
            bar_roi=RatioRegion(
                x_ratio=self.bar_x.value(),
                y_ratio=self.bar_y.value(),
                w_ratio=self.bar_w.value(),
                h_ratio=self.bar_h.value(),
            ),
            slot_count=self.slot_count.value(),
            slot_width=self.slot_width.value(),
            slot_height=self.slot_height.value(),
            slot_spacing=self.slot_spacing.value(),
            variance_threshold=self.variance_threshold.value(),
        )
        return replace(
            self.settings,
            window_title=self.window_title_edit.text().strip(),
            window_match_mode=self.match_mode_combo.currentText(),
            activate_window=self.activate_window_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            bottom_region=RatioRegion(
                x_ratio=self.bottom_region_x.value(),
                y_ratio=self.bottom_region_y.value(),
                w_ratio=self.bottom_region_w.value(),
                h_ratio=self.bottom_region_h.value(),
            ),
            battle_bar=battle_bar,
        )

    def _handle_detect_window(self) -> None:
        try:
            self.settings = self._read_settings_from_form()
            window = self.setup_service.detect_window(self.settings)
            self._append_log(
                f'Janela detectada: {window.title} ({window.left},{window.top}) {window.width}x{window.height}'
            )
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_capture_bottom_region(self) -> None:
        try:
            self.settings = self._read_settings_from_form()
            preview = self.setup_service.capture_bottom_region_preview(self.settings)
            self.preview.set_bgr_image(preview.image_bgr)
            self._append_log(preview.message)
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_detect_slots(self) -> None:
        try:
            self.settings = self._read_settings_from_form()
            preview, slots = self.setup_service.detect_slots_preview(self.settings)
            self.preview.set_bgr_image(preview.image_bgr)
            self.slot_list.clear()
            for slot in slots:
                text = f'#{slot.index} lane={slot.lane} empty={slot.is_empty}'
                if not slot.is_empty:
                    text += f' type={slot.content_type} state={slot.state}'
                QListWidgetItem(text, self.slot_list)
            self._append_log(preview.message)
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_save_settings(self) -> None:
        try:
            self.settings = self._read_settings_from_form()
            self.setup_service.save_settings(self.settings)
            self._append_log('Configuracao salva em AppData/Roaming.')
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_start(self) -> None:
        try:
            self.settings = self._read_settings_from_form()
            self.setup_service.save_settings(self.settings)
            if not self.automation_service.start():
                self._append_log('Nao foi possivel iniciar a automacao.')
                return
            self._append_log('Automacao iniciada.')
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_pause(self) -> None:
        if not self.automation_service.pause():
            self._append_log('Nenhum worker em execucao para pausar.')

    def _handle_stop(self) -> None:
        if self.automation_service.stop():
            self._append_log('Solicitacao de parada enviada.')
            return
        self._append_log('Nenhum worker em execucao para parar.')

    def _refresh_status(self) -> None:
        status = self.automation_service.status()
        labels = {
            'idle': 'Parado',
            'running': 'Executando',
            'paused': 'Pausado',
            'stopping': 'Encerrando',
            'stopped': 'Parado',
            'error': 'Erro',
        }
        self.status_label.setText(f'Status: {labels.get(status.state, status.state)}')
        if status.last_error:
            if status.last_error != self._last_error_message:
                self._append_log(f'Erro: {status.last_error}')
                self._last_error_message = status.last_error
        self.start_button.setEnabled(not status.is_running)
        self.pause_button.setEnabled(status.state == 'running')
        self.stop_button.setEnabled(status.is_running or status.stop_requested)

    def _append_log(self, message: str) -> None:
        self.log_output.append(message)

    def _show_error(self, message: str) -> None:
        self._append_log(f'Erro: {message}')
        QMessageBox.critical(self, 'Erro', message)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Solicita parada do worker ao encerrar a janela."""
        self.automation_service.stop()
        super().closeEvent(event)
