import os
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
        
        # 🔥 Detectamos el Proxy de GitHub Actions
        self.proxy_url = os.environ.get("PROXY_URL")
        self.proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url
        } if self.proxy_url else None

    def get_data(self, endpoint, params):
        try:
            # 🔥 Añadimos el parámetro proxies y un timeout de seguridad
            response = requests.get(
                f"{self.base_url}/{endpoint}", 
                headers=self.headers, 
                params=params,
                proxies=self.proxies,
                timeout=20 
            )
            response.raise_for_status() # Lanza error si el status no es 200
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error conectando a API Football: {e}")
            return None
            
class BasketballAPI(DataClient):
    def __init__(self, key):
        self.base_url = "https://v1.basketball.api-sports.io"
        self.headers = {
            "x-rapidapi-key": key
        }
        
        # 🔥 También protegemos las peticiones de Básquetbol
        self.proxy_url = os.environ.get("PROXY_URL")
        self.proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url
        } if self.proxy_url else None

    def get_data(self, endpoint, params):
        try:
            # 🔥 Añadimos el parámetro proxies y un timeout de seguridad
            response = requests.get(
                f"{self.base_url}/{endpoint}", 
                headers=self.headers, 
                params=params,
                proxies=self.proxies,
                timeout=20
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error conectando a API Basketball: {e}")
            return None
