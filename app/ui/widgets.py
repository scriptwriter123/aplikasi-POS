from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton


COPYRIGHT_CAPTION = "ANJAY Solution Software Dev. 2026"
PRIMARY_BUTTON_STYLE = (
    "QPushButton { background: #1d4ed8; color: white; border: none; "
    "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
    "QPushButton:hover { background: #1e40af; }"
)
DASHBOARD_BACK_BUTTON_STYLE = (
    "QPushButton { background: #1d4ed8; color: white; border: none; "
    "border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
    "QPushButton:hover { background: #1e40af; }"
    "QPushButton:pressed { background: #1e3a8a; }"
)


def create_dashboard_back_button(parent=None) -> QPushButton:
    button = QPushButton("Dashboard", parent)
    button.setObjectName("dashboardBackButton")
    pixmap = QPixmap(QSize(20, 20))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(
        QPen(
            QColor("#ffffff"),
            2.2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.drawLine(QPointF(16, 10), QPointF(4, 10))
    painter.drawLine(QPointF(4, 10), QPointF(10, 4))
    painter.drawLine(QPointF(4, 10), QPointF(10, 16))
    painter.end()
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(18, 18))
    button.setStyleSheet(DASHBOARD_BACK_BUTTON_STYLE)
    return button


def create_copyright_label(parent=None) -> QLabel:
    label = QLabel(COPYRIGHT_CAPTION, parent)
    label.setObjectName("copyrightCredit")
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    label.setStyleSheet(
        "color: #1d4ed8; font-size: 10px; font-weight: 600; padding: 3px 8px;"
    )
    return label
