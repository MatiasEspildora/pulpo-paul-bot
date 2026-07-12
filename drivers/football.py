import os
import json
import pandas as pd
from datetime import datetime, timedelta
import pytz
import sys

# Ajuste para importar módulos de la raíz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import FootballAPI
from analyzer import MatchAnalyzer
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes

def cargar_configuracion():
    with open("config/leagues.json", "r", encoding="utf-8") as f:
        config_leagues = json.load(f)
        api_to_master = config_leagues.get("api_football_to_master", {})
        master_leagues_info = config_leagues.get("master_leagues", {})
        
    with open("config/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
        
    with open("config/team_aliases.json", "r", encoding="utf-8") as f:
        aliases_data = json.load(f)
        
    return api_to_master, master_leagues_info, statuses, aliases_data

def normalizar_equipo(nombre, master_league_id, aliases_data, equipos_historicos, unmapped_log):
    global_map = aliases_data.get("global_aliases", {})
    conflict_map = aliases_data.get("conflicting_aliases", {})
    liga_conflicto = conflict_map.get(master_league_id, {})
    encontrado = False
    
    for nombre_oficial, lista_variaciones in liga_conflicto.items():
        if nombre == nombre_oficial or nombre in lista_variaciones:
            nombre = nombre_oficial
            encontrado = True
            break
    if not encontrado:
        for nombre_oficial, lista_variaciones in global_map.items():
            if nombre == nombre_oficial or nombre in lista_variaciones:
                nombre = nombre_oficial
                encontrado = True
                break
    excluir_auditoria = master_league_id in ["WOR_FRIENDLIES_CLUBS", "WOR_FRIENDLY_INTERNATIONAL"]
    if nombre not in equipos_historicos and not encontrado and not excluir_auditoria:
        registro_log = {"team": nombre, "master_league": master_league_id}
        if registro_log not in unmapped_log:
            unmapped_log.append(registro_log)
    return nombre

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, api_to_master, statuses, aliases_data, unmapped_log):
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique()))
    ligas_permitidas = list(api_to_master.keys())
    
    for match in partidos_lista:
        liga_id_raw = str(match["league"]["id"])
        if liga_id_raw in ligas_permitidas:
            status_short = match["fixture"]["status"]["short"]
            master_league_id = api_to_master[liga_id_raw]
            if status_short in statuses["finished"]:
                h_team = normalizar_equipo(match["teams"]["home"]["name"], master_league_id, aliases_data, equipos_historicos, unmapped_log)
                a_team = normalizar_equipo(match["teams"]["away"]["name"], master_league_id, aliases_data, equipos_historicos, unmapped_log)
                h_score, a_score, liga_nombre = match["goals"]["home"], match["goals"]["away"], match["league"]["name"]
                
                mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = h_score, a_score
                else:
                    nuevo_row = {"League": liga_nombre, "Date": fecha_str, "HomeTeam": h_team, "AwayTeam": a_team, "FTHG": h_score, "FTAG": a_score}
                    df_hist = pd.concat([df_hist, pd.DataFrame([nuevo_row])], ignore_index=True)
    return df_hist

def run_process():
    print("⚽ Iniciando proceso de Fútbol...")
    API_KEY = os.environ.get("API_FOOTBALL_KEY")
    csv_path = "historico_maestro_global.csv"
    
    api_to_master, _, statuses_map, team_aliases = cargar_configuracion()
    ligas_permitidas = list(api_to_master.keys())
    df = pd.read_csv(csv_path)
    api = FootballAPI(API_KEY)
    zona_chile = pytz.timezone('America/Santiago')
    now_chile = datetime.now(zona_chile)
    
    fecha_ayer_str = (now_chile - timedelta(days=1)).strftime("%Y-%m-%d")
    fecha_hoy_str = now_chile.strftime("%Y-%m-%d")
    fecha_mañana_str = (now_chile + timedelta(days=1)).strftime("%Y-%m-%d")
    
    unmapped_teams = []
    
    # Procesar partidos
    data_ayer = api.get_data("fixtures", {"date": fecha_ayer_str, "timezone": "America/Santiago"})
    if data_ayer and data_ayer.get("response"):
        df = actualizar_maestro_con_partidos(df, data_ayer.get("response"), fecha_ayer_str, api_to_master, statuses_map, team_aliases, unmapped_teams)
    
    data_hoy = api.get_data("fixtures", {"date": fecha_hoy_str, "timezone": "America/Santiago"})
    df = actualizar_maestro_con_partidos(df, data_hoy.get("response", []), fecha_hoy_str, api_to_master, statuses_map, team_aliases, unmapped_teams)
    
    data_mañana = api.get_data("fixtures", {"date": fecha_mañana_str, "timezone": "America/Santiago"})
    
    df.to_csv(csv_path, index=False)
    analyzer = MatchAnalyzer(df)

    # Proyecciones
    proyecciones_hoy, proyecciones_mañana = {}, {}
    
    def procesar_lote_partidos(lista_partidos):
        for match in lista_partidos:
            if str(match["league"]["id"]) in ligas_permitidas:
                status_short = match["fixture"]["status"]["short"]
                if status_short in statuses_map["upcoming"]:
                    h_name = normalizar_equipo(match["teams"]["home"]["name"], api_to_master[str(match["league"]["id"])], team_aliases, set(), [])
                    a_name = normalizar_equipo(match["teams"]["away"]["name"], api_to_master[str(match["league"]["id"])], team_aliases, set(), [])
                    
                    proj = analyzer.get_projections(h_name, a_name)
                    proj['hora'] = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00")).astimezone(zona_chile).strftime("%H:%M")
                    proj['pais'] = match["league"]["country"]
                    
                    target = proyecciones_mañana if match["fixture"]["date"] > fecha_mañana_str else proyecciones_hoy
                    target.setdefault(match["league"]["name"], []).append(proj)

    procesar_lote_partidos(data_hoy.get("response", []))
    if data_mañana and isinstance(data_mañana, dict):
        procesar_lote_partidos(data_mañana.get("response", []))

    enviar_mensaje_telegram(f"🏁 *FIN DIA: {fecha_hoy_str}*")
    enviar_bloque_reportes(proyecciones_hoy, "", analyzer)
    if proyecciones_mañana:
        enviar_mensaje_telegram(f"🚀 *INICIO DIA: {fecha_mañana_str} (Ventana Anticipada)*")
        enviar_bloque_reportes(proyecciones_mañana, "Madrugada", analyzer)
    
    print("✅ Proceso de Fútbol finalizado.")
