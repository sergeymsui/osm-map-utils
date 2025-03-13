import random as rnd
from PySide6.QtNetwork import QNetworkAccessManager


class NetworkAccessManagerPool:

    def __init__(self, parent, manager_count=1):
        self.parent = parent
        self.manager_count = manager_count
        self.network_manager_list = list()

        for _ in range(manager_count):
            network_manager = QNetworkAccessManager(self.parent)
            network_manager.setTransferTimeout(5000)
            self.network_manager_list.append(network_manager)

    def getNetworkManager(self):
        return rnd.choice(self.network_manager_list)
