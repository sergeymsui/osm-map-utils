
import re
import sys
import redis
import random as rnd

from PIL.ImageQt import QIODevice
from PySide6.QtWidgets import QApplication
from functools import partial, cache
from math import pow
from PySide6.QtCore import Qt, QUrl, QVariantAnimation
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsItemGroup,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QAbstractSocket, QNetworkReply

redis_connection = redis.Redis(host='192.168.141.133', port=6379, db=0)

def check_and_extract_numbers(filename):
    # Template for file name validation
    pattern = r'^(\d+)_(\d+)_(\d+)\_tile$'

    # Checking if the file name matches the pattern
    match = re.match(pattern, filename)

    if match:
        # If it matches, we extract the numbers
        numbers = match.groups()
        return True, [int(v) for v in numbers]
    else:
        # If it doesn't match, return False and an empty list.
        return False, []

class NetworkAccessManagerPool:

    def __init__(self, parent, manager_count = 1):
        self.parent = parent
        self.manager_count = manager_count
        self.network_manager_list = list()

        for _ in range(manager_count):
            network_manager = QNetworkAccessManager(self.parent)
            network_manager.setTransferTimeout(5000)
            self.network_manager_list.append(network_manager)

    def getNetworkManager(self):
        return rnd.choice(self.network_manager_list)


