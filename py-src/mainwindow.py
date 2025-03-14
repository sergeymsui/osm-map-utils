
from PySide6.QtWidgets import QMainWindow
from osm_graphics_view import OSMGraphicsView
from PySide6.QtCore import QSettings, QMargins
from PySide6.QtWidgets import QMessageBox, QGridLayout, QToolBar, QLabel, QWidget, QSizePolicy

class MainWindow (QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("MapView")

        mapGridLayout = QGridLayout()
        mapGridLayout.setSpacing(0)
        mapGridLayout.setHorizontalSpacing(0)
        mapGridLayout.setVerticalSpacing(0)
        mapGridLayout.setContentsMargins(QMargins(0, 0, 0, 0))

        self.setCentralWidget(QWidget())
        self.createToolBar()

        self.centralWidget().setLayout(mapGridLayout)
        self.mapView = OSMGraphicsView(zoom=5)
        mapGridLayout.addWidget(self.mapView)



    def createToolBar(self):
        toolBar = QToolBar()

        self.addToolBar(toolBar)