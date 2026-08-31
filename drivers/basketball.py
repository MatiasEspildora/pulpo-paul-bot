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

from api_client import BasketballAPI
from analyzer import MatchAnalyzer
from notifier import enviar_mensaje_telegram, enviar_bloque_reportes_basket


def cargar_configuracion_basket():
    with open("config/basketball/statuses.json", "r", encoding="utf-8") as f:
        statuses = json.load(f)["active_providers"].get("api_basketball", {"finished": ["FT"], "upcoming": ["NS"]})
    return {}, {}, statuses, {}


def cargar_historico_mensual_basket():
    all_files = glob.glob("historico_mensual/basketball/historico_*.csv")
    default_cols = ['League', 'LeagueId', 'Date', 'HomeTeamId', 'AwayTeamId', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HasOT', 'Home_OT', 'Away_OT']
    
    if not all_files:
        return pd.DataFrame(columns=default_cols)
        
    li = [pd.read_csv(filename) for filename in all_files]
    df = pd.concat(li, axis=0, ignore_index=True)
    
    if 'LeagueId' not in df.columns: df['LeagueId'] = pd.NA
    if 'HomeTeamId' not in df.columns: df['HomeTeamId'] = pd.NA
    if 'AwayTeamId' not in df.columns: df['AwayTeamId'] = pd.NA
        
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
    cols_present = [c for c in default_cols if c in df.columns]
    df = df[cols_present + [c for c in df.columns if c not in cols_present]]
    return df


def guardar_historico_mensual_basket(df, meses_a_actualizar=None):
    os.makedirs("historico_mensual/basketball", exist_ok=True)
    if df.empty: 
        return
    df_temp = df.copy()
    df_temp['Date_dt'] = pd.to_datetime(df_temp['Date'], format='mixed', errors='coerce')
    df_temp['year_month'] = df_temp['Date_dt'].dt.to_period('M')
    
    for period, group in df_temp.groupby('year_month'):
        if pd.isna(period):
            continue
        if meses_a_actualizar is None or period in meses_a_actualizar:
            filename = f'historico_mensual/basketball/historico_{period.year}_{period.month:02d}.csv'
            g_clean = group.drop(columns=['Date_dt', 'year_month'], errors='ignore')
            g_clean.sort_values(by=['Date', 'League', 'HomeTeam', 'AwayTeam'], ascending=[False, True, True, True]).to_csv(filename, index=False)


def actualizar_maestro_con_partidos(df_hist, partidos_lista, fecha_str, statuses):
    for col in ["HasOT", "Home_OT", "Away_OT"]:
        if col not in df_hist.columns:
            df_hist[col] = False if col == "HasOT" else 0

    for match in partidos_lista:
        league_info = match.get("league") or {}
        liga_id = league_info.get("id")
        liga_id_str = str(liga_id) if liga_id is not None else pd.NA
        
        status_short = match.get("status", {}).get("short", "")
        
        if status_short in statuses.get("finished", []):
            teams_info = match.get("teams") or {}
            h_team_info = teams_info.get("home") or {}
            a_team_info = teams_info.get("away") or {}
            
            h_id = h_team_info.get("id")
            a_id = a_team_info.get("id")
            h_team = h_team_info.get("name")
            a_team = a_team_info.get("name")
            
            scores = match.get("scores") or {}
            h_score = (scores.get("home") or {}).get("total", 0)
            a_score = (scores.get("away") or {}).get("total", 0)
            h_ot = (scores.get("home") or {}).get("over_time") or 0
            a_ot = (scores.get("away") or {}).get("over_time") or 0
            has_ot = bool(h_ot > 0 or a_ot > 0)
            
            if not df_hist.empty and "HomeTeamId" in df_hist.columns and pd.notna(h_id) and pd.notna(a_id):
                mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeamId"] == h_id) & (df_hist["AwayTeamId"] == a_id)
                if mask.any():
                    idx = df_hist[mask].index[0]
                    df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = h_score, a_score
                    df_hist.at[idx, "HasOT"], df_hist.at[idx, "Home_OT"], df_hist.at[idx, "Away_OT"] = has_ot, h_ot, a_ot
                    continue
                    
            legacy_mask = (df_hist["Date"] == fecha_str) & (df_hist["HomeTeam"] == h_team) & (df_hist["AwayTeam"] == a_team)
            if legacy_mask.any():
                idx = df_hist[legacy_mask].index[0]
                df_hist.at[idx, "FTHG"], df_hist.at[idx, "FTAG"] = h_score, a_score
                df_hist.at[idx, "HasOT"], df_hist.at[idx, "Home_OT"], df_hist.at[idx, "Away_OT"] = has_ot, h_ot, a_ot
                if pd.notna(h_id): df_hist.at[idx, "HomeTeamId"] = h_id
                if pd.notna(a_id): df_hist.at[idx, "AwayTeamId"] = a_id
                continue
            
            nuevo = {
                "League": league_info.get("name", "Unknown"), 
                "LeagueId": liga_id_str,
                "Date": fecha_str, 
                "HomeTeamId": h_id if pd.notna(h_id) else pd.NA,
                "AwayTeamId": a_id if pd.notna(a_id) else pd.NA,
                "HomeTeam": h_team, 
                "AwayTeam": a_team, 
                "FTHG": h_score, 
                "FTAG": a_score,
                "HasOT": has_ot,
                "Home_OT": h_ot,
                "Away_OT": a_ot
            }
            df_hist = pd.concat([df_hist, pd.DataFrame([nuevo])], ignore_index=True)
            
    return df_hist


def run_process(df_externo=None):
    os.makedirs("logs/basketball", exist_ok=True)
    os.makedirs("resultados/basketball", exist_ok=True)
    
    try:
        TOKEN_BASKET = os.environ.get("TELEGRAM_BOT_TOKEN_BASKET")
        API_KEY = os.environ.get("API_BASKETBALL_KEY")
        
        _, _, statuses_map, _ = cargar_configuracion_basket()
        
        df = df_externo if df_externo is not None else cargar_historico_mensual_basket()
        api = BasketballAPI(API_KEY)
        zona = pytz.timezone('America/Santiago')
        now = datetime.now(zona)
        
        fecha_hoy_str = now.strftime("%Y-%m-%d")
        fecha_mañana_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        
        datos_fechas = {}
        meses_afectados = set()
        
        print("🏀 [BASKETBALL] Iniciando descarga y actualización global...")
        for i in range(-1, 2):
            try:
                f_dt = now + timedelta(days=i)
                meses_afectados.add(pd.Period(f_dt.strftime("%Y-%m"), 'M'))
                f_str = f_dt.strftime("%Y-%m-%d")
                
                file_path = f"resultados/basketball/basket_partidos_{f_str}.json"
                partidos_del_dia = None
                origen_datos = "🌐 API" 
                
                try:
                    data = api.get_data("games", {"date": f_str, "timezone": "America/Santiago"} )
                    time.sleep(1.5) 
                except Exception as e:
                    print(f"⚠️ [BASKETBALL] Error al consultar API para {f_str}: {e}")
                    data = None

                if data and data.get("response"):
                    partidos_del_dia = data["response"]
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            json.dump(partidos_del_dia, f, ensure_ascii=False, indent=4)
                    except Exception as e:
                        print(f"⚠️ [BASKETBALL] Error al guardar caché: {e}")
                else:
                    origen_datos = "📂 LOCAL" 
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                partidos_del_dia = json.load(f)
                        except Exception as e:
                            print(f"⚠️ [BASKETBALL] Error al leer caché para {f_str}: {e}")
                            partidos_del_dia = None
                    
                if partidos_del_dia:
                    print(f"✔️ [BASKETBALL] {f_str} procesado desde {origen_datos} ({len(partidos_del_dia)} partidos).")
                    datos_fechas[f_str] = partidos_del_dia
                    df = actualizar_maestro_con_partidos(df, partidos_del_dia, f_str, statuses_map)
                else:
                     print(f"❌ [BASKETBALL] Sin datos para {f_str} (Ni API ni LOCAL).")
                     
            except Exception as e:
                print(f"❌ [BASKETBALL] Error procesando el día {f_str}: {e}")
                print(traceback.format_exc())
                continue

        guardar_historico_mensual_basket(df, meses_afectados)
        analyzer = MatchAnalyzer(df)
        
        proyecciones_hoy, proyecciones_mañana = {}, {}
        
        def procesar_lote_partidos(lista_partidos):
            for match in lista_partidos:
                try:
                    status_short = match.get("status", {}).get("short", "")
                    if status_short in statuses_map.get("upcoming", []):
                        
                        game_date = match.get("date", "")
                        if not game_date:
                            continue
                            
                        dt_obj = datetime.fromisoformat(game_date.replace("Z", "+00:00")).astimezone(zona)
                        
                        if dt_obj < now:
                            continue

                        teams_info = match.get("teams") or {}
                        h_team_info = teams_info.get("home") or {}
                        a_team_info = teams_info.get("away") or {}
                        
                        h_name = h_team_info.get("name")
                        a_name = a_team_info.get("name")
                        h_id = h_team_info.get("id")
                        a_id = a_team_info.get("id")

                        league_id_raw = match.get("league", {}).get("id")
                        league_id_str = str(league_id_raw) if league_id_raw is not None else None
                        
                        proj = analyzer.get_basketball_projections(
                            h_name, a_name, h_id, a_id, 
                            league_id=league_id_str, 
                            match_data=match
                        )
                        
                        proj['fecha_str'] = dt_obj.strftime("%Y-%m-%d")
                        proj['hora'] = dt_obj.strftime("%H:%M")
                        
                        pais_obj = match.get("country", {})
                        pais = pais_obj.get("name", "World") if isinstance(pais_obj, dict) else (pais_obj or "World")
                        liga = match.get("league", {}).get("name", "Unknown")
                        proj['pais'] = pais
                        
                        target = proyecciones_mañana if dt_obj.strftime("%Y-%m-%d") > fecha_hoy_str else proyecciones_hoy
                        target.setdefault((pais, liga), []).append(proj)
                except Exception as e:
                    print(f"⚠️ [BASKETBALL] Error procesando partido: {e}")
                    continue

        print("🏀 [BASKETBALL] Generando proyecciones globales...")
        procesar_lote_partidos(datos_fechas.get(fecha_hoy_str, []))
        procesar_lote_partidos(datos_fechas.get(fecha_mañana_str, []))
                
        if now.hour < 12: titulo_hoy = f"🌅 *INICIO DIA BASKET: {fecha_hoy_str}*"
        else: titulo_hoy = f"🏁 *FIN DIA BASKET: {fecha_hoy_str}*"

        enviar_mensaje_telegram(titulo_hoy, TOKEN_BASKET)
        enviar_bloque_reportes_basket(proyecciones_hoy, "", analyzer, TOKEN_BASKET)
        
        if proyecciones_mañana and now.hour >= 22:
            enviar_mensaje_telegram(f"🚀 *INICIO DIA BASKET: {fecha_mañana_str} (Ventana Anticipada)*", TOKEN_BASKET)
            enviar_bloque_reportes_basket(proyecciones_mañana, "Madrugada", analyzer, TOKEN_BASKET)

        print("✅ [BASKETBALL] Proceso completo con éxito.")

    except Exception as e:
        print(f"❌ [BASKETBALL] Error crítico: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    run_process()
