import os
import json
import requests
from datetime import datetime

# ==========================================
# 🤖 BENDER V4.0 - ACTUALIZADOR DE LIGAS (RADAR TÁCTICO)
# ==========================================

# Credenciales (Asegúrate de que coincidan con las variables de entorno de tu servidor/PC)
API_KEY = os.environ.get("API_FOOTBALL_KEY") # Cambia el nombre si tu variable se llama distinto
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "x-apisports-key": API_KEY,
    "v": "3"
}

RUTA_JSON = os.path.join("config", "Active_Leagues_Coverage.json")

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Credenciales de Telegram no encontradas. Imprimiendo en consola:")
        print(mensaje)
        return
    
    for chat in CHAT_ID.split(","):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": chat.strip(), "text": mensaje, "parse_mode": "Markdown"}
            )
        except Exception as e:
            print(f"Error enviando a Telegram: {e}")

def actualizar_ligas():
    print("📡 Iniciando escaneo global de ligas activas en API-Football...")
    
    url = "https://v3.football.api-sports.io/leagues?current=true"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        enviar_telegram(f"❌ *Bender Error:* Falló la conexión al endpoint de Ligas.\nDetalle: `{e}`")
        return

    ligas_validas = {}
    total_escaneadas = data.get("results", 0)
    
    for item in data.get("response", []):
        liga = item.get("league", {})
        pais = item.get("country", {})
        seasons = item.get("seasons", [])
        
        if not seasons:
            continue
            
        # Tomamos la temporada actual (la API filtra por current=true, así que suele ser la primera/única en la lista)
        current_season = seasons[0]
        coverage = current_season.get("coverage", {})
        fixtures_cov = coverage.get("fixtures", {})
        
        # 🔥 EL FILTRO DE TITANIO PARA COBERTURA 🔥
        # Exigimos Eventos (Goles/Tarjetas rojas), Estadísticas (Córners/Remates) y Alineaciones
        tiene_eventos = fixtures_cov.get("events", False)
        tiene_estadisticas = fixtures_cov.get("statistics_fixtures", False)
        tiene_alineaciones = fixtures_cov.get("lineups", False)
        
        if tiene_eventos and tiene_estadisticas and tiene_alineaciones:
            id_liga = str(liga.get("id"))
            nombre_pais = pais.get("name", "Desconocido")
            nombre_liga = liga.get("name", "Desconocida")
            
            # Guardamos con un formato legible para humanos en el JSON
            ligas_validas[id_liga] = f"{nombre_pais} - {nombre_liga}"

    # Guardar en config/Active_Leagues_Coverage.json
    os.makedirs("config", exist_ok=True)
    
    # Leemos el anterior para ver cuántas nuevas hay
    ligas_anteriores = {}
    if os.path.exists(RUTA_JSON):
        try:
            with open(RUTA_JSON, "r", encoding="utf-8") as f:
                ligas_anteriores = json.load(f)
        except json.JSONDecodeError:
            pass

    nuevas = len(ligas_validas) - len(ligas_anteriores)
    signo = "+" if nuevas >= 0 else ""
    
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(ligas_validas, f, indent=4, ensure_ascii=False)

    msg = (
        f"🤖 *BENDER RADAR ACTUALIZADO*\n\n"
        f"🌍 Ligas activas escaneadas: `{total_escaneadas}`\n"
        f"✅ Ligas que pasaron el filtro táctico: `{len(ligas_validas)}`\n"
        f"📈 Variación semanal: `{signo}{nuevas}` ligas\n\n"
        f"💾 _Archivo config/Active_Leagues_Coverage.json sobreescrito con éxito._"
    )
    enviar_telegram(msg)
    print("✅ Proceso completado con éxito.")

if __name__ == "__main__":
    actualizar_ligas()
