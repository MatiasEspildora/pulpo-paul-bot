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

from api_client import FootballAPI
from analyzer import MatchAnalyzer
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes

def cargar_configuracion():
    with open("config/football/leagues.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        api_to_master = data.get("api_football_to_master", {})
        master_leagues_info = data.get("master_leagues", {})
    with open("config/football/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
    with open("config/football/team_aliases.json", "r", encoding="utf-8") as f:
        aliases_data = json.load(f)
    return api_to_master, master_leagues_info, statuses, aliases_data

def cargar_historico_mensual():
    all_files = glob.glob("historico_mensual/football/historico_*.csv")
    if not all_files:
        return pd.DataFrame(columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HS', 'AS'])
    li = [pd.read_csv(filename) for filename in all_files]
    df = pd.concat(li, axis=0, ignore_index=True)
    df['Date'] = pd.to_datetime(df['Date'], format='mixed').dt.strftime('%Y-%m-%d')
    return df

def guardar_historico_mensual(df, meses_a_actualizar=None):
    os.makedirs("historico_mensual/football", exist_ok=True)
    df_temp = df.copy()
    df_temp['Date_dt'] = pd.to_datetime(df_temp['Date'], format='mixed')
    df_temp['year_month'] = df_temp['Date_dt'].dt.to_period('M')
    
    for period, group in df_temp.groupby('year_month'):
        if meses_a_actualizar is None or period in meses_a_actualizar:
            filename = f'historico_mensual/football/historico_{period.year}_{period.month:02d}.csv'
            g_clean = group.drop(columns=['Date_dt', 'year_month'], errors='ignore')
            g_clean.sort_values(by='Date', ascending=False).to_csv(filename, index=False)
            
def normalizar_equipo(nombre, master_league_id, aliases_data, equipos_historicos, unmapped_log):
    global_map = aliases_data.get("global_aliases", {})
    conflict_map = aliases_data.get("conflicting_aliases", {})
    liga_conflicto = conflict_map.get(master_league_id, {})
    
    # 1. Intentar mapear
    for n_oficial, variaciones in {**liga_conflicto, **global_map}.items():
        if nombre == n_oficial or nombre in variaciones:
            return n_oficial
            
    # 2. Si no se mapeó, clasificar el error
    if master_league_id not in ["WOR_FRIENDLIES_CLUBS", "WOR_FRIENDLY_INTERNATIONAL"]:
        existe_en_historico = nombre in equipos_historicos
        estado = "EQUIPO_NUEVO" if not existe_en_historico else "ERROR_MAPEO"
        
        registro = {
            "team": nombre, 
            "master_league": master_league_id,
            "status": estado
        }
        
        ya_registrado = any(r.get("team") == nombre and r.get("master_league") == master_league_id for r in unmapped_log)
        if not ya_registrado: 
            unmapped_log.append(registro)
            
    return nombre

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, api_to_master, statuses, aliases_data, unmapped_log):
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique())) if not df_hist.empty else set()
    for match in partidos_lista:
        liga_id = str(match["league"]["id"])
        if liga_id in api_to_master and match["fixture"]["status"]["short"] in statuses["finished"]:
            h_team = normalizar_equipo(match["teams"]["home"]["name"], api_to_master[liga_id], aliases_data, equipos_historicos, unmapped_log)
            a_team = normalizar_equipo(match["teams"]["away"]["name"], api_to_master[liga_id], aliases_data, equipos_historicos, unmapped_log)
            
            if not df_hist.empty and "HomeTeam" in df_hist.columns:
                mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = match["goals"]["home"], match["goals"]["away"]
                    continue
                    
            nuevo = {"League": match["league"]["name"], "Date": fecha_str, "HomeTeam": h_team, "AwayTeam": a_team, "FTHG": match["goals"]["home"], "FTAG": match["goals"]["away"]}
            df_hist = pd.concat([df_hist, pd.DataFrame([nuevo])], ignore_index=True)
    return df_hist

