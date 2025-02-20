import sys
import redis
from PySide6.QtWidgets import QApplication
from osm_graphics_view import OSMGraphicsView

if __name__ == "__main__":
    app = QApplication(sys.argv)

    redis_cache = redis.Redis(host="localhost", port=6379, db=0)

    view = OSMGraphicsView(redis_cache, zoom=2)
    view.show()

    sys.exit(app.exec())
