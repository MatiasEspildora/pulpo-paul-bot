import os
import glob
import pandas as pd
import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🚀 Forzar que los prints salgan en tiempo real en los logs de GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api_client import FootballAPI

def cargar_ligas_con_estadisticas():
    rutas_posibles = ["config/Active_Leagues_Coverage.json", "config/football/Active_Leagues_Coverage.json"]
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    coverage = json.load(f)
                
                ligas_soportadas = {str(item.get("league_id", item.get("id"))) for item in coverage if item.get("can_fetch_stats") is True}
                print(f"📊 [INFO] Cobertura Táctica Activa: {len(ligas_soportadas)} ligas configuradas para estadísticas.")
                return ligas_soportadas
            except Exception as e:
                print(f"⚠️ Aviso: Error leyendo {ruta} ({e}).")
    return set()

def _rescatar_un_partido(idx, row, api):
    """Función auxiliar para consultar un partido de forma concurrente."""
    try:
        fixture_id = int(row['FixtureId'])
        h_team = row['HomeTeam']
        a_team = row['AwayTeam']
        h_id = row['HomeTeamId']

        resp = api.get_fixture_statistics(fixture_id)
        time.sleep(1.0)  # Pausa de cortesía para la API

        if resp and resp.get("response"):
            datos_stats = resp["response"]
            stats_dict = {}
            
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

            if stats_dict:
                return idx, stats_dict
    except Exception:
        pass
    return None

def rescatar_estadisticas_selecciones():
    API_KEY = os.environ.get("API_FOOTBALL_KEY")
    if not API_KEY:
        print("❌ Error: Falta la API_FOOTBALL_KEY en las variables de entorno.")
        return

    api = FootballAPI(API_KEY)
    ligas_soportadas = cargar_ligas_con_estadisticas()
    
    archivos = sorted(glob.glob("historico_mensual/football/historico_*.csv"))
    if not archivos:
        print("⚠️ No se encontraron archivos históricos mensuales.")
        return

    print(f"🔍 [RESCATE TÁCTICO] Analizando {len(archivos)} archivos mensuales (desde el más antiguo al más reciente)...")

    total_actualizados = 0

    for filepath in archivos:
        nombre_archivo = os.path.basename(filepath)
        # Extraer año y mes del nombre del archivo (ej: historico_2024_01.csv -> Año: 2024, Mes: 01)
        partes_nombre = nombre_archivo.replace(".csv", "").split("_")
        periodo_str = f"{partes_nombre[1]}-{partes_nombre[2]}" if len(partes_nombre) >= 3 else "Período desconocido"

        df = pd.read_csv(filepath)
        
        if 'FixtureId' in df.columns:
            df['FixtureId'] = pd.to_numeric(df['FixtureId'], errors='coerce').astype('Int64')
        if 'LeagueId' in df.columns:
            df['LeagueId'] = df['LeagueId'].astype(str)

        if 'Country' in df.columns and 'HS' in df.columns:
            mask = (df['Country'] == 'World') & (df['FixtureId'].notna()) & (df['HS'].isna())
            if 'LeagueId' in df.columns and ligas_soportadas:
                mask = mask & (df['LeagueId'].isin(ligas_soportadas))

            pendientes = df[mask]

            if not pendientes.empty:
                print(f"\n📅 [PERIODO: {periodo_str}] Archivo {nombre_archivo}: {len(pendientes)} partidos pendientes de selecciones.")
                
                archivo_modificado = False
                exitosos_archivo = 0
                
                # Ejecutar en paralelo con max_workers=4
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {
                        executor.submit(_rescatar_un_partido, idx, row, api): idx 
                        for idx, row in pendientes.iterrows()
                    }
                    
                    for future in as_completed(futures):
                        res = future.result()
                        if res is not None:
                            idx, stats_dict = res
                            for k, v in stats_dict.items():
                                if k in df.columns:
                                    df.at[idx, k] = v
                            archivo_modificado = True
                            exitosos_archivo += 1
                            total_actualizados += 1

                if archivo_modificado:
                    df.to_csv(filepath, index=False)
                    print(f"   💾 Archivo actualizado y guardado: {nombre_archivo} ({exitosos_archivo} rescatados con éxito).")
                else:
                    print(f"   ℹ️ Sin estadísticas nuevas recuperadas en este período.")
            else:
                print(f"⏩ [PERIODO: {periodo_str}] {nombre_archivo}: Sin partidos pendientes (todo al día).")

    print(f"\n🎉 [RESCATE FINALIZADO] Se completaron estadísticas tácticas para un total de {total_actualizados} partidos de selecciones.")

if __name__ == "__main__":
    rescatar_estadisticas_selecciones()
