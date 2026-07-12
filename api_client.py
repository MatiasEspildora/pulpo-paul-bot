import requests
from abc import ABC, abstractmethod

# Interfaz genérica para clientes de API
class DataClient(ABC):
    @abstractmethod
    def get_data(self, endpoint, params):
        pass

class FootballAPI(DataClient):
    def __init__(self, key):
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            "x-rapidapi-key": key, 
            "x-rapidapi-host": "v3.football.api-sports.io"
        }

    def get_data(self, endpoint, params):
        try:
            response = requests.get(f"{self.base_url}/{endpoint}", headers=self.headers, params=params)
            response.raise_for_status() # Lanza error si el status no es 200
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error conectando a API Football: {e}")
            return None
            
class BasketballAPI(DataClient):
    def __init__(self, key):
        self.base_url = "https://v1.basketball.api-sports.io"
        self.headers = {
            "x-rapidapi-key": key,
            "x-rapidapi-host": "v1.basketball.api-sports.io"
        }

    def get_data(self, endpoint, params):
        try:
            response = requests.get(f"{self.base_url}/{endpoint}", headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error conectando a API Basketball: {e}")
            return None