import re
import math

from searchwidget import SearchWidget

from functools import partial
from PySide6.QtCore import QUrl
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtNetwork import QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QPushButton,
)

from network_access_manager_pool import NetworkAccessManagerPool


def check_and_extract_numbers(filename):
    # Template for file name validation
    pattern = r"^(\d+)_(\d+)_(\d+)\_tile$"

    # Checking if the file name matches the pattern
    match = re.match(pattern, filename)

    if match:
        # If it matches, we extract the numbers
        numbers = match.groups()
        return True, [int(v) for v in numbers]
    else:
        # If it doesn't match, return False and an empty list.
        return False, list()


class OSMGraphicsView(QGraphicsView):
    def __init__(self, zoom=2, parent=None):
        super().__init__(parent)

        # Настройки рендеринга
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheNone)

        self.tile_size = 256  # Размер одного тайла в пикселях
        self.zoom = zoom  # Текущий уровень зума
        self.tiles = {}  # Загруженные тайлы: ключ (zoom, x, y, world_offset)
        self._fade_anim_group = None  # Ссылка на группу анимаций fade-out

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.updateSceneRect()

        # Предполагается, что NetworkAccessManagerPool определён
        self.network_manager_pool = NetworkAccessManagerPool(self, 100)

        # Начальная загрузка тайлов
        self.updateTiles()

        self.h_margin = 20
        self.w_margin = 20

        self.findLine = SearchWidget(self)
        self.findLine.move(self.w_margin, self.h_margin)
        self.findLine.changedLocation.connect(self.fitToBoundingBox)

        self.plusButton = QPushButton("+", self)
        self.plusButton.setFixedSize(30, 30)
        self.plusButton.move(self.width() - self.w_margin, self.h_margin)
        self.plusButton.clicked.connect(self.upZoomEvent)

        self.minusButton = QPushButton("-", self)
        self.minusButton.setFixedSize(30, 30)
        self.minusButton.move(self.width() - self.w_margin, self.h_margin)
        self.minusButton.clicked.connect(self.downZoomEvent)

    def fitToBoundingBox(self, south, north, west, east):
        """
        Подгоняет область видимости карты так, чтобы она охватывала `boundingbox`.

        boundingbox = [south, north, west, east] (широта и долгота в градусах).
        """

        print(south, north, west, east)

        # Проверяем, что координаты корректны
        if south >= north or west >= east:
            print("Ошибка: некорректные границы boundingbox")
            return

        # Найдем центр boundingbox
        center_lat = (south + north) / 2.0
        center_lon = (west + east) / 2.0

        # Найдем уровень зума, который поместит всю область в экран
        self.zoom = self.calculateBestZoom(south, north, west, east)
        self.updateSceneRect()

        # Переведем центр в пиксельные координаты
        x_tile, y_tile = self.latLonToTile(center_lat, center_lon, self.zoom)
        x_pix = x_tile * self.tile_size
        y_pix = y_tile * self.tile_size

        # Устанавливаем новый центр карты
        self.centerOn(x_pix, y_pix)
        self.updateTiles()

        print(
            f"Карта сдвинута к BBOX: lat={center_lat}, lon={center_lon}, zoom={self.zoom}"
        )

    def calculateBestZoom(self, south, north, west, east):
        """
        Вычисляет оптимальный уровень зума, чтобы boundingbox полностью влез в окно.
        """
        for z in range(19, 0, -1):  # Перебираем зум от 19 до 0
            x_min, y_max = self.latLonToTile(north, west, z)
            x_max, y_min = self.latLonToTile(south, east, z)

            # Размер boundingbox в пикселях
            width_px = (x_max - x_min) * self.tile_size
            height_px = (y_max - y_min) * self.tile_size

            # Проверяем, влезает ли он в окно
            if (
                width_px <= self.viewport().width()
                and height_px <= self.viewport().height()
            ):
                return z  # Возвращаем первый подходящий зум

        return None  # Если ничего не нашли, оставляем текущий

    def latLonToTile(self, lat, lon, zoom):
        """
        Конвертирует широту и долготу в тайловые координаты (x, y) для заданного зума.
        """
        n = 2**zoom
        x_tile = (lon + 180.0) / 360.0 * n
        y_tile = (
            (
                1.0
                - math.log(
                    math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))
                )
                / math.pi
            )
            / 2.0
            * n
        )
        return x_tile, y_tile

    def moveToCoordinates(self, lat, lon):
        """
        Перемещает вид карты в указанные координаты (lat, lon).
        """
        # Проверяем, что зум установлен корректно
        if not (0 <= self.zoom <= 19):
            print("Ошибка: Некорректный уровень зума")
            return

        # Переводим широту и долготу в тайловые координаты
        n = 2**self.zoom  # Количество тайлов в ряду на данном уровне зума
        x_tile = (lon + 180.0) / 360.0 * n
        y_tile = (
            (
                1.0
                - math.log(
                    math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))
                )
                / math.pi
            )
            / 2.0
            * n
        )

        # Переводим тайловые координаты в пиксельные
        x_pix = x_tile * self.tile_size
        y_pix = y_tile * self.tile_size

        # Перемещаем центр карты на вычисленные координаты
        self.centerOn(x_pix, y_pix)
        self.updateTiles()

        print(f"Перемещено в координаты: lat={lat}, lon={lon}, x={x_pix}, y={y_pix}")

    def updateSceneRect(self):
        """
        Обновление размеров сцены с горизонтальным повторением.
        Задаем ширину сцены в 3 раза больше базовой ширины карты,
        чтобы при прокрутке за левую или правую границу карта повторялась.
        """

        world_width = self.tile_size * (2**self.zoom)
        self.scene.setSceneRect(0, 0, world_width + 0.1 * world_width, world_width)

    def updateTiles(self):
        """
        Определяем, какие тайлы должны отображаться с учётом горизонтального оборачивания.
        Вычисляем область видимой части сцены и для каждой координаты x, y
        рассчитываем обёрнутые координаты с помощью x % n_tiles и world_offset = x - (x % n_tiles).
        """
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        x_min = int(rect.left() // self.tile_size)
        x_max = int(rect.right() // self.tile_size) + 1
        y_min = int(rect.top() // self.tile_size)
        y_max = int(rect.bottom() // self.tile_size) + 1
        n_tiles = 2**self.zoom

        for x in range(x_min, x_max + 1):
            wrapped_x = x % n_tiles
            world_offset = x - wrapped_x
            for y in range(y_min, y_max + 1):
                if y < 0 or y >= n_tiles:
                    continue  # Вертикальное оборачивание не требуется
                key = (self.zoom, wrapped_x, y, world_offset)
                if key not in self.tiles:
                    self.preLoadTile(wrapped_x, y, self.zoom, world_offset)
                    self.loadTile(wrapped_x, y, self.zoom, world_offset)

    def preLoadTile(self, x, y, z, world_offset):
        pixmap = QPixmap()
        pixmap.load("../data/preview.png")
        if pixmap.isNull():
            print(f"Не могу превью для ({z}/{x}/{y})")
            return

        item = QGraphicsPixmapItem(pixmap)
        # Позиционирование с учетом горизонтального оборачивания:
        # (x + world_offset) учитывает повторения карты слева и справа.
        item.setPos((x + world_offset) * self.tile_size, y * self.tile_size)
        item.setZValue(1)
        self.scene.addItem(item)
        self.tiles[(z, x, y, world_offset)] = item

    def loadTile(self, x, y, z, world_offset=0):
        """
        Формирование URL и запуск асинхронной загрузки тайла с учётом смещения.
        """

        url = f"http://localhost:8080/{z}/{x}/{y}.png"

        request = QNetworkRequest(QUrl(url))
        reply = self.network_manager_pool.getNetworkManager().get(request)
        reply.finished.connect(
            partial(self.handleTileReply, reply, x, y, z, world_offset)
        )

    def handleTileReply(self, reply, x, y, z, world_offset):
        """
        Обработка ответа и добавление тайла на сцену.
        Если уровень зума уже изменился, ответ игнорируется.
        """
        if z != self.zoom:
            reply.deleteLater()
            return

        err = reply.error()
        if err != QNetworkReply.NetworkError.NoError:
            print(
                f"Error: {err} Ошибка загрузки тайла {z}/{x}/{y}: {reply.errorString()}"
            )
            reply.deleteLater()
            return

        data = reply.readAll()
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            print(f"Не могу загрузить тайл ({z}/{x}/{y})")
            reply.deleteLater()
            return

        item = QGraphicsPixmapItem(pixmap)
        # Позиционирование с учетом горизонтального оборачивания:
        # (x + world_offset) учитывает повторения карты слева и справа.
        item.setPos((x + world_offset) * self.tile_size, y * self.tile_size)
        item.setZValue(1)
        self.scene.addItem(item)
        self.tiles[(z, x, y, world_offset)] = item

        reply.deleteLater()

    def wheelEvent(self, event):
        """
        При изменении зума:
          - Старые тайлы сохраняются для плавного исчезновения (fade-out).
          - Вычисляется новый уровень зума, обновляются размеры сцены и центр.
          - После загрузки новых тайлов для нового зума, старые плавно исчезают.
        """

        visibleRect = self.mapToScene(self.viewport().rect()).boundingRect()
        sceneRect = self.scene.sceneRect()

        if visibleRect.width() >= sceneRect.width():
            self.scene.clear()
            self.scene.setSceneRect(visibleRect)

        delta = event.angleDelta().y()
        old_zoom = self.zoom
        if delta > 0:
            new_zoom = min(self.zoom + 1, 19)
        else:
            new_zoom = max(self.zoom - 1, 0)
        if new_zoom == old_zoom:
            return

        # Сохраняем старые тайлы и очищаем словарь для новых
        old_items = list(self.tiles.values())
        self.tiles.clear()

        # Вычисляем новую позицию центра
        cursor_scene_pos = self.mapToScene(event.position().toPoint())
        factor = pow(2, new_zoom - old_zoom)
        new_center = cursor_scene_pos * factor

        self.zoom = new_zoom
        self.updateSceneRect()
        self.centerOn(new_center)
        self.updateTiles()

        print(f"ZOOM: {self.zoom}")

    def cleanupOldTiles(self, items):
        for item in items:
            self.scene.removeItem(item)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.plusButton.move(
            self.width() - self.w_margin - self.plusButton.width(), self.h_margin
        )
        self.minusButton.move(
            self.width() - self.w_margin - self.plusButton.width(), 2.5 * self.h_margin
        )
        self.updateTiles()

    def upZoomEvent(self):

        new_zoom = self.zoom + 1
        old_zoom = self.zoom

        if new_zoom > 19 or new_zoom < 0:
            return

        visibleRect = self.mapToScene(self.viewport().rect()).boundingRect()
        sceneRect = self.scene.sceneRect()

        if visibleRect.width() >= sceneRect.width():
            self.scene.clear()
            self.scene.setSceneRect(visibleRect)

        self.tiles.clear()

        # Вычисляем новую позицию центра
        cursor_scene_pos = visibleRect.center().toPoint()
        factor = pow(2, new_zoom - old_zoom)
        new_center = cursor_scene_pos * factor

        self.zoom = new_zoom
        self.updateSceneRect()
        self.centerOn(new_center)
        self.updateTiles()

    def downZoomEvent(self):

        new_zoom = self.zoom - 1
        old_zoom = self.zoom

        if new_zoom > 19 or new_zoom < 0:
            return

        visibleRect = self.mapToScene(self.viewport().rect()).boundingRect()
        sceneRect = self.scene.sceneRect()

        if visibleRect.width() >= sceneRect.width():
            self.scene.clear()
            self.scene.setSceneRect(visibleRect)

        self.tiles.clear()

        # Вычисляем новую позицию центра
        cursor_scene_pos = visibleRect.center().toPoint()
        factor = pow(2, new_zoom - old_zoom)
        new_center = cursor_scene_pos * factor

        self.zoom = new_zoom
        self.updateSceneRect()
        self.centerOn(new_center)
        self.updateTiles()

    def isNearMapBoundary(self, margin=50):
        # Получаем видимую область в координатах сцены
        visibleRect = self.mapToScene(self.viewport().rect()).boundingRect()
        # Получаем границы сцены
        sceneRect = self.scene.sceneRect()

        nearLeft = visibleRect.left() <= sceneRect.left() + margin
        nearRight = visibleRect.right() >= sceneRect.right() - margin
        nearTop = visibleRect.top() <= sceneRect.top() + margin
        nearBottom = visibleRect.bottom() >= sceneRect.bottom() - margin

        return nearLeft, nearRight, nearTop, nearBottom

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.updateTiles()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.updateTiles()
