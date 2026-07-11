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

# Diccionario de banderas para embellecer los reportes
BANDERAS = {
    "Argentina": "🇦🇷", "Chile": "🇨🇱", "World": "🌍", "Australia": "🇦🇺", 
    "Belarus": "🇧🇾", "Ecuador": "🇪🇨", "USA": "🇺🇸", "Russia": "🇷🇺",
    "Finland": "🇫🇮", "Paraguay": "🇵🇾", "South-Korea": "🇰🇷", "Estonia": "🇪🇪",
    "Ireland": "🇮🇪", "Kazakhstan": "🇰🇿", "Lebanon": "🇱🇧", "Zimbabwe": "🇿🇼",
    "Kyrgyzstan": "🇰🇬", "Latvia": "🇱🇻", "Brazil": "🇧🇷", "Peru": "🇵🇪", "China": "🇨🇳"
}

def cargar_configuracion():
    """Carga de forma desacoplada los archivos de configuración."""
    with open("config/leagues.json", "r", encoding="utf-8") as f:
        config_leagues = json.load(f)
        # Extraemos el mapeo de la API hacia el maestro
        api_to_master = config_leagues.get("api_football_to_master", {})
        # También podemos extraer la data maestra si la necesitamos
        master_leagues_info = config_leagues.get("master_leagues", {})
        
    with open("config/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
        
    with open("config/team_aliases.json", "r", encoding="utf-8") as f:
        aliases = json.load(f)
        
    return api_to_master, master_leagues_info, statuses, aliases

def normalizar_equipo(nombre, master_league_id, aliases, equipos_historicos, unmapped_log):
    """Homologa el nombre del equipo anidado por liga y registra los huérfanos."""
    # Buscar dentro de la liga correspondiente
    liga_aliases = aliases.get(master_league_id, {})
    
    # Recorrer los alias para ver si el 'nombre' raw coincide con alguna variación
    for nombre_oficial, lista_variaciones in liga_aliases.items():
        if nombre == nombre_oficial or nombre in lista_variaciones:
            nombre = nombre_oficial
            break
    
    # Si no está en el histórico, lo registramos para auditoría con su liga
    if nombre not in equipos_historicos:
        registro_log = {"team": nombre, "master_league": master_league_id}
        if registro_log not in unmapped_log:
            unmapped_log.append(registro_log)
            
    return nombre

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, api_to_master, statuses, aliases, unmapped_log):
    """Actualiza o inserta resultados finalizados filtrando por ligas mapeadas."""
    actualizados = 0
    agregados = 0
    equipos_historicos = set(df_hist["HomeTeam"].dropna().unique()).union(set(df_hist["AwayTeam"].dropna().unique()))
    
    # Convertir a strings por seguridad al buscar en diccionarios JSON
    ligas_permitidas = list(api_to_master.keys())
    
    for match in partidos_lista:
        liga_id_raw = str(match["league"]["id"])
        
        if liga_id_raw in ligas_permitidas:
            status_short = match["fixture"]["status"]["short"]
            master_league_id = api_to_master[liga_id_raw] # Ej: ARG_PB_METRO
            
            if status_short in statuses["finished"]:
                h_team_raw = match["teams"]["home"]["name"]
                a_team_raw = match["teams"]["away"]["name"]
                
                # Pasamos el master_league_id a la función normalizadora
                h_team = normalizar_equipo(h_team_raw, master_league_id, aliases, equipos_historicos, unmapped_log)
                a_team = normalizar_equipo(a_team_raw, master_league_id, aliases, equipos_historicos, unmapped_log)
                
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
    
    # 1. Cargar nueva estructura
    api_to_master, master_leagues_info, statuses_map, team_aliases = cargar_configuracion()
    ligas_permitidas = list(api_to_master.keys())
    
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
        df = actualizar_maestro_con_partidos(df, data_ayer.get("response"), fecha_ayer_str, api_to_master, statuses_map, team_aliases, unmapped_teams)

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

    df = actualizar_maestro_con_partidos(df, data_hoy.get("response", []), fecha_hoy_str, api_to_master, statuses_map, team_aliases, unmapped_teams)
    df.to_csv(csv_path, index=False)
    analyzer = MatchAnalyzer(df)

    if unmapped_teams:
        with open("logs/unmapped_teams.json", "w", encoding="utf-8") as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)
        print(f"⚠️ Alerta: Se detectaron {len(unmapped_teams)} equipos sin mapear en las ligas seguidas.")
    else:
        if os.path.exists("logs/unmapped_teams.json"):
            os.remove("logs/unmapped_teams.json")

    # 3. Proyecciones del día
    reporte_agrupado = {}
    equipos_historicos = set(df["HomeTeam"].dropna().unique()).union(set(df["AwayTeam"].dropna().unique()))

    for match in data_hoy.get("response", []):
        liga_id_raw = str(match["league"]["id"])
        
        if liga_id_raw in ligas_permitidas:
            status_short = match["fixture"]["status"]["short"]
            master_league_id = api_to_master[liga_id_raw]
            
            if status_short in statuses_map["excluded"]:
                continue
                
            fixture_date_utc = datetime.fromisoformat(match["fixture"]["date"].replace("Z", "+00:00"))
            match_local = fixture_date_utc.astimezone(zona_chile)
            
            if status_short in statuses_map["upcoming"]:
                liga_nombre = match["league"]["name"]
                pais = match["league"]["country"] # Obtenemos el país para la bandera
                
                home_name = normalizar_equipo(match["teams"]["home"]["name"], master_league_id, team_aliases, equipos_historicos, unmapped_teams)
                away_name = normalizar_equipo(match["teams"]["away"]["name"], master_league_id, team_aliases, equipos_historicos, unmapped_teams)
                hora_formateada = match_local.strftime("%H:%M")
                
                proj = analyzer.get_projections(home_name, away_name)
                proj['hora'] = hora_formateada
                proj['pais'] = pais # Guardamos el país
                
                if liga_nombre not in reporte_agrupado:
                    reporte_agrupado[liga_nombre] = []
                reporte_agrupado[liga_nombre].append(proj)

    # 4. Envío de reportes a Telegram con formato mejorado y validación de historial
    for liga, proyecciones in reporte_agrupado.items():
        if not proyecciones:
            continue
            
        top_3 = analyzer.get_top_by_league(proyecciones, n=3)
        pais_liga = top_3[0].get('pais', 'World')
        bandera = BANDERAS.get(pais_liga, "🏴")
        
        mensaje = f"🏆 {bandera} *TOP 3: {liga}*\n\n"
        
        for p in top_3:
            s_l = analyzer.get_team_stats(p['local'])
            s_v = analyzer.get_team_stats(p['visita'])
            
            # Cabecera con Hora y Equipos debajo ordenados claramente
            mensaje += f"🕒 `{p['hora']}`\n⚽ *{p['local']}* vs *{p['visita']}*\n"
            mensaje += (f"📊 Probabilidades: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                        f"🎯 Ambos anotan: {p['btts']:.0%} | Marcadores: {', '.join(p['scores'])}\n")
            
            # Validar si realmente tenemos historial registrado para ambos equipos
            count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
            count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0
            
            if count_l > 0 and count_v > 0:
                mensaje += (f"📐 *Promedios últimos partidos ({count_l}p | {count_v}p):*\n"
                            f"  🚩 Córners: `{s_l['corners']:.0f}` | `{s_v['corners']:.0f}`\n"
                            f"  🟨 Tarjetas: `{s_l['tarjetas']:.0f}` | `{s_v['tarjetas']:.0f}`\n"
                            f"  🥅 Remates: `{s_l['remates']:.0f}` | `{s_v['remates']:.0f}`\n\n")
            else:
                mensaje += "⚠️ *Sin historial suficiente para promedios detallados.*\n\n"
        
        if TOKEN and CHAT_ID:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
            print(f"✅ Reporte enviado a Telegram para {liga}")
        else:
            print(f"⚠️ Faltan credenciales de Telegram para {liga}")

if __name__ == "__main__":
    main()
