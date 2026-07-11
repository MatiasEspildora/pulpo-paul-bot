import os
import pandas as pd
from datetime import datetime, timedelta
import pytz
import json
from api_client import FootballAPI
from analyzer import MatchAnalyzer

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_KEY = os.environ.get("API_FOOTBALL_KEY")
LIGAS_PERMITIDAS = [10, 242, 254, 292, 649, 660, 1031, 1232, 1, 2, 13, 39, 61, 78, 135, 140, 265, 667]

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str):
    """Actualiza o inserta los resultados finalizados (FT) preservando estadísticas finas previas."""
    actualizados = 0
    agregados = 0
    
    for match in partidos_lista:
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            status_short = match["fixture"]["status"]["short"]
            
            # Solo procesar partidos finalizados oficialmente
            if status_short == "FT":
                h_team = match["teams"]["home"]["name"]
                a_team = match["teams"]["away"]["name"]
                h_score = match["goals"]["home"]
                a_score = match["goals"]["away"]
                liga_nombre = match["league"]["name"]
                
                mask = (df_hist["Date"] == fecha_str) & \
                       (df_hist["HomeTeam"] == h_team) & \
                       (df_hist["AwayTeam"] == a_team)
                       
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"] = h_score
                    df_hist.at[idx, "FTAG"] = a_score
                    actualizados += 1
                else:
                    nuevo_row = {
                        "League": liga_nombre,
                        "Date": fecha_str,
                        "HomeTeam": h_team,
                        "AwayTeam": a_team,
                        "FTHG": h_score,
                        "FTAG": a_score,
                        "HC": None, "AC": None,
                        "HY": None, "AY": None,
                        "HR": None, "AR": None,
                        "HS": None, "AS": None
                    }
                    df_hist = pd.concat([df_hist, pd.DataFrame([nuevo_row])], ignore_index=True)
                    agregados += 1
                    
    return df_hist

def main():
    csv_path = "historico_maestro_global.csv"
    if not os.path.exists(csv_path):
        print(f"❌ No se encontró el archivo {csv_path} en la raíz.")
        return

    df = pd.read_csv(csv_path)
    analyzer = MatchAnalyzer(df)
    
    if not API_KEY:
        print("⚠️ Falta la clave API_FOOTBALL_KEY en el entorno.")
        return
        
    api = FootballAPI(API_KEY)
    zona_chile = pytz.timezone('America/Santiago')
    now_chile = datetime.now(zona_chile)
    
    # Fechas operativas para ayer y hoy
    fecha_ayer_dt = now_chile - timedelta(days=1)
    fecha_ayer_str = fecha_ayer_dt.strftime("%Y-%m-%d")
    fecha_ayer_file = fecha_ayer_dt.strftime("%Y%m%d")
    
    fecha_hoy_str = now_chile.strftime("%Y-%m-%d")
    fecha_hoy_file = now_chile.strftime("%Y%m%d")
    
    if not os.path.exists("resultados"):
        os.makedirs("resultados")

    # 1. Petición y procesamiento de AYER (Actualización de resultados cerrados)
    print(f"🔄 [Ayer] Consultando fixtures de la fecha {fecha_ayer_str}...")
    data_ayer = api.get_data("fixtures", {"date": fecha_ayer_str, "timezone": "America/Santiago"})
    if data_ayer and data_ayer.get("response"):
        archivo_ayer = f"resultados/partidos_{fecha_ayer_file}.json"
        with open(archivo_ayer, 'w', encoding='utf-8') as f:
            json.dump(data_ayer, f, ensure_ascii=False, indent=4)
        df = actualizar_maestro_con_partidos(df, data_ayer.get("response"), fecha_ayer_str)

    # 2. Petición de HOY (Caché local o consulta a la API)
    archivo_hoy_local = f"resultados/partidos_{fecha_hoy_file}.json"
    if os.path.exists(archivo_hoy_local):
        print(f"📂 [Caché] Leyendo partidos del día {fecha_hoy_str} desde archivo local...")
        with open(archivo_hoy_local, 'r', encoding='utf-8') as f:
            data_hoy = json.load(f)
    else:
        print(f"🌐 [API] Consultando calendario del día {fecha_hoy_str}...")
        data_hoy = api.get_data("fixtures", {"date": fecha_hoy_str, "timezone": "America/Santiago"})
        if not data_hoy:
            print("⚠️ No se obtuvieron datos de la API para hoy.")
            df.to_csv(csv_path, index=False)
            return
        with open(archivo_hoy_local, 'w', encoding='utf-8') as f:
            json.dump(data_hoy, f, ensure_ascii=False, indent=4)

    # Actualizar también los FT de hoy que ya hayan concluido al momento de la ejecución
    df = actualizar_maestro_con_partidos(df, data_hoy.get("response", []), fecha_hoy_str)
    
    # Guardar cambios consolidados en el CSV maestro antes de calcular proyecciones
    df.to_csv(csv_path, index=False)
    analyzer = MatchAnalyzer(df)  # Recargar el analizador con la data más fresca

    # 3. Filtrado y Proyecciones para partidos válidos del día (Excluyendo CANC, PST y terminados antiguos)
    reporte_agrupado = {}
    partidos_en_ligas = 0
    partidos_omitidos = 0

    for match in data_hoy.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in LIGAS_PERMITIDAS:
            status_short = match["fixture"]["status"]["short"]
            
            # Descartar explícitamente cancelados, pospuestos o ya finalizados hace rato
            if status_short in ["CANC", "PST"]:
                partidos_omitidos += 1
                continue
                
            fixture_date_utc = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00"))
            match_local = fixture_date_utc.astimezone(zona_chile)
            
            # Si ya terminó hace más de 30 minutos, no entra en el reporte de proyecciones del día
            if match_local < (now_chile - timedelta(minutes=30)) and status_short == "FT":
                partidos_omitidos += 1
                continue
                
            # Solo permitir partidos por iniciar (NS) para proyecciones matemáticas limpias
            if status_short == "NS":
                partidos_en_ligas += 1
                liga_nombre = match["league"]["name"]
                home_name = match["teams"]["home"]["name"]
                away_name = match["teams"]["away"]["name"]
                hora_formateada = match_local.strftime("%H:%M")
                
                proj = analyzer.get_projections(home_name, away_name)
                proj['hora'] = hora_formateada
                
                if liga_nombre not in reporte_agrupado:
                    reporte_agrupado[liga_nombre] = []
                reporte_agrupado[liga_nombre].append(proj)

    print(f"🎯 Partidos listos para pronóstico (NS): {partidos_en_ligas}")
    print(f"🕒 Partidos omitidos/finalizados/suspendidos: {partidos_omitidos}\n")
    
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
