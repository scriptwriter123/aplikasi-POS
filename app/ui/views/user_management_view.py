from PySide6.QtCore import Qt, Signal
from sqlalchemy.exc import SQLAlchemyError
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.user_management_service import UserManagementService
from app.ui.widgets import create_dashboard_back_button


class UserManagementView(QWidget):
    back_requested = Signal()

    def __init__(
        self,
        actor,
        user_management: UserManagementService,
        parent=None,
    ):
        super().__init__(parent)
        self.actor = actor
        self.user_management = user_management

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(16)

        header = QHBoxLayout()
        back_button = create_dashboard_back_button(self)
        back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Manajemen Pengguna")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #172554;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        description = QLabel(
            "Buat akun Admin, Supervisor, atau Kasir. Hanya OWNER yang dapat "
            "menambahkan akun pengguna."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #64748b;")
        root.addWidget(description)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.username_input = QLineEdit()
        self.username_input.setMaxLength(80)
        self.username_input.setPlaceholderText("Contoh: kasir01")
        self.full_name_input = QLineEdit()
        self.full_name_input.setMaxLength(150)
        self.full_name_input.setPlaceholderText("Nama lengkap pegawai")
        self.role_input = QComboBox()
        self.role_input.addItem("Admin", "ADMIN")
        self.role_input.addItem("Supervisor", "SUPERVISOR")
        self.role_input.addItem("Kasir", "CASHIER")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Minimal 8 karakter")
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Username", self.username_input)
        form_layout.addRow("Nama lengkap", self.full_name_input)
        form_layout.addRow("Role", self.role_input)
        form_layout.addRow("Password", self.password_input)
        form_layout.addRow("Ulangi password", self.confirm_password_input)
        root.addLayout(form_layout)

        self.create_button = QPushButton("Tambah Pengguna")
        self.create_button.setStyleSheet(
            "QPushButton { background: #1d4ed8; color: white; border: none; "
            "border-radius: 8px; padding: 10px 16px; font-weight: 600; }"
            "QPushButton:hover { background: #1e40af; }"
        )
        self.create_button.clicked.connect(self._create_user)
        root.addWidget(self.create_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.delete_button = QPushButton("Hapus Pengguna Terpilih")
        self.delete_button.clicked.connect(self._delete_selected_user)
        root.addWidget(self.delete_button, alignment=Qt.AlignmentFlag.AlignLeft)

        root.addWidget(QLabel("Pengguna terdaftar"))
        self.user_table = QTableWidget(0, 3)
        self.user_table.setHorizontalHeaderLabels(["Nama", "Username", "Role"])
        self.user_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.user_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.user_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.user_table, 1)

        self.refresh_users()

    def refresh_users(self):
        users = self.user_management.list_users(self.actor)
        self.user_table.setRowCount(len(users))
        self.user_ids = []
        for row, user in enumerate(users):
            self.user_ids.append(user.id)
            values = (user.full_name, user.username, user.role.name)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.user_table.setItem(row, column, item)
        self.user_table.resizeColumnsToContents()

    def _delete_selected_user(self):
        row = self.user_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih pengguna",
                "Pilih pengguna yang akan dihapus.",
            )
            return
        user_id = self.user_ids[row]
        username = self.user_table.item(row, 1).text()
        answer = QMessageBox.question(
            self,
            "Hapus pengguna",
            f"Akun {username} akan dihapus dan tidak dapat digunakan untuk login. "
            "Riwayat transaksi tetap tersimpan. Lanjutkan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.user_management.delete_user(self.actor, user_id)
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pengguna tidak dapat dihapus", str(exc))
            return
        self.refresh_users()

    def _create_user(self):
        password = self.password_input.text()
        if password != self.confirm_password_input.text():
            QMessageBox.warning(
                self,
                "Password tidak cocok",
                "Password dan konfirmasi password harus sama.",
            )
            return

        try:
            self.user_management.create_user(
                self.actor,
                username=self.username_input.text(),
                full_name=self.full_name_input.text(),
                password=password,
                role_name=self.role_input.currentData(),
            )
        except (AuthorizationError, ValidationError) as exc:
            QMessageBox.warning(self, "Tidak dapat membuat pengguna", str(exc))
            return

        self.username_input.clear()
        self.full_name_input.clear()
        self.password_input.clear()
        self.confirm_password_input.clear()
        self.refresh_users()
        QMessageBox.information(
            self,
            "Pengguna ditambahkan",
            "Akun pengguna berhasil dibuat.",
        )
