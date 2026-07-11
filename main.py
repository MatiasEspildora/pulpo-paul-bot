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
    if not os.path.exists("historico_maestro_global.csv"):
        print("❌ No se encontró el archivo historico_maestro_global.csv en la ruta esperada.")
        return

    df = pd.read_csv("historico_maestro_global.csv")
    analyzer = MatchAnalyzer(df)
    
    zona_chile = pytz.timezone('America/Santiago')
    fecha_hoy = datetime.now(zona_chile).strftime("%Y-%m-%d")
    fecha_str = datetime.now(zona_chile).strftime("%Y%m%d")
    archivo_local = f"resultados/partidos_{fecha_str}.json"

    # Caché
    if os.path.exists(archivo_local):
        with open(archivo_local, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        if not API_KEY:
            print("⚠️ Falta la clave API_FOOTBALL_KEY en el entorno.")
            return
        api = FootballAPI(API_KEY)
        data = api.get_data("fixtures", {"date": fecha_hoy})
        if not data: 
            return
        if not os.path.exists("resultados"): 
            os.makedirs("resultados")
        with open(archivo_local, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    reporte_agrupado = {}
    for match in data.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            liga_nombre = match["league"]["name"]
            home_name = match["teams"]["home"]["name"]
            away_name = match["teams"]["away"]["name"]
            
            proj = analyzer.get_projections(home_name, away_name)
            
            if liga_nombre not in reporte_agrupado: 
                reporte_agrupado[liga_nombre] = []
            reporte_agrupado[liga_nombre].append(proj)
            
    for liga, proyecciones in reporte_agrupado.items():
        top_3 = analyzer.get_top_by_league(proyecciones, n=3)
        mensaje = f"🏆 *TOP 3: {liga}*\n\n"
        for p in top_3:
            s_l = analyzer.get_team_stats(p['local'])
            s_v = analyzer.get_team_stats(p['visita'])
            
            # Formato más explícito y legible con emojis
            mensaje += (f"⚽ *{p['local']}* vs *{p['visita']}*\n"
                        f"📊 Probabilidades: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                        f"🎯 Ambos anotan: {p['btts']:.0%} | Marcadores: {', '.join(p['scores'])}\n"
                        f"📐 *Promedios últimos 5 partidos (Local | Visita):*\n"
                        f"  🚩 Córners: `{s_l['corners']:.0f}` | `{s_v['corners']:.0f}`\n"
                        f"  🟨 Tarjetas: `{s_l['tarjetas']:.0f}` | `{s_v['tarjetas']:.0f}`\n"
                        f"  🥅 Remates: `{s_l['remates']:.0f}` | `{s_v['remates']:.0f}`\n\n")
        
        if TOKEN and CHAT_ID:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                        data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
        else:
            print(f"⚠️ Faltan credenciales de Telegram para enviar el reporte de {liga}.")

if __name__ == "__main__":
    main()
