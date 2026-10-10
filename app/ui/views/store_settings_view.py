from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.store_settings_service import StoreSettingsService
from app.ui.widgets import create_dashboard_back_button


class StoreSettingsView(QWidget):
    back_requested = Signal()
    settings_saved = Signal(object)

    def __init__(self, actor, service: StoreSettingsService, parent=None):
        super().__init__(parent)
        self.actor = actor
        self.service = service
        self.logo_source: str | None = None
        self.remove_logo = False
        self.store = None
        self._editing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(16)

        header = QHBoxLayout()
        self.back_button = create_dashboard_back_button(self)
        self.back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Pengaturan Toko")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #172554;")
        header.addWidget(self.back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        description = QLabel(
            "Identitas ini ditampilkan pada dashboard dan judul jendela aplikasi. "
            "Logo bersifat opsional dan digunakan sebagai ikon jendela."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #64748b;")
        root.addWidget(description)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setMaxLength(150)
        self.name_input.setPlaceholderText("Nama toko")
        self.slogan_input = QLineEdit()
        self.slogan_input.setMaxLength(200)
        self.slogan_input.setPlaceholderText("Slogan toko")
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Alamat lengkap toko")
        self.whatsapp_input = QLineEdit()
        self.whatsapp_input.setMaxLength(30)
        self.whatsapp_input.setPlaceholderText("Contoh: +62 812 3456 7890")
        form.addRow("Nama toko *", self.name_input)
        form.addRow("Slogan", self.slogan_input)
        form.addRow("Alamat", self.address_input)
        form.addRow("Nomor WhatsApp", self.whatsapp_input)

        logo_row = QHBoxLayout()
        self.logo_preview = QLabel("Belum ada logo")
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_preview.setFixedSize(110, 90)
        self.logo_preview.setStyleSheet(
            "border: 1px dashed #94a3b8; color: #64748b; background: #f8fafc;"
        )
        logo_buttons = QVBoxLayout()
        self.choose_logo_button = QPushButton("Pilih Logo")
        self.choose_logo_button.clicked.connect(self._choose_logo)
        self.remove_logo_button = QPushButton("Hapus Logo")
        self.remove_logo_button.clicked.connect(self._remove_logo)
        logo_buttons.addWidget(self.choose_logo_button)
        logo_buttons.addWidget(self.remove_logo_button)
        logo_buttons.addStretch(1)
        logo_row.addWidget(self.logo_preview)
        logo_row.addLayout(logo_buttons)
        logo_row.addStretch(1)
        form.addRow("Logo (opsional)", logo_row)
        root.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.edit_button = QPushButton("Ubah")
        self.edit_button.clicked.connect(self._begin_edit)
        self.save_button = QPushButton("Simpan")
        self.save_button.clicked.connect(self._save)
        self.cancel_button = QPushButton("Batal")
        self.cancel_button.clicked.connect(self._cancel_edit)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.cancel_button)
        root.addLayout(action_row)
        root.addStretch(1)

        self._load_store()
        self._set_editing(False)

    def _load_store(self):
        try:
            self.store = self.service.get_store()
        except SQLAlchemyError as exc:
            QMessageBox.critical(self, "Gagal memuat pengaturan toko", str(exc))
            self.store = None
        self.logo_source = None
        self.remove_logo = False
        self.name_input.setText(self.store.name if self.store else "")
        self.slogan_input.setText(
            self.store.slogan if self.store and self.store.slogan else ""
        )
        self.address_input.setText(
            self.store.address if self.store and self.store.address else ""
        )
        self.whatsapp_input.setText(
            self.store.whatsapp if self.store and self.store.whatsapp else ""
        )
        self._show_logo(self.store.logo_path if self.store else None)

    def reload_settings(self):
        self._load_store()
        self._set_editing(False)

    def _show_logo(self, logo_path: str | None):
        self.logo_preview.clear()
        if logo_path and Path(logo_path).is_file():
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                self.logo_preview.setPixmap(
                    pixmap.scaled(
                        self.logo_preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.logo_preview.setText("Belum ada logo")

    def _begin_edit(self):
        self._editing = True
        self._set_editing(True)

    def _set_editing(self, editing: bool):
        self.name_input.setReadOnly(not editing)
        self.slogan_input.setReadOnly(not editing)
        self.address_input.setReadOnly(not editing)
        self.whatsapp_input.setReadOnly(not editing)
        self.choose_logo_button.setEnabled(editing)
        self.remove_logo_button.setEnabled(editing)
        self.edit_button.setVisible(not editing)
        self.save_button.setVisible(editing)
        self.cancel_button.setVisible(editing)
        self._editing = editing

    def _choose_logo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Logo Toko",
            "",
            "Gambar (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not file_path:
            return
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(
                self,
                "Logo tidak valid",
                "File yang dipilih tidak dapat dibaca sebagai gambar.",
            )
            return
        self.logo_source = file_path
        self.remove_logo = False
        self._show_logo(file_path)

    def _remove_logo(self):
        self.logo_source = None
        self.remove_logo = True
        self._show_logo(None)

    def _save(self):
        try:
            store = self.service.save(
                self.actor,
                name=self.name_input.text(),
                slogan=self.slogan_input.text(),
                address=self.address_input.text(),
                whatsapp=self.whatsapp_input.text(),
                logo_source=self.logo_source,
                remove_logo=self.remove_logo,
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pengaturan tidak tersimpan", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "Logo tidak dapat disimpan", str(exc))
            return

        self.store = store
        self.logo_source = None
        self.remove_logo = False
        self._show_logo(store.logo_path)
        self._set_editing(False)
        self.settings_saved.emit(store)
        QMessageBox.information(
            self,
            "Pengaturan tersimpan",
            "Profil toko berhasil diperbarui.",
        )

    def _cancel_edit(self):
        self._load_store()
        self._set_editing(False)
