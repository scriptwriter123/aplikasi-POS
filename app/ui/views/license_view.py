from pathlib import Path

from PySide6.QtCore import Qt, Signal
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

from app.services.license_service import LicenseError, LicenseService
from app.ui.theme import PALETTE
from app.ui.widgets import create_copyright_label


class LicenseView(QWidget):
    license_activated = Signal()

    def __init__(self, license_service: LicenseService, parent=None):
        super().__init__(parent)
        self.setObjectName("licenseRoot")
        self.license_service = license_service
        self.setWindowTitle("Aktivasi Lisensi — POS Retail")
        self.resize(620, 390)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 20)
        root.setSpacing(14)

        heading = QLabel("Aktivasi Lisensi POS Retail")
        heading.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {PALETTE['text']};"
        )
        root.addWidget(heading)

        description = QLabel(
            "Lisensi POS Retail diterbitkan untuk satu instalasi komputer. "
            "Simpan permintaan lisensi lalu kirimkan kepada penerbit. "
            "Setelah menerima file lisensi, pilih file tersebut untuk "
            "mengaktifkan POS. Aktivasi dan penggunaan POS dapat dilakukan "
            "tanpa koneksi internet."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.store_name_input = QLineEdit()
        self.store_name_input.setMaxLength(150)
        self.store_name_input.setPlaceholderText("Nama toko")
        self.installation_id_input = QLineEdit(
            self.license_service.installation_id()
        )
        self.installation_id_input.setReadOnly(True)
        form.addRow("Nama toko", self.store_name_input)
        form.addRow("ID instalasi", self.installation_id_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        request_button = QPushButton("Simpan Permintaan Lisensi")
        request_button.clicked.connect(self._save_request)
        import_button = QPushButton("Pilih File Lisensi")
        import_button.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['accent']}; color: white; border: none; "
            f"border-radius: 8px; padding: 10px 16px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {PALETTE['accent_hover']}; }}"
        )
        import_button.clicked.connect(self._import_license)
        actions.addWidget(request_button)
        actions.addWidget(import_button)
        root.addLayout(actions)
        root.addStretch(1)
        root.addWidget(
            create_copyright_label(self),
            alignment=Qt.AlignmentFlag.AlignRight,
        )

    def _save_request(self) -> None:
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Permintaan Lisensi",
            "permintaan-lisensi.posreq",
            "Permintaan lisensi (*.posreq)",
        )
        if not output_path:
            return
        try:
            self.license_service.create_request(
                self.store_name_input.text(),
                Path(output_path),
            )
        except (LicenseError, OSError) as exc:
            QMessageBox.warning(self, "Permintaan gagal disimpan", str(exc))
            return
        QMessageBox.information(
            self,
            "Permintaan tersimpan",
            "Kirim file permintaan tersebut kepada penerbit lisensi. "
            "Setelah menerima file lisensi, impor melalui jendela ini.",
        )

    def _import_license(self) -> None:
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih File Lisensi",
            "",
            "Lisensi POS Retail (*.poslic)",
        )
        if not source_path:
            return
        try:
            store_name = self.license_service.activate(Path(source_path))
        except (LicenseError, OSError) as exc:
            QMessageBox.warning(self, "Lisensi tidak valid", str(exc))
            return
        QMessageBox.information(
            self,
            "POS berhasil diaktifkan",
            f"Lisensi untuk {store_name} berhasil diaktifkan.",
        )
        self.license_activated.emit()
