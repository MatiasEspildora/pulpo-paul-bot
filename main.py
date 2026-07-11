import os
import pandas as pd
from datetime import datetime, timedelta
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
    csv_path = "historico_maestro_global.csv"
    if not os.path.exists(csv_path):
        print(f"❌ No se encontró el archivo {csv_path} en la raíz.")
        return

    df = pd.read_csv(csv_path)
    analyzer = MatchAnalyzer(df)
    
    zona_chile = pytz.timezone('America/Santiago')
    now_chile = datetime.now(zona_chile)
    fecha_hoy = now_chile.strftime("%Y-%m-%d")
    fecha_str = now_chile.strftime("%Y%m%d")
    archivo_local = f"resultados/partidos_{fecha_str}.json"

    # Caché del día (1 sola petición a la API)
    if os.path.exists(archivo_local):
        print(f"📂 [Caché] Leyendo partidos del día {fecha_hoy} desde el archivo local...")
        with open(archivo_local, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        if not API_KEY:
            print("⚠️ Falta la clave API_FOOTBALL_KEY en el entorno.")
            return
        print(f"🌐 [API] Consultando calendario del día {fecha_hoy} (1 petición gastada)...")
        api = FootballAPI(API_KEY)
        data = api.get_data("fixtures", {"date": fecha_hoy})
        if not data: 
            print("⚠️ No se obtuvieron datos de la API para hoy.")
            return
        if not os.path.exists("resultados"): 
            os.makedirs("resultados")
        with open(archivo_local, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    # Contadores para visibilidad en consola/logs
    total_api_partidos = len(data.get("response", []))
    partidos_en_ligas = 0
    partidos_filtrados_horario = 0
    
    print(f"📊 Partidos totales devueltos por la API para hoy: {total_api_partidos}")

    reporte_agrupado = {}

    for match in data.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            partidos_en_ligas += 1
            
            # Filtro de horario: Convertir UTC a hora Chile
            fixture_date_utc = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00"))
            match_local = fixture_date_utc.astimezone(zona_chile)
            
            # Omitir partidos que ya terminaron hace más de 30 minutos
            if match_local < (now_chile - timedelta(minutes=30)) and match["fixture"]["status"]["short"] == "FT":
                partidos_filtrados_horario += 1
                continue

            liga_nombre = match["league"]["name"]
            home_name = match["teams"]["home"]["name"]
            away_name = match["teams"]["away"]["name"]
            hora_formateada = match_local.strftime("%H:%M")
            
            # Las proyecciones se calculan localmente usando el CSV histórico
            proj = analyzer.get_projections(home_name, away_name)
            proj['hora'] = hora_formateada
            
            if liga_nombre not in reporte_agrupado: 
                reporte_agrupado[liga_nombre] = []
            reporte_agrupado[liga_nombre].append(proj)

    print(f"🎯 Partidos que coinciden con tus Ligas Permitidas: {partidos_en_ligas}")
    print(f"🕒 Partidos omitidos por haber finalizado hace más de 30 min: {partidos_filtrados_horario}")
    print(f"⚡ Partidos listos para calcular Top 3 y enviar: {sum(len(v) for v in reporte_agrupado.values())}\n")
    
    # Enviar Top 3 por liga a Telegram
    for liga, proyecciones in reporte_agrupado.items():
        if not proyecciones: 
            continue
        top_3 = analyzer.get_top_by_league(proyecciones, n=3)
        mensaje = f"🏆 *TOP 3: {liga}*\n\n"
        for p in top_3:
            s_l = analyzer.get_team_stats(p['local'])
            s_v = analyzer.get_team_stats(p['visita'])
            
            mensaje += (f"🕒 Hora: `{p['hora']}` | ⚽ *{p['local']}* vs *{p['visita']}*\n"
                        f"📊 Probabilidades: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                        f"🎯 Ambos anotan: {p['btts']:.0%} | Marcadores: {', '.join(p['scores'])}\n"
                        f"📐 *Promedios últimos 5 partidos (Local | Visita):*\n"
                        f"  🚩 Córners: `{s_l['corners']:.0f}` | `{s_v['corners']:.0f}`\n"
                        f"  🟨 Tarjetas: `{s_l['tarjetas']:.0f}` | `{s_v['tarjetas']:.0f}`\n"
                        f"  🥅 Remates: `{s_l['remates']:.0f}` | `{s_v['remates']:.0f}`\n\n")
        
        if TOKEN and CHAT_ID:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                        data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
            print(f"✅ Reporte enviado a Telegram para {liga}")
        else:
            print(f"⚠️ Faltan credenciales de Telegram para {liga}")

if __name__ == "__main__":
    main()
