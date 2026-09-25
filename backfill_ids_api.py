import os
import glob
import pandas as pd
import time
import json
from api_client import FootballAPI

def backfill_ids_desde_api():
    print("🌐 [API BACKFILL] Iniciando rescate de IDs y Árbitros faltantes...")
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        print("❌ No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
        return

    api = FootballAPI(api_key)
    archivos = sorted(glob.glob("historico_mensual/football/historico_*.csv"))
    
    # 🔥 Asegurar que el directorio de resultados exista
    os.makedirs("resultados/football", exist_ok=True)

    total_peticiones = 0
    total_actualizados = 0

    for archivo in archivos:
        try:
            df = pd.read_csv(archivo)
            if 'Date' not in df.columns: continue

            # Forzamos las columnas a tipo texto ('object') para evitar errores de tipo en Pandas
            columnas_a_forzar = ['LeagueId', 'HomeTeamId', 'AwayTeamId', 'Country', 'Referee']
            for col in columnas_a_forzar:
                if col in df.columns:
                    df[col] = df[col].astype('object')

            # Identificar fechas que tienen al menos un partido sin ID de equipo o liga
            mask_incompletos = df['HomeTeamId'].isna() | df['LeagueId'].isna()
            fechas_necesitadas = df[mask_incompletos]['Date'].dropna().unique()

            if len(fechas_necesitadas) == 0:
                continue

            print(f"\n📄 {os.path.basename(archivo)}: {len(fechas_necesitadas)} días requieren consulta.")
            cambios_en_archivo = False

            for fecha_str in fechas_necesitadas:
                file_path = f"resultados/football/partidos_{fecha_str}.json"
                fixtures_api = None
                origen_datos = "🌐 API"
                
                # 1. Intentar leer desde el caché local primero (Costo: 0 peticiones)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            fixtures_api = json.load(f)
                        origen_datos = "📂 LOCAL"
                    except Exception:
                        fixtures_api = None

                # 2. Si no hay caché, consultar a la API y guardar el resultado
                if not fixtures_api:
                    print(f"   📡 Consultando API para el {fecha_str}...")
                    try:
                        data = api.get_data("fixtures", {"date": fecha_str, "timezone": "America/Santiago"})
                        total_peticiones += 1
                        time.sleep(1.2) # Protegemos el rate-limit
                        
                        if data and data.get("response"):
                            fixtures_api = data["response"]
                            # Guardar en caché para futuras ejecuciones
                            try:
                                with open(file_path, "w", encoding="utf-8") as f:
                                    json.dump(fixtures_api, f, ensure_ascii=False, indent=4)
                            except Exception as e:
                                print(f"      ⚠️ No se pudo guardar caché local: {e}")
                    except Exception as e:
                        print(f"      ❌ Error en API: {e}")
                        continue

                if not fixtures_api:
                    continue
                    
                if origen_datos == "📂 LOCAL":
                    print(f"   📂 Usando caché local para el {fecha_str}...")

                # Mapear los datos de la respuesta para cruzarlos rápido
                mapa_api = {}
                for fix in fixtures_api:
                    h_name = fix.get("teams", {}).get("home", {}).get("name")
                    a_name = fix.get("teams", {}).get("away", {}).get("name")
                    if h_name and a_name:
                        mapa_api[f"{h_name}_{a_name}"] = fix

                # Recorrer solo las filas de ese día en el CSV
                filas_del_dia = df[df['Date'] == fecha_str].index
                for idx in filas_del_dia:
                    if pd.isna(df.at[idx, 'HomeTeamId']) or pd.isna(df.at[idx, 'LeagueId']):
                        h_csv = df.at[idx, 'HomeTeam']
                        a_csv = df.at[idx, 'AwayTeam']
                        key = f"{h_csv}_{a_csv}"

                        # Parchamos los IDs si el partido está en los datos de la API/Caché
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
                df.to_csv(archivo, index=False, encoding='utf-8')
                print(f"   💾 OK: {os.path.basename(archivo)} guardado con nuevos datos.")

        except Exception as e:
            print(f"❌ Error procesando {archivo}: {e}")

    print(f"\n🎉 ¡Proceso finalizado! Se actualizaron {total_actualizados} partidos usando solo {total_peticiones} peticiones a la API.")

if __name__ == "__main__":
    backfill_ids_desde_api()
