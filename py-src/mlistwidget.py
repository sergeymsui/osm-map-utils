from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget


class MListWidget(QListWidget):
    outFucus = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.outFucus.emit()
