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

        # 🕵️ INICIO DEL TEST DE VERIFICACIÓN DE IP
        print("\n--- PRUEBA DE CAMUFLAJE ---")
        try:
            # Consultamos cómo nos ve el mundo exterior
            ip_real = requests.get("https://api.ipify.org", proxies=self.proxies, timeout=10).text
            if self.proxies:
                print(f"✅ Túnel ACTIVO. El mundo nos ve con la IP: {ip_real}")
            else:
                print(f"⚠️ Túnel APAGADO. Usando conexión directa. IP: {ip_real}")
        except Exception as e:
            print(f"❌ Error al conectar por el Proxy o test de IP fallido: {e}")
        print("---------------------------\n")

    def get_data(self, endpoint, params):
        try:
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
            print(f"❌ Error conectando a API Football: {e}")
            return None

    # NUEVO: Endpoint específico para extraer la táctica post-partido
    def get_fixture_statistics(self, fixture_id):
        try:
            response = requests.get(
                f"{self.base_url}/fixtures/statistics", 
                headers=self.headers, 
                params={"fixture": fixture_id},
                proxies=self.proxies,
                timeout=15 
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error conectando a API (Estadísticas {fixture_id}): {e}")
            return None
            
class BasketballAPI(DataClient):
    def __init__(self, key):
        self.base_url = "https://v1.basketball.api-sports.io"
        self.headers = {
            "x-rapidapi-key": key
        }
        
        self.proxy_url = os.environ.get("PROXY_URL")
        self.proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url
        } if self.proxy_url else None

    def get_data(self, endpoint, params):
        try:
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
