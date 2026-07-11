import os
import pandas as pd
from datetime import datetime
import pytz
import requests
import json
from api_client import FootballAPI
from analyzer import MatchAnalyzer

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_KEY = os.environ.get("API_FOOTBALL_KEY")
LIGAS_PERMITIDAS = [10, 242, 254, 292, 649, 660, 1031, 1232, 1, 2, 13, 39, 61, 78, 135, 140, 265, 667]

def main():
    df = pd.read_csv("historico_maestro_global.csv")
    analyzer = MatchAnalyzer(df)
    api = FootballAPI(API_KEY)
    
    zona_chile = pytz.timezone('America/Santiago')
    fecha_hoy = datetime.now(zona_chile).strftime("%Y-%m-%d")
    fecha_str = datetime.now(zona_chile).strftime("%Y%m%d")
    
    if not os.path.exists("resultados"): os.makedirs("resultados")
    
    data = api.get_data("fixtures", {"date": fecha_hoy})
    if not data: return
    
    with open(f"resultados/partidos_{fecha_str}.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    reporte_agrupado = {}
    for match in data.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            liga_nombre = match["league"]["name"]
            # Analizamos con la nueva lógica de mercados y métricas
            proj = analyzer.get_projections(match["teams"]["home"]["name"], match["teams"]["away"]["name"])
            
            if liga_nombre not in reporte_agrupado: reporte_agrupado[liga_nombre] = []
            reporte_agrupado[liga_nombre].append(proj)
            
    for liga, proyecciones in reporte_agrupado.items():
        top_3 = analyzer.get_top_by_league(proyecciones, n=3)
        mensaje = f"🏆 *TOP 3: {liga}*\n\n"
        for p in top_3:
            # Mostramos el desglose de métricas que calculamos en analyzer.py
            score_txt = ", ".join(p['score_exacto'].keys())
            mensaje += (f"⚽ {p['local']} vs {p['visita']}\n"
                        f"🎯 {p['mejor_apuesta']}\n"
                        f"📊 Scores probables: {score_txt}\n"
                        f"📐 C:{p['corners_proy']} | T:{p['tarjetas_proy']} | R:{p['remates_proy']}\n\n")
        
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})

if __name__ == "__main__":
    main()
