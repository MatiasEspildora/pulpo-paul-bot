import os
import glob
import pandas as pd

def mapear_ids_historicos():
    print("🧠 [CEREBRO BENDER] Iniciando escaneo de memoria para mapear IDs locales...")
    ruta_carpeta = "historico_mensual/football"
    archivos = glob.glob(os.path.join(ruta_carpeta, "historico_*.csv"))
    
    if not archivos:
        print("❌ No se encontraron archivos históricos.")
        return

    mapa_equipos = {}
    mapa_ligas = {}

    # FASE 1: Aprender de los archivos que SÍ tienen IDs (ej. 2025, 2026)
    print("🔍 Fase 1: Extrayendo Diccionario de IDs conocidos...")
    for archivo in archivos:
        try:
            df = pd.read_csv(archivo)
            
            # Extraer Ligas
            if 'League' in df.columns and 'LeagueId' in df.columns:
                valid_leagues = df.dropna(subset=['League', 'LeagueId'])
                for _, row in valid_leagues.iterrows():
                    mapa_ligas[row['League']] = int(row['LeagueId'])
            
            # Extraer Equipos Locales
            if 'HomeTeam' in df.columns and 'HomeTeamId' in df.columns:
                valid_home = df.dropna(subset=['HomeTeam', 'HomeTeamId'])
                for _, row in valid_home.iterrows():
                    mapa_equipos[row['HomeTeam']] = int(row['HomeTeamId'])
            
            # Extraer Equipos Visitas
            if 'AwayTeam' in df.columns and 'AwayTeamId' in df.columns:
                valid_away = df.dropna(subset=['AwayTeam', 'AwayTeamId'])
                for _, row in valid_away.iterrows():
                    mapa_equipos[row['AwayTeam']] = int(row['AwayTeamId'])
        except Exception:
            pass

    print(f"✅ ¡Memoria cargada! Se encontraron {len(mapa_equipos)} equipos y {len(mapa_ligas)} ligas con ID único.")

    # FASE 2: Rellenar los huecos en los archivos antiguos (ej. 2024)
    print("\n💉 Fase 2: Inyectando IDs en partidos antiguos...")
    total_parchados = 0

    for archivo in archivos:
        try:
            df = pd.read_csv(archivo)
            cambios = False

            # Rellenar LeagueId
            mask_lig_vacio = df['LeagueId'].isna()
            if mask_lig_vacio.any():
                df.loc[mask_lig_vacio, 'LeagueId'] = df.loc[mask_lig_vacio, 'League'].map(mapa_ligas)
                if df['LeagueId'].notna().any(): cambios = True

            # Rellenar HomeTeamId
            mask_home_vacio = df['HomeTeamId'].isna()
            if mask_home_vacio.any():
                df.loc[mask_home_vacio, 'HomeTeamId'] = df.loc[mask_home_vacio, 'HomeTeam'].map(mapa_equipos)
                if df['HomeTeamId'].notna().any(): cambios = True

            # Rellenar AwayTeamId
            mask_away_vacio = df['AwayTeamId'].isna()
            if mask_away_vacio.any():
                df.loc[mask_away_vacio, 'AwayTeamId'] = df.loc[mask_away_vacio, 'AwayTeam'].map(mapa_equipos)
                if df['AwayTeamId'].notna().any(): cambios = True

            if cambios:
                # Guardar archivo parchado, evitando que queden decimales raros en los IDs que encontró
                df.to_csv(archivo, index=False, encoding='utf-8')
                print(f"   🩹 Archivo actualizado con nuevos IDs: {os.path.basename(archivo)}")
                total_parchados += 1
                
        except Exception as e:
            print(f"   ❌ Error parchando {archivo}: {e}")

    print(f"\n🎉 ¡Proceso finalizado! Se actualizaron {total_parchados} archivos con IDs recuperados localmente.")

if __name__ == "__main__":
    mapear_ids_historicos()
