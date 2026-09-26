import os
import glob
import pandas as pd
import time
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api_client import FootballAPI

def rescatar_estadisticas_selecciones():
    API_KEY = os.environ.get("API_FOOTBALL_KEY")
    if not API_KEY:
        print("❌ Error: Falta la API_FOOTBALL_KEY en las variables de entorno.")
        return

    api = FootballAPI(API_KEY)
    
    # Buscar todos los históricos mensuales
    archivos = sorted(glob.glob("historico_mensual/football/historico_*.csv"))
    if not archivos:
        print("⚠️ No se encontraron archivos históricos mensuales.")
        return

    print(f"🔍 [RESCATE TÁCTICO] Analizando {len(archivos)} archivos mensuales en busca de selecciones sin estadísticas...")

    total_actualizados = 0
    limite_diario = 350  # Lote seguro para no quemar cuota de la API en una sola ejecución
    peticiones_realizadas = 0

    for filepath in archivos:
        if peticiones_realizadas >= limite_diario:
            print(f"🛡️ [LÍMITE ALCANZADO] Se procesaron {peticiones_realizadas} peticiones en este ciclo. Continuaremos mañana.")
            break

        df = pd.read_csv(filepath)
        
        # Asegurar tipado Int64 para los IDs
        if 'FixtureId' in df.columns:
            df['FixtureId'] = pd.to_numeric(df['FixtureId'], errors='coerce').astype('Int64')

        # Filtrar filas donde Country == 'World', tenga FixtureId y falten remates (HS)
        if 'Country' in df.columns and 'HS' in df.columns:
            mask = (df['Country'] == 'World') & (df['FixtureId'].notna()) & (df['HS'].isna())
            pendientes_indices = df[mask].index

            if len(pendientes_indices) > 0:
                print(f"📂 Archivo {os.path.basename(filepath)}: Encontrados {len(pendientes_indices)} partidos de selecciones sin estadística táctica.")
                
                modificado = False
                for idx in pendientes_indices:
                    if peticiones_realizadas >= limite_diario:
                        break

                    fixture_id = int(df.at[idx, 'FixtureId'])
                    h_team = df.at[idx, 'HomeTeam']
                    a_team = df.at[idx, 'AwayTeam']
                    h_id = df.at[idx, 'HomeTeamId']

                    print(f"   ↳ 📥 Consultando API para: {h_team} vs {a_team} (ID: {fixture_id})...")
                    resp = api.get_fixture_statistics(fixture_id)
                    peticiones_realizadas += 1
                    time.sleep(1.2)  # Pausa de cortesía para la API

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

                        # Inyectar estadísticas rescatadas al DataFrame
                        for k, v in stats_dict.items():
                            if k in df.columns:
                                df.at[idx, k] = v
                        
                        modificado = False # se puede marcar True para guardar
                        total_actualizados += 1
                        print(f"     ✅ Estadísticas inyectadas con éxito.")
                    else:
                        print(f"     ⚠️ Sin respuesta de estadísticas para este partido.")

                # Guardar el archivo actualizado si hubo cambios
                if total_actualizados > 0:
                    df.to_csv(filepath, index=False)
                    print(f"💾 Archivo guardado con las mejoras tácticas: {os.path.basename(filepath)}")

    print(f"\n🎉 [RESCATE FINALIZADO] Se completaron estadísticas tácticas para {total_actualizados} partidos de selecciones.")

if __name__ == "__main__":
    rescatar_estadisticas_selecciones()
