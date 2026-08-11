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
    default_cols = ['League', 'Country', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HS', 'AS']
    if not all_files:
        return pd.DataFrame(columns=default_cols)
    li = [pd.read_csv(filename) for filename in all_files]
    df = pd.concat(li, axis=0, ignore_index=True)
    # Asegurar que la columna Country exista en historiales antiguos
    if 'Country' not in df.columns:
        df['Country'] = ''
    df['Date'] = pd.to_datetime(df['Date'], format='mixed').dt.strftime('%Y-%m-%d')
    # Reordenar columnas para consistencia
    cols_present = [c for c in default_cols if c in df.columns]
    df = df[cols_present + [c for c in df.columns if c not in cols_present]]
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
            # Ordenar incluyendo Country para evitar colisiones de ligas con mismo nombre en distintos paises
            sort_cols = ['Date']
            if 'Country' in g_clean.columns:
                sort_cols.append('Country')
            if 'League' in g_clean.columns:
                sort_cols.append('League')
            sort_cols.extend(['HomeTeam', 'AwayTeam'])
            g_clean.sort_values(by=sort_cols, ascending=[False] + [True]*(len(sort_cols)-1)).to_csv(filename, index=False)
            

def normalizar_equipo(nombre, master_league_id, aliases_data, equipos_historicos, unmapped_log):
    """
    Normaliza el nombre del equipo usando aliases cuando exista master_league_id.
    Si master_league_id es None, devolvemos el nombre tal cual (guardamos igualmente para histórico).
    """
    # Si no hay mapeo de liga, no intentamos normalizar
    if not master_league_id:
        return nombre

    # Intento de mapear usando datos de aliases (mantengo comportamiento simple)
    global_map = aliases_data.get("global_aliases", {})
    conflict_map = aliases_data.get("conflicting_aliases", {})
    liga_conflicto = conflict_map.get(master_league_id, {})

    for n_oficial, variaciones in {**liga_conflicto, **global_map}.items():
        if nombre == n_oficial or nombre in variaciones:
            return n_oficial

    # Si no se mapeó, registramos en el log de equipos no mapeados
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


def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, api_to_master, statuses, aliases_data, unmapped_teams, unmapped_leagues):
    """
    Ahora guarda TODOS los partidos finalizados independientemente de si la liga está mapeada.
    Si la liga no está en api_to_master, se agrega a unmapped_leagues para revisión.
    """
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique())) if not df_hist.empty else set()
    for match in partidos_lista:
        liga_id = str(match.get("league", {}).get("id")) if match.get("league") else None
        master_league = api_to_master.get(liga_id) if liga_id else None

        # Si el partido está finalizado, lo guardamos siempre
        if match.get("fixture", {}).get("status", {}).get("short") in statuses["finished"]:
            # Registrar liga no mapeada
            if liga_id and not master_league:
                unmapped_leagues.add((liga_id, match.get("league", {}).get("name")))

            h_team = normalizar_equipo(match.get("teams", {}).get("home", {}).get("name"), master_league, aliases_data, equipos_historicos, unmapped_teams)
            a_team = normalizar_equipo(match.get("teams", {}).get("away", {}).get("name"), master_league, aliases_data, equipos_historicos, unmapped_teams)

            league_name = match.get("league", {}).get("name")
            league_country = match.get("league", {}).get("country")

            if not df_hist.empty and "HomeTeam" in df_hist.columns:
                # Preparar columnas de League/Country si no existen para comparación
                league_col = df_hist["League"] if "League" in df_hist.columns else pd.Series([""] * len(df_hist))
                country_col = df_hist["Country"] if "Country" in df_hist.columns else pd.Series([""] * len(df_hist))

                mask = (
                    (df_hist["Date"] == fecha_str) &
                    (df_hist["HomeTeam"] == h_team) &
                    (df_hist["AwayTeam"] == a_team) &
                    (league_col == league_name) &
                    (country_col == league_country)
                )
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = match.get("goals", {}).get("home"), match.get("goals", {}).get("away")
                    continue

            nuevo = {
                "League": league_name,
                "Country": league_country,
                "Date": fecha_str,
                "HomeTeam": h_team,
                "AwayTeam": a_team,
                "FTHG": match.get("goals", {}).get("home"),
                "FTAG": match.get("goals", {}).get("away")
            }
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
    unmapped_leagues = set()
    
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
            df = actualizar_maestro_con_partidos(df, partidos_del_dia, f_str, api_to_master, statuses_map, team_aliases, unmapped_teams, unmapped_leagues)
    
    # Guardar únicamente los meses que sufrieron cambios en esta ejecución
    guardar_historico_mensual(df, meses_afectados)
        
    analyzer = MatchAnalyzer(df)
    
    # Proyecciones reutilizando los datos en memoria
    proyecciones_hoy, proyecciones_mañana = {}, {}
    
    def procesar_lote_partidos(lista_partidos):
        for match in lista_partidos:
            # Procesar proyecciones para todas las ligas, usando normalización cuando exista el mapeo
            liga_id = str(match.get("league", {}).get("id")) if match.get("league") else None
            master = api_to_master.get(liga_id)
            if match.get("fixture", {}).get("status", {}).get("short") in statuses_map["upcoming"]:
                h_name = normalizar_equipo(match.get("teams", {}).get("home", {}).get("name"), master, team_aliases, set(), [])
                a_name = normalizar_equipo(match.get("teams", {}).get("away", {}).get("name"), master, team_aliases, set(), [])
                
                proj = analyzer.get_projections(h_name, a_name)
                proj['fecha_str'] = datetime.fromisoformat(match.get("fixture", {}).get("date").replace("Z", "+00:00")).astimezone(zona).strftime("%Y-%m-%d")
                proj['hora'] = datetime.fromisoformat(match.get("fixture", {}).get("date").replace("Z", "+00:00")).astimezone(zona).strftime("%H:%M")
                proj['pais'] = match.get("league", {}).get("country")
                
                target = proyecciones_mañana if match.get("fixture", {}).get("date") > fecha_mañana_str else proyecciones_hoy
                target.setdefault(match.get("league", {}).get("name"), []).append(proj)

    procesar_lote_partidos(datos_fechas.get(fecha_hoy_str, []))
    procesar_lote_partidos(datos_fechas.get(fecha_mañana_str, []))
    
    # Guardar logs de elementos no mapeados para revisión
    if unmapped_teams:
        with open(f"logs/football/unmapped_teams_{now.strftime('%Y%m%d')}.json", "w", encoding="utf-8") as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)

    if unmapped_leagues:
        # Convertir set de tuplas a lista de dicts
        ul = [{"id": lid, "name": name} for lid, name in sorted(unmapped_leagues, key=lambda x:int(x[0]) if x[0].isdigit() else x[0])]
        with open(f"logs/football/unmapped_leagues_{now.strftime('%Y%m%d')}.json", "w", encoding="utf-8") as f:
            json.dump(ul, f, ensure_ascii=False, indent=4)
            
     # Título dinámico dependiendo de la hora (si es antes de las 12:00, es Inicio de Día)
    if now.hour < 12:
        titulo_hoy = f"🌅 *INICIO DIA: {fecha_hoy_str}*"
    else:
        titulo_hoy = f"🏁 *FIN DIA: {fecha_hoy_str}*"

    enviar_mensaje_telegram(titulo_hoy)
    enviar_bloque_reportes(proyecciones_hoy, "", analyzer)
    
    # Solo envía la ventana anticipada en la ejecución nocturna (ej. a partir de las 22:00)
    if proyecciones_mañana and now.hour >= 22:
        enviar_mensaje_telegram(f"🚀 *INICIO DIA: {fecha_mañana_str} (Ventana Anticipada)*")
        enviar_bloque_reportes(proyecciones_mañana, "Madrugada", analyzer)

    print("✅ Proceso completo.")
