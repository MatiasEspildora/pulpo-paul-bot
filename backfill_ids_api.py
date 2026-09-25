import os
import glob
import pandas as pd
import time
from api_client import FootballAPI

def backfill_ids_desde_api():
    print("🌐 [API BACKFILL] Iniciando rescate de IDs y Árbitros faltantes...")
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        print("❌ No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
        return

    api = FootballAPI(api_key)
    archivos = sorted(glob.glob("historico_mensual/football/historico_*.csv"))

    total_peticiones = 0
    total_actualizados = 0

    for archivo in archivos:
        try:
            df = pd.read_csv(archivo)
            if 'Date' not in df.columns: continue

            # Identificar fechas que tienen al menos un partido sin ID de equipo o liga
            mask_incompletos = df['HomeTeamId'].isna() | df['LeagueId'].isna()
            fechas_necesitadas = df[mask_incompletos]['Date'].dropna().unique()

            if len(fechas_necesitadas) == 0:
                continue

            print(f"\n📄 {os.path.basename(archivo)}: {len(fechas_necesitadas)} días requieren consulta API.")
            cambios_en_archivo = False

            for fecha_str in fechas_necesitadas:
                print(f"   📡 Consultando API para el {fecha_str}...")
                try:
                    # Traemos TODOS los partidos de ese día con 1 sola petición
                    data = api.get_data("fixtures", {"date": fecha_str, "timezone": "America/Santiago"})
                    total_peticiones += 1
                    time.sleep(1.2) # Protegemos el rate-limit
                except Exception as e:
                    print(f"      ❌ Error en API: {e}")
                    continue

                if not data or not data.get("response"):
                    continue

                # Diccionario rápido para cruzar datos de la API con tu CSV
                mapa_api = {}
                for fix in data["response"]:
                    h_name = fix.get("teams", {}).get("home", {}).get("name")
                    a_name = fix.get("teams", {}).get("away", {}).get("name")
                    if h_name and a_name:
                        mapa_api[f"{h_name}_{a_name}"] = fix

                # Recorremos solo las filas de ese día en tu CSV
                filas_del_dia = df[df['Date'] == fecha_str].index
                for idx in filas_del_dia:
                    if pd.isna(df.at[idx, 'HomeTeamId']) or pd.isna(df.at[idx, 'LeagueId']):
                        h_csv = df.at[idx, 'HomeTeam']
                        a_csv = df.at[idx, 'AwayTeam']
                        key = f"{h_csv}_{a_csv}"

                        # Si la API tiene ese partido, parchamos los IDs
                        if key in mapa_api:
                            info = mapa_api[key]
                            df.at[idx, 'HomeTeamId'] = info["teams"]["home"]["id"]
                            df.at[idx, 'AwayTeamId'] = info["teams"]["away"]["id"]
                            df.at[idx, 'LeagueId'] = info["league"]["id"]
                            df.at[idx, 'Country'] = info["league"]["country"]
                            
                            ref = info.get("fixture", {}).get("referee")
                            if ref and pd.notna(ref) and df.at[idx, 'Referee'] == 'Desconocido':
                                df.at[idx, 'Referee'] = str(ref).strip()
                            
                            total_actualizados += 1
                            cambios_en_archivo = True

            if cambios_en_archivo:
                # Guardamos el archivo sin alterar su formato
                df.to_csv(archivo, index=False, encoding='utf-8')
                print(f"   💾 OK: {os.path.basename(archivo)} guardado con nuevos datos.")

        except Exception as e:
            print(f"❌ Error procesando {archivo}: {e}")

    print(f"\n🎉 ¡Proceso finalizado! Se actualizaron {total_actualizados} partidos usando solo {total_peticiones} peticiones a la API.")

if __name__ == "__main__":
    backfill_ids_desde_api()