def run_process(df_externo=None):
    os.makedirs("logs/football", exist_ok=True)
    os.makedirs("resultados/football", exist_ok=True)
    
    API_KEY = os.environ.get("API_FOOTBALL_KEY")
    api_to_master, _, statuses_map, team_aliases = cargar_configuracion()
    ligas_permitidas = list(api_to_master.keys())
    
    # Cargar histórico desde la carpeta modular mensual
    df = df_externo if df_externo is not None else cargar_historico_mensual()
    
    api = FootballAPI(API_KEY)
    zona = pytz.timezone('America/Santiago')
    now = datetime.now(zona)
    unmapped_teams = []
    
    fecha_hoy_str = now.strftime("%Y-%m-%d")
    fecha_mañana_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Almacén temporal en memoria para las proyecciones
    datos_fechas = {}
    
    # Procesamiento inteligente de días con caché optimizado
    meses_afectados = set()
    for i in range(-1, 2):
        f_dt = now + timedelta(days=i)
        meses_afectados.add(pd.Period(f_dt.strftime("%Y-%m"), 'M'))
        f_str = f_dt.strftime("%Y-%m-%d")
        
        file_path = f"resultados/football/partidos_{f_str}.json"
        partidos_del_dia = None
        
        # Usamos caché estricto solo para días pasados
        es_dia_pasado = f_str < fecha_hoy_str
        if es_dia_pasado and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    partidos_del_dia = json.load(f)
            except Exception:
                pass
                
        # Consultar a la API si es hoy/mañana o si no existe el archivo anterior
        if not partidos_del_dia:
            data = api.get_data("fixtures", {"date": f_str, "timezone": "America/Santiago"})
            if data and data.get("response"):
                partidos_del_dia = data["response"]
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(partidos_del_dia, f, ensure_ascii=False, indent=4)
            time.sleep(1)
            
        if partidos_del_dia:
            datos_fechas[f_str] = partidos_del_dia
            df = actualizar_maestro_con_partidos(df, partidos_del_dia, f_str, api_to_master, statuses_map, team_aliases, unmapped_teams)
    
    # Guardar únicamente los meses que sufrieron cambios en esta ejecución
    guardar_historico_mensual(df, meses_afectados)
        
    analyzer = MatchAnalyzer(df)
    
    # Proyecciones reutilizando los datos en memoria
    proyecciones_hoy, proyecciones_mañana = {}, {}
    
    def procesar_lote_partidos(lista_partidos):
        for match in lista_partidos:
            if str(match["league"]["id"]) in ligas_permitidas and match["fixture"]["status"]["short"] in statuses_map["upcoming"]:
                h_name = normalizar_equipo(match["teams"]["home"]["name"], api_to_master[str(match["league"]["id"])], team_aliases, set(), [])
                a_name = normalizar_equipo(match["teams"]["away"]["name"], api_to_master[str(match["league"]["id"])], team_aliases, set(), [])
                
                proj = analyzer.get_projections(h_name, a_name)
                proj['fecha_str'] = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00")).astimezone(zona).strftime("%Y-%m-%d")
                proj['hora'] = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00")).astimezone(zona).strftime("%H:%M")
                proj['pais'] = match["league"]["country"]
                
                target = proyecciones_mañana if match["fixture"]["date"] > fecha_mañana_str else proyecciones_hoy
                target.setdefault(match["league"]["name"], []).append(proj)

    procesar_lote_partidos(datos_fechas.get(fecha_hoy_str, []))
    procesar_lote_partidos(datos_fechas.get(fecha_mañana_str, []))
    
    if unmapped_teams:
        with open(f"logs/football/unmapped_teams_{now.strftime('%Y%m%d')}.json", "w", encoding="utf-8") as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)
            
    enviar_mensaje_telegram(f"🏁 *FIN DIA: {fecha_hoy_str}*")
    enviar_bloque_reportes(proyecciones_hoy, "", analyzer)
    if proyecciones_mañana:
        enviar_mensaje_telegram(f"🚀 *INICIO DIA: {fecha_mañana_str} (Ventana Anticipada)*")
        enviar_bloque_reportes(proyecciones_mañana, "Madrugada", analyzer)
        
    print("✅ Proceso completo.")
