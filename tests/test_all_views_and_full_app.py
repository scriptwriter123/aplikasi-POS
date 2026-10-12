import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.hardware.printer import ReceiptPrinter
from app.models import (
    Account,
    Category,
    Product,
    Role,
    Store,
    Supplier,
    Unit,
    User,
)
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.financial_service import FinancialService
from app.services.license_service import LicenseService
from app.services.owner_setup_service import OwnerSetupService
from app.services.store_settings_service import StoreSettingsService
from app.services.user_management_service import UserManagementService
from app.ui.main_window import MainWindow
from app.ui.views.cashier_view import CashierView
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.financial_view import FinancialView
from app.ui.views.license_view import LicenseView
from app.ui.views.login_view import LoginView
from app.ui.views.master_data_view import MasterDataView
from app.ui.views.purchase_view import PurchaseView
from app.ui.views.report_view import ReportView
from app.ui.views.store_settings_view import StoreSettingsView
from app.ui.views.supplier_view import SupplierView
from app.ui.views.user_management_view import UserManagementView


@pytest.fixture
def qt_application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def full_app_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            # Seed basic roles
            roles = {}
            for role_name in ("OWNER", "ADMIN", "SUPERVISOR", "CASHIER"):
                r = Role(name=role_name, description=f"Role {role_name}")
                session.add(r)
                roles[role_name] = r
            session.flush()

            # Seed Store
            store = Store(code="MAIN", name="Toko Super Mart", slogan="Murah Lengkap")
            session.add(store)

            # Seed Users
            owner = User(
                username="owner",
                full_name="Owner Toko",
                password_hash=hash_password("owner123"),
                role=roles["OWNER"],
            )
            cashier = User(
                username="kasir1",
                full_name="Kasir Utama",
                password_hash=hash_password("kasir123"),
                role=roles["CASHIER"],
            )
            session.add_all([owner, cashier])
            session.flush()

            # Seed Accounts
            accounts = [
                Account(code="1000", name="Kas", account_type="ASSET", is_active=True, is_system=True),
                Account(code="1010", name="Bank", account_type="ASSET", is_active=True, is_system=True),
                Account(code="1200", name="Persediaan", account_type="ASSET", is_active=True, is_system=True),
                Account(code="2000", name="Hutang Usaha", account_type="LIABILITY", is_active=True, is_system=True),
                Account(code="3000", name="Modal Pemilik", account_type="EQUITY", is_active=True, is_system=True),
                Account(code="3100", name="Saldo Awal", account_type="EQUITY", is_active=True, is_system=True),
                Account(code="4000", name="Penjualan", account_type="REVENUE", is_active=True, is_system=True),
                Account(code="5000", name="HPP", account_type="EXPENSE", is_active=True, is_system=True),
                Account(code="6000", name="Beban Listrik", account_type="EXPENSE", is_active=True, is_system=False),
            ]
            session.add_all(accounts)
            session.flush()

            # Initialize Financial Service
            fin_service = FinancialService(session)
            cash_acc = next(a for a in accounts if a.code == "1000")
            fin_service.initialize(
                owner,
                date.today(),
                {cash_acc.id: 5_000_000},
            )

            # Seed Category, Unit, Supplier
            cat = Category(name="Makanan")
            unit = Unit(name="Piece", symbol="pcs")
            sup = Supplier(code="SUP-01", name="Pemasok Maju", phone="08123456789")
            session.add_all([cat, unit, sup])
            session.flush()

            # Seed Products
            prod1 = Product(
                sku="SKU-ROTI-01",
                barcode="899123456001",
                name="Roti Tawar",
                category_id=cat.id,
                unit_id=unit.id,
                supplier_id=sup.id,
                purchase_price=8_000,
                selling_price=12_000,
                stock_qty=50,
                min_stock=5,
            )
            prod2 = Product(
                sku="SKU-SUSU-01",
                barcode="899123456002",
                name="Susu Cokelat",
                category_id=cat.id,
                unit_id=unit.id,
                supplier_id=sup.id,
                purchase_price=5_000,
                selling_price=8_000,
                stock_qty=30,
                min_stock=5,
            )
            session.add_all([prod1, prod2])
            session.commit()

            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_full_owner_navigation_and_all_views(qt_application: QApplication, full_app_session: Session):
    owner = full_app_session.query(User).filter_by(username="owner").one()
    user_mgmt = UserManagementService(full_app_session, UserRepository(full_app_session))
    
    window = MainWindow(owner, user_mgmt)
    window.show()
    assert isinstance(window.stack.currentWidget(), DashboardView)
    assert "Toko Super Mart" in window.windowTitle()

    # 1. Dashboard -> User Management View
    window.show_user_management()
    assert isinstance(window.stack.currentWidget(), UserManagementView)
    window.user_management_view.refresh_users()
    assert window.user_management_view.user_table.rowCount() >= 2

    # 2. Dashboard -> Sales Report View
    window.show_sales_report()
    assert isinstance(window.stack.currentWidget(), ReportView)
    assert window.sales_report_view.report_type == "sales"
    window.sales_report_view.refresh_report()

    # 3. Dashboard -> Financial Report View
    window.show_financial_report()
    assert isinstance(window.stack.currentWidget(), FinancialView)
    assert window.financial_view.service.is_initialized()

    # 4. Dashboard -> Master Data View
    window.show_master_data()
    assert isinstance(window.stack.currentWidget(), MasterDataView)
    window.master_data_view.refresh_products()
    assert window.master_data_view.product_table.rowCount() >= 2

    # 5. Dashboard -> Store Settings View
    window.show_store_settings()
    assert isinstance(window.stack.currentWidget(), StoreSettingsView)
    assert window.store_settings_view.name_input.text() == "Toko Super Mart"

    # 6. Dashboard -> Suppliers View
    window.show_suppliers()
    assert isinstance(window.stack.currentWidget(), SupplierView)
    assert window.supplier_view.supplier_table.rowCount() >= 1

    # 7. Dashboard -> Purchases View
    window.show_purchases()
    assert isinstance(window.stack.currentWidget(), PurchaseView)
    assert window.purchase_view.product_input.count() >= 2

    # Return to Dashboard
    window.show_dashboard()
    assert isinstance(window.stack.currentWidget(), DashboardView)
    window.close()


