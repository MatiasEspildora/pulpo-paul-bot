import os
import json
import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests
from api_client import FootballAPI
from analyzer import MatchAnalyzer

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_KEY = os.environ.get("API_FOOTBALL_KEY")

def cargar_configuracion():
    """Carga de forma desacoplada los archivos de configuración."""
    with open("config/leagues.json", "r", encoding="utf-8") as f:
        leagues = json.load(f)["api_football"]
    with open("config/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
    with open("config/team_aliases.json", "r", encoding="utf-8") as f:
        aliases = json.load(f)
    return leagues, statuses, aliases

def normalizar_equipo(nombre, aliases, equipos_historicos, unmapped_log):
    """Homologa el nombre del equipo y registra los huérfanos para auditoría."""
    if nombre in aliases:
        nombre = aliases[nombre]
    
    if nombre not in equipos_historicos:
        if nombre not in unmapped_log:
            unmapped_log.append(nombre)
            
    return nombre

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, statuses, aliases, unmapped_log):
    """Actualiza o inserta los resultados finalizados utilizando el mapeo dinámico."""
    actualizados = 0
    agregados = 0
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique()))
    
    for match in partidos_lista:
        status_short = match["fixture"]["status"]["short"]
        if status_short in statuses["finished"]:
            h_team_raw = match["teams"]["home"]["name"]
            a_team_raw = match["teams"]["away"]["name"]
            
            h_team = normalizar_equipo(h_team_raw, aliases, equipos_historicos, unmapped_log)
            a_team = normalizar_equipo(a_team_raw, aliases, equipos_historicos, unmapped_log)
            
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

    os.makedirs("logs", exist_ok=True)
    os.makedirs("resultados", exist_ok=True)
    
    leagues_map, statuses_map, team_aliases = cargar_configuracion()
    ligas_permitidas = list(leagues_map.values())
    
    df = pd.read_csv(csv_path)
    analyzer = MatchAnalyzer(df)
    
    if not API_KEY:
        print("⚠️ Falta la clave API_FOOTBALL_KEY en el entorno.")
        return
        
    api = FootballAPI(API_KEY)
    zona_chile = pytz.timezone('America/Santiago')
    now_chile = datetime.now(zona_chile)
    
    unmapped_teams = []
    
    fecha_ayer_dt = now_chile - timedelta(days=1)
    fecha_ayer_str = fecha_ayer_dt.strftime("%Y-%m-%d")
    fecha_ayer_file = fecha_ayer_dt.strftime("%Y%m%d")
    
    fecha_hoy_str = now_chile.strftime("%Y-%m-%d")
    fecha_hoy_file = now_chile.strftime("%Y%m%d")
    
    # 1. Procesamiento de Ayer
    print(f"🔄 [Ayer] Consultando fixtures de la fecha {fecha_ayer_str}...")
    data_ayer = api.get_data("fixtures", {"date": fecha_ayer_str, "timezone": "America/Santiago"})
    if data_ayer and data_ayer.get("response"):
        with open(f"resultados/partidos_{fecha_ayer_file}.json", 'w', encoding='utf-8') as f:
            json.dump(data_ayer, f, ensure_ascii=False, indent=4)
        df = actualizar_maestro_con_partidos(df, data_ayer.get("response"), fecha_ayer_str, statuses_map, team_aliases, unmapped_teams)

    # 2. Procesamiento de Hoy
    archivo_hoy_local = f"resultados/partidos_{fecha_hoy_file}.json"
    if os.path.exists(archivo_hoy_local):
        with open(archivo_hoy_local, 'r', encoding='utf-8') as f:
            data_hoy = json.load(f)
    else:
        data_hoy = api.get_data("fixtures", {"date": fecha_hoy_str, "timezone": "America/Santiago"})
        if data_hoy:
            with open(archivo_hoy_local, 'w', encoding='utf-8') as f:
                json.dump(data_hoy, f, ensure_ascii=False, indent=4)

    df = actualizar_maestro_con_partidos(df, data_hoy.get("response", []), fecha_hoy_str, statuses_map, team_aliases, unmapped_teams)
    df.to_csv(csv_path, index=False)
    analyzer = MatchAnalyzer(df)

    # Registrar alertas si existen equipos sin mapear
    if unmapped_teams:
        with open("logs/unmapped_teams.json", "w", encoding="utf-8") as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)
        print(f"⚠️ Alerta: Se detectaron {len(unmapped_teams)} equipos sin mapear y se guardaron en logs/unmapped_teams.json")

    # 3. Proyecciones del día
    reporte_agrupado = {}
    equipos_historicos = set(df["HomeTeam"].dropna().unique()).union(set(df["AwayTeam"].dropna().unique()))

    for match in data_hoy.get("response", []):
        liga_id = match["league"]["id"]
        if liga_id in ligas_permitidas:
            status_short = match["fixture"]["status"]["short"]
            
            if status_short in statuses_map["excluded"]:
                continue
                
            fixture_date_utc = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00"))
            match_local = fixture_date_utc.astimezone(zona_chile)
            
            if status_short in statuses_map["upcoming"]:
                liga_nombre = match["league"]["name"]
                home_name = normalizar_equipo(match["teams"]["home"]["name"], team_aliases, equipos_historicos, unmapped_teams)
                away_name = normalizar_equipo(match["teams"]["away"]["name"], team_aliases, equipos_historicos, unmapped_teams)
                hora_formateada = match_local.strftime("%H:%M")
                
                proj = analyzer.get_projections(home_name, away_name)
                proj['hora'] = hora_formateada
                
                if liga_nombre not in reporte_agrupado:
                    reporte_agrupado[liga_nombre] = []
                reporte_agrupado[liga_nombre].append(proj)

    # Envío de reportes a Telegram...

if __name__ == "__main__":
    main()
