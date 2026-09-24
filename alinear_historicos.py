import os
import glob
import pandas as pd

def alinear_historicos():
    print("🧹 [ALINEADOR] Asegurando el formato oficial para todos los históricos...")
    ruta_carpeta = "historico_mensual/football"
    all_files = glob.glob(os.path.join(ruta_carpeta, "historico_*.csv"))
    
    # Si tienes archivos en la raíz como el que subiste, inclúyelos también
    raiz_files = glob.glob("historico_*.csv")
    todos_los_archivos = list(set(all_files + raiz_files))
    
    if not todos_los_archivos:
        print("❌ No se encontraron archivos históricos.")
        return

    # Las 23 columnas oficiales que exige Bender V4.0
    columnas_oficiales = [
        'League', 'LeagueId', 'Country', 'Round', 'EsEliminatoria', 
        'Date', 'HomeTeamId', 'AwayTeamId', 'HomeTeam', 'AwayTeam', 
        'FTHG', 'FTAG', 'HTHG', 'HTAG', 'HC', 'AC', 
        'HY', 'AY', 'HR', 'AR', 'HS', 'AS', 'Referee'
    ]

    for archivo in todos_los_archivos:
        try:
            df = pd.read_csv(archivo)
            print(f"📄 Procesando: {os.path.basename(archivo)}...")
            
            # 1. Rellenar columnas faltantes con valores por defecto seguros
            for col in columnas_oficiales:
                if col not in df.columns:
                    if col == 'EsEliminatoria':
                        df[col] = False
                    elif col == 'Referee':
                        df[col] = 'Desconocido'
                    elif col in ['LeagueId', 'HomeTeamId', 'AwayTeamId']:
                        df[col] = pd.NA
                    else:
                        df[col] = pd.NA

            # 2. Eliminar la columna 'year_month' antigua si venía en el archivo para evitar conflictos
            if 'year_month' in df.columns:
                df = df.drop(columns=['year_month'])

            # 3. Filtrar y ordenar estrictamente con las columnas oficiales
            df = df[columnas_oficiales]
            df = df.dropna(subset=['Date', 'HomeTeam', 'AwayTeam'])
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
            
            # 4. Ordenar cronológicamente y guardar
            df.sort_values(by=['Date', 'HomeTeam'], ascending=[False, True], inplace=True)
            
            # Asegurar que se guarden en la carpeta oficial de históricos
            os.makedirs(ruta_carpeta, exist_ok=True)
            nombre_base = os.path.basename(archivo)
            ruta_destino = os.path.join(ruta_carpeta, nombre_base)
            
            df.to_csv(ruta_destino, index=False, encoding='utf-8')
            print(f"   ✅ OK: {nombre_base} normalizado con {len(df)} registros.")
            
        except Exception as e:
            print(f"   ❌ Error en {archivo}: {e}")

    print("\n🎉 ¡Todos los históricos están perfectamente alineados y listos para Bender V4.0!")

if __name__ == "__main__":
    alinear_historicos()
