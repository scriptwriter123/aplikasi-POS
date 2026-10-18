from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.financial_service import FinancialService
from app.services.purchase_service import PurchaseService
from app.services.report_service import ReportService
from app.ui.widgets import TableSearchBar
from app.utils.formatters import rupiah

_STATUS_STYLES = {
    "muted": "color: #a1a1aa;",
    "warn": "color: #fdba74;",
    "ok": "color: #86efac;",
    "error": "color: #fca5a5;",
}


class _ReportTab(QWidget):
    """Dasar tab laporan: label status, ringkasan, dan tabel hasil query."""

    SEARCH_PLACEHOLDER = "Cari data..."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 26, 32, 30)
        self.root.setSpacing(12)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(_STATUS_STYLES["muted"])
        self.root.addWidget(self.status_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #ffffff;"
        )
        self.root.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.search_bar = TableSearchBar(self.table, self.SEARCH_PLACEHOLDER)
        self.root.addWidget(self.search_bar)
        self.root.addWidget(self.table, 1)

    def _set_status(self, kind: str, text: str) -> None:
        self.status_label.setStyleSheet(_STATUS_STYLES[kind])
        self.status_label.setText(text)

    def _set_headers(self, headers: list[str]) -> None:
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)

    def _fill_rows(self, rows: list[tuple]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                self.table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )


