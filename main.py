import os
import pandas as pd
from datetime import datetime
import pytz
import requests
from api_client import FootballAPI
from analyzer import MatchAnalyzer

# Configuración
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_KEY = os.environ.get("API_FOOTBALL_KEY")
LIGAS_PERMITIDAS = [10, 242, 254, 292, 649, 660, 1031, 1232, 1, 2, 13, 39, 61, 78, 135, 140, 265, 667]

def main():
    # Inicializar
    df = pd.read_csv("historico_maestro_global.csv")
    analyzer = MatchAnalyzer(df)
    api = FootballAPI(API_KEY)
    
    # Fecha Chile
    zona_chile = pytz.timezone('America/Santiago')
    fecha = datetime.now(zona_chile).strftime("%Y-%m-%d")
    
    # 1. Obtener datos
    data = api.get_data("fixtures", {"date": fecha})
    if not data: return
    
    # 2. Procesar
    reporte_agrupado = {}
    for match in data.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            liga_nombre = match["league"]["name"]
            proj = analyzer.get_projections(match["teams"]["home"]["name"], match["teams"]["away"]["name"])
            
            if liga_nombre not in reporte_agrupado: reporte_agrupado[liga_nombre] = []
            reporte_agrupado[liga_nombre].append(proj)
            
    # 3. Reportar Top 3
    for liga, proyecciones in reporte_agrupado.items():
        top_3 = analyzer.get_top_by_league(proyecciones, n=3)
        mensaje = f"🏆 *TOP 3: {liga}*\n\n"
        for p in top_3:
            mensaje += f"⚽ {p['local']} vs {p['visita']}\n🎯 {p['mejor_apuesta']}\n\n"
        
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})

if __name__ == "__main__":
    main()
