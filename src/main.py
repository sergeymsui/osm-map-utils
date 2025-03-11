import sys
from PySide6.QtWidgets import QApplication
from osm_graphics_view import OSMGraphicsView

if __name__ == "__main__":
    app = QApplication(sys.argv)

    view = OSMGraphicsView(zoom=2)
    view.show()

    sys.exit(app.exec())