def test_full_cashier_flow_and_checkout(qt_application: QApplication, full_app_session: Session, tmp_path: Path):
    cashier = full_app_session.query(User).filter_by(username="kasir1").one()
    cashier_view = CashierView(cashier, full_app_session)
    cashier_view.show()

    # 1. Open Shift
    cashier_view.shift_service.open_shift(cashier, opening_cash=100_000)
    cashier_view._refresh_shift_status()
    assert cashier_view.current_shift is not None
    assert cashier_view.current_shift.status == "OPEN"

    # 2. Search Product
    cashier_view.search_input.setText("Roti")
    cashier_view._search_products()
    assert cashier_view.product_table.rowCount() >= 1

    # 3. Add Product to Cart directly
    prod = full_app_session.query(Product).filter_by(sku="SKU-ROTI-01").one()
    cashier_view._add_product(prod, 2)
    assert prod.id in cashier_view.cart
    assert cashier_view.cart[prod.id]["qty"] == 2
    assert cashier_view.cart_table.rowCount() == 1

    # 4. Modify Cart Qty
    cashier_view._set_cart_quantity(0, 3)
    assert cashier_view.cart[prod.id]["qty"] == 3

    # 5. Checkout with Cash
    sale = cashier_view._save_sale(36_000, "CASH", 50_000)
    assert sale.invoice_no.startswith("POS-")
    assert sale.grand_total == 36_000

    # 6. Verify Receipt Data
    receipt_data = cashier_view._build_receipt_data(sale, "CASH", 50_000, 14_000)
    assert receipt_data["total"] == 36_000
    assert receipt_data["paid"] == 50_000
    assert receipt_data["change"] == 14_000

    # 7. Generate PDF receipt
    printer = ReceiptPrinter()
    pdf_path = printer.save_pdf(receipt_data, tmp_path / "test_struk.pdf")
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0

    # 8. Check stock reduction
    full_app_session.refresh(prod)
    assert prod.stock_qty == 47  # 50 - 3

    # 9. Save Cashier Daily Report
    report = cashier_view.daily_reports.save(cashier, date.today(), "Lancar aman")
    assert report.sales_count == 1
    assert report.sales_total == 36_000
    assert report.notes == "Lancar aman"

    cashier_view.close()


def test_license_view_and_service(qt_application: QApplication, tmp_path: Path):
    lic_service = LicenseService(tmp_path, device_id="test-device-id-12345")
    view = LicenseView(lic_service)
    view.show()
    assert view.installation_id_input.text() != ""
    view.close()


def test_login_view_setup_and_branding(qt_application: QApplication, full_app_session: Session):
    repo = UserRepository(full_app_session)
    auth = AuthService(repo)
    setup = OwnerSetupService(full_app_session, repo)
    store = full_app_session.query(Store).first()

    login = LoginView(auth, store, setup_service=setup)
    login.show()
    assert login.store_name_label.text() == "Toko Super Mart"
    assert login.login_panel.isVisible()
    assert not login.setup_panel.isVisible()
    login.close()

