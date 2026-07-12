import os
import json
import pandas as pd
import glob
from datetime import datetime, timedelta
import pytz
import sys
import time

# Ajuste para importar módulos de la raíz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import BasketballAPI
from analyzer import MatchAnalyzer
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes

def cargar_configuracion_basket():
    with open("config/basketball/leagues.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        api_to_master = data.get("api_basketball_to_master", {})
        master_leagues_info = data.get("master_leagues", {})
    with open("config/basketball/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"].get("api_basketball", {"finished": ["FT"], "upcoming": ["NS"]})
    with open("config/basketball/team_aliases.json", "r", encoding="utf-8") as f:
        aliases_data = json.load(f)
    return api_to_master, master_leagues_info, statuses, aliases_data

def cargar_historico_mensual_basket():
    all_files = glob.glob("historico_mensual/basketball/historico_*.csv")
    if not all_files:
        return pd.DataFrame(columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'])
    li = [pd.read_csv(filename) for filename in all_files]
    df = pd.concat(li, axis=0, ignore_index=True)
    df['Date'] = pd.to_datetime(df['Date'], format='mixed').dt.strftime('%Y-%m-%d')
    return df

def guardar_historico_mensual_basket(df, meses_a_actualizar=None):
    os.makedirs("historico_mensual/basketball", exist_ok=True)
    if df.empty:
        return
    df_temp = df.copy()
    df_temp['Date_dt'] = pd.to_datetime(df_temp['Date'], format='mixed')
    df_temp['year_month'] = df_temp['Date_dt'].dt.to_period('M')
    
    for period, group in df_temp.groupby('year_month'):
        # Si se especificó una lista de meses permitidos a actualizar, filtramos.
        # Si no, guardamos los periodos que hayan cambiado o todos los involucrados.
        if meses_a_actualizar is None or period in meses_a_actualizar:
            filename = f'historico_mensual/football/historico_{period.year}_{period.month:02d}.csv'
            g_clean = group.drop(columns=['Date_dt', 'year_month'], errors='ignore')
            g_clean.sort_values(by='Date', ascending=False).to_csv(filename, index=False)

def normalizar_equipo(nombre, master_league_id, aliases_data, equipos_historicos, unmapped_log):
    global_map = aliases_data.get("global_aliases", {})
    conflict_map = aliases_data.get("conflicting_aliases", {})
    liga_conflicto = conflict_map.get(master_league_id, {})
    
    for n_oficial, variaciones in {**liga_conflicto, **global_map}.items():
        if nombre == n_oficial or nombre in variaciones:
            return n_oficial
            
    if master_league_id not in ["WOR_FRIENDLIES_CLUBS", "WOR_FRIENDLY_INTERNATIONAL"]:
        existe_en_historico = nombre in equipos_historicos
        estado = "EQUIPO_NUEVO" if not existe_en_historico else "ERROR_MAPEO"
        registro = {
            "team": nombre, 
            "master_league": master_league_id,
            "status": estado
        }
        if registro not in unmapped_log: 
            unmapped_log.append(registro)
    return nombre

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, api_to_master, statuses, aliases_data, unmapped_log):
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique())) if not df_hist.empty else set()
    for match in partidos_lista:
        liga_id = str(match["league"]["id"])
        status_short = match.get("status", {}).get("short", "")
        if liga_id in api_to_master and status_short in statuses.get("finished", []):
            h_name = match.get("teams", {}).get("home", {}).get("name", "")
            a_name = match.get("teams", {}).get("away", {}).get("name", "")
            h_team = normalizar_equipo(h_name, api_to_master[liga_id], aliases_data, equipos_historicos, unmapped_log)
            a_team = normalizar_equipo(a_name, api_to_master[liga_id], aliases_data, equipos_historicos, unmapped_log)
            
            scores = match.get("scores", {}).get("total", {})
            h_score = scores.get("home", 0)
            a_score = scores.get("away", 0)
            
            if not df_hist.empty and "HomeTeam" in df_hist.columns:
                mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = h_score, a_score
                    continue
            
            nuevo = {"League": match["league"]["name"], "Date": fecha_str, "HomeTeam": h_team, "AwayTeam": a_team, "FTHG": h_score, "FTAG": a_score}
            df_hist = pd.concat([df_hist, pd.DataFrame([nuevo])], ignore_index=True)
    return df_hist

