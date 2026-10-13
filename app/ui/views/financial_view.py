from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AuthorizationError, ValidationError
from app.hardware.report_exporter import ReportExporter
from app.models import Expense
from app.services.financial_service import FinancialService
from app.ui.widgets import create_dashboard_back_button
from app.utils.formatters import rupiah


class OpeningBalancesDialog(QDialog):
    def __init__(self, service: FinancialService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Aktivasi Pembukuan dan Saldo Awal")
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Masukkan saldo aset, kewajiban, dan modal pada tanggal mulai "
            "pembukuan. Data transaksi sebelum tanggal ini tidak direkonstruksi. "
            "Selisih jurnal dicatat ke akun Saldo Awal."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.effective_date_input = QDateEdit()
        self.effective_date_input.setCalendarPopup(True)
        self.effective_date_input.setDisplayFormat("dd MMMM yyyy")
        self.effective_date_input.setDate(date.today())
        form.addRow("Tanggal mulai pembukuan", self.effective_date_input)
        self.balance_inputs: dict[int, QDoubleSpinBox] = {}
        accounts = [
            account
            for account in service.accounts()
            if account.account_type in {"ASSET", "LIABILITY", "EQUITY"}
            and account.code != "3100"
        ]
        for account in accounts:
            field = QDoubleSpinBox()
            field.setDecimals(0)
            field.setRange(0, 2_000_000_000)
            field.setGroupSeparatorShown(True)
            self.balance_inputs[account.id] = field
            side = "debit" if account.account_type == "ASSET" else "kredit"
            form.addRow(f"{account.code} · {account.name} ({side})", field)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Aktifkan Pembukuan"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def opening_balances(self) -> dict[int, int]:
        return {
            account_id: int(field.value())
            for account_id, field in self.balance_inputs.items()
        }


class ExpenseDialog(QDialog):
    def __init__(self, service: FinancialService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Catat Pengeluaran Toko")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.account_input = QComboBox()
        self.accounts = [
            account
            for account in service.accounts("EXPENSE")
            if account.code != "5000"
        ]
        for account in self.accounts:
            self.account_input.addItem(
                f"{account.code} · {account.name}",
                account.id,
            )
        self.amount_input = self._money_input()
        self.incurred_date_input = QDateEdit()
        self.incurred_date_input.setCalendarPopup(True)
        self.incurred_date_input.setDisplayFormat("dd MMMM yyyy")
        self.incurred_date_input.setDate(date.today())
        self.payee_input = QLineEdit()
        self.payee_input.setPlaceholderText("Nama penerima/vendor")
        self.memo_input = QTextEdit()
        self.memo_input.setMaximumHeight(72)
        self.paid_amount_input = self._money_input()
        self.due_date_input = QDateEdit()
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("dd MMMM yyyy")
        self.due_date_input.setDate(date.today())
        self.payment_account_input = QComboBox()
        self.cash_accounts = [
            account
            for account in service.accounts("ASSET")
            if account.code in {"1000", "1010"}
        ]
        for account in self.cash_accounts:
            self.payment_account_input.addItem(account.name, account.id)
        self.payment_method_input = QComboBox()
        self.payment_method_input.addItem("Tunai", "CASH")
        self.payment_method_input.addItem("Bank/Transfer", "BANK")

        form.addRow("Kategori beban *", self.account_input)
        form.addRow("Tanggal pengeluaran *", self.incurred_date_input)
        form.addRow("Penerima / vendor", self.payee_input)
        form.addRow("Keterangan", self.memo_input)
        form.addRow("Total pengeluaran (Rp) *", self.amount_input)
        form.addRow("Dibayar sekarang (Rp)", self.paid_amount_input)
        form.addRow("Tanggal jatuh tempo", self.due_date_input)
        form.addRow("Bayar dari akun", self.payment_account_input)
        form.addRow("Metode pembayaran", self.payment_method_input)
        layout.addLayout(form)

        help_label = QLabel(
            "Pengeluaran dibukukan pada tanggal pengeluaran. Pembayaran "
            "mencatat arus kas; sisa yang belum dibayar menjadi hutang."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _money_input():
        field = QDoubleSpinBox()
        field.setDecimals(0)
        field.setRange(0, 2_000_000_000)
        field.setGroupSeparatorShown(True)
        field.setSingleStep(10_000)
        return field


class FinancialView(QWidget):
    back_requested = Signal()

    def __init__(
        self,
        actor,
        session,
        exporter: ReportExporter | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.actor = actor
        self.session = session
        self.service = FinancialService(session)
        self.exporter = exporter or ReportExporter()
        self.report_data: dict | None = None
        self.expense_ids: list[int] = []
        self.setWindowTitle("Laporan Keuangan")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(10)
        header = QHBoxLayout()
        back = create_dashboard_back_button(self)
        self.back_button = back
        back.clicked.connect(self.back_requested.emit)
        title = QLabel("Laporan Keuangan")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #ffffff;")
        header.addWidget(back)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        self.setup_status = QLabel()
        self.setup_status.setWordWrap(True)
        self.setup_status.setStyleSheet(
            "color: #fdba74; background: #3a2410; padding: 8px; "
            "border-radius: 6px;"
        )
        root.addWidget(self.setup_status)
        setup_row = QHBoxLayout()
        self.setup_button = QPushButton("Atur Saldo Awal / Aktifkan")
        self.setup_button.clicked.connect(self._setup_finances)
        self.expense_button = QPushButton("Catat Pengeluaran")
        self.expense_button.clicked.connect(self._add_expense)
        self.pay_expense_button = QPushButton("Bayar Pengeluaran")
        self.pay_expense_button.clicked.connect(self._pay_selected_expense)
        setup_row.addWidget(self.setup_button)
        setup_row.addWidget(self.expense_button)
        setup_row.addWidget(self.pay_expense_button)
        setup_row.addStretch(1)
        root.addLayout(setup_row)

        filters = QHBoxLayout()
        self.report_type_input = QComboBox()
        self.report_type_input.addItem("Laba Rugi", "profit_loss")
        self.report_type_input.addItem("Neraca", "balance_sheet")
        self.report_type_input.addItem("Arus Kas", "cash_flow")
        self.report_type_input.addItem("Neraca Saldo", "trial_balance")
        self.report_type_input.addItem("Jurnal Umum", "journal")
        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("dd MMM yyyy")
        self.start_date_input.setDate(date.today().replace(day=1))
        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("dd MMM yyyy")
        self.end_date_input.setDate(date.today())
        self.show_report_button = QPushButton("Tampilkan")
        self.show_report_button.clicked.connect(self.refresh_report)
        filters.addWidget(QLabel("Laporan"))
        filters.addWidget(self.report_type_input)
        filters.addWidget(QLabel("Dari"))
        filters.addWidget(self.start_date_input)
        filters.addWidget(QLabel("Sampai"))
        filters.addWidget(self.end_date_input)
        filters.addWidget(self.show_report_button)
        root.addLayout(filters)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-weight: 700; color: #ffffff; padding: 4px;"
        )
        root.addWidget(self.summary_label)
        self.report_table = QTableWidget(0, 0)
        self.report_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.report_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        root.addWidget(self.report_table, 1)

        self.expense_heading = QLabel("Daftar Pengeluaran")
        self.expense_heading.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #ffffff;"
        )
        root.addWidget(self.expense_heading)
        self.expense_table = QTableWidget(0, 7)
        self.expense_table.setHorizontalHeaderLabels(
            [
                "Tanggal",
                "Kategori",
                "Penerima",
                "Keterangan",
                "Total",
                "Dibayar",
                "Sisa Hutang",
            ]
        )
        self.expense_table.setMaximumHeight(200)
        self.expense_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.expense_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.expense_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        root.addWidget(self.expense_table)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.print_button = QPushButton("Cetak")
        self.print_button.clicked.connect(self._print_report)
        self.save_button = QPushButton("Simpan PDF/DOCX")
        self.save_button.clicked.connect(self._save_report)
        actions.addWidget(self.print_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        self.refresh_view()

    def refresh_view(self):
        try:
            settings = self.service.settings()
            initialized = (
                settings is not None and settings.effective_from is not None
            )
            self.setup_button.setEnabled(not initialized)
            self.expense_button.setEnabled(initialized)
            self.pay_expense_button.setEnabled(initialized)
            if settings is not None and settings.effective_from is not None:
                self.setup_status.setStyleSheet(
                    "color: #86efac; background: #12291b; padding: 8px; "
                    "border-radius: 6px;"
                )
                self.setup_status.setText(
                    "Pembukuan aktif sejak "
                    f"{settings.effective_from.strftime('%d-%m-%Y')}. "
                    "Saldo awal dicatat dalam jurnal pembukaan."
                )
            else:
                self.setup_status.setText(
                    "Pembukuan belum aktif. Atur tanggal mulai dan saldo awal "
                    "sebelum transaksi operasional dicatat."
                )
            self._refresh_expenses()
        except (AuthorizationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Data keuangan gagal dimuat", str(exc))

    def _setup_finances(self):
        dialog = OpeningBalancesDialog(self.service, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.service.initialize(
                self.actor,
                dialog.effective_date_input.date().toPython(),
                dialog.opening_balances(),
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pembukuan gagal diaktifkan", str(exc))
            return
        QMessageBox.information(
            self,
            "Pembukuan diaktifkan",
            "Saldo awal dan tanggal mulai berhasil disimpan.",
        )
        self.refresh_view()
        self.refresh_report()

    def _add_expense(self):
        dialog = ExpenseDialog(self.service, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        initial_payment = int(dialog.paid_amount_input.value())
        try:
            self.service.create_expense(
                self.actor,
                account_id=dialog.account_input.currentData(),
                amount=int(dialog.amount_input.value()),
                incurred_at=datetime.combine(
                    dialog.incurred_date_input.date().toPython(),
                    datetime.min.time(),
                ).astimezone(),
                payee=dialog.payee_input.text(),
                description=dialog.memo_input.toPlainText(),
                due_date=(
                    dialog.due_date_input.date().toPython()
                    if initial_payment < int(dialog.amount_input.value())
                    else None
                ),
                initial_payment=initial_payment,
                payment_account_id=(
                    dialog.payment_account_input.currentData()
                    if initial_payment
                    else None
                ),
                payment_method=dialog.payment_method_input.currentData(),
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pengeluaran gagal disimpan", str(exc))
            return
        self.refresh_view()
        self.refresh_report()

    def _pay_selected_expense(self):
        row = self.expense_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih pengeluaran",
                "Pilih pengeluaran yang masih memiliki hutang.",
            )
            return
        expense_id = self.expense_ids[row]
        expense = self.session.get(Expense, expense_id)
        if expense is None:
            self.refresh_view()
            return
        outstanding = expense.amount - expense.paid_amount
        if outstanding <= 0:
            QMessageBox.information(
                self,
                "Tidak ada hutang",
                "Pengeluaran ini sudah lunas.",
            )
            return
        amount, accepted = QInputDialog.getInt(
            self,
            "Bayar Pengeluaran",
            f"Sisa hutang: {rupiah(outstanding)}\nNominal pembayaran:",
            outstanding,
            1,
            outstanding,
        )
        if not accepted:
            return
        accounts = [
            account
            for account in self.service.accounts("ASSET")
            if account.code in {"1000", "1010"}
        ]
        if not accounts:
            QMessageBox.warning(self, "Akun Kas/Bank tidak tersedia", "Periksa daftar akun.")
            return
        labels = [account.name for account in accounts]
        selected, accepted = QInputDialog.getItem(
            self,
            "Pilih akun pembayaran",
            "Bayar dari:",
            labels,
            0,
            False,
        )
        if not accepted:
            return
        account = accounts[labels.index(selected)]
        try:
            self.service.record_expense_payment(
                self.actor,
                expense_id,
                amount,
                account.id,
                "CASH" if account.code == "1000" else "BANK",
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Pembayaran gagal dicatat", str(exc))
            return
        self.refresh_view()
        self.refresh_report()

    def _refresh_expenses(self):
        expenses = self.service.list_expenses(self.actor)
        self.expense_ids = [expense.id for expense in expenses]
        self.expense_table.setRowCount(len(expenses))
        for row, expense in enumerate(expenses):
            values = (
                expense.incurred_at.astimezone().strftime("%d-%m-%Y"),
                expense.category,
                expense.payee or "-",
                expense.description or "-",
                rupiah(expense.amount),
                rupiah(expense.paid_amount),
                rupiah(expense.amount - expense.paid_amount),
            )
            for column, value in enumerate(values):
                self.expense_table.setItem(row, column, QTableWidgetItem(value))
        self.expense_table.resizeColumnsToContents()

    def refresh_report(self):
        try:
            start = self.start_date_input.date().toPython()
            end = self.end_date_input.date().toPython()
            result = self.service.financial_report(
                self.report_type_input.currentData(),
                start,
                end,
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            self.report_data = None
            self.report_table.setRowCount(0)
            self.summary_label.setText(str(exc))
            self.print_button.setEnabled(False)
            self.save_button.setEnabled(False)
            return
        self.report_table.setColumnCount(len(result["headers"]))
        self.report_table.setHorizontalHeaderLabels(result["headers"])
        self.report_table.setRowCount(len(result["rows"]))
        for row_index, row in enumerate(result["rows"]):
            for column_index, value in enumerate(row):
                header = result["headers"][column_index].casefold()
                if isinstance(value, int) and any(
                    token in header
                    for token in ("saldo", "debit", "kredit", "kas masuk", "kas keluar")
                ):
                    value = rupiah(value)
                self.report_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(str(value)),
                )
        self.report_table.resizeColumnsToContents()
        self.summary_label.setText(self._formatted_summary(result))
        period = f"{start:%d-%m-%Y} s.d. {end:%d-%m-%Y}"
        self.report_data = {
            "title": result["title"],
            "period": period,
            "generated_at": datetime.now().astimezone().strftime(
                "%d-%m-%Y %H:%M:%S"
            ),
            "summary": self.summary_label.text(),
            "headers": result["headers"],
            "rows": [
                [
                    rupiah(value)
                    if isinstance(value, int)
                    and any(
                        token in result["headers"][column].casefold()
                        for token in (
                            "saldo",
                            "debit",
                            "kredit",
                            "kas masuk",
                            "kas keluar",
                        )
                    )
                    else str(value)
                    for column, value in enumerate(row)
                ]
                for row in result["rows"]
            ],
        }
        self.print_button.setEnabled(True)
        self.save_button.setEnabled(True)

    @staticmethod
    def _formatted_summary(result: dict) -> str:
        if "net_income" in result:
            return (
                f"Pendapatan: {rupiah(result['total_revenue'])}  |  "
                f"Beban: {rupiah(result['total_expenses'])}  |  "
                f"Laba (Rugi) Bersih: {rupiah(result['net_income'])}"
            )
        if "difference" in result:
            return (
                f"Aset: {rupiah(result['assets'])}  |  "
                f"Kewajiban: {rupiah(result['liabilities'])}  |  "
                f"Ekuitas: {rupiah(result['equity'])}  |  "
                f"Selisih: {rupiah(result['difference'])}"
            )
        if "closing_cash" in result:
            return (
                f"Saldo awal: {rupiah(result['opening_cash'])}  |  "
                f"Kas masuk: {rupiah(result['cash_in'])}  |  "
                f"Kas keluar: {rupiah(result['cash_out'])}  |  "
                f"Saldo akhir: {rupiah(result['closing_cash'])}"
            )
        if "debit_total" in result:
            return (
                f"Total debit: {rupiah(result['debit_total'])}  |  "
                f"Total kredit: {rupiah(result['credit_total'])}  |  "
                f"Selisih: {rupiah(result['debit_total'] - result['credit_total'])}"
            )
        return result["summary"]

    def _print_report(self):
        if self.report_data is None:
            return
        try:
            printer = self.exporter.print_report(self.report_data)
        except OSError as exc:
            QMessageBox.warning(self, "Laporan tidak dapat dicetak", str(exc))
            return
        QMessageBox.information(
            self,
            "Laporan dicetak",
            f"Laporan dikirim ke printer {printer}.",
        )

    def _save_report(self):
        if self.report_data is None:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Simpan Laporan Keuangan",
            "laporan_keuangan.pdf",
            "PDF (*.pdf);;Word Document (*.docx)",
        )
        if not path:
            return
        extension = ".pdf" if "PDF" in selected_filter else ".docx"
        output = Path(path)
        if output.suffix.lower() != extension:
            output = output.with_suffix(extension)
        try:
            saved = (
                self.exporter.save_pdf(self.report_data, output)
                if extension == ".pdf"
                else self.exporter.save_docx(self.report_data, output)
            )
        except (ImportError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Laporan gagal disimpan", str(exc))
            return
        QMessageBox.information(
            self,
            "Laporan tersimpan",
            f"Laporan tersimpan di:\n{saved}",
        )