class IncomeReportView(_ReportTab):
    """Tab "Pendapatan": rekap penjualan per harian/bulanan/tahunan."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.report_service = ReportService(session)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Tampilan data"))
        self.period_mode = QComboBox()
        self.period_mode.addItem("Harian", "day")
        self.period_mode.addItem("Bulanan", "month")
        self.period_mode.addItem("Tahunan", "year")
        self.period_mode.setFixedWidth(220)
        controls.addWidget(self.period_mode)
        controls.addStretch(1)
        self.root.insertLayout(0, controls)

        self.period_mode.currentIndexChanged.connect(self.refresh_report)
        self.refresh_report()

    def refresh_report(self) -> None:
        try:
            summaries = self.report_service.sales_summary(
                self.period_mode.currentData()
            )
        except (ValueError, SQLAlchemyError) as exc:
            self._set_headers(["Periode", "Transaksi", "Pendapatan (Rp)"])
            self.summary_label.setText("")
            self._set_status("error", f"Gagal memuat pendapatan: {exc}")
            return
        self._set_headers(["Periode", "Transaksi", "Pendapatan (Rp)"])
        self._fill_rows(
            [
                (row["period"], row["transactions"], rupiah(row["revenue"]))
                for row in summaries
            ]
        )
        if summaries:
            transactions = sum(row["transactions"] for row in summaries)
            revenue = sum(row["revenue"] for row in summaries)
            self._set_status("muted", "")
            self.summary_label.setText(
                f"Total pendapatan {rupiah(revenue)} dari "
                f"{transactions} transaksi."
            )
        else:
            self.summary_label.setText("")
            self._set_status(
                "muted", "Belum ada penjualan untuk ditampilkan."
            )


class CashExpenseReportView(_ReportTab):
    """Tab "Pengeluaran": seluruh pengeluaran kas berstatus Tunai."""

    _HEADERS = [
        "Tanggal",
        "Kategori",
        "Penerima",
        "Keterangan",
        "Total (Rp)",
    ]

    def __init__(self, session, actor, parent=None):
        super().__init__(parent)
        self.financial_service = FinancialService(session)
        self.actor = actor
        self.refresh_report()

    def refresh_report(self) -> None:
        try:
            expenses = [
                expense
                for expense in self.financial_service.list_expenses(
                    self.actor
                )
                if expense.payment_status == "CASH"
            ]
        except (
            AuthorizationError,
            ValidationError,
            SQLAlchemyError,
        ) as exc:
            self._set_headers(self._HEADERS)
            self.summary_label.setText("")
            self._set_status("error", f"Gagal memuat pengeluaran: {exc}")
            return
        self._set_headers(self._HEADERS)
        self._fill_rows(
            [
                (
                    expense.incurred_at.astimezone().strftime("%d-%m-%Y"),
                    expense.category,
                    expense.payee or "-",
                    expense.description or "-",
                    rupiah(expense.amount),
                )
                for expense in expenses
            ]
        )
        if expenses:
            total = sum(expense.amount for expense in expenses)
            self._set_status("muted", "")
            self.summary_label.setText(
                f"Total pengeluaran tunai {rupiah(total)} dari "
                f"{len(expenses)} pengeluaran."
            )
        else:
            self.summary_label.setText("")
            self._set_status(
                "muted",
                "Belum ada pengeluaran kas berstatus Tunai.",
            )


class DebtReportView(_ReportTab):
    """Tab "Jumlah Hutang": sisa hutang pengeluaran & pembelian."""

    _HEADERS = [
        "Jenis",
        "Tanggal",
        "Sumber",
        "Keterangan",
        "Total (Rp)",
        "Dibayar (Rp)",
        "Sisa (Rp)",
        "Jatuh Tempo",
    ]

    def __init__(self, session, actor, parent=None):
        super().__init__(parent)
        self.financial_service = FinancialService(session)
        self.purchase_service = PurchaseService(session)
        self.actor = actor
        self.refresh_report()

    def refresh_report(self) -> None:
        try:
            expenses = [
                expense
                for expense in self.financial_service.list_expenses(
                    self.actor
                )
                if expense.payment_status in {"HUTANG", "DP"}
            ]
            purchases = [
                item
                for item in self.purchase_service.list_purchases(self.actor)
                if item["purchase"].payment_status in {"TEMPO", "DP"}
            ]
        except (
            AuthorizationError,
            ValidationError,
            SQLAlchemyError,
        ) as exc:
            self._set_headers(self._HEADERS)
            self.summary_label.setText("")
            self._set_status("error", f"Gagal memuat hutang: {exc}")
            return
        self._set_headers(self._HEADERS)
        rows = []
        for expense in expenses:
            rows.append(
                (
                    "Pengeluaran",
                    expense.incurred_at.astimezone().strftime("%d-%m-%Y"),
                    expense.payee or expense.category,
                    expense.description or "-",
                    rupiah(expense.amount),
                    rupiah(expense.paid_amount),
                    rupiah(expense.amount - expense.paid_amount),
                    expense.due_date.strftime("%d-%m-%Y")
                    if expense.due_date
                    else "-",
                )
            )
        for item in purchases:
            purchase = item["purchase"]
            rows.append(
                (
                    "Pembelian",
                    purchase.ordered_at.astimezone().strftime("%d-%m-%Y"),
                    item["supplier_name"],
                    purchase.order_no,
                    rupiah(purchase.subtotal),
                    rupiah(purchase.paid_amount),
                    rupiah(purchase.subtotal - purchase.paid_amount),
                    purchase.due_date.strftime("%d-%m-%Y")
                    if purchase.due_date
                    else "-",
                )
            )
        self._fill_rows(rows)
        if rows:
            total_sisa = sum(
                expense.amount - expense.paid_amount for expense in expenses
            ) + sum(
                item["purchase"].subtotal - item["purchase"].paid_amount
                for item in purchases
            )
            self._set_status("muted", "")
            self.summary_label.setText(
                f"Total hutang berjalan {rupiah(total_sisa)} dari "
                f"{len(rows)} tagihan."
            )
        else:
            self.summary_label.setText("")
            self._set_status("muted", "Tidak ada hutang berjalan.")


class InventoryValueView(_ReportTab):
    """Tab "Nilai Inventaris": stok x harga beli tiap barang."""

    SEARCH_PLACEHOLDER = "Cari barang..."
    _HEADERS = [
        "SKU",
        "Nama Barang",
        "Stok",
        "Harga Beli (Rp)",
        "Nilai (Rp)",
    ]

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.report_service = ReportService(session)
        self.refresh_report()

    def refresh_report(self) -> None:
        try:
            items = self.report_service.inventory_valuation()
        except SQLAlchemyError as exc:
            self._set_headers(self._HEADERS)
            self.summary_label.setText("")
            self._set_status(
                "error", f"Gagal memuat nilai inventaris: {exc}"
            )
            return
        self._set_headers(self._HEADERS)
        self._fill_rows(
            [
                (
                    item["sku"],
                    item["name"],
                    item["stock_qty"],
                    rupiah(item["purchase_price"]),
                    rupiah(item["value"]),
                )
                for item in items
            ]
        )
        if items:
            total = sum(item["value"] for item in items)
            self._set_status("muted", "")
            self.summary_label.setText(
                f"Total nilai inventaris {rupiah(total)} dari "
                f"{len(items)} barang."
            )
        else:
            self.summary_label.setText("")
            self._set_status("muted", "Belum ada barang di inventaris.")


class LowStockReportView(_ReportTab):
    """Tab "Stok Tipis": barang habis atau stoknya di bawah batas."""

    SEARCH_PLACEHOLDER = "Cari barang..."
    _HEADERS = [
        "SKU",
        "Nama Barang",
        "Stok",
        "Stok Minimum",
        "Status",
        "Nilai Stok (Rp)",
    ]
    _THRESHOLD = 5

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.report_service = ReportService(session)
        self.refresh_report()

    def refresh_report(self) -> None:
        try:
            products = self.report_service.low_stock_products(
                threshold=self._THRESHOLD
            )
        except SQLAlchemyError as exc:
            self._set_headers(self._HEADERS)
            self.summary_label.setText("")
            self._set_status("error", f"Gagal memuat stok tipis: {exc}")
            return
        self._set_headers(self._HEADERS)
        self._fill_rows(
            [
                (
                    product.sku,
                    product.name,
                    product.stock_qty,
                    product.min_stock,
                    "HABIS" if product.stock_qty == 0 else "RENDAH",
                    rupiah(product.stock_qty * product.purchase_price),
                )
                for product in sorted(
                    products,
                    key=lambda item: (item.stock_qty, item.sku),
                )
            ]
        )
        if products:
            habis = sum(1 for p in products if p.stock_qty == 0)
            nilai = sum(p.stock_qty * p.purchase_price for p in products)
            self._set_status("muted", "")
            self.summary_label.setText(
                f"{len(products)} barang stok tipis "
                f"({habis} habis, {len(products) - habis} menipis); "
                f"nilai stok tersisa {rupiah(nilai)}."
            )
        else:
            self.summary_label.setText("")
            self._set_status(
                "muted",
                f"Tidak ada barang aktif dengan stok di bawah "
                f"{self._THRESHOLD}.",
            )


class _StatementPane(QWidget):
    """Satu pernyataan keuangan: ringkasan + tabel standar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #a1a1aa;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

    def clear(self) -> None:
        self.summary_label.setText("")
        self.table.setRowCount(0)

    def load(self, report: dict) -> None:
        headers = list(report["headers"])
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        rows = list(report["rows"])
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                if isinstance(value, int) and not isinstance(value, bool):
                    value = rupiah(value) if column >= 2 else str(value)
                self.table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self.summary_label.setText(str(report.get("summary", "")))


