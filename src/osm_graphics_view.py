import re
import random as rnd

from functools import partial
import math
from PySide6.QtCore import QUrl, QVariantAnimation
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
)
from PySide6.QtNetwork import (
    QNetworkRequest,
    QNetworkReply,
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


from functools import partial
from PySide6.QtCore import QUrl, QPropertyAnimation, QParallelAnimationGroup, QRectF
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtNetwork import QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsOpacityEffect,
)


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
        self.network_manager_pool = NetworkAccessManagerPool(self, 10)

        # Начальная загрузка тайлов
        self.updateTiles()

    def updateSceneRect(self):
        """
        Обновление размеров сцены с горизонтальным повторением.
        Задаем ширину сцены в 3 раза больше базовой ширины карты,
        чтобы при прокрутке за левую или правую границу карта повторялась.
        """

        world_width = self.tile_size * (2**self.zoom)
        self.scene.setSceneRect(0, 0, world_width, world_width)

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
                    self.loadTile(wrapped_x, y, self.zoom, world_offset)

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

        # Анимация fade-out для старых тайлов
        anim_group = QParallelAnimationGroup(self)
        for item in old_items:
            effect = QGraphicsOpacityEffect()
            item.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity")
            anim.setDuration(300)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim_group.addAnimation(anim)
        # По окончании группы анимаций удаляем старые тайлы
        anim_group.finished.connect(lambda: self.cleanupOldTiles(old_items))
        anim_group.start()
        self._fade_anim_group = (
            anim_group  # Сохраняем ссылку, чтобы группа не была уничтожена
        )

    def cleanupOldTiles(self, items):
        for item in items:
            self.scene.removeItem(item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
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

        nearLeft, nearRight, nearTop, nearBottom = self.isNearMapBoundary()

        world_width = self.tile_size * (2**self.zoom)
        # self.scene.setSceneRect(0, 0, world_width, world_width)

        # sceneRect = self.scene.sceneRect()
        # sceneRect.width()

        self.updateTiles()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.updateTiles()
