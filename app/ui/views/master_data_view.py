from pathlib import Path
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AuthorizationError, ValidationError
from app.models import Product
from app.services.bulk_pricing_service import BulkPricingService
from app.services.master_data_service import MasterDataService
from app.services.product_import_service import (
    PRODUCT_HEADERS,
    ProductImportError,
    ProductImportService,
)
from app.utils.formatters import rupiah
from app.ui.widgets import create_copyright_label, create_dashboard_back_button


class FileDropFrame(QFrame):
    file_dropped = Signal(str)

    def __init__(self, hint: str, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #94a3b8; border-radius: 8px; "
            "background: #f8fafc; }"
        )
        layout = QVBoxLayout(self)
        label = QLabel(hint)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #475569; border: none;")
        layout.addWidget(label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()
            return
        event.ignore()


class ProductFileImportDialog(QDialog):
    def __init__(self, mode: str, service: ProductImportService, actor, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.service = service
        self.actor = actor
        titles = {
            "excel": "Import Produk dari Excel",
            "csv": "Import Produk dari CSV",
            "database": "Import Produk dari Database",
        }
        self.setWindowTitle(titles[mode])
        self.setMinimumSize(720, 480)

        layout = QVBoxLayout(self)
        descriptions = {
            "excel": (
                "Pilih file .xlsx dengan kolom sesuai template. SKU yang sudah "
                "ada akan memperbarui informasi produk, tetapi stok tetap."
            ),
            "csv": (
                "Pilih file .csv UTF-8 dengan kolom sesuai template Excel. SKU "
                "yang sudah ada akan diperbarui tanpa mengubah stok."
            ),
            "database": (
                "Pilih file database SQLite POS (.db, .sqlite, .sqlite3). "
                "Kategori, produk, dan satuan yang diperlukan produk akan "
                "digabungkan; transaksi dan pengguna tidak diimpor."
            ),
        }
        description = QLabel(descriptions[mode])
        description.setWordWrap(True)
        layout.addWidget(description)

        self.drop_frame = FileDropFrame("Tarik dan lepas file di sini", self)
        self.drop_frame.setMinimumHeight(72)
        self.drop_frame.file_dropped.connect(self._set_file)
        layout.addWidget(self.drop_frame)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setReadOnly(True)
        self.file_input.setPlaceholderText("Pilih file untuk melihat pratinjau")
        file_row.addWidget(self.file_input, 1)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_button)
        layout.addLayout(file_row)

        self.preview_table = QTableWidget(0, len(PRODUCT_HEADERS))
        self.preview_table.setHorizontalHeaderLabels(list(PRODUCT_HEADERS))
        self.preview_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.preview_table.setAlternatingRowColors(True)
        layout.addWidget(self.preview_table, 1)
        self.status_label = QLabel("Pilih file untuk menampilkan pratinjau.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.import_button = QPushButton("Import")
        self.import_button.setStyleSheet(
            "QPushButton { background: #15803d; color: white; border: none; "
            "border-radius: 8px; padding: 9px 16px; font-weight: 600; }"
        )
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import_file)
        self.cancel_button = QPushButton("Tutup")
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.import_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

    def _browse_file(self):
        filters = {
            "excel": "Excel Workbook (*.xlsx)",
            "csv": "CSV (*.csv)",
            "database": "SQLite Database (*.db *.sqlite *.sqlite3)",
        }
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih File",
            "",
            filters[self.mode],
        )
        if path:
            self._set_file(path)

    def _set_file(self, file_path: str):
        self.file_input.setText(file_path)
        try:
            if self.mode == "database":
                records = self.service.preview_database(file_path)
            else:
                records = self.service.preview(file_path)
        except (OSError, ProductImportError, ValueError) as exc:
            self.preview_table.setRowCount(0)
            self.status_label.setText(str(exc))
            self.import_button.setEnabled(False)
            return
        self.preview_table.setRowCount(min(len(records), 100))
        for row_index, record in enumerate(records[:100]):
            for column_index, header in enumerate(PRODUCT_HEADERS):
                self.preview_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(str(record.get(header, "") or "")),
                )
        self.preview_table.resizeColumnsToContents()
        self.status_label.setText(
            f"{len(records)} baris siap dipratinjau"
            + (" (maksimal 100 baris ditampilkan)." if len(records) > 100 else ".")
        )
        self.import_button.setEnabled(bool(records))

    def _import_file(self):
        file_path = self.file_input.text()
        if not file_path:
            return
        try:
            result = (
                self.service.import_database(self.actor, file_path)
                if self.mode == "database"
                else self.service.import_file(self.actor, file_path)
            )
        except (ProductImportError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Import gagal", str(exc))
            return
        if result["errors"]:
            QMessageBox.warning(
                self,
                "Data import tidak valid",
                "\n".join(result["errors"][:20]),
            )
            return
        QMessageBox.information(
            self,
            "Import selesai",
            f"Produk baru: {result['created']}\n"
            f"Produk diperbarui: {result['updated']}\n"
            "Stok produk yang sudah ada tidak diubah.",
        )
        self.accept()


class EditExcelDialog(QDialog):
    def __init__(self, service: ProductImportService, actor, parent=None):
        super().__init__(parent)
        self.service = service
        self.actor = actor
        self.setWindowTitle("Edit Produk dengan Excel")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Ekspor data produk ke template Excel, edit menggunakan Excel, "
            "lalu pilih file yang sudah diedit untuk mengimpor perubahan. "
            "Kolom stok hanya digunakan untuk produk baru."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        export_row = QHBoxLayout()
        self.export_path_input = QLineEdit()
        self.export_path_input.setPlaceholderText("Lokasi template .xlsx")
        export_row.addWidget(self.export_path_input, 1)
        export_browse = QPushButton("Lokasi...")
        export_browse.clicked.connect(self._browse_export_path)
        export_row.addWidget(export_browse)
        layout.addLayout(export_row)
        self.export_button = QPushButton("Ekspor Template")
        self.export_button.clicked.connect(self._export_template)
        layout.addWidget(self.export_button)

        self.edited_file_input = QLineEdit()
        self.edited_file_input.setReadOnly(True)
        self.edited_file_input.setPlaceholderText("Pilih file Excel hasil edit")
        layout.addWidget(self.edited_file_input)
        choose_edited = QPushButton("Pilih File Excel Hasil Edit...")
        choose_edited.clicked.connect(self._browse_edited_file)
        layout.addWidget(choose_edited)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.import_button = QPushButton("Import Perubahan")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import_edited_file)
        self.close_button = QPushButton("Tutup")
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.import_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

    def _browse_export_path(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Template Produk",
            "produk.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if path:
            output = Path(path)
            if output.suffix.casefold() != ".xlsx":
                output = output.with_suffix(".xlsx")
            self.export_path_input.setText(str(output))

    def _export_template(self):
        path = self.export_path_input.text().strip()
        if not path:
            self._browse_export_path()
            path = self.export_path_input.text().strip()
        if not path:
            return
        try:
            saved_path = self.service.export_template(path)
        except (OSError, SQLAlchemyError, ValueError) as exc:
            QMessageBox.warning(self, "Template gagal diekspor", str(exc))
            return
        QMessageBox.information(
            self,
            "Template diekspor",
            f"Template tersimpan di:\n{saved_path}",
        )

    def _browse_edited_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Excel Hasil Edit",
            "",
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        self.edited_file_input.setText(path)
        self.import_button.setEnabled(True)

    def _import_edited_file(self):
        path = self.edited_file_input.text()
        if not path:
            return
        try:
            result = self.service.import_file(self.actor, path)
        except (ProductImportError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Import gagal", str(exc))
            return
        if result["errors"]:
            QMessageBox.warning(
                self,
                "Data import tidak valid",
                "\n".join(result["errors"][:20]),
            )
            return
        QMessageBox.information(
            self,
            "Import selesai",
            f"Produk baru: {result['created']}\n"
            f"Produk diperbarui: {result['updated']}\n"
            "Stok produk yang sudah ada tidak diubah.",
        )
        self.accept()


class BulkPriceDialog(QDialog):
    def __init__(
        self,
        service: BulkPricingService,
        actor,
        products,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self.actor = actor
        self.products = products
        self.setWindowTitle("Harga Spesial Partai")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product_input = QComboBox()
        for product in products:
            self.product_input.addItem(
                f"{product.name} ({product.sku})",
                product.id,
            )
        self.product_input.currentIndexChanged.connect(self._load_rule)
        form.addRow("Produk", self.product_input)

        self.quantity_threshold_input = QSpinBox()
        self.quantity_threshold_input.setRange(1, 2_000_000_000)
        self.quantity_threshold_input.setValue(1)
        self.quantity_threshold_input.valueChanged.connect(
            self._update_discount_display
        )
        form.addRow("Batas jumlah barang", self.quantity_threshold_input)

        quantity_hint = QLabel(
            "Harga spesial berlaku saat qty yang dibeli sama dengan atau "
            "lebih besar dari batas ini."
        )
        quantity_hint.setWordWrap(True)
        form.addRow("", quantity_hint)

        self.regular_price_label = QLabel("-")
        self.regular_price_label.setStyleSheet(
            "font-weight: 600; color: #334155;"
        )
        form.addRow("Harga satuan saat ini", self.regular_price_label)

        self._syncing_price_inputs = False
        self.pricing_mode = "PERCENT"
        self.special_price_input = QDoubleSpinBox()
        self.special_price_input.setDecimals(0)
        self.special_price_input.setRange(0, 2_000_000_000)
        self.special_price_input.setGroupSeparatorShown(True)
        self.special_price_input.valueChanged.connect(
            self._manual_price_changed
        )
        form.addRow("Harga spesial per satuan", self.special_price_input)

        self.discount_input = QDoubleSpinBox()
        self.discount_input.setDecimals(2)
        self.discount_input.setRange(0.01, 100)
        self.discount_input.setSingleStep(1)
        self.discount_input.setSuffix("%")
        self.discount_input.valueChanged.connect(self._discount_percent_changed)
        form.addRow("Potongan harga", self.discount_input)

        price_hint = QLabel(
            "Isi harga spesial atau persentase potongan; nilai di kolom "
            "lain akan dihitung otomatis."
        )
        price_hint.setWordWrap(True)
        price_hint.setStyleSheet("color: #64748b;")
        form.addRow("", price_hint)
        layout.addLayout(form)

        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Produk", "Berlaku qty >=", "Diskon", "Harga Spesial"]
        )
        self.rules_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.rules_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.rules_table.cellClicked.connect(self._select_rule_from_table)
        self.rules_table.setToolTip(
            "Klik produk pada tabel untuk memilih dan mengubah aturannya."
        )
        self.rules_table.setMaximumHeight(180)
        layout.addWidget(self.rules_table)

        actions = QHBoxLayout()
        self.delete_button = QPushButton("Hapus Harga Spesial")
        self.delete_button.clicked.connect(self._delete_rule)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        self.save_button = QPushButton("Simpan")
        self.save_button.setStyleSheet(
            "QPushButton { background: #1d4ed8; color: white; border: none; "
            "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
        )
        self.save_button.clicked.connect(self._save_rule)
        close_button = QPushButton("Tutup")
        close_button.clicked.connect(self.reject)
        actions.addWidget(self.save_button)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self._refresh_rules()
        self._load_rule()

    def _selected_product(self):
        product_id = self.product_input.currentData()
        return next(
            (product for product in self.products if product.id == product_id),
            None,
        )

    def _update_special_price(self, *_args):
        product = self._selected_product()
        if product is None:
            self.regular_price_label.setText("-")
            return
        self.regular_price_label.setText(rupiah(product.selling_price))
        self._syncing_price_inputs = True
        self.special_price_input.setValue(
            self.service.special_price(
                product.selling_price,
                Decimal(str(self.discount_input.value())),
            )
        )
        self._syncing_price_inputs = False

    def _update_discount_display(self, *_args):
        if self.pricing_mode == "PERCENT":
            self._update_special_price()

    def _manual_price_changed(self, value: float):
        if self._syncing_price_inputs:
            return
        product = self._selected_product()
        if product is None or product.selling_price <= 0:
            return
        self.pricing_mode = "PRICE"
        percent = self.service.discount_percent_for_price(
            product.selling_price,
            int(value),
        )
        if percent > 0:
            self._syncing_price_inputs = True
            self.discount_input.setValue(float(percent))
            self._syncing_price_inputs = False

    def _discount_percent_changed(self, value: float):
        if self._syncing_price_inputs:
            return
        self.pricing_mode = "PERCENT"
        self._update_special_price()

    def _load_rule(self, *_args):
        product = self._selected_product()
        if product is None:
            self.delete_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self._update_special_price()
            return
        self.save_button.setEnabled(True)
        try:
            rule = self.service.rule_for_product(product.id)
        except SQLAlchemyError as exc:
            QMessageBox.warning(self, "Harga spesial gagal dimuat", str(exc))
            return
        self.delete_button.setEnabled(rule is not None)
        self.regular_price_label.setText(rupiah(product.selling_price))
        self._syncing_price_inputs = True
        if rule is not None:
            self.quantity_threshold_input.setValue(rule.quantity_threshold)
            self.pricing_mode = rule.pricing_mode
            if rule.pricing_mode == "PRICE":
                self.special_price_input.setValue(rule.special_price)
                if product.selling_price > 0:
                    percent = self.service.discount_percent_for_price(
                        product.selling_price,
                        rule.special_price,
                    )
                    self.discount_input.setValue(float(percent))
            else:
                self.discount_input.setValue(float(rule.discount_percent))
                self.special_price_input.setValue(
                    self.service.special_price(
                        product.selling_price,
                        rule.discount_percent,
                    )
                )
        else:
            self.quantity_threshold_input.setValue(1)
            self.discount_input.setValue(1)
            self.pricing_mode = "PERCENT"
            self.special_price_input.setValue(
                self.service.special_price(
                    product.selling_price,
                    Decimal("1"),
                )
            )
        self._syncing_price_inputs = False

    def _refresh_rules(self):
        try:
            rules = self.service.rules()
        except SQLAlchemyError as exc:
            QMessageBox.warning(self, "Harga spesial gagal dimuat", str(exc))
            return
        self.rules_table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            product = rule.product
            values = (
                f"{product.name} ({product.sku})",
                str(rule.quantity_threshold),
                f"{rule.discount_percent}%",
                rupiah(self.service.effective_special_price(product, rule)),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, product.id)
                    item.setToolTip("Klik untuk memilih produk ini.")
                self.rules_table.setItem(row, column, item)
        self.rules_table.resizeColumnsToContents()

    def _select_rule_from_table(self, row: int, _column: int):
        product_item = self.rules_table.item(row, 0)
        if product_item is None:
            return
        product_id = product_item.data(Qt.ItemDataRole.UserRole)
        index = self.product_input.findData(product_id)
        if index >= 0:
            self.product_input.setCurrentIndex(index)

    def _save_rule(self):
        product = self._selected_product()
        if product is None:
            return
        try:
            self.service.save_rule(
                actor=self.actor,
                product_id=product.id,
                quantity_threshold=self.quantity_threshold_input.value(),
                discount_percent=Decimal(str(self.discount_input.value())),
                special_price=int(self.special_price_input.value()),
                pricing_mode=self.pricing_mode,
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Harga spesial gagal disimpan", str(exc))
            return
        self._refresh_rules()
        self.delete_button.setEnabled(True)
        QMessageBox.information(
            self,
            "Harga spesial tersimpan",
            f"Harga {product.name} berlaku untuk qty minimal "
            f"{self.quantity_threshold_input.value()}.",
        )

    def _delete_rule(self):
        product = self._selected_product()
        if product is None:
            return
        try:
            deleted = self.service.delete_rule(self.actor, product.id)
        except (AuthorizationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Harga spesial gagal dihapus", str(exc))
            return
        if deleted:
            self._refresh_rules()
            self.delete_button.setEnabled(False)
            QMessageBox.information(
                self,
                "Harga spesial dihapus",
                f"Aturan harga spesial {product.name} sudah dihapus.",
            )


class CategoryBatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Kategori")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.category_inputs = []
        for index in range(1, 6):
            category_input = QLineEdit()
            category_input.setMaxLength(100)
            category_input.setPlaceholderText(f"Nama kategori {index}")
            self.category_inputs.append(category_input)
            form.addRow(f"Kategori {index}", category_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        layout.addWidget(
            create_copyright_label(self),
            alignment=Qt.AlignmentFlag.AlignRight,
        )

    def category_names(self) -> list[str]:
        return [field.text().strip() for field in self.category_inputs]

    def _validate_and_accept(self):
        if not any(self.category_names()):
            QMessageBox.warning(
                self,
                "Kategori belum diisi",
                "Isi minimal satu nama kategori.",
            )
            return
        self.accept()


class ProductFormDialog(QDialog):
    def __init__(
        self,
        categories,
        units,
        suppliers,
        product: Product | None = None,
        bulk_pricing_service: BulkPricingService | None = None,
        bulk_rule=None,
        parent=None,
    ):
        super().__init__(parent)
        self.product = product
        self.bulk_pricing_service = bulk_pricing_service
        self.bulk_rule = bulk_rule
        self.setWindowTitle("Ubah Produk" if product else "Tambah Produk")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sku_input = self._new_line_edit("SKU unik, contoh SKU-001")
        self.barcode_input = self._new_line_edit("Scan atau ketik barcode (opsional)")
        self.name_input = self._new_line_edit("Nama produk")
        self.category_input = QComboBox()
        self.category_input.addItem("Pilih kategori", None)
        for category in categories:
            self.category_input.addItem(category.name, category.id)
        self.unit_input = QComboBox()
        self.unit_input.addItem("Pilih satuan", None)
        for unit in units:
            self.unit_input.addItem(f"{unit.name} ({unit.symbol})", unit.id)
        self.supplier_input = QComboBox()
        self.supplier_input.addItem("Tidak ditentukan", None)
        for supplier in suppliers:
            self.supplier_input.addItem(
                f"{supplier.name} ({supplier.code})",
                supplier.id,
            )

        self.purchase_price = self._money_input()
        self.selling_price = self._money_input()
        self.stock_qty = QSpinBox()
        self.stock_qty.setRange(0, 2_000_000_000)
        self.min_stock = QSpinBox()
        self.min_stock.setRange(0, 2_000_000_000)
        self.active_checkbox = QCheckBox("Aktif dan dapat dicari kasir")
        self.active_checkbox.setChecked(True)

        form.addRow("SKU *", self.sku_input)
        form.addRow("Barcode", self.barcode_input)
        form.addRow("Nama produk *", self.name_input)
        form.addRow("Kategori *", self.category_input)
        form.addRow("Satuan *", self.unit_input)
        form.addRow("Supplier pilihan", self.supplier_input)
        form.addRow("Harga modal (Rp) *", self.purchase_price)
        form.addRow("Harga jual (Rp) *", self.selling_price)
        form.addRow("Stok awal", self.stock_qty)
        form.addRow("Batas minimum stok", self.min_stock)
        form.addRow("", self.active_checkbox)
        layout.addLayout(form)

        bulk_group = QGroupBox("Harga Spesial Partai (opsional)")
        bulk_form = QFormLayout(bulk_group)
        self.bulk_enabled_input = QCheckBox("Aktifkan harga spesial partai")
        bulk_form.addRow("", self.bulk_enabled_input)
        self.bulk_flow_label = QLabel()
        self.bulk_flow_label.setWordWrap(True)
        self.bulk_flow_label.setStyleSheet(
            "color: #1e3a8a; background: #eff6ff; padding: 8px; "
            "border-radius: 6px;"
        )
        bulk_form.addRow("Alur harga", self.bulk_flow_label)
        self.bulk_threshold_input = QSpinBox()
        self.bulk_threshold_input.setRange(1, 2_000_000_000)
        self.bulk_threshold_input.setValue(1)
        bulk_form.addRow("Berlaku mulai qty (≥)", self.bulk_threshold_input)
        self.bulk_regular_price_label = QLabel()
        self.bulk_regular_price_label.setStyleSheet(
            "font-weight: 600; color: #334155;"
        )
        bulk_form.addRow("Harga satuan normal", self.bulk_regular_price_label)
        self.bulk_pricing_mode = "PERCENT"
        self.bulk_special_price_input = self._money_input()
        bulk_form.addRow(
            "Harga spesial per satuan",
            self.bulk_special_price_input,
        )
        self.bulk_discount_input = QDoubleSpinBox()
        self.bulk_discount_input.setDecimals(2)
        self.bulk_discount_input.setRange(0.01, 100)
        self.bulk_discount_input.setSingleStep(1)
        self.bulk_discount_input.setSuffix("%")
        bulk_form.addRow("Potongan harga", self.bulk_discount_input)
        bulk_help = QLabel(
            "Isi harga spesial atau persentase potongan. Nilai lainnya "
            "dihitung otomatis dari harga jual normal."
        )
        bulk_help.setWordWrap(True)
        bulk_help.setStyleSheet("color: #64748b;")
        bulk_form.addRow("", bulk_help)
        self.bulk_enabled_input.toggled.connect(
            self._set_bulk_inputs_enabled
        )
        self.bulk_special_price_input.valueChanged.connect(
            self._bulk_price_changed
        )
        self.bulk_discount_input.valueChanged.connect(
            self._bulk_discount_changed
        )
        self.selling_price.valueChanged.connect(self._update_bulk_price_reference)
        layout.addWidget(bulk_group)

        note = QLabel(
            "Stok awal hanya diisi saat produk baru dibuat. Perubahan stok "
            "produk yang sudah ada dilakukan lewat transaksi stok agar tercatat."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #64748b;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        layout.addWidget(
            create_copyright_label(self),
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        if product is not None:
            self.sku_input.setText(product.sku)
            self.barcode_input.setText(product.barcode or "")
            self.name_input.setText(product.name)
            self._select_data(self.category_input, product.category_id)
            self._select_data(self.unit_input, product.unit_id)
            self._select_data(self.supplier_input, product.supplier_id)
            self.purchase_price.setValue(product.purchase_price)
            self.selling_price.setValue(product.selling_price)
            self.stock_qty.setValue(product.stock_qty)
            self.stock_qty.setEnabled(False)
            self.min_stock.setValue(product.min_stock)
            self.active_checkbox.setChecked(product.is_active)
        self._load_bulk_rule()

    def _validate_and_accept(self):
        if not self.sku_input.text().strip():
            QMessageBox.warning(self, "SKU wajib", "Isi SKU produk.")
            self.sku_input.setFocus()
            return
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Nama wajib", "Isi nama produk.")
            self.name_input.setFocus()
            return
        if self.category_input.currentData() is None:
            QMessageBox.warning(self, "Kategori wajib", "Pilih kategori produk.")
            self.category_input.setFocus()
            return
        if self.unit_input.currentData() is None:
            QMessageBox.warning(self, "Satuan wajib", "Pilih satuan produk.")
            self.unit_input.setFocus()
            return
        if self.bulk_enabled_input.isChecked():
            regular_price = int(self.selling_price.value())
            special_price = int(self.bulk_special_price_input.value())
            if regular_price <= 0:
                QMessageBox.warning(
                    self,
                    "Harga jual belum valid",
                    "Isi harga jual lebih dari Rp 0 sebelum mengaktifkan "
                    "harga spesial partai.",
                )
                self.selling_price.setFocus()
                return
            if special_price >= regular_price:
                QMessageBox.warning(
                    self,
                    "Harga spesial belum valid",
                    "Harga spesial harus lebih rendah dari harga jual normal.",
                )
                self.bulk_special_price_input.setFocus()
                return
        self.accept()

    def _load_bulk_rule(self):
        regular_price = int(self.selling_price.value())
        if self.bulk_rule is not None:
            self.bulk_enabled_input.setChecked(True)
            self.bulk_threshold_input.setValue(
                self.bulk_rule.quantity_threshold
            )
            self.bulk_pricing_mode = self.bulk_rule.pricing_mode
            if self.bulk_pricing_mode == "PRICE":
                self.bulk_special_price_input.setValue(
                    self.bulk_rule.special_price
                )
                percent = (
                    self.bulk_pricing_service.discount_percent_for_price(
                        regular_price,
                        self.bulk_rule.special_price,
                    )
                    if regular_price > 0
                    else Decimal("1")
                )
                self.bulk_discount_input.setValue(float(percent))
            else:
                self.bulk_discount_input.setValue(
                    float(self.bulk_rule.discount_percent)
                )
                self.bulk_special_price_input.setValue(
                    self.bulk_pricing_service.special_price(
                        regular_price,
                        self.bulk_rule.discount_percent,
                    )
                )
        else:
            self.bulk_discount_input.setValue(1)
            self._update_bulk_price_reference()
        self._set_bulk_inputs_enabled(self.bulk_enabled_input.isChecked())

    def _set_bulk_inputs_enabled(self, enabled: bool):
        for widget in (
            self.bulk_threshold_input,
            self.bulk_special_price_input,
            self.bulk_discount_input,
        ):
            widget.setEnabled(enabled)
        self._update_bulk_price_reference()

    def _update_bulk_price_reference(self, *_args):
        regular_price = int(self.selling_price.value())
        self.bulk_regular_price_label.setText(rupiah(regular_price))
        self.bulk_flow_label.setText(
            f"Jika qty pembelian ≥ {self.bulk_threshold_input.value()}, "
            "gunakan harga spesial per satuan; jika kurang, gunakan harga "
            f"normal {rupiah(regular_price)}."
        )
        if (
            not self.bulk_enabled_input.isChecked()
            or self._bulk_syncing()
            or self.bulk_pricing_mode != "PERCENT"
        ):
            return
        self.bulk_special_price_input.setValue(
            self._special_price_from_percent(regular_price)
        )

    def _bulk_syncing(self) -> bool:
        return getattr(self, "_syncing_bulk_fields", False)

    def _special_price_from_percent(self, regular_price: int) -> int:
        if self.bulk_pricing_service is None:
            return 0
        return self.bulk_pricing_service.special_price(
            regular_price,
            Decimal(str(self.bulk_discount_input.value())),
        )

    def _bulk_price_changed(self, value: float):
        if self._bulk_syncing() or not self.bulk_enabled_input.isChecked():
            return
        regular_price = int(self.selling_price.value())
        if regular_price <= 0:
            return
        self.bulk_pricing_mode = "PRICE"
        percent = self.bulk_pricing_service.discount_percent_for_price(
            regular_price,
            int(value),
        )
        if percent > 0:
            self._syncing_bulk_fields = True
            self.bulk_discount_input.setValue(float(percent))
            self._syncing_bulk_fields = False

    def _bulk_discount_changed(self, value: float):
        if self._bulk_syncing() or not self.bulk_enabled_input.isChecked():
            return
        self.bulk_pricing_mode = "PERCENT"
        self._update_bulk_price_reference()

    @staticmethod
    def _new_line_edit(placeholder: str) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        return line_edit

    @staticmethod
    def _money_input():
        field = QDoubleSpinBox()
        field.setDecimals(0)
        field.setRange(0, 2_000_000_000)
        field.setGroupSeparatorShown(True)
        field.setSingleStep(500)
        return field

    @staticmethod
    def _select_data(combo: QComboBox, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def form_data(self) -> dict:
        return {
            "product_id": self.product.id if self.product else None,
            "sku": self.sku_input.text(),
            "barcode": self.barcode_input.text(),
            "name": self.name_input.text(),
            "category_id": self.category_input.currentData(),
            "unit_id": self.unit_input.currentData(),
            "supplier_id": self.supplier_input.currentData(),
            "purchase_price": int(self.purchase_price.value()),
            "selling_price": int(self.selling_price.value()),
            "stock_qty": self.stock_qty.value(),
            "min_stock": self.min_stock.value(),
            "is_active": self.active_checkbox.isChecked(),
            "bulk_pricing_enabled": self.bulk_enabled_input.isChecked(),
            "bulk_quantity_threshold": self.bulk_threshold_input.value(),
            "bulk_discount_percent": Decimal(
                str(self.bulk_discount_input.value())
            ),
            "bulk_special_price": int(self.bulk_special_price_input.value()),
            "bulk_pricing_mode": self.bulk_pricing_mode,
        }


class AddStockDialog(QDialog):
    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Stok")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        remaining_capacity = 2_000_000_000 - product.stock_qty
        self.product_name_label = QLabel(product.name)
        self.current_stock_label = QLabel(str(product.stock_qty))
        self.additional_stock_input = QSpinBox()
        self.additional_stock_input.setRange(
            1,
            max(1, remaining_capacity),
        )
        self.additional_stock_input.setValue(1)
        self.additional_stock_input.setEnabled(remaining_capacity > 0)
        form.addRow("Nama produk", self.product_name_label)
        form.addRow("Stok saat ini", self.current_stock_label)
        form.addRow("Stok tambahan", self.additional_stock_input)
        layout.addLayout(form)

        self.confirm_button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button_box.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Tambah Stok")
        self.confirm_button_box.button(
            QDialogButtonBox.StandardButton.Ok
        ).setEnabled(remaining_capacity > 0)
        self.confirm_button_box.accepted.connect(self.accept)
        self.confirm_button_box.rejected.connect(self.reject)
        layout.addWidget(self.confirm_button_box)


class MasterDataView(QWidget):
    back_requested = Signal()

    def __init__(self, actor, session, parent=None):
        super().__init__(parent)
        self.actor = actor
        self.service = MasterDataService(session)
        self.import_service = ProductImportService(session)
        self.bulk_pricing_service = BulkPricingService(session)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 30)
        root.setSpacing(14)

        header = QHBoxLayout()
        back_button = create_dashboard_back_button(self)
        back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Master Data Produk")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #172554;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        description = QLabel(
            "Kelola produk, kategori, harga, barcode, satuan, dan stok awal. "
            "Produk aktif langsung tersedia pada pencarian kasir."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #64748b;")
        root.addWidget(description)

        actions = QHBoxLayout()
        create_button_style = (
            "QPushButton { background: #1d4ed8; color: white; border: none; "
            "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #1e40af; }"
        )
        edit_button_style = (
            "QPushButton { background: #facc15; color: #422006; border: none; "
            "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #eab308; }"
        )
        self.add_category_button = QPushButton("Tambah Kategori")
        self.add_category_button.setStyleSheet(create_button_style)
        self.add_category_button.clicked.connect(self._add_category)
        self.add_product_button = QPushButton("Tambah Produk")
        self.add_product_button.setStyleSheet(create_button_style)
        self.add_product_button.clicked.connect(self._add_product)
        self.bulk_price_button = QPushButton("Harga Spesial")
        self.bulk_price_button.setStyleSheet(create_button_style)
        self.bulk_price_button.clicked.connect(self._open_bulk_price_dialog)
        self.bulk_price_button.setVisible(
            getattr(getattr(actor, "role", None), "name", "").upper() == "OWNER"
        )
        self.import_button = QToolButton()
        self.import_button.setText("Import Data   ▾")
        self.import_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.import_button.setStyleSheet(
            "QToolButton { background: #1d4ed8; color: white; border: none; "
            "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
            "QToolButton:hover { background: #1e40af; }"
            "QToolButton:pressed { background: #1e3a8a; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        import_menu = QMenu(self.import_button)
        import_menu.addAction(
            "Import Excel",
            lambda _checked=False: self._open_import_dialog("excel"),
        )
        import_menu.addAction(
            "Import database",
            lambda _checked=False: self._open_import_dialog("database"),
        )
        import_menu.addAction(
            "Import CSV",
            lambda _checked=False: self._open_import_dialog("csv"),
        )
        import_menu.addAction(
            "Edit Excel",
            lambda _checked=False: self._open_edit_excel_dialog(),
        )
        self.import_button.setMenu(import_menu)
        self.edit_product_button = QPushButton("Ubah Produk")
        self.edit_product_button.setStyleSheet(edit_button_style)
        self.edit_product_button.clicked.connect(self._edit_selected_product)
        self.delete_product_button = QPushButton("Hapus Produk")
        self.delete_product_button.setStyleSheet(edit_button_style)
        self.delete_product_button.clicked.connect(self._delete_selected_product)
        self.add_stock_button = QPushButton("Tambah Stok")
        self.add_stock_button.setStyleSheet(create_button_style)
        self.add_stock_button.clicked.connect(self._add_stock_to_selected_product)
        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.setStyleSheet(edit_button_style)
        self.refresh_button.clicked.connect(self.refresh_products)
        for button in (
            self.add_category_button,
            self.add_product_button,
            self.import_button,
            self.bulk_price_button,
            self.add_stock_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.edit_product_button)
        actions.addWidget(self.delete_product_button)
        root.addLayout(actions)

        self.category_label = QLabel()
        root.addWidget(self.category_label)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Cari berdasarkan nama produk, kategori, atau supplier"
        )
        self.search_input.textChanged.connect(
            lambda _text: self.refresh_products()
        )
        root.addWidget(self.search_input)
        self.product_table = QTableWidget(0, 10)
        self.product_table.setHorizontalHeaderLabels(
            [
                "SKU",
                "Barcode",
                "Nama Produk",
                "Kategori",
                "Satuan",
                "Modal",
                "Harga Jual",
                "Supplier",
                "Stok",
                "Status",
            ]
        )
        self.product_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.product_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.product_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.product_table.horizontalHeader().setStretchLastSection(True)
        self.product_table.doubleClicked.connect(self._edit_selected_product)
        root.addWidget(self.product_table, 1)
        root.addWidget(
            create_copyright_label(self),
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.refresh_products()

    def refresh_products(self):
        try:
            categories = self.service.list_categories()
            units = {unit.id: unit for unit in self.service.list_units()}
            suppliers = {
                supplier.id: supplier
                for supplier in self.service.list_suppliers()
            }
            products = self.service.list_products()
        except SQLAlchemyError as exc:
            QMessageBox.critical(self, "Master data gagal dimuat", str(exc))
            return

        category_names = {category.id: category.name for category in categories}
        self.category_label.setText(
            "Kategori tersedia: "
            + (", ".join(category.name for category in categories) or "belum ada")
        )
        query = self.search_input.text().strip().casefold()
        if query:
            products = [
                product
                for product in products
                if query in product.name.casefold()
                or query in category_names.get(product.category_id, "").casefold()
                or query
                in (
                    suppliers[product.supplier_id].name.casefold()
                    if product.supplier_id in suppliers
                    else ""
                )
            ]
        self.product_table.setRowCount(len(products))
        self.product_ids = []
        for row, product in enumerate(products):
            self.product_ids.append(product.id)
            category = category_names.get(product.category_id, "-")
            unit = units.get(product.unit_id)
            values = (
                product.sku,
                product.barcode or "-",
                product.name,
                category,
                f"{unit.name} ({unit.symbol})" if unit else "-",
                rupiah(product.purchase_price),
                rupiah(product.selling_price),
                suppliers[product.supplier_id].name
                if product.supplier_id in suppliers
                else "-",
                str(product.stock_qty),
                "Aktif" if product.is_active else "Nonaktif",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.product_table.setItem(row, column, item)
            if not product.is_active:
                for column in range(len(values)):
                    self.product_table.item(row, column).setForeground(
                        Qt.GlobalColor.darkGray
                    )
        self.product_table.resizeColumnsToContents()

    def _add_category(self):
        dialog = CategoryBatchDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            categories = self.service.create_categories(
                self.actor,
                dialog.category_names(),
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Kategori tidak dapat disimpan", str(exc))
            return
        QMessageBox.information(
            self,
            "Kategori tersimpan",
            f"{len(categories)} kategori berhasil ditambahkan.",
        )
        self.refresh_products()

    def _add_product(self):
        dialog = self._create_product_dialog()
        if dialog is None:
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_form(dialog)

    def _open_import_dialog(self, mode: str):
        dialog = ProductFileImportDialog(
            mode,
            self.import_service,
            self.actor,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_products()

    def _open_edit_excel_dialog(self):
        dialog = EditExcelDialog(
            self.import_service,
            self.actor,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_products()

    def _open_bulk_price_dialog(self):
        try:
            products = self.service.list_products()
        except SQLAlchemyError as exc:
            QMessageBox.warning(self, "Produk gagal dimuat", str(exc))
            return
        dialog = BulkPriceDialog(
            self.bulk_pricing_service,
            self.actor,
            products,
            self,
        )
        dialog.exec()

    def _edit_selected_product(self, *_args):
        row = self.product_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih produk",
                "Pilih baris produk yang akan diubah.",
            )
            return
        product = self.service.session.get(Product, self.product_ids[row])
        if product is None:
            QMessageBox.warning(self, "Produk tidak ditemukan", "Muat ulang data.")
            self.refresh_products()
            return
        dialog = self._create_product_dialog(product)
        if dialog is None:
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_form(dialog)

    def _delete_selected_product(self):
        row = self.product_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih produk",
                "Pilih produk yang akan dihapus.",
            )
            return
        product_id = self.product_ids[row]
        product_name = self.product_table.item(row, 2).text()
        answer = QMessageBox.question(
            self,
            "Hapus produk",
            f"Produk {product_name} akan dihapus dari data aktif. "
            "Riwayat transaksi tetap tersimpan. Lanjutkan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_product(self.actor, product_id)
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Produk tidak dapat dihapus", str(exc))
            return
        self.refresh_products()

    def _add_stock_to_selected_product(self):
        row = self.product_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih produk",
                "Pilih produk yang akan ditambah stoknya.",
            )
            return

        product = self.service.session.get(Product, self.product_ids[row])
        if product is None or product.deleted_at is not None:
            QMessageBox.warning(
                self,
                "Produk tidak ditemukan",
                "Muat ulang data sebelum menambah stok.",
            )
            self.refresh_products()
            return

        dialog = AddStockDialog(product, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated_product = self.service.add_stock(
                self.actor,
                product.id,
                dialog.additional_stock_input.value(),
            )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Stok tidak dapat ditambahkan", str(exc))
            return
        self.refresh_products()
        QMessageBox.information(
            self,
            "Stok ditambahkan",
            f"Stok {updated_product.name} sekarang "
            f"{updated_product.stock_qty}.",
        )

    def _create_product_dialog(
        self,
        product: Product | None = None,
    ) -> ProductFormDialog | None:
        try:
            return ProductFormDialog(
                self.service.list_categories(),
                self.service.list_units(),
                self.service.list_suppliers(),
                product=product,
                bulk_pricing_service=self.bulk_pricing_service,
                bulk_rule=(
                    self.bulk_pricing_service.rule_for_product(product.id)
                    if product is not None
                    else None
                ),
                parent=self,
            )
        except SQLAlchemyError as exc:
            QMessageBox.critical(self, "Gagal memuat pilihan produk", str(exc))
            return None

    def _save_form(self, dialog: ProductFormDialog):
        values = dialog.form_data()
        bulk_pricing = {
            key: values.pop(key)
            for key in (
                "bulk_pricing_enabled",
                "bulk_quantity_threshold",
                "bulk_discount_percent",
                "bulk_special_price",
                "bulk_pricing_mode",
            )
        }
        if values["category_id"] is None:
            QMessageBox.warning(self, "Kategori wajib", "Pilih kategori produk.")
            return
        if values["unit_id"] is None:
            QMessageBox.warning(self, "Satuan wajib", "Pilih satuan produk.")
            return
        try:
            product = self.service.save_product(self.actor, **values)
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "Produk tidak dapat disimpan", str(exc))
            return
        try:
            if bulk_pricing["bulk_pricing_enabled"]:
                self.bulk_pricing_service.save_rule(
                    actor=self.actor,
                    product_id=product.id,
                    quantity_threshold=bulk_pricing["bulk_quantity_threshold"],
                    discount_percent=bulk_pricing["bulk_discount_percent"],
                    special_price=bulk_pricing["bulk_special_price"],
                    pricing_mode=bulk_pricing["bulk_pricing_mode"],
                )
            else:
                self.bulk_pricing_service.delete_rule(
                    self.actor,
                    product.id,
                )
        except (AuthorizationError, ValidationError, SQLAlchemyError) as exc:
            self.refresh_products()
            QMessageBox.warning(
                self,
                "Produk tersimpan, tetapi aturan harga spesial gagal",
                f"Data produk sudah tersimpan, tetapi aturan harga spesial "
                f"belum diperbarui. Buka kembali produk atau popup Harga "
                f"Spesial untuk memperbaikinya.\n\n{exc}",
            )
            return
        self.refresh_products()
        QMessageBox.information(
            self,
            "Produk tersimpan",
            f"{product.name} ({product.sku}) tersimpan dan dapat dicari kasir "
            "jika statusnya aktif.",
        )
