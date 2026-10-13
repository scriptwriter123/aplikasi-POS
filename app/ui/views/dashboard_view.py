from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import Store


class DashboardView(QWidget):
    logout_requested = Signal()
    manage_users_requested = Signal()
    sales_report_requested = Signal()
    financial_report_requested = Signal()
    master_data_requested = Signal()
    store_settings_requested = Signal()
    suppliers_requested = Signal()

    def __init__(self, user, parent=None, store: Store | None = None):
        super().__init__(parent)
        role_name = user.role.name.upper()
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 18, 28, 22)
        root.setSpacing(10)

        heading_row = QHBoxLayout()
        heading_row.addStretch(1)
        self.logout_button = QPushButton("Keluar")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.logout_button.setStyleSheet(
            "QPushButton { background: #dc2626; color: white; border: none; "
            "border-radius: 8px; padding: 9px 16px; font-weight: 600; }"
            "QPushButton:hover { background: #ef4444; }"
        )
        heading_row.addWidget(self.logout_button)
        root.addLayout(heading_row)

        self.store_profile = QWidget()
        store_profile_layout = QVBoxLayout(self.store_profile)
        store_profile_layout.setContentsMargins(0, 0, 0, 0)
        store_profile_layout.setSpacing(2)
        self.store_logo_label = QLabel()
        self.store_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_logo_label.setFixedSize(90, 58)
        self.store_name_label = QLabel()
        self.store_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_name_label.setStyleSheet(
            "font-size: 25px; font-weight: 700; color: #89b4fa;"
        )
        self.store_slogan_label = QLabel()
        self.store_slogan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_slogan_label.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #89b4fa;"
        )
        self.store_address_label = QLabel()
        self.store_address_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_address_label.setStyleSheet(
            "font-size: 16px; color: #89b4fa;"
        )
        self.store_whatsapp_label = QLabel()
        self.store_whatsapp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_whatsapp_label.setStyleSheet(
            "font-size: 16px; color: #89b4fa;"
        )
        store_profile_layout.addWidget(
            self.store_logo_label,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        store_profile_layout.addWidget(self.store_name_label)
        store_profile_layout.addWidget(self.store_slogan_label)
        store_profile_layout.addWidget(self.store_address_label)
        store_profile_layout.addWidget(self.store_whatsapp_label)
        root.addWidget(self.store_profile, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.update_store_profile(store)

        welcome_row = QHBoxLayout()
        subtitle = QLabel(f"Selamat datang, {user.full_name}")
        subtitle.setStyleSheet("font-size: 14px; color: #a1a1aa;")
        welcome_row.addWidget(subtitle)
        welcome_row.addStretch(1)

        role_label = QLabel(role_name)
        role_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #89b4fa; "
            "background: #0e2f4a; padding: 4px 8px; border-radius: 8px;"
        )
        role_label.setMaximumWidth(150)
        welcome_row.addWidget(role_label)
        root.addLayout(welcome_row)

        self.menu_grid = QGridLayout()
        self.menu_grid.setSpacing(10)
        root.addLayout(self.menu_grid, 1)

        if role_name == "OWNER":
            self.menu_grid.addWidget(
                self._create_card(
                    "Manajemen Pengguna",
                    "Buat akun Admin, Supervisor, dan Kasir.",
                    "Kelola Pengguna",
                    self.manage_users_requested.emit,
                ),
                0,
                0,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Laporan Penjualan",
                    "Tinjau transaksi berdasarkan hari, bulan, tahun, atau periode khusus.",
                    "Lihat Laporan",
                    self.sales_report_requested.emit,
                ),
                0,
                1,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Laporan Keuangan",
                    "Kelola saldo awal, pengeluaran toko, dan laporan keuangan.",
                    "Lihat Laporan",
                    self.financial_report_requested.emit,
                ),
                0,
                2,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Master Data",
                    "Kelola produk, kategori, barcode, harga, dan stok awal.",
                    "Kelola Data",
                    self.master_data_requested.emit,
                ),
                1,
                0,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Pengaturan",
                    "Atur nama, slogan, alamat, WhatsApp, dan logo toko.",
                    "Pengaturan",
                    self.store_settings_requested.emit,
                ),
                1,
                1,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Belanja dan Supplier",
                    "Catat barang masuk, stok, harga modal, dan status pembayaran; "
                    "kelola data pemasok.",
                    "Catat Belanja",
                    self.suppliers_requested.emit,
                ),
                1,
                2,
            )
        else:
            self.menu_grid.addWidget(
                self._create_card(
                    "Operasional Toko",
                    "Akses modul operasional sesuai peran Anda.",
                    "Buka Operasional",
                    self._show_placeholder,
                ),
                0,
                0,
            )
            self.menu_grid.addWidget(
                self._create_card(
                    "Laporan Penjualan",
                    "Ringkasan transaksi dan stok toko.",
                    "Lihat Laporan",
                    self._show_placeholder,
                ),
                0,
                1,
            )
        for column in range(3 if role_name == "OWNER" else 2):
            self.menu_grid.setColumnStretch(column, 1)

    def _create_card(self, title, description, action, callback):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(
            "QFrame#dashboardCard { background: #1a1a1e; border: 1px solid #2d2d34; "
            "border-radius: 14px; }"
            "QLabel { border: none; background: transparent; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        action_button = QPushButton(action)
        action_button.setStyleSheet(
            "QPushButton { background: #007acc; color: white; border: none; "
            "border-radius: 7px; padding: 7px 10px; font-weight: 600; }"
            "QPushButton:hover { background: #0098ff; }"
        )
        action_button.clicked.connect(callback)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addStretch(1)
        layout.addWidget(action_button, alignment=Qt.AlignmentFlag.AlignLeft)
        card.setMinimumHeight(125)
        return card

    def _show_placeholder(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "Belum tersedia",
            "Modul ini akan dikembangkan pada tahap berikutnya.",
        )

    def update_store_profile(self, store: Store | None) -> None:
        self.store = store
        self.store_name_label.setText(store.name if store else "")
        self.store_slogan_label.setText(
            (store.slogan or "") if store else ""
        )
        self.store_address_label.setText(
            (store.address or "") if store else ""
        )
        self.store_whatsapp_label.setText(
            f"WhatsApp: {store.whatsapp}" if store and store.whatsapp else ""
        )
        self.store_slogan_label.setVisible(bool(store and store.slogan))
        self.store_address_label.setVisible(bool(store and store.address))
        self.store_whatsapp_label.setVisible(bool(store and store.whatsapp))

        self.store_logo_label.clear()
        self.store_logo_label.setVisible(False)
        if store and store.logo_path and Path(store.logo_path).is_file():
            pixmap = QPixmap(store.logo_path)
            if not pixmap.isNull():
                self.store_logo_label.setPixmap(
                    pixmap.scaled(
                        self.store_logo_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.store_logo_label.setVisible(True)
