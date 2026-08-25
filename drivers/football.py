import os
import json
import pandas as pd
import glob
from datetime import datetime, timedelta
import pytz
import sys
import time
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import FootballAPI
from analyzer import MatchAnalyzer
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes

def cargar_configuracion():
    with open("config/football/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
    return {}, {}, statuses, {}

def cargar_historico_mensual():
    all_files = glob.glob("historico_mensual/football/historico_*.csv")
    default_cols = ['League', 'LeagueId', 'Country', 'Round', 'EsEliminatoria', 'Date', 'HomeTeamId', 'AwayTeamId', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HS', 'AS']
    if not all_files:
        return pd.DataFrame(columns=default_cols)
    li = [pd.read_csv(filename) for filename in all_files]
    df = pd.concat(li, axis=0, ignore_index=True)
    
    if 'Country' not in df.columns: df['Country'] = ''
    if 'LeagueId' not in df.columns: df['LeagueId'] = ''
    if 'Round' not in df.columns: df['Round'] = ''
    if 'EsEliminatoria' not in df.columns: df['EsEliminatoria'] = False
    if 'HomeTeamId' not in df.columns: df['HomeTeamId'] = pd.NA
    if 'AwayTeamId' not in df.columns: df['AwayTeamId'] = pd.NA
    if 'HTHG' not in df.columns: df['HTHG'] = pd.NA
    if 'HTAG' not in df.columns: df['HTAG'] = pd.NA
        
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
    cols_present = [c for c in default_cols if c in df.columns]
    df = df[cols_present + [c for c in df.columns if c not in cols_present]]
    return df

def guardar_historico_mensual(df, meses_a_actualizar=None):
    os.makedirs("historico_mensual/football", exist_ok=True)
    df_temp = df.copy()
    df_temp['Date_dt'] = pd.to_datetime(df_temp['Date'], format='mixed', errors='coerce')
    df_temp['year_month'] = df_temp['Date_dt'].dt.to_period('M')
    
    for period, group in df_temp.groupby('year_month'):
        if pd.isna(period):
            continue
        if meses_a_actualizar is None or period in meses_a_actualizar:
            filename = f'historico_mensual/football/historico_{period.year}_{period.month:02d}.csv'
            g_clean = group.drop(columns=['Date_dt', 'year_month'], errors='ignore')
            sort_cols = ['Date']
            if 'Country' in g_clean.columns: sort_cols.append('Country')
            if 'League' in g_clean.columns: sort_cols.append('League')
            sort_cols.extend(['HomeTeam', 'AwayTeam'])
            g_clean.sort_values(by=sort_cols, ascending=[False] + [True]*(len(sort_cols)-1)).to_csv(filename, index=False)

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, statuses):
    for match in partidos_lista:
        liga = match.get("league") or {}
        liga_id = liga.get("id") if liga else None
        liga_id_str = str(liga_id) if liga_id is not None else None

        if match.get("fixture", {}).get("status", {}).get("short") in statuses["finished"]:
            h_id = match.get("teams", {}).get("home", {}).get("id")
            a_id = match.get("teams", {}).get("away", {}).get("id")
            h_team = match.get("teams", {}).get("home", {}).get("name")
            a_team = match.get("teams", {}).get("away", {}).get("name")

            league_name = liga.get("name")
            league_country = liga.get("country")
            
            h_ht_score = match.get("score", {}).get("halftime", {}).get("home")
            a_ht_score = match.get("score", {}).get("halftime", {}).get("away")

            if not df_hist.empty and "HomeTeamId" in df_hist.columns:
                base_mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeamId"] == h_id) & (df_hist["AwayTeamId"] == a_id)
                if base_mask.any():
                    idx = df_hist[base_mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = match.get("goals", {}).get("home"), match.get("goals", {}).get("away")
                    df_hist.at[idx, "HTHG"], df_hist.at[idx, "HTAG"] = h_ht_score, a_ht_score
                    continue
                    
                legacy_mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
                if legacy_mask.any():
                    idx = df_hist[legacy_mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = match.get("goals", {}).get("home"), match.get("goals", {}).get("away")
                    df_hist.at[idx, "HTHG"], df_hist.at[idx, "HTAG"] = h_ht_score, a_ht_score
                    df_hist.at[idx, "HomeTeamId"], df_hist.at[idx, "AwayTeamId"] = h_id, a_id
                    continue

            ronda_texto = (liga.get("round") or "").lower()
            palabras_clave = ["round", "quarter", "semi", "final", "elimination", "playoff", "play-off", "qualifying"]
            es_eliminatoria = any(palabra in ronda_texto for palabra in palabras_clave)

            nuevo = {
                "League": league_name,
                "LeagueId": liga_id_str,
                "Country": league_country,
                "Round": liga.get("round", ""),              
                "EsEliminatoria": es_eliminatoria, 
                "Date": fecha_str,
                "HomeTeamId": h_id,
                "AwayTeamId": a_id,
                "HomeTeam": h_team,
                "AwayTeam": a_team,
                "FTHG": match.get("goals", {}).get("home"),
                "FTAG": match.get("goals", {}).get("away"),
                "HTHG": h_ht_score,
                "HTAG": a_ht_score
            }
            df_hist = pd.concat([df_hist, pd.DataFrame([nuevo])], ignore_index=True)
    return df_hist

# 🔥 NUEVA FUNCIÓN: Infiere la liga local del equipo desde la Base de Datos
def obtener_liga_domestica(df, team_id, team_name):
    if df is None or df.empty: return ""
    try:
        if pd.notna(team_id) and str(team_id).strip() != "" and str(team_id) != "None":
            mask = (df['HomeTeamId'] == team_id) | (df['AwayTeamId'] == team_id)
        else:
            mask = (df['HomeTeam'] == team_name) | (df['AwayTeam'] == team_name)
        
        # Filtramos partidos de Copa/Mata-Mata para encontrar su liga habitual
        mask_league = mask & (df['EsEliminatoria'] == False) & (~df['League'].fillna("").str.contains("Cup|Copa|Pokal|Trophy|Taça|Coppa|Coupe|Shield", case=False))
        df_team = df[mask_league]
        
        if not df_team.empty:
            liga = df_team['League'].mode().iloc[0]
            # Pequeña limpieza visual
            liga = str(liga).replace("Primera División", "1ra").replace("Segunda División", "2da")
            return liga
    except Exception:
        pass
    return ""

def run_process(df_externo=None):
    os.makedirs("logs/football", exist_ok=True)
    os.makedirs("resultados/football", exist_ok=True)
    
    try:
        API_KEY = os.environ.get("API_FOOTBALL_KEY")
        _, _, statuses_map, _ = cargar_configuracion()
        
        df = df_externo if df_externo is not None else cargar_historico_mensual()
        
        api = FootballAPI(API_KEY)
        zona = pytz.timezone('America/Santiago')
        now = datetime.now(zona)
        hora_actual = now.hour
        
        fechas_a_procesar = [now.strftime("%Y-%m-%d")] 
        
        if hora_actual >= 20: 
            fechas_a_procesar.append((now + timedelta(days=1)).strftime("%Y-%m-%d"))
        
        datos_fechas = {}
        meses_afectados = set()
        
        print(f"⚽ [FOOTBALL] Iniciando descarga para fechas: {fechas_a_procesar}")
        
        for i in range(-1, 2): 
            f_dt = now + timedelta(days=i)
            f_str = f_dt.strftime("%Y-%m-%d")
            
            if i == -1 or f_str in fechas_a_procesar:
                try:
                    meses_afectados.add(pd.Period(f_dt.strftime("%Y-%m"), 'M'))
                    file_path = f"resultados/football/partidos_{f_str}.json"
                    partidos_del_dia = None
                    origen_datos = "🌐 API" 
                    
                    try:
                        data = api.get_data("fixtures", {"date": f_str, "timezone": "America/Santiago"})
                        time.sleep(1.5) 
                    except Exception:
                        data = None

                    if data and data.get("response"):
                        partidos_del_dia = data["response"]
                        try:
                            with open(file_path, "w", encoding="utf-8") as f:
                                json.dump(partidos_del_dia, f, ensure_ascii=False, indent=4)
                        except Exception as e:
                            print(f"⚠️ [FOOTBALL] Error al guardar caché: {e}")
                    else:
                        origen_datos = "📂 LOCAL" 
                        if os.path.exists(file_path):
                            try:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    partidos_del_dia = json.load(f)
                            except Exception:
                                partidos_del_dia = None
                        
                    if partidos_del_dia:
                        print(f"✔️ [FOOTBALL] {f_str} procesado desde {origen_datos} ({len(partidos_del_dia)} partidos).")
                        if f_str in fechas_a_procesar:
                            datos_fechas[f_str] = partidos_del_dia
                            
                        df = actualizar_maestro_con_partidos(df, partidos_del_dia, f_str, statuses_map)
                    else:
                        print(f"❌ [FOOTBALL] Sin datos para {f_str} (Ni API ni LOCAL).")
                        
                except Exception as e:
                    print(f"❌ [FOOTBALL] Error procesando el día {f_str}: {e}")
                    print(traceback.format_exc())
                    continue 

        guardar_historico_mensual(df, meses_afectados)
            
        analyzer = MatchAnalyzer(df)
        proyecciones_globales = {} 
        
        def procesar_lote_partidos(lista_partidos):
            for match in lista_partidos:
                try:
                    if match.get("fixture", {}).get("status", {}).get("short") in statuses_map["upcoming"]:
                        
                        date_str = match.get("fixture", {}).get("date", "")
                        if not date_str:
                            continue
                            
                        dt_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(zona)
                        
                        if dt_obj < now:
                            continue
                            
                        h_name = match.get("teams", {}).get("home", {}).get("name")
                        a_name = match.get("teams", {}).get("away", {}).get("name")
                        h_id = match.get("teams", {}).get("home", {}).get("id")
                        a_id = match.get("teams", {}).get("away", {}).get("id")
                        
                        proj = analyzer.get_projections(h_name, a_name, h_id, a_id)
                        
                        proj['fecha_str'] = dt_obj.strftime("%Y-%m-%d")
                        proj['hora'] = dt_obj.strftime("%H:%M")
                        pais = match.get("league", {}).get("country", "World")
                        liga = match.get("league", {}).get("name", "Unknown")
                        proj['pais'] = pais
                        
                        ronda_texto = (match.get("league", {}).get("round") or "").lower()
                        palabras_clave = ["round", "quarter", "semi", "final", "elimination", "playoff", "play-off", "qualifying"]
                        proj['es_eliminatoria'] = any(palabra in ronda_texto for palabra in palabras_clave)
                        
                        # 🔥 AÑADIMOS LA LIGA DOMÉSTICA PARA LA AUTOPSIA
                        proj['local_league'] = obtener_liga_domestica(df, h_id, h_name)
                        proj['visita_league'] = obtener_liga_domestica(df, a_id, a_name)
                        
                        proyecciones_globales.setdefault((pais, liga), []).append(proj)
                except Exception as e:
                    continue

        print("⚽ [FOOTBALL] Generando proyecciones globales...")
        for fecha in fechas_a_procesar:
             procesar_lote_partidos(datos_fechas.get(fecha, []))
                
        if hora_actual < 12: titulo_bloque = "Turno Mañana"
        elif hora_actual < 17: titulo_bloque = "Turno Mediodía"
        elif hora_actual < 20: titulo_bloque = "Turno Latam"
        else: titulo_bloque = "Turno Nocturno"

        if proyecciones_globales:
            enviar_bloque_reportes(proyecciones_globales, titulo_bloque, analyzer)
        else:
            enviar_mensaje_telegram(f"⚠️ No hay partidos proyectables en el {titulo_bloque}.")

        print("✅ [FOOTBALL] Proceso completo con éxito.")

    except Exception as e:
        print(f"❌ [FOOTBALL] Error crítico: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    run_process()
