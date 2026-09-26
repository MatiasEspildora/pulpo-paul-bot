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
from bet_builder import BetBuilderEngine
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes

def cargar_configuracion():
    with open("config/football/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"]["api_football"]
    return {}, {}, statuses, {}

def cargar_ligas_con_estadisticas():
    rutas_posibles = ["config/Active_Leagues_Coverage.json", "config/football/Active_Leagues_Coverage.json"]
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    coverage = json.load(f)
                
                ligas_soportadas = {item.get("league_id", item.get("id")) for item in coverage if item.get("can_fetch_stats") is True}
                print(f"📊 [INFO] Cobertura Táctica Activa: {len(ligas_soportadas)} ligas configuradas para extracción de estadísticas.")
                return ligas_soportadas
            except Exception as e:
                print(f"⚠️ Aviso: Error leyendo {ruta} ({e}).")
    
    print("⚠️ Aviso: No se encontró Active_Leagues_Coverage.json. Se omitirán estadísticas.")
    return set()

def cargar_blacklist():
    ruta_blacklist = os.path.join("config", "blacklist.json")
    baneadas = set()
    if os.path.exists(ruta_blacklist):
        try:
            with open(ruta_blacklist, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("ligas_toxicas", []):
                    baneadas.add(f"{item.get('country')}_{item.get('league')}")
            if baneadas:
                print(f"🛡️ [AUTO-BLACKLIST] Se interceptarán {len(baneadas)} ligas tóxicas en cuarentena.")
        except Exception as e:
            print(f"⚠️ Aviso: Error leyendo {ruta_blacklist}: {e}")
    return baneadas

def cargar_historico_mensual(meses_clubes=6, meses_selecciones=24):
    all_files = sorted(glob.glob("historico_mensual/football/historico_*.csv"))
    
    default_cols = ['FixtureId', 'League', 'LeagueId', 'Country', 'Round', 'EsEliminatoria', 'Date', 'HomeTeamId', 'AwayTeamId', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HS', 'AS', 'Referee']
    if not all_files:
        return pd.DataFrame(columns=default_cols)
        
    # 🎯 1. Calcular puntos de corte para Carga Híbrida
    archivos_recientes = all_files[-meses_clubes:] if len(all_files) > meses_clubes else all_files
    archivos_antiguos = all_files[-meses_selecciones:-meses_clubes] if len(all_files) > meses_clubes else []
    
    li = []
    
    # 🎯 2. CARGA HÍBRIDA - ANTIGUOS (Solo Selecciones Nacionales)
    for filename in archivos_antiguos:
        try:
            temp_df = pd.read_csv(filename)
            if 'Country' in temp_df.columns:
                mask_selecciones = (temp_df['Country'] == 'World') | (temp_df['League'].fillna('').str.contains('World Cup|Nations League|Copa America|Euro Championship', case=False, na=False))
                temp_df = temp_df[mask_selecciones]
                if not temp_df.empty:
                    li.append(temp_df)
        except Exception:
            pass
            
    # 🎯 3. CARGA HÍBRIDA - RECIENTES (Todos los equipos del mundo)
    for filename in archivos_recientes:
        try:
            temp_df = pd.read_csv(filename)
            li.append(temp_df)
        except Exception:
            pass
            
    if not li:
        return pd.DataFrame(columns=default_cols)
        
    df = pd.concat(li, axis=0, ignore_index=True)
    
    # 🔥 FIX: Forzar FixtureId como enteros limpios (Int64) compatibles con vacíos sin alterar el disco
    if 'FixtureId' in df.columns:
        df['FixtureId'] = pd.to_numeric(df['FixtureId'], errors='coerce').astype('Int64')
    else:
        df['FixtureId'] = pd.Series(dtype='Int64')

    # Asegurar el estándar de las 24 columnas
    for col in default_cols:
        if col not in df.columns:
            df[col] = pd.NA
            
    if 'EsEliminatoria' not in df.columns: df['EsEliminatoria'] = False
    if 'Referee' not in df.columns: df['Referee'] = 'Desconocido'
        
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

STATS_DESCARGADAS_HOY = 0 
MAX_STATS_POR_RUN = 400

def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, statuses, api_client=None, ligas_soportadas=None, cosechar_stats=False):
    global STATS_DESCARGADAS_HOY
    if ligas_soportadas is None: ligas_soportadas = set()
    
    partidos_cosechados_nombres = []
    total_finalizados = 0
    
    for match in partidos_lista:
        liga = match.get("league") or {}
        liga_id = liga.get("id") if liga else None
        liga_id_str = str(liga_id) if liga_id is not None else None
        match_id = match.get("fixture", {}).get("id")

        if match.get("fixture", {}).get("status", {}).get("short") in statuses["finished"]:
            total_finalizados += 1
            h_id = match.get("teams", {}).get("home", {}).get("id")
            a_id = match.get("teams", {}).get("away", {}).get("id")
            h_team = match.get("teams", {}).get("home", {}).get("name")
            a_team = match.get("teams", {}).get("away", {}).get("name")

            league_name = liga.get("name")
            league_country = liga.get("country")
            
            h_ht_score = match.get("score", {}).get("halftime", {}).get("home")
            a_ht_score = match.get("score", {}).get("halftime", {}).get("away")
            
            referee_raw = match.get("fixture", {}).get("referee")
            referee_name = str(referee_raw).strip() if referee_raw else "Desconocido"

            stats_dict = {'HS': pd.NA, 'AS': pd.NA, 'HC': pd.NA, 'AC': pd.NA, 'HY': pd.NA, 'AY': pd.NA, 'HR': pd.NA, 'AR': pd.NA}
            necesita_stats = False
            
            idx_existente = None
            if not df_hist.empty and "HomeTeamId" in df_hist.columns:
                base_mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeamId"] == h_id) & (df_hist["AwayTeamId"] == a_id)
                if base_mask.any():
                    idx_existente = df_hist[base_mask].index[0]
                else:
                    legacy_mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
                    if legacy_mask.any():
                        idx_existente = df_hist[legacy_mask].index[0]

            if cosechar_stats and liga_id in ligas_soportadas and api_client is not None and STATS_DESCARGADAS_HOY < MAX_STATS_POR_RUN:
                ya_tiene_stats = False
                if idx_existente is not None and 'HS' in df_hist.columns:
                    ya_tiene_stats = pd.notna(df_hist.at[idx_existente, 'HS'])
                
                if not ya_tiene_stats:
                    necesita_stats = True
                    
            if necesita_stats:
                resp = api_client.get_fixture_statistics(match_id)
                STATS_DESCARGADAS_HOY += 1
                partidos_cosechados_nombres.append(f"{h_team} vs {a_team}")
                
                time.sleep(1.2) 
                
                if resp and resp.get("response"):
                    datos_stats = resp["response"]
                    for equipo_stats in datos_stats:
                        es_local = equipo_stats.get("team", {}).get("id") == h_id
                        prefijo = "H" if es_local else "A"
                        
                        for metrica in equipo_stats.get("statistics", []):
                            tipo = str(metrica.get("type"))
                            valor = metrica.get("value")
                            if valor is None: valor = 0
                                
                            if tipo == "Total Shots": stats_dict[f'{prefijo}S'] = int(valor)
                            elif tipo == "Corner Kicks": stats_dict[f'{prefijo}C'] = int(valor)
                            elif tipo == "Yellow Cards": stats_dict[f'{prefijo}Y'] = int(valor)
                            elif tipo == "Red Cards": stats_dict[f'{prefijo}R'] = int(valor)

            if idx_existente is not None:
                df_hist.at[idx_existente, "FixtureId"] = int(match_id) if pd.notna(match_id) else pd.NA
                df_hist.at[idx_existente, "FTHG"] = match.get("goals", {}).get("home")
                df_hist.at[idx_existente, "FTAG"] = match.get("goals", {}).get("away")
                df_hist.at[idx_existente, "HTHG"] = h_ht_score
                df_hist.at[idx_existente, "HTAG"] = a_ht_score
                df_hist.at[idx_existente, "HomeTeamId"] = h_id
                df_hist.at[idx_existente, "AwayTeamId"] = a_id
                df_hist.at[idx_existente, "Referee"] = referee_name
                
                if necesita_stats:
                    for k, v in stats_dict.items():
                        df_hist.at[idx_existente, k] = v
                continue

            ronda_texto = (liga.get("round") or "").lower()
            palabras_clave = ["round", "quarter", "semi", "final", "elimination", "playoff", "play-off", "qualifying"]
            es_eliminatoria = any(palabra in ronda_texto for palabra in palabras_clave)

            nuevo = {
                "FixtureId": int(match_id) if pd.notna(match_id) else pd.NA,
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
                "HTAG": a_ht_score,
                "Referee": referee_name
            }
            nuevo.update(stats_dict)
            
            df_hist = pd.concat([df_hist, pd.DataFrame([nuevo])], ignore_index=True)
            
    if total_finalizados > 0:
        cosechados = len(partidos_cosechados_nombres)
        omitidos = total_finalizados - cosechados
        print(f"✅ [RESUMEN] {fecha_str} - Terminados: {total_finalizados} | Táctica nueva: {cosechados} | Básicos o listos: {omitidos}")
        
        if cosechados > 0:
            if cosechados <= 2:
                detalle = " y ".join(partidos_cosechados_nombres)
            else:
                detalle = f"{partidos_cosechados_nombres[0]}, {partidos_cosechados_nombres[1]} y {cosechados - 2} más"
            print(f"   ↳ 📥 Extraídos: {detalle}")

    return df_hist

def obtener_liga_domestica(df, team_id, team_name):
    if df is None or df.empty: return ""
    try:
        if pd.notna(team_id) and str(team_id).strip() != "" and str(team_id) != "None":
            mask = (df['HomeTeamId'] == team_id) | (df['AwayTeamId'] == team_id)
        else:
            mask = (df['HomeTeam'] == team_name) | (df['AwayTeam'] == team_name)
        
        mask_league = mask & (df['EsEliminatoria'] == False) & (~df['League'].fillna("").str.contains("Cup|Copa|Pokal|Trophy|Taça|Coppa|Coupe|Shield", case=False))
        df_team = df[mask_league]
        
        if not df_team.empty:
            liga = df_team['League'].mode().iloc[0]
            liga = str(liga).replace("Primera División", "1ra").replace("Segunda División", "2da")
            return liga
    except Exception:
        pass
    return ""

def calcular_dias_descanso(df_global, team_id, fecha_actual_dt):
    if df_global is None or df_global.empty or pd.isna(team_id): 
        return 7
    try:
        mask = (df_global['HomeTeamId'] == team_id) | (df_global['AwayTeamId'] == team_id)
        pasados = df_global[mask & (df_global['Date_dt'] < fecha_actual_dt)]
        
        if pasados.empty: 
            return 7
            
        ultima_fecha = pasados['Date_dt'].max()
        dias = (fecha_actual_dt - ultima_fecha).days
        
        return max(0, min(dias, 15))
    except Exception:
        return 7

def registrar_predicciones(proyecciones_dict):
    archivo_log = "kpi/football/predicciones_log.csv"
    os.makedirs(os.path.dirname(archivo_log), exist_ok=True)
    
    filas = []
    for key, projs in proyecciones_dict.items():
        for p in projs:
            match_id = p.get('fixture_id')
            if pd.notna(match_id):
                match_id_val = str(int(match_id))
            else:
                match_id_val = f"{p.get('local_id', '')}_{p.get('visita_id', '')}_{p.get('fecha_str', '')}"
            if not match_id_val or match_id_val == "__": continue
            
            base = {
                'MatchId': match_id_val,
                'Fecha': p.get('fecha_str', ''),
                'Local': p.get('local', ''),
                'Visita': p.get('visita', ''),
                'HomeTeamId': p.get('local_id', ''),
                'AwayTeamId': p.get('visita_id', ''),
                'Estado': 'PENDIENTE',
                'ResultadoReal': '',
                'Acierto': ''
            }
            
            sgbb = p.get('sgbb', {})
            for sel, prob in sgbb.items():
                if prob >= 0.85:
                    filas.append({**base, 'Mercado': 'Mega-Misil SGBB', 'Seleccion': sel, 'Probabilidad': round(prob, 3)})
            
            probs_1x2 = p.get('probs', [0, 0, 0])
            prob_gana = max(probs_1x2[0], probs_1x2[2])
            sel_gana = p.get('local') if probs_1x2[0] > probs_1x2[2] else p.get('visita')
            
            if prob_gana >= 0.90:
                filas.append({**base, 'Mercado': 'Ganador Directo', 'Seleccion': f'Gana {sel_gana}', 'Probabilidad': round(prob_gana, 3)})
                
            prob_doble = max(p.get('prob_1X', 0), p.get('prob_X2', 0))
            sel_doble = "1X" if p.get('prob_1X', 0) > p.get('prob_X2', 0) else "X2"
            if prob_doble >= 0.80:
                filas.append({**base, 'Mercado': 'Doble Oportunidad', 'Seleccion': sel_doble, 'Probabilidad': round(prob_doble, 3)})
                
            if p.get('under_3_5', 0) >= 0.85: filas.append({**base, 'Mercado': 'Goles', 'Seleccion': '-3.5 Goles', 'Probabilidad': round(p['under_3_5'], 3)})
            if p.get('over_1_5', 0) >= 0.80: filas.append({**base, 'Mercado': 'Goles', 'Seleccion': '+1.5 Goles', 'Probabilidad': round(p['over_1_5'], 3)})
            if p.get('over_2_5', 0) >= 0.80: filas.append({**base, 'Mercado': 'Goles', 'Seleccion': '+2.5 Goles', 'Probabilidad': round(p['over_2_5'], 3)})
            if p.get('btts', 0) >= 0.80: filas.append({**base, 'Mercado': 'Ambos Anotan', 'Seleccion': 'Sí', 'Probabilidad': round(p['btts'], 3)})
            if p.get('btts_no', 0) >= 0.80: filas.append({**base, 'Mercado': 'Ambos Anotan', 'Seleccion': 'No', 'Probabilidad': round(p['btts_no'], 3)})

    if not filas: return

    df_nuevo = pd.DataFrame(filas)
    
    if os.path.exists(archivo_log):
        df_existente = pd.read_csv(archivo_log, dtype={'MatchId': 'str'})
        df_combined = pd.concat([df_existente, df_nuevo]).drop_duplicates(subset=['MatchId', 'Seleccion'], keep='last')
        df_combined.to_csv(archivo_log, index=False, encoding='utf-8')
    else:
        df_nuevo.to_csv(archivo_log, index=False, encoding='utf-8')

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
        
        ligas_soportadas = cargar_ligas_con_estadisticas()
        ligas_baneadas = cargar_blacklist()
        
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
                            
                        es_ayer = (i == -1)
                        df = actualizar_maestro_con_partidos(
                            df, partidos_del_dia, f_str, statuses_map, 
                            api_client=api, ligas_soportadas=ligas_soportadas, cosechar_stats=es_ayer
                        )
                    else:
                        print(f"❌ [FOOTBALL] Sin datos para {f_str} (Ni API ni LOCAL).")
                        
                except Exception as e:
                    print(f"❌ [FOOTBALL] Error procesando el día {f_str}: {e}")
                    print(traceback.format_exc())
                    continue 

        guardar_historico_mensual(df, meses_afectados)
        
        try:
            import evaluator
            print("📊 [AUDITORÍA] Evaluando predicciones pasadas...")
            evaluator.auditar_y_reportar()
        except Exception as e:
            print(f"⚠️ [AUDITORÍA] Error al evaluar KPIs: {e}")
            
        df['Date_dt'] = pd.to_datetime(df['Date'], errors='coerce').dt.tz_localize(None)

        analyzer = MatchAnalyzer(df)
        proyecciones_globales = {} 
        
        def procesar_lote_partidos(lista_partidos):
            partidos_validos = [
                m for m in lista_partidos 
                if m.get("fixture", {}).get("status", {}).get("short") in statuses_map["upcoming"]
            ]
            
            total_partidos = len(partidos_validos)
            print(f"   ↳ 🎯 Encontrados {total_partidos} partidos próximos para proyectar en este lote.")
            
            idx_match = 0
            for match in lista_partidos:
                try:
                    if match.get("fixture", {}).get("status", {}).get("short") in statuses_map["upcoming"]:
                        idx_match += 1
                        h_name = match.get("teams", {}).get("home", {}).get("name", "Local")
                        a_name = match.get("teams", {}).get("away", {}).get("name", "Visita")
                        
                        print(f"     [{idx_match}/{total_partidos}] Analizando: {h_name} vs {a_name}...")
                        
                        date_str = match.get("fixture", {}).get("date", "")
                        if not date_str:
                            continue
                            
                        dt_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(zona)
                        fecha_dt_naive = dt_obj.replace(tzinfo=None)
                        
                        if dt_obj < now:
                            continue
                            
                        pais = match.get("league", {}).get("country", "World")
                        liga = match.get("league", {}).get("name", "Unknown")
                        
                        es_seleccion = (pais == "World")
                        
                        if f"{pais}_{liga}" in ligas_baneadas:
                            print(f"       ⚠️ Omitido por Cuarentena (Blacklist): {pais} - {liga}")
                            continue
                            
                        h_id = match.get("teams", {}).get("home", {}).get("id")
                        a_id = match.get("teams", {}).get("away", {}).get("id")
                        
                        league_id_raw = match.get("league", {}).get("id")
                        league_id_str = str(league_id_raw) if league_id_raw is not None else None
                        
                        ronda_texto = (match.get("league", {}).get("round") or "").lower()
                        palabras_clave = ["round", "quarter", "semi", "final", "elimination", "playoff", "play-off", "qualifying"]
                        es_elimi = any(palabra in ronda_texto for palabra in palabras_clave)
                        
                        referee_str = str(match.get("fixture", {}).get("referee") or "Desconocido").strip()
                        
                        raw_proj = analyzer.get_projections(
                            h_name, a_name, h_id, a_id, 
                            league_id=league_id_str, 
                            es_eliminatoria=es_elimi,
                            referee=referee_str,
                            es_seleccion=es_seleccion
                        )
                        
                        raw_proj['fixture_id'] = match.get("fixture", {}).get("id")
                        raw_proj['referee'] = referee_str 
       
                        proj = BetBuilderEngine.generar_mercados(raw_proj)
                        
                        proj['fecha_str'] = dt_obj.strftime("%Y-%m-%d")
                        proj['hora'] = dt_obj.strftime("%H:%M")
                        proj['pais'] = pais
                        proj['es_eliminatoria'] = es_elimi
                        proj['local_league'] = obtener_liga_domestica(df, h_id, h_name)
                        proj['visita_league'] = obtener_liga_domestica(df, a_id, a_name)
                        
                        proj['dias_descanso_local'] = calcular_dias_descanso(df, h_id, fecha_dt_naive)
                        proj['dias_descanso_visita'] = calcular_dias_descanso(df, a_id, fecha_dt_naive)
                        
                        proj['fixture_id'] = raw_proj['fixture_id']
                        proj['referee'] = raw_proj['referee']
                        
                        proyecciones_globales.setdefault((pais, liga), []).append(proj)
                except Exception as e:
                    print(f"       ❌ Error procesando partido individual: {e}")
                    continue

        print("⚽ [FOOTBALL] Generando proyecciones globales...")
        for fecha in fechas_a_procesar:
             procesar_lote_partidos(datos_fechas.get(fecha, []))
                
        if hora_actual < 12: titulo_bloque = "Turno Mañana"
        elif hora_actual < 17: titulo_bloque = "Turno Mediodía"
        elif hora_actual < 20: titulo_bloque = "Turno Latam"
        else: titulo_bloque = "Turno Nocturno"

        if proyecciones_globales:
            registrar_predicciones(proyecciones_globales)
            enviar_bloque_reportes(proyecciones_globales, titulo_bloque, analyzer)
        else:
            enviar_mensaje_telegram(f"⚠️ No hay partidos proyectables en el {titulo_bloque}.")

        print("✅ [FOOTBALL] Proceso completo con éxito.")

    except Exception as e:
        print(f"❌ [FOOTBALL] Error crítico: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    run_process()
