import os
import pandas as pd
import time
import json
from datetime import datetime
from api_client import FootballAPI

def actualizar_historicos_completos():
    print("🏗️ [RECONSTRUCCIÓN TOTAL] Escaneando calendario desde 2024 hasta hoy...")
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        print("❌ No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
        return

    api = FootballAPI(api_key)
    os.makedirs("resultados/football", exist_ok=True)
    os.makedirs("historico_mensual/football", exist_ok=True)

    # 1. Definir rango de fechas (Desde 2024-01-01 hasta HOY)
    fecha_fin = datetime.now()
    rango_fechas = pd.date_range(start="2024-01-01", end=fecha_fin, freq='D')

    peticiones = 0
    fechas_por_mes = {}

    # 2. Rellenar vacíos en la caché local
    print("🔍 Revisando la caché local para identificar días faltantes...")
    for fecha_obj in rango_fechas:
        fecha_str = fecha_obj.strftime("%Y-%m-%d")
        mes_str = fecha_obj.strftime("%Y_%m") # Formato para el nombre del CSV
        
        if mes_str not in fechas_por_mes:
            fechas_por_mes[mes_str] = []
        fechas_por_mes[mes_str].append(fecha_str)

        file_path = f"resultados/football/partidos_{fecha_str}.json"
        
        if not os.path.exists(file_path):
            print(f"   📡 Descargando día faltante: {fecha_str}...")
            try:
                data = api.get_data("fixtures", {"date": fecha_str, "timezone": "America/Santiago"})
                peticiones += 1
                time.sleep(1.2) # Protección de cuota
                
                if data and data.get("response") is not None:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data["response"], f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"      ❌ Error API en {fecha_str}: {e}")

    print(f"\n✅ Sincronización de caché completada. Peticiones usadas: {peticiones}")
    print("\n🏗️ Reconstruyendo archivos históricos mensuales...")

    columnas_oficiales = [
        'League', 'LeagueId', 'Country', 'Round', 'EsEliminatoria', 
        'Date', 'HomeTeamId', 'AwayTeamId', 'HomeTeam', 'AwayTeam', 
        'FTHG', 'FTAG', 'HTHG', 'HTAG', 'HC', 'AC', 
        'HY', 'AY', 'HR', 'AR', 'HS', 'AS', 'Referee'
    ]

    # 3. Generar los CSV definitivos agrupados por mes
    for mes, fechas in fechas_por_mes.items():
        nuevas_filas = []
        
        for fecha_str in fechas:
            file_path = f"resultados/football/partidos_{fecha_str}.json"
            if not os.path.exists(file_path):
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    fixtures_api = json.load(f)
            except Exception:
                continue

            if not isinstance(fixtures_api, list):
                continue

            for fix in fixtures_api:
                if not isinstance(fix, dict): continue
                
                status = fix.get("fixture", {}).get("status", {}).get("short")
                if status not in ['FT', 'AET', 'PEN']: 
                    continue # Excluir partidos cancelados o no iniciados

                league_info = fix.get("league", {})
                teams_info = fix.get("teams", {})
                goals_info = fix.get("goals", {})
                score_ht = fix.get("score", {}).get("halftime", {})
                fixture_info = fix.get("fixture", {})

                raw_date = fixture_info.get("date", "")
                match_date = raw_date[:10] if raw_date else fecha_str
                
                round_name = str(league_info.get("round", ""))
                es_elim = "Group" not in round_name and "Regular" not in round_name

                fila = {
                    'League': league_info.get("name"),
                    'LeagueId': league_info.get("id"),
                    'Country': league_info.get("country"),
                    'Round': round_name,
                    'EsEliminatoria': es_elim,
                    'Date': match_date,
                    'HomeTeamId': teams_info.get("home", {}).get("id"),
                    'AwayTeamId': teams_info.get("away", {}).get("id"),
                    'HomeTeam': teams_info.get("home", {}).get("name"),
                    'AwayTeam': teams_info.get("away", {}).get("name"),
                    'FTHG': goals_info.get("home"),
                    'FTAG': goals_info.get("away"),
                    'HTHG': score_ht.get("home"),
                    'HTAG': score_ht.get("away"),
                    'HC': pd.NA, 'AC': pd.NA, 'HY': pd.NA, 'AY': pd.NA,
                    'HR': pd.NA, 'AR': pd.NA, 'HS': pd.NA, 'AS': pd.NA,
                    'Referee': fixture_info.get("referee") if fixture_info.get("referee") else "Desconocido"
                }
                nuevas_filas.append(fila)

        # Si el mes tiene partidos, creamos su CSV oficial
        if nuevas_filas:
            df_nuevo = pd.DataFrame(nuevas_filas, columns=columnas_oficiales)
            df_nuevo.drop_duplicates(subset=['Date', 'HomeTeamId', 'AwayTeamId'], inplace=True)
            df_nuevo.sort_values(by=['Date', 'League', 'HomeTeam'], ascending=[False, True, True], inplace=True)
            
            ruta_csv = f"historico_mensual/football/historico_{mes}.csv"
            df_nuevo.to_csv(ruta_csv, index=False, encoding='utf-8')
            print(f"   ✅ OK: historico_{mes}.csv reconstruido ({len(df_nuevo)} partidos).")

    print("\n🎉 ¡Base de datos histórica estandarizada y al día!")

if __name__ == "__main__":
    actualizar_historicos_completos()