def run_process(df_externo=None):
    os.makedirs("logs/basketball", exist_ok=True)
    os.makedirs("resultados/basketball", exist_ok=True)
    
    # Manejo independiente del token de Basketball
    TOKEN_BASKET = os.environ.get("TELEGRAM_BOT_TOKEN_BASKET")
    API_KEY = os.environ.get("API_BASKETBALL_KEY")
    API_KEY_2 = os.environ.get("API_FOOTBALL_KEY")
    api_to_master, _, statuses_map, team_aliases = cargar_configuracion_basket()
    ligas_permitidas = list(api_to_master.keys())
    
    df = df_externo if df_externo is not None else cargar_historico_mensual_basket()
    print(API_KEY)
    print(API_KEY_2)
    api = BasketballAPI(API_KEY)
    zona = pytz.timezone('America/Santiago')
    now = datetime.now(zona)
    unmapped_teams = []
    
    fecha_hoy_str = now.strftime("%Y-%m-%d")
    fecha_mañana_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    for i in range(-1, 2):
        f_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        data = api.get_data("games", {"date": f_str})
        if data and data.get("response"):
            df = actualizar_maestro_con_partidos(df, data["response"], f_str, api_to_master, statuses_map, team_aliases, unmapped_teams)
        time.sleep(1)

    # Rango de fechas procesadas (ayer, hoy, mañana)
    meses_afectados = set()
    for i in range(-1, 2):
        f_dt = now + timedelta(days=i)
        meses_afectados.add(pd.Period(f_dt.strftime("%Y-%m"), 'M'))
        f_str = f_dt.strftime("%Y-%m-%d")
        data = api.get_data("games", {"date": f_str, "timezone": "America/Santiago"})
        if data and data.get("response"):
            df = actualizar_maestro_con_partidos(df, data["response"], f_str, api_to_master, statuses_map, team_aliases, unmapped_teams)

    guardar_historico_mensual_basket(df, meses_afectados)
    analyzer = MatchAnalyzer(df)
    
    proyecciones_hoy, proyecciones_mañana = {}, {}
    
    def procesar_lote_partidos(lista_partidos):
        for match in lista_partidos:
            liga_id = str(match["league"]["id"])
            status_short = match.get("status", {}).get("short", "")
            if liga_id in ligas_permitidas and status_short in statuses_map.get("upcoming", []):
                h_name = match.get("teams", {}).get("home", {}).get("name", "")
                a_name = match.get("teams", {}).get("away", {}).get("name", "")
                h_team = normalizar_equipo(h_name, api_to_master[liga_id], team_aliases, set(), [])
                a_team = normalizar_equipo(a_name, api_to_master[liga_id], team_aliases, set(), [])
                
                proj = analyzer.get_basketball_projections(h_team, a_team)
                game_date = match.get("date", datetime.now().isoformat())
                proj['fecha_str'] = datetime.fromisoformat(game_date.replace("Z", "+00:00")).astimezone(zona).strftime("%Y-%m-%d")
                proj['hora'] = datetime.fromisoformat(game_date.replace("Z", "+00:00")).astimezone(zona).strftime("%H:%M")
                proj['pais'] = match.get("country", "")
                
                target = proyecciones_mañana if proj['fecha_str'] == fecha_mañana_str else proyecciones_hoy
                target.setdefault(match["league"]["name"], []).append(proj)

    hoy_data = api.get_data("games", {"date": fecha_hoy_str})
    if hoy_data and hoy_data.get("response"):
        procesar_lote_partidos(hoy_data["response"])
        
    manana_data = api.get_data("games", {"date": fecha_mañana_str})
    if manana_data and manana_data.get("response"):
        procesar_lote_partidos(manana_data["response"])
        
    if unmapped_teams:
        with open(f"logs/basketball/unmapped_basket_teams_{now.strftime('%Y%m%d')}.json", "w", encoding="utf-8") as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)
            
    # Nota: Si tus funciones de notificación soportan el token por parámetro, pásalo aquí; 
    # de lo contrario, asegúrate de que el notifier lea TELEGRAM_BOT_TOKEN_BASKET si corresponde.
    enviar_mensaje_telegram(f"🏀 *FIN DIA BASKET: {fecha_hoy_str}*", TOKEN_BASKET)
    enviar_bloque_reportes(proyecciones_hoy, "", analyzer, TOKEN_BASKET)
    if proyecciones_mañana:
        enviar_mensaje_telegram(f"🚀 *INICIO DIA BASKET: {fecha_mañana_str} (Ventana Anticipada)*")
        enviar_bloque_reportes(proyecciones_mañana, "Madrugada", analyzer, TOKEN_BASKET)
        
    print("✅ Proceso de Basketball completo.")