class FinancialStatementView(QWidget):
    """Tab "Laporan Keuangan": laporan standar perusahaan.

    Berisi Laba Rugi, Neraca, Arus Kas, dan Neraca Saldo untuk periode
    yang dipilih (default: sejak tanggal aktivasi pembukuan).
    """

    STATEMENTS = [
        ("profit_loss", "Laba Rugi"),
        ("balance_sheet", "Neraca"),
        ("cash_flow", "Arus Kas"),
        ("trial_balance", "Neraca Saldo"),
    ]

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.financial_service = FinancialService(session)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(12)

        period = QHBoxLayout()
        period.addWidget(QLabel("Dari"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd MMMM yyyy")
        self.start_date.setDate(date.today())
        period.addWidget(self.start_date)
        period.addWidget(QLabel("Sampai"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd MMMM yyyy")
        self.end_date.setDate(date.today())
        period.addWidget(self.end_date)
        period.addStretch(1)
        root.addLayout(period)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(_STATUS_STYLES["muted"])
        root.addWidget(self.status_label)

        self.tabs = QTabWidget()
        self.panes: dict[str, _StatementPane] = {}
        for key, label in self.STATEMENTS:
            pane = _StatementPane()
            self.panes[key] = pane
            self.tabs.addTab(pane, label)
        root.addWidget(self.tabs, 1)

        settings = self.financial_service.settings()
        if settings is not None and settings.effective_from is not None:
            self.start_date.setDate(settings.effective_from)

        self.start_date.dateChanged.connect(self.refresh_report)
        self.end_date.dateChanged.connect(self.refresh_report)
        self.refresh_report()

    def refresh_report(self) -> None:
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        try:
            for key, _label in self.STATEMENTS:
                self.panes[key].load(
                    self.financial_service.financial_report(key, start, end)
                )
            self.status_label.setStyleSheet(_STATUS_STYLES["muted"])
            self.status_label.setText("")
        except (ValidationError, SQLAlchemyError) as exc:
            for pane in self.panes.values():
                pane.clear()
            self.status_label.setStyleSheet(_STATUS_STYLES["warn"])
            self.status_label.setText(str(exc))


class ProgressReportView(QWidget):
    """Tab "Progress": placeholder — isi laporan menyusul."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        label = QLabel(
            "Laporan Progress belum tersedia — isi laporan akan menyusul."
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #a1a1aa; font-size: 15px;")
        root.addStretch(1)
        root.addWidget(label)
        root.addStretch(1)

    def refresh_report(self) -> None:
        return
