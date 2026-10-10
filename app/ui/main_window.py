from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from app.models import Store
from app.services.store_settings_service import StoreSettingsService
from app.services.user_management_service import UserManagementService
from app.ui.views.cashier_view import CashierView
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.financial_view import FinancialView
from app.ui.views.master_data_view import MasterDataView
from app.ui.views.purchase_view import PurchaseView
from app.ui.views.report_view import ReportView
from app.ui.views.store_settings_view import StoreSettingsView
from app.ui.views.supplier_view import SupplierView
from app.ui.views.user_management_view import UserManagementView
from app.ui.widgets import create_copyright_label


class MainWindow(QMainWindow):
    logout_requested = Signal()
    store_branding_changed = Signal(object)

    def __init__(
        self,
        user,
        user_management: UserManagementService,
        parent=None,
    ):
        super().__init__(parent)
        self.user = user
        self.user_management = user_management
        self.store_settings = StoreSettingsService(self.user_management.session)
        self.store: Store | None = self.store_settings.get_store()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.statusBar().addPermanentWidget(create_copyright_label(self))
        self.resize(1100, 700)
        self.stack.currentChanged.connect(self._update_window_branding)

        role = user.role.name.upper()
        if role in {"ADMIN", "SUPERVISOR", "CASHIER"}:
            self.dashboard = None
            cashier_view = CashierView(user, self.user_management.session)
            cashier_view.logout_requested.connect(self.logout_requested.emit)
            self.stack.addWidget(cashier_view)
            self._update_window_branding(0)
            return
        if role != "OWNER":
            raise ValueError(f"Role pengguna tidak dikenali: {role}")

        self.dashboard = DashboardView(user, store=self.store)
        self.dashboard.logout_requested.connect(self.logout_requested.emit)
        self.stack.addWidget(self.dashboard)
        if role == "OWNER":
            self.dashboard.manage_users_requested.connect(
                self.show_user_management
            )
            self.user_management_view = UserManagementView(
                user,
                self.user_management,
            )
            self.user_management_view.back_requested.connect(
                self.show_dashboard
            )
            self.stack.addWidget(self.user_management_view)
            self.sales_report_view = ReportView(
                self.user_management.session,
                "sales",
            )
            self.sales_report_view.back_requested.connect(self.show_dashboard)
            self.stack.addWidget(self.sales_report_view)
            self.financial_view = FinancialView(
                user,
                self.user_management.session,
            )
            self.financial_view.back_requested.connect(self.show_dashboard)
            self.stack.addWidget(self.financial_view)
            self.master_data_view = MasterDataView(
                user,
                self.user_management.session,
            )
            self.master_data_view.back_requested.connect(self.show_dashboard)
            self.stack.addWidget(self.master_data_view)
            self.store_settings_view = StoreSettingsView(
                user,
                self.store_settings,
            )
            self.store_settings_view.back_requested.connect(self.show_dashboard)
            self.store_settings_view.settings_saved.connect(
                self._store_settings_saved
            )
            self.stack.addWidget(self.store_settings_view)
            self.supplier_view = SupplierView(
                user,
                self.user_management.session,
            )
            self.supplier_view.back_requested.connect(self.show_dashboard)
            self.stack.addWidget(self.supplier_view)
            self.purchase_view = PurchaseView(
                user,
                self.user_management.session,
            )
            self.purchase_view.back_requested.connect(self.show_dashboard)
            self.stack.addWidget(self.purchase_view)
            self.dashboard.sales_report_requested.connect(
                self.show_sales_report
            )
            self.dashboard.financial_report_requested.connect(
                self.show_financial_report
            )
            self.dashboard.master_data_requested.connect(self.show_master_data)
            self.dashboard.store_settings_requested.connect(
                self.show_store_settings
            )
            self.dashboard.suppliers_requested.connect(self.show_purchases)
            self.supplier_view.purchases_requested.connect(
                self.show_purchases
            )
            self.purchase_view.suppliers_requested.connect(self.show_suppliers)
            self._update_window_branding(self.stack.currentIndex())

    def closeEvent(self, event: QCloseEvent) -> None:
        self.logout_requested.emit()
        event.accept()

    def show_user_management(self):
        if self.user.role.name.upper() != "OWNER":
            return
        self.user_management_view.refresh_users()
        self.stack.setCurrentWidget(self.user_management_view)

    def show_dashboard(self):
        if self.dashboard is not None:
            self.stack.setCurrentWidget(self.dashboard)

    def show_sales_report(self):
        if self.user.role.name.upper() == "OWNER":
            self.sales_report_view.refresh_report()
            self.stack.setCurrentWidget(self.sales_report_view)

    def show_financial_report(self):
        if self.user.role.name.upper() == "OWNER":
            self.financial_view.refresh_view()
            self.financial_view.refresh_report()
            self.stack.setCurrentWidget(self.financial_view)

    def show_master_data(self):
        if self.user.role.name.upper() == "OWNER":
            self.master_data_view.refresh_products()
            self.stack.setCurrentWidget(self.master_data_view)

    def show_store_settings(self):
        if self.user.role.name.upper() == "OWNER":
            self.store_settings_view.reload_settings()
            self.stack.setCurrentWidget(self.store_settings_view)

    def show_suppliers(self):
        if self.user.role.name.upper() == "OWNER":
            self.supplier_view.refresh_suppliers()
            self.stack.setCurrentWidget(self.supplier_view)

    def show_purchases(self):
        if self.user.role.name.upper() == "OWNER":
            self.purchase_view.refresh_data()
            self.stack.setCurrentWidget(self.purchase_view)

    def _store_settings_saved(self, store: Store):
        self.store = store
        self.dashboard.update_store_profile(store)
        self._update_window_branding(self.stack.currentIndex())
        self.store_branding_changed.emit(store)

    def _update_window_branding(self, page_index: int):
        widget = self.stack.widget(page_index)
        page_title = "Penjualan Harian"
        if self.dashboard is not None:
            page_titles = {
                self.dashboard: "Dashboard",
                getattr(self, "user_management_view", None): "Manajemen Pengguna",
                getattr(self, "sales_report_view", None): "Laporan Penjualan",
                getattr(self, "financial_view", None): "Laporan Keuangan",
                getattr(self, "master_data_view", None): "Master Data",
                getattr(self, "store_settings_view", None): "Pengaturan Toko",
                getattr(self, "supplier_view", None): "Data Supplier",
                getattr(self, "purchase_view", None): "Belanja dan Supplier",
            }
            page_title = page_titles.get(widget, "POS Retail")

        store_name = self.store.name if self.store else "POS Retail"
        self.setWindowTitle(f"{store_name} — {page_title}")
        logo_path = self.store.logo_path if self.store else None
        if logo_path:
            icon = QIcon(logo_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
                return
        self.setWindowIcon(QIcon())
