from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import create_dashboard_back_button


class ReportCenterView(QWidget):
    """Jendela "Laporan": tab Penjualan dan Absensi Karyawan.

    Membungkus ReportView (Penjualan) dan AttendanceView (Absensi) yang
    dibangun di luar — instance yang sama tetap dipegang MainWindow
    sehingga akses langsung ke view anak masih berfungsi. Tab Keuangan
    (Modal Awal) dipindahkan ke jendela Manajemen Toko.
    """

    TAB_SALES = 0
    TAB_ATTENDANCE = 1

    back_requested = Signal()

    def __init__(
        self,
        *,
        sales_view: QWidget,
        attendance_view: QWidget,
        parent=None,
    ):
        super().__init__(parent)
        self.sales_view = sales_view
        self.attendance_view = attendance_view

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        self.back_button = create_dashboard_back_button(self)
        self.back_button.clicked.connect(self.back_requested.emit)
        title = QLabel("Laporan")
        title.setStyleSheet("font-size: 25px; font-weight: 700; color: #ffffff;")
        header.addWidget(self.back_button)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        # Header internal tiap view disembunyikan; jendela ini punya
        # judul dan tombol kembali sendiri.
        for view in (sales_view, attendance_view):
            back = getattr(view, "back_button", None)
            if back is not None:
                back.hide()
            heading = getattr(view, "heading_label", None)
            if heading is not None:
                heading.hide()

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #3f3f46; "
            "border-radius: 8px; top: -1px; }"
            "QTabBar::tab { background: transparent; color: #a1a1aa; "
            "padding: 8px 16px; font-weight: 600; "
            "border-bottom: 2px solid transparent; }"
            "QTabBar::tab:selected { color: #007acc; "
            "border-bottom: 2px solid #007acc; }"
        )
        self.tabs.addTab(sales_view, "Penjualan")
        self.tabs.addTab(attendance_view, "Absensi Karyawan")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

    def show_tab(self, name: str) -> None:
        """Pindah ke tab tertentu (selalu me-refresh isinya)."""
        index = next(
            (
                i
                for i in range(self.tabs.count())
                if self.tabs.tabText(i) == name
            ),
            -1,
        )
        if index < 0:
            return
        if self.tabs.currentIndex() == index:
            self._refresh_tab(index)
        else:
            self.tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        self._refresh_tab(index)

    def _refresh_tab(self, index: int) -> None:
        if index == self.TAB_SALES:
            self.sales_view.refresh_report()
        elif index == self.TAB_ATTENDANCE:
            self.attendance_view.refresh()
