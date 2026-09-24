import os
import json
from api_client import FootballAPI

# ==========================================
# 🤖 BENDER V4.0 - ACTUALIZADOR DE LIGAS (RADAR TÁCTICO)
# ==========================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_KEY = os.environ.get("API_FOOTBALL_KEY")

RUTA_JSON = os.path.join("config", "Active_Leagues_Coverage.json")

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Credenciales de Telegram no encontradas. Imprimiendo en consola:")
        print(mensaje)
        return
    
    for chat in CHAT_ID.split(","):
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": chat.strip(), "text": mensaje, "parse_mode": "Markdown"}
            )
        except Exception as e:
            print(f"Error enviando a Telegram: {e}")

def actualizar_ligas():
    print("📡 Iniciando escaneo global de ligas activas usando FootballAPI...")
    
    api = FootballAPI(API_KEY)
    data = api.get_data("leagues", {"current": "true"})
    
    if not data or "response" not in data:
        enviar_telegram("❌ *Bender Error:* Falló la conexión al endpoint de Ligas.")
        return

    ligas_validas = []
    total_escaneadas = data.get("results", 0)
    
    # 🔥 IDs de Ligas VIP (Selecciones y Élite) que SÍ tienen stats aunque la API diga lo contrario
    # 1: World Cup, 4: Euro Championship, 5: UEFA Nations League, 9: Copa America
    LIGAS_VIP = {1, 4, 5, 9}
    
    for item in data.get("response", []):
        liga = item.get("league", {})
        pais = item.get("country", {})
        seasons = item.get("seasons", [])
        
        if not seasons:
            continue
            
        current_season = seasons[0]
        coverage = current_season.get("coverage", {})
        fixtures_cov = coverage.get("fixtures", {})
        
        # Filtro Táctico de Bender
        tiene_eventos = fixtures_cov.get("events", False)
        tiene_estadisticas = fixtures_cov.get("statistics_fixtures", False)
        tiene_alineaciones = fixtures_cov.get("lineups", False)
        
        # Verificamos si la liga está en nuestra Lista VIP
        es_vip = liga.get("id") in LIGAS_VIP
        
        # Si cumple los requisitos normales O es una liga VIP, la agregamos al radar
        if es_vip or (tiene_eventos and tiene_estadisticas and tiene_alineaciones):
            # 🔥 Guardamos como estructura de lista compatible con football.py
            ligas_validas.append({
                "league_id": liga.get("id"),
                "name": liga.get("name"),
                "country": pais.get("name"),
                "can_fetch_stats": True
            })

    os.makedirs("config", exist_ok=True)
    
    ligas_anteriores = []
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
        f"✅ Ligas que pasaron el filtro (incluye VIP): `{len(ligas_validas)}`\n"
        f"📈 Variación semanal: `{signo}{nuevas}` ligas\n\n"
        f"💾 _Archivo config/Active_Leagues_Coverage.json sobreescrito con éxito._"
    )
    enviar_telegram(msg)
    print("✅ Proceso completado con éxito.")

if __name__ == "__main__":
    actualizar_ligas()
