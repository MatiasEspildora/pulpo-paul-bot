import pandas as pd
import json
import os

def procesar_historico_con_overtime(ruta_csv, ruta_json):
    if not os.path.exists(ruta_csv) or not os.path.exists(ruta_json):
        print("Asegúrate de que los archivos CSV y JSON existan en la ruta especificada.")
        return

    # 1. Leer el CSV y el JSON
    df = pd.read_csv(ruta_csv)
    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. Asegurar que las columnas de Overtime existan en el DataFrame
    if 'HasOT' not in df.columns:
        df['HasOT'] = False
    if 'Home_OT' not in df.columns:
        df['Home_OT'] = 0
    if 'Away_OT' not in df.columns:
        df['Away_OT'] = 0

    # 3. Crear diccionario para búsqueda rápida (Fecha, Home, Away)
    match_dict = {}
    for match in data:
        # Usamos split('T') para capturar únicamente YYYY-MM-DD
        date = match['date'].split('T')[0]
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        
        # Extraer marcadores usando la estructura correcta del JSON
        scores = match.get('scores', {})
        h_score = scores.get('home', {}).get('total', 0)
        a_score = scores.get('away', {}).get('total', 0)
        
        # Extraer puntos en overtime si existen, si son null quedan en 0
        h_ot = scores.get('home', {}).get('over_time') or 0
        a_ot = scores.get('away', {}).get('over_time') or 0
        
        match_dict[(date, home, away)] = {
            'FTHG': h_score,
            'FTAG': a_score,
            'Home_OT': h_ot,
            'Away_OT': a_ot,
            'HasOT': bool(h_ot > 0 or a_ot > 0)
        }

    # 4. Actualizar el DataFrame si hay coincidencias
    partidos_actualizados = 0
    for idx, row in df.iterrows():
        key = (row['Date'], row['HomeTeam'], row['AwayTeam'])
        
        if key in match_dict:
            m = match_dict[key]
            df.at[idx, 'FTHG'] = m['FTHG']
            df.at[idx, 'FTAG'] = m['FTAG']
            df.at[idx, 'Home_OT'] = m['Home_OT']
            df.at[idx, 'Away_OT'] = m['Away_OT']
            df.at[idx, 'HasOT'] = m['HasOT']
            partidos_actualizados += 1

    # 5. Sobreescribir el archivo CSV con la información completa
    df.to_csv(ruta_csv, index=False)
    print(f"¡Proceso Exitoso! Se actualizaron {partidos_actualizados} partidos en '{ruta_csv}'.")

# Ejecución: Reemplaza "partidos.json" por el nombre de tu archivo JSON real
procesar_historico_con_overtime("../historico_mensual/basketball/historico_2026_07.csv", "../resultados/basketball/basket_partidos_2026-07-13.json")