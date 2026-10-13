from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.store_settings_service import StoreSettingsService
from app.services.payment_settings_service import PaymentSettingsService
from app.ui.theme import PALETTE
from app.ui.widgets import create_dashboard_back_button


class StoreSettingsView(QWidget):
    back_requested = Signal()
    settings_saved = Signal(object)

    def __init__(
        self,
        actor,
        service: StoreSettingsService,
        payment_service: PaymentSettingsService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.actor = actor
        self.service = service
        self.payment_service = payment_service
        self.logo_source: str | None = None
        self.remove_logo = False
        self.store = None
        self.payment_settings = None
        self._editing = False
        self._syncing_all = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content = QWidget()
        content.setObjectName("storeSettingsContent")
        content.setStyleSheet(
            f"QWidget#storeSettingsContent {{ background-color: {PALETTE['window']}; }}"
        )
        outer.addWidget(scroll)

        root = QVBoxLayout(content)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(16)

        header = QHBoxLayout()
        self.back_button = create_dashboard_back_button(self)
        self.back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Pengaturan Toko")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #ffffff;")
        header.addWidget(self.back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        description = QLabel(
            "Identitas ini ditampilkan pada dashboard dan judul jendela aplikasi. "
            "Logo bersifat opsional dan digunakan sebagai ikon jendela."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #a1a1aa;")
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
            "border: 1px dashed #3f3f4a; color: #a1a1aa; background: #1a1a1e;"
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

        payment_section_label = QLabel("Pengaturan Pembayaran")
        payment_section_label.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #ffffff; margin-top: 8px;"
        )
        root.addWidget(payment_section_label)

        payment_description = QLabel(
            "Pilih metode pembayaran yang tersedia pada jendela kasir. "
            "Jika hanya Tunai (Offline) yang dipilih, kasir hanya dapat menerima tunai. "
            "Metode non-tunai baru muncul di kasir bila dicentang dan status "
            "wizard-nya sudah Aktif."
        )
        payment_description.setWordWrap(True)
        payment_description.setStyleSheet("color: #a1a1aa;")
        root.addWidget(payment_description)

        self.payment_cash = QCheckBox("Tunai (Offline)")
        self.payment_qris_dana = QCheckBox("QRIS DANA")
        self.payment_qris_midtrans = QCheckBox("QRIS MIDTRANS")
        self.payment_transfer = QCheckBox("TF (m BANKING)")
        self.payment_all = QCheckBox("Semua (termasuk tunai)")

        self.payment_cash.toggled.connect(self._sync_all_checkbox)
        self.payment_qris_dana.toggled.connect(self._sync_all_checkbox)
        self.payment_qris_midtrans.toggled.connect(self._sync_all_checkbox)
        self.payment_transfer.toggled.connect(self._sync_all_checkbox)
        self.payment_all.toggled.connect(self._on_all_toggled)

        self._payment_setting_buttons: list[QPushButton] = []
        self._payment_status_labels: dict[str, QLabel] = {}

        def add_payment_row(
            checkbox: QCheckBox, with_setting: bool, method_code: str | None = None
        ):
            row = QHBoxLayout()
            row.addWidget(checkbox)
            row.addStretch(1)
            if with_setting:
                if method_code:
                    status_label = QLabel("")
                    status_label.setStyleSheet("color: #a1a1aa;")
                    self._payment_status_labels[method_code] = status_label
                    row.addWidget(status_label)
                setting_button = QPushButton("SETTING")
                setting_button.setFixedWidth(90)
                setting_button.clicked.connect(
                    lambda _=False, label=checkbox.text(): self._open_payment_wizard(label)
                )
                row.addWidget(setting_button)
                self._payment_setting_buttons.append(setting_button)
            root.addLayout(row)

        add_payment_row(self.payment_cash, with_setting=False)
        add_payment_row(self.payment_qris_dana, True, "QRIS_DANA")
        add_payment_row(self.payment_qris_midtrans, True, "QRIS_MIDTRANS")
        add_payment_row(self.payment_transfer, True, "BANK")
        add_payment_row(self.payment_all, with_setting=True)

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

        scroll.setWidget(content)

        self._load_store()
        self._set_editing(False)
        self._refresh_payment_status_labels()

    def _refresh_payment_status_labels(self):
        from app.models import PaymentWizardState
        from app.services.payment_wizard_service import STATUS_LABELS

        statuses: dict[str, str] = {}
        if self.payment_service is not None:
            try:
                statuses = {
                    row.method: row.status
                    for row in self.payment_service.session.query(
                        PaymentWizardState
                    ).all()
                }
            except SQLAlchemyError:
                statuses = {}
        for method, label in self._payment_status_labels.items():
            status = statuses.get(method, "not_started")
            label.setText(f"Status: {STATUS_LABELS.get(status, status)}")
            color = "#4ade80" if status == "active" else "#a1a1aa"
            label.setStyleSheet(f"color: {color};")

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
        self._load_payment_settings()

    def _load_payment_settings(self):
        if self.payment_service is None:
            return
        try:
            self.payment_settings = self.payment_service.get_settings()
        except SQLAlchemyError as exc:
            QMessageBox.critical(self, "Gagal memuat pengaturan pembayaran", str(exc))
            self.payment_settings = None
            return
        self._syncing_all = True
        self.payment_cash.setChecked(self.payment_settings.cash_enabled)
        self.payment_qris_dana.setChecked(self.payment_settings.qris_dana_enabled)
        self.payment_qris_midtrans.setChecked(
            self.payment_settings.qris_midtrans_enabled
        )
        self.payment_transfer.setChecked(self.payment_settings.transfer_enabled)
        all_enabled = all(
            box.isChecked()
            for box in (
                self.payment_cash,
                self.payment_qris_dana,
                self.payment_qris_midtrans,
                self.payment_transfer,
            )
        )
        self.payment_all.setChecked(all_enabled)
        self._syncing_all = False

    def _sync_all_checkbox(self, _checked: bool):
        if self._syncing_all:
            return
        self._syncing_all = True
        all_enabled = all(
            box.isChecked()
            for box in (
                self.payment_cash,
                self.payment_qris_dana,
                self.payment_qris_midtrans,
                self.payment_transfer,
            )
        )
        self.payment_all.setChecked(all_enabled)
        self._syncing_all = False

    def _on_all_toggled(self, checked: bool):
        if self._syncing_all:
            return
        self._syncing_all = True
        self.payment_cash.setChecked(checked)
        self.payment_qris_dana.setChecked(checked)
        self.payment_qris_midtrans.setChecked(checked)
        self.payment_transfer.setChecked(checked)
        self._syncing_all = False

    def _open_payment_wizard(self, label: str):
        method = {
            "QRIS DANA": "QRIS_DANA",
            "QRIS MIDTRANS": "QRIS_MIDTRANS",
            "TF (m BANKING)": "BANK",
        }.get(label)
        if method is None or self.payment_service is None:
            QMessageBox.information(
                self,
                "Wizard Pembayaran",
                f"Pengaturan detail {label} akan diatur melalui Wizard.\n"
                "Wizard belum tersedia dan akan menyusul.",
            )
            return
        self._open_wizard(method)

    def _open_wizard(self, method: str):
        from app.services.payment_wizard_service import PaymentWizardService
        from app.ui.views.payment_wizard_view import PaymentWizardDialog

        service = PaymentWizardService(self.payment_service.session)
        dialog = PaymentWizardDialog(method, self.actor, service, self)
        dialog.exec()
        self._refresh_payment_status_labels()

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
        for checkbox in (
            self.payment_cash,
            self.payment_qris_dana,
            self.payment_qris_midtrans,
            self.payment_transfer,
            self.payment_all,
        ):
            checkbox.setEnabled(editing)
        for setting_button in self._payment_setting_buttons:
            setting_button.setEnabled(editing)
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
        self._save_payment_settings()

    def _save_payment_settings(self):
        if self.payment_service is None:
            return
        try:
            self.payment_settings = self.payment_service.save(
                self.actor,
                cash_enabled=self.payment_cash.isChecked(),
                qris_dana_enabled=self.payment_qris_dana.isChecked(),
                qris_midtrans_enabled=self.payment_qris_midtrans.isChecked(),
                transfer_enabled=self.payment_transfer.isChecked(),
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pengaturan pembayaran tidak tersimpan", str(exc))

    def _cancel_edit(self):
        self._load_store()
        self._set_editing(False)
