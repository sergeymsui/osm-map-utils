import requests

from PySide6.QtCore import Signal
from mlineedit import MLineEdit
from mlistwidget import MListWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout


def get_coordinates_from_location(location_name):
    # Базовый URL API Nominatim
    base_url = "https://nominatim.openstreetmap.org/search"

    # Параметры запроса
    params = {
        "q": location_name,  # Название места или адрес
        "format": "json",  # Формат ответа (JSON)
        "limit": 10,  # Ограничение на количество результатов
    }

    # Заголовки для имитации браузера (требуется Nominatim)
    headers = {"User-Agent": "MyGeocodingApp/1.0"}  # Укажите свое приложение/версию

    # Выполняем GET-запрос
    response = requests.get(base_url, params=params, headers=headers)

    # Проверяем статус ответа
    if response.status_code == 200:
        data = response.json()

        if data:
            return data
        else:
            raise ValueError("Местоположение не найдено.")
    else:
        raise Exception(f"Ошибка запроса: {response.status_code}")


class SearchWidget(QWidget):
    changedLocation = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(350)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Поле ввода
        self.search_box = MLineEdit(self)
        self.search_box.textChanged.connect(self.changeEditText)
        self.search_box.setFixedSize(350, 30)
        self.search_box.setPlaceholderText("Введите запрос...")

        layout.addWidget(self.search_box)
        self.setLayout(layout)

        # Хранение координат
        self.location_dict = dict()
        self.suggestions = list()

        self.suggestList = MListWidget(self.parent())
        self.suggestList.setFixedWidth(350)
        self.suggestList.move(20, 30 + 20)
        self.suggestList.hide()
        self.suggestList.itemClicked.connect(self.onSelection)

        self.search_box.onFucus.connect(self.onActive)
        self.suggestList.outFucus.connect(self.onDeactive)
        self.search_box.outFucus.connect(self.onDeactive)

    def onActive(self):
        if len(self.suggestions):
            self.suggestList.setVisible(True)

    def onDeactive(self):
        if not self.suggestList.hasFocus():
            self.suggestList.setVisible(False)

    def changeEditText(self, text):

        if len(text) <= 3:
            self.suggestList.hide()
            return
        self.suggestList.setVisible(True)

        self.location_dict.clear()  # Очищаем старые данные

        ranked_place = list()
        mrequest = get_coordinates_from_location(text)
        for place in mrequest:
            place_rank = int(place["place_rank"])
            display_name = place["display_name"]

            print(place)

            self.location_dict[display_name] = place["boundingbox"]
            ranked_place.append((place_rank, display_name))

        ranked_place.sort(reverse=False)

        self.updateSuggestions([place for _, place in ranked_place])

    def updateSuggestions(self, suggestions):
        """Обновляет список предложений в Completer"""

        self.suggestions = suggestions
        self.suggestList.clear()
        self.suggestList.addItems(suggestions)

    def onSelection(self, item):
        """Обрабатывает выбор элемента и выводит координаты"""

        text = item.text()

        boundingbox = self.location_dict.get(text, None)
        if boundingbox:
            print(f"Выбрано: {text}, Координаты: {boundingbox}")
            if len(boundingbox) != 4:
                print(
                    "Ошибка: boundingbox должен содержать 4 координаты (south, north, west, east)"
                )
                return

            # Преобразуем строки в числа
            south, north, west, east = map(float, boundingbox)
            self.changedLocation.emit(south, north, west, east)
            self.suggestList.hide()
