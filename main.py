import logging

from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import settings
from app.core.database import get_session
from app.core.logging_config import configure_logging
from app.core.migrations import upgrade_database
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.license_service import LicenseService
from app.services.owner_setup_service import OwnerSetupService
from app.services.store_settings_service import StoreSettingsService
from app.services.user_management_service import UserManagementService
from app.ui.main_window import MainWindow
from app.ui.views.license_view import LicenseView
from app.ui.views.login_view import LoginView

logger = logging.getLogger("pos")


class Application:
    def __init__(self):
        configure_logging(debug=settings.app_debug)
        logger.info("Starting POS application")
        self.qt = QApplication([])
        self.qt.setQuitOnLastWindowClosed(True)
        try:
            upgrade_database()
        except Exception as exc:
            logger.exception("Database startup/migration failed")
            error_message = f"Aplikasi tidak dapat menyiapkan database:\n{exc}"
            try:
                log_path = settings.data_dir / "startup-error.log"
                log_path.write_text(
                    f"{type(exc).__name__}: {exc}\n",
                    encoding="utf-8",
                )
                error_message += f"\nDetail tersimpan di:\n{log_path}"
            except OSError as log_error:
                error_message += f"\nLog error: {log_error}"
            QMessageBox.critical(
                None,
                "Database tidak dapat disiapkan",
                error_message,
            )
            raise SystemExit(1) from exc

        logger.info("Database migrations are up to date")
        self.session = get_session()
        self.user_repository = UserRepository(self.session)
        self.auth = AuthService(self.user_repository)
        self.owner_setup = OwnerSetupService(self.session, self.user_repository)
        self.user_management = UserManagementService(
            self.session,
            self.user_repository,
        )
        self.store_settings = StoreSettingsService(self.session)
        self.license_service = LicenseService(settings.data_dir)
        self.login = LoginView(
            self.auth,
            self.store_settings.get_store(),
            setup_service=self.owner_setup,
        )
        self.window = None
        self.license_view = None
        self.login.login_success.connect(self.on_login)
        licensed, status = self.license_service.license_status()
        if licensed:
            logger.info(status)
            self.login.show()
        else:
            logger.info("POS license required: %s", status)
            self.license_view = LicenseView(self.license_service)
            self.license_view.license_activated.connect(
                self.on_license_activated
            )
            self.license_view.show()

    def on_license_activated(self):
        logger.info("POS license activated")
        if self.license_view is not None:
            self.license_view.hide()
            self.license_view.deleteLater()
            self.license_view = None
        self.login.show()

    def on_login(self, user):
        logger.info("Login succeeded")
        self.window = MainWindow(user, self.user_management)
        self.window.logout_requested.connect(self.on_logout)
        self.window.store_branding_changed.connect(
            self.login.update_store_branding
        )
        self.window.show()
        self.login.hide()

    def on_logout(self):
        logger.info("User logged out")
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
            self.window = None
        self.session.rollback()
        self.session.expire_all()
        self.login.reset()
        self.login.show()

    def run(self):
        try:
            return self.qt.exec()
        finally:
            self.session.close()
            logger.info("POS application stopped")


if __name__ == "__main__":
    import logging

    raise SystemExit(Application().run())
