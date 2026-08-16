import pandas as pd
import json
import os

def procesar_historico_con_ids_y_overtime(ruta_csv, ruta_json):
    if not os.path.exists(ruta_csv) or not os.path.exists(ruta_json):
        print(f"❌ Archivo no encontrado. Verifica las rutas:\nCSV: {ruta_csv}\nJSON: {ruta_json}")
        return

    df = pd.read_csv(ruta_csv)
    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Asegurar nuevas columnas
    if 'LeagueId' not in df.columns: df['LeagueId'] = ''
    if 'HomeTeamId' not in df.columns: df['HomeTeamId'] = pd.NA
    if 'AwayTeamId' not in df.columns: df['AwayTeamId'] = pd.NA
    if 'HasOT' not in df.columns: df['HasOT'] = False
    if 'Home_OT' not in df.columns: df['Home_OT'] = 0
    if 'Away_OT' not in df.columns: df['Away_OT'] = 0

    # 2. Mapear datos desde el JSON
    match_dict = {}
    for match in data:
        date = match['date'].split('T')[0]
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        
        scores = match.get('scores', {})
        h_ot = scores.get('home', {}).get('over_time') or 0
        a_ot = scores.get('away', {}).get('over_time') or 0
        
        match_dict[(date, home, away)] = {
            'LeagueId': match['league']['id'],
            'HomeTeamId': match['teams']['home']['id'],
            'AwayTeamId': match['teams']['away']['id'],
            'FTHG': scores.get('home', {}).get('total', 0),
            'FTAG': scores.get('away', {}).get('total', 0),
            'Home_OT': h_ot,
            'Away_OT': a_ot,
            'HasOT': bool(h_ot > 0 or a_ot > 0)
        }

    # 3. Inyectar datos al CSV
    actualizados = 0
    for idx, row in df.iterrows():
        key = (row['Date'], row['HomeTeam'], row['AwayTeam'])
        if key in match_dict:
            m = match_dict[key]
            df.at[idx, 'LeagueId'] = m['LeagueId']
            df.at[idx, 'HomeTeamId'] = m['HomeTeamId']
            df.at[idx, 'AwayTeamId'] = m['AwayTeamId']
            df.at[idx, 'FTHG'] = m['FTHG']
            df.at[idx, 'FTAG'] = m['FTAG']
            df.at[idx, 'Home_OT'] = m['Home_OT']
            df.at[idx, 'Away_OT'] = m['Away_OT']
            df.at[idx, 'HasOT'] = m['HasOT']
            actualizados += 1

    df.to_csv(ruta_csv, index=False)
    print(f"✅ ¡Éxito! Se actualizaron IDs y Overtimes en {actualizados} partidos del archivo '{ruta_csv}'.")

# Puedes ejecutarlo así:
# procesar_historico_con_ids_y_overtime("historico_mensual/basketball/historico_2026_07.csv", "resultados/basketball/basket_partidos_2026-07-13.json")
