from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    AuthorizationError,
    LicenseExpiredError,
    ValidationError,
)
from app.models import Account, Product, PurchaseOrder
from app.services.purchase_service import PurchaseService
from app.ui.widgets import create_copyright_label
from app.utils.formatters import rupiah


class PurchaseView(QWidget):
    back_requested = Signal()
    suppliers_requested = Signal()

    def __init__(self, actor, session, parent=None, *, read_only=False):
        super().__init__(parent)
        self.actor = actor
        self.session = session
        self.read_only = bool(read_only)
        self.service = PurchaseService(
            session,
            transaction_locked=self.read_only,
        )
        self.setWindowTitle("Belanja dan Supplier")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(12)

        header = QHBoxLayout()
        self.back_button = QPushButton("← Dashboard")
        self.back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Belanja dan Supplier")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #ffffff;")
        header.addWidget(self.back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        description = QLabel(
            "Catat barang yang sudah diterima. Pembelian Tempo menjadi hutang "
            "sampai jatuh tempo; pembelian Lunas langsung tercatat lunas."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #a1a1aa;")
        root.addWidget(description)

        form = QFormLayout()
        self.supplier_input = QComboBox()
        self.product_input = QComboBox()
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 2_000_000_000)
        self.unit_cost_input = QDoubleSpinBox()
        self.unit_cost_input.setDecimals(0)
        self.unit_cost_input.setRange(0, 2_000_000_000)
        self.unit_cost_input.setGroupSeparatorShown(True)
        self.payment_account_input = QComboBox()
        self.payment_status_input = QComboBox()
        self.payment_status_input.addItem("Lunas", "PAID")
        self.payment_status_input.addItem("Tempo", "TEMPO")
        self.due_date_input = QDateEdit()
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("dd MMMM yyyy")
        self.due_date_input.setDate(date.today())
        self.payment_status_input.currentIndexChanged.connect(
            self._update_due_date_state
        )
        self.product_input.currentIndexChanged.connect(
            self._update_product_cost
        )

        form.addRow("Supplier *", self.supplier_input)
        form.addRow("Produk *", self.product_input)
        form.addRow("Jumlah diterima *", self.quantity_input)
        form.addRow("Harga modal per unit (Rp) *", self.unit_cost_input)
        form.addRow("Pembayaran dari akun", self.payment_account_input)
        form.addRow("Status pembelian *", self.payment_status_input)
        form.addRow("Jatuh tempo *", self.due_date_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.record_button = QPushButton("Simpan Pembelian")
        self.record_button.clicked.connect(self._record_purchase)
        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.clicked.connect(self.refresh_data)
        self.mark_paid_button = QPushButton("Catat Pembayaran")
        self.mark_paid_button.clicked.connect(self._record_selected_payment)
        self.manage_suppliers_button = QPushButton("Kelola Supplier")
        self.manage_suppliers_button.clicked.connect(
            self.suppliers_requested.emit
        )
        actions.addWidget(self.record_button)
        actions.addWidget(self.mark_paid_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.manage_suppliers_button)
        actions.addStretch(1)
        root.addLayout(actions)

        if self.read_only:
            banner = QLabel(
                "MODE BACA-SAJA — pembelian dan pembayaran baru terkunci "
                "karena masa lisensi berakhir."
            )
            banner.setStyleSheet(
                "color: #fef3c7; background: #78350f; border-radius: 8px; "
                "padding: 9px 12px; font-weight: 600;"
            )
            banner.setWordWrap(True)
            root.addWidget(banner)
            self.record_button.setEnabled(False)
            self.mark_paid_button.setEnabled(False)

        self.purchase_table = QTableWidget(0, 8)
        self.purchase_table.setHorizontalHeaderLabels(
            [
                "No. Pembelian",
                "Tanggal",
                "Supplier",
                "Produk",
                "Total",
                "Status",
                "Jatuh Tempo",
                "Sisa Hutang",
            ]
        )
        self.purchase_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.purchase_table.horizontalHeader().setStretchLastSection(True)
        self.purchase_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.purchase_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        root.addWidget(self.purchase_table, 1)
        self.debt_summary = QLabel()
        self.debt_summary.setStyleSheet(
            "font-weight: 700; color: #fdba74; font-size: 14px;"
        )
        root.addWidget(self.debt_summary)
        root.addWidget(
            create_copyright_label(self),
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.refresh_data()

    def refresh_data(self):
        try:
            suppliers = self.service.active_suppliers(self.actor)
            products = self.service.active_products(self.actor)
            purchases = self.service.list_purchases(self.actor)
            payment_accounts = [
                account
                for account in self.service.financial.accounts("ASSET")
                if account.code in {"1000", "1010"}
            ]
        except (AuthorizationError, SQLAlchemyError) as exc:
            QMessageBox.critical(self, "Pembelian gagal dimuat", str(exc))
            return

        self.supplier_input.clear()
        for supplier in suppliers:
            self.supplier_input.addItem(
                f"{supplier.name} ({supplier.code})",
                supplier.id,
            )
        self.product_input.clear()
        for product in products:
            self.product_input.addItem(
                f"{product.name} ({product.sku})",
                product.id,
            )
        self.payment_account_input.clear()
        for account in payment_accounts:
            self.payment_account_input.addItem(
                account.name,
                account.id,
            )
        self._update_product_cost()

        self.purchase_table.setRowCount(len(purchases))
        self.purchase_ids = []
        outstanding = 0
        for row, record in enumerate(purchases):
            purchase = record["purchase"]
            self.purchase_ids.append(purchase.id)
            due = purchase.subtotal - purchase.paid_amount
            if purchase.payment_status == "TEMPO":
                outstanding += due
            values = (
                purchase.order_no,
                purchase.ordered_at.astimezone().strftime("%d-%m-%Y %H:%M")
                if purchase.ordered_at
                else "-",
                record["supplier_name"],
                record["product_name"],
                rupiah(purchase.subtotal),
                (
                    "Lunas"
                    if purchase.payment_status == "PAID"
                    else (
                        "Sebagian dibayar"
                        if purchase.paid_amount
                        else "Tempo"
                    )
                ),
                purchase.due_date.astimezone().strftime("%d-%m-%Y")
                if purchase.due_date
                else "-",
                rupiah(due),
            )
            for column, value in enumerate(values):
                self.purchase_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self.purchase_table.resizeColumnsToContents()
        self.debt_summary.setText(f"Total hutang pembelian Tempo: {rupiah(outstanding)}")
        self._update_due_date_state()

    def _update_product_cost(self, _index: int = -1):
        product_id = self.product_input.currentData()
        if product_id is None:
            self.unit_cost_input.setValue(0)
            self.record_button.setEnabled(False)
            return
        product = self.service.get_product(self.actor, product_id)
        if product is None:
            self.record_button.setEnabled(False)
            return
        self.unit_cost_input.setValue(product.purchase_price)
        supplier_index = self.supplier_input.findData(product.supplier_id)
        if supplier_index >= 0:
            self.supplier_input.setCurrentIndex(supplier_index)
        elif self.supplier_input.count():
            self.supplier_input.setCurrentIndex(0)
        self.record_button.setEnabled(
            bool(self.supplier_input.count()) and not self.read_only
        )

    def _update_due_date_state(self, _index: int = -1):
        self.due_date_input.setEnabled(
            self.payment_status_input.currentData() == "TEMPO"
        )

    def _record_purchase(self):
        supplier_id = self.supplier_input.currentData()
        product_id = self.product_input.currentData()
        if supplier_id is None or product_id is None:
            QMessageBox.warning(
                self,
                "Data belum lengkap",
                "Tambahkan supplier dan produk aktif sebelum mencatat pembelian.",
            )
            return

        payment_status = self.payment_status_input.currentData()
        due_date = (
            self.due_date_input.date().toPython()
            if payment_status == "TEMPO"
            else None
        )
        try:
            purchase = self.service.record_purchase(
                self.actor,
                supplier_id=supplier_id,
                product_id=product_id,
                quantity=self.quantity_input.value(),
                unit_cost=int(self.unit_cost_input.value()),
                payment_status=payment_status,
                due_date=due_date,
                payment_account_id=(
                    self.payment_account_input.currentData()
                    if payment_status == "PAID"
                    else None
                ),
            )
        except (
            AuthorizationError,
            LicenseExpiredError,
            ValidationError,
            SQLAlchemyError,
        ) as exc:
            QMessageBox.warning(self, "Pembelian tidak dapat disimpan", str(exc))
            return

        self.refresh_data()
        QMessageBox.information(
            self,
            "Pembelian tersimpan",
            f"Pembelian {purchase.order_no} tersimpan. "
            f"Total: {rupiah(purchase.subtotal)}",
        )

    def _record_selected_payment(self):
        row = self.purchase_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih pembelian",
                "Pilih transaksi Tempo yang akan ditandai Lunas.",
            )
            return
        purchase_id = self.purchase_ids[row]
        purchase = self.session.get(PurchaseOrder, purchase_id)
        if purchase is None:
            QMessageBox.warning(self, "Pembelian tidak ditemukan", "Muat ulang data.")
            self.refresh_data()
            return
        remaining = purchase.subtotal - purchase.paid_amount
        amount, accepted = QInputDialog.getInt(
            self,
            "Catat Pembayaran Pembelian",
            f"Sisa hutang: {rupiah(remaining)}\nJumlah pembayaran:",
            remaining,
            1,
            remaining,
            1,
        )
        if not accepted:
            return
        payment_account_id = self.payment_account_input.currentData()
        if payment_account_id is None:
            QMessageBox.warning(
                self,
                "Akun pembayaran belum tersedia",
                "Pilih atau siapkan akun Kas/Bank terlebih dahulu.",
            )
            return
        account = self.session.get(Account, payment_account_id)
        try:
            self.service.record_payment(
                self.actor,
                purchase_id,
                amount,
                payment_account_id,
                "CASH" if account.code == "1000" else "BANK",
            )
        except (
            AuthorizationError,
            LicenseExpiredError,
            ValidationError,
            SQLAlchemyError,
        ) as exc:
            QMessageBox.warning(self, "Status pembayaran tidak berubah", str(exc))
            return
        self.refresh_data()
        QMessageBox.information(
            self,
            "Pembelian lunas",
            "Transaksi pembelian ditandai Lunas.",
        )