class OSMGraphicsView(QGraphicsView):
    def __init__(self, zoom=2, parent=None):
        super().__init__(parent)
        self.tile_size = 256  # The size of one tile in pixels
        self.zoom = zoom  # Current zoom level
        self.tiles = {}  # Loaded tiles: key (zoom, x, y)
        self.old_tiles_group = None  # Group for scaling animation
        self._zoom_anim = None  # Link to zoom animation

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.updateSceneRect()

        self.network_manager_pool = NetworkAccessManagerPool(self, 5)

        # Rendering settings
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Initial loading of tiles
        self.updateTiles()

    def loadCache(self):
        self.cache = dict()

        for key in redis_connection.keys():
            tile_name = key.decode("utf-8")
            is_valid, numbers = check_and_extract_numbers(tile_name)
            if is_valid:
                data = redis_connection.get(tile_name)
                self.cache[tuple(numbers)] = data

                print(f"The tile {tuple(numbers)} is loaded into cache ")
            else:
                print(f"Can't open load tile: {tile_name}")

    def updateSceneRect(self):
        """Updates the scene dimensions depending on the zoom level"""
        size = self.tile_size * (2**self.zoom)
        self.scene.setSceneRect(0, 0, size, size)

    def updateTiles(self):
        """Determines which tiles fall within the visible area and starts loading them"""
        rect = self.mapToScene(self.viewport().rect()).boundingRect()

        x_min = int(rect.left() // self.tile_size)
        x_max = int(rect.right() // self.tile_size) + 1
        y_min = int(rect.top() // self.tile_size)
        y_max = int(rect.bottom() // self.tile_size) + 1
        max_index = 2**self.zoom - 1

        for x in range(x_min, x_max + 1):
            if x < 0 or x > max_index:
                continue
            for y in range(y_min, y_max + 1):
                if y < 0 or y > max_index:
                    continue
                key = (self.zoom, x, y)
                if key not in self.tiles:
                    self.loadTile(x, y, self.zoom)

    def loadTile(self, x, y, z):
        """Generates a tile URL and starts asynchronous loading"""

        tile_name = f"{x}_{y}_{z}_tile"
        if redis_connection.exists(tile_name):
            data = redis_connection.get(tile_name)
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            item = QGraphicsPixmapItem(pixmap)
            # We place the tile according to its coordinates for a given zoom
            item.setPos(x * self.tile_size, y * self.tile_size)
            # New tiles are drawn on top of the animated layer
            item.setZValue(1)
            self.scene.addItem(item)
            self.tiles[(z, x, y)] = item
            return

        url = rnd.choice([
            f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            f"https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
            f"https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
            f"https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
            f"https://tile.openstreetmap.de/{z}/{x}/{y}.png"
        ])

        request = QNetworkRequest(QUrl(url))
        # Set the correct User-Agent according to OSM policy
        request.setRawHeader(b"User-Agent", b"OSM-Viewer/1.0 (contact@example.com)")
        reply = self.network_manager_pool.getNetworkManager().get(request)
        reply.finished.connect(partial(self.handleTileReply, reply, x, y, z))

    def handleTileReply(self, reply, x, y, z):
        """Processes the response and adds the tile to the scene"""

        err = reply.error()
        if err != QNetworkReply.NetworkError.NoError:
            print(f"Error {err} tile loading {z}/{x}/{y}: {reply.errorString()}")
            reply.deleteLater()
            return

        data = reply.readAll()
        pixmap = QPixmap()
        pixmap.loadFromData(data)

        if pixmap.isNull():
            reply.deleteLater()
            return

        item = QGraphicsPixmapItem(pixmap)
        # We place the tile according to its coordinates for a given zoom
        item.setPos(x * self.tile_size, y * self.tile_size)
        # New tiles are drawn on top of the animated layer
        item.setZValue(1)
        self.scene.addItem(item)
        self.tiles[(z, x, y)] = item
        reply.deleteLater()

        tile_name = f"{x}_{y}_{z}_tile"
        redis_connection.set(tile_name, bytes(data))


    def clearOldTilesGroup(self):
        """Removes an animated group of old tiles after the animation is complete"""
        if self.old_tiles_group:
            self.scene.removeItem(self.old_tiles_group)
            self.old_tiles_group = None
        self._zoom_anim = None

    def onZoomAnimValueChanged(self, value):
        """Slot that updates the group scale during animation"""
        if self.old_tiles_group:
            self.old_tiles_group.setScale(value)

    def wheelEvent(self, event):
        """
        When scrolling the mouse wheel, smooth scaling is performed
        Current tiles are grouped and animated, and new ones are loaded in parallel
        """

        delta = event.angleDelta().y()
        old_zoom = self.zoom
        if delta > 0:
            new_zoom = min(self.zoom + 1, 19)
        else:
            new_zoom = max(self.zoom - 1, 0)
        if new_zoom == old_zoom:
            return

        # If the zoom animation is already running, we finish it
        if (
            self._zoom_anim is not None
            and self._zoom_anim.state() == QVariantAnimation.Running
        ):
            self._zoom_anim.stop()
            self.clearOldTilesGroup()

        # Scaling factor (eg 2 to increase by 1 level)
        factor = pow(2, new_zoom - old_zoom)
        cursor_scene_pos = self.mapToScene(event.position().toPoint())

        # Grouping current tiles for animation
        if self.tiles:
            items = list(self.tiles.values())
            self.old_tiles_group = self.scene.createItemGroup(items)
            self.old_tiles_group.setZValue(0)
            origin = self.old_tiles_group.mapFromScene(cursor_scene_pos)
            self.old_tiles_group.setTransformOriginPoint(origin)

            # Using QVariantAnimation for Smooth Scaling
            self._zoom_anim = QVariantAnimation(self)
            self._zoom_anim.setDuration(300)  # animation duration in ms
            self._zoom_anim.setStartValue(1.0)
            self._zoom_anim.setEndValue(factor)
            self._zoom_anim.valueChanged.connect(self.onZoomAnimValueChanged)
            self._zoom_anim.finished.connect(self.clearOldTilesGroup)
            self._zoom_anim.start()

        # Update zoom and scene sizes
        self.zoom = new_zoom
        self.updateSceneRect()
        new_center = cursor_scene_pos * factor
        self.centerOn(new_center)
        # Clear old tiles; new ones will be loaded for the new zoom
        self.tiles.clear()
        self.updateTiles()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateTiles()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.updateTiles()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.updateTiles()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = OSMGraphicsView(zoom=2)
    view.setWindowTitle("OpenStreetMap Viewer")
    view.resize(800, 600)
    view.show()
    sys.exit(app.exec())
