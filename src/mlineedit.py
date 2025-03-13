from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit


class MLineEdit(QLineEdit):
    onFucus = Signal()
    outFucus = Signal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.onFucus.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.outFucus.emit()
