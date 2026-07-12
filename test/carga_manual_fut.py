import os
import glob
import json
import pandas as pd

# 1. Cargar el archivo JSON
with open('../resultados/football/partidos_2026-07-12.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

if isinstance(data, dict) and 'response' in data:
    lista_partidos = data['response']
else:
    lista_partidos = data

estados_finalizados = ['FT', 'AET', 'PEN']

# 2. Extraer y aplanar los datos respetando el esquema
rows = []
for match in lista_partidos:
    estado_actual = match.get('fixture', {}).get('status', {}).get('short')
    
    if estado_actual in estados_finalizados:
        rows.append({
            'League': match.get('league', {}).get('name'),
            'Date': match.get('fixture', {}).get('date', '')[:10],
            'HomeTeam': match.get('teams', {}).get('home', {}).get('name'),
            'AwayTeam': match.get('teams', {}).get('away', {}).get('name'),
            'FTHG': match.get('goals', {}).get('home'),
            'FTAG': match.get('goals', {}).get('away'),
            'HC': None, 'AC': None, 'HY': None, 'AY': None, 
            'HR': None, 'AR': None, 'HS': None, 'AS': None
        })

if not rows:
    print("No se encontraron partidos finalizados en el JSON. No hay datos para actualizar.")
else:
    df_nuevos = pd.DataFrame(rows)
    df_nuevos['FTHG'] = pd.to_numeric(df_nuevos['FTHG'], errors='coerce')
    df_nuevos['FTAG'] = pd.to_numeric(df_nuevos['FTAG'], errors='coerce')

    # 3. Cargar el histórico mensual existente
    os.makedirs("../historico_mensual/football", exist_ok=True)
    all_files = glob.glob("../historico_mensual/football/historico_*.csv")
    
    columnas_ordenadas = ['League', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HS', 'AS']
    
    if all_files:
        li = [pd.read_csv(filename) for filename in all_files]
        df_historico = pd.concat(li, axis=0, ignore_index=True)
    else:
        df_historico = pd.DataFrame(columns=columnas_ordenadas)

    # 4. Unir y limpiar duplicados
    df_actualizado = pd.concat([df_historico, df_nuevos], ignore_index=True)
    df_actualizado['Date'] = pd.to_datetime(df_actualizado['Date'], format='mixed').dt.strftime('%Y-%m-%d')
    df_actualizado = df_actualizado.drop_duplicates(subset=['Date', 'HomeTeam', 'AwayTeam'], keep='last')
    
    # Asegurar el esquema exacto de columnas
    df_actualizado = df_actualizado[columnas_ordenadas]

    # 5. Guardar particionado por mes ordenado de forma descendente por fecha
    df_actualizado['Date_dt'] = pd.to_datetime(df_actualizado['Date'], format='mixed')
    df_actualizado['year_month'] = df_actualizado['Date_dt'].dt.to_period('M')
    
    meses_afectados = df_nuevos['Date'].apply(lambda x: pd.Period(x[:7], 'M')).unique()
    
    for period, group in df_actualizado.groupby('year_month'):
        if period in meses_afectados:
            filename = f'../historico_mensual/football/historico_{period.year}_{period.month:02d}.csv'
            g_clean = group.drop(columns=['Date_dt', 'year_month'], errors='ignore')
            
            # --- ORDENACIÓN DESCENDENTE APLICADA ---
            g_clean.sort_values(by=['Date', 'League', 'HomeTeam', 'AwayTeam'], ascending=[False, True, True, True]).to_csv(filename, index=False)
            print(f"Archivo guardado ordenado (descendente) y limpio: {filename}")

    print("Carga manual completada con éxito.")