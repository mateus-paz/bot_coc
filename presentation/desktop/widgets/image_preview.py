"""Widget simples para exibir previews BGR na interface."""

from __future__ import annotations

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel


class ImagePreviewWidget(QLabel):
    """Exibe imagens de diagnostico dimensionadas ao espaco disponivel."""

    def __init__(self) -> None:
        super().__init__('Nenhuma imagem carregada.')
        self.setMinimumSize(420, 240)
        self.setScaledContents(False)
        self.setStyleSheet('border: 1px solid #999; background: #181818; color: #ddd;')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_bgr_image(self, image_bgr) -> None:
        """Atualiza o preview com uma imagem BGR do OpenCV."""
        if image_bgr is None:
            self.setText('Nenhuma imagem carregada.')
            self.setPixmap(QPixmap())
            return
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        """Mantem o pixmap escalado ao redimensionar o widget."""
        if self.pixmap() is not None and not self.pixmap().isNull():
            self.setPixmap(self.pixmap().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        super().resizeEvent(event)
