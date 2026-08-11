#!/usr/bin/env python3
import os
import glob
import json
import argparse
from datetime import datetime
import pandas as pd
import sys

# Asegurar que la raíz del repo esté en sys.path para que 'from drivers import football' funcione
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
# Cambiar cwd a la raíz del repo para asegurar rutas relativas consistentes en CI
os.chdir(REPO_ROOT)

# Script de recarga manual
# - Por defecto procesa TODOS los JSON en resultados/football/partidos_*.json
# - Se puede pasar una lista de archivos con --files file1 file2 ...
# - Se puede pasar --all explícito para procesar todo.

from drivers import football

def gather_files(files_list, all_flag):
    if files_list:
        # Normalizar rutas relativas y filtrar los que existan
        normalized = []
        for f in files_list:
            if not os.path.isabs(f):
                f = os.path.join(REPO_ROOT, f)
            if os.path.exists(f):
                normalized.append(f)
        return normalized
    pattern = os.path.join('resultados', 'football', 'partidos_*.json')
    return sorted(glob.glob(pattern))

def main(args=None):
    parser = argparse.ArgumentParser(description='Recarga historicos desde JSONs en resultados/football')
    parser.add_argument('--files', nargs='+', help='Archivos JSON concretos a procesar')
    parser.add_argument('--all', action='store_true', help='Procesar todos los JSON en resultados/football')
    parsed = parser.parse_args(args=args)

    files = gather_files(parsed.files, parsed.all)
    if not files:
        print('No se encontraron archivos a procesar. Usa --all o pasa --files <paths>')
        return

    os.makedirs(os.path.join('logs', 'football'), exist_ok=True)

    api_to_master, master_leagues, statuses, aliases = football.cargar_configuracion()
    df_hist = football.cargar_historico_mensual()

    unmapped_teams = []
    unmapped_leagues = set()
    meses_afectados = set()

    lista_partidos = []
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ No pude leer {fp}: {e} — se salta.")
            continue

        if isinstance(data, dict) and 'response' in data:
            lista = data['response']
        else:
            lista = data

        if isinstance(lista, list):
            lista_partidos.extend(lista)
        else:
            print(f"⚠️ Formato inesperado en {fp} — se salta.")

    if not lista_partidos:
        print('No se encontraron partidos finalizados en los JSON proporcionados.')
        return

    estados_finalizados = ['FT', 'AET', 'PEN']

    # Procesar partidos usando la lógica del driver (normalización, logs, etc.)
    for match in lista_partidos:
        estado_actual = match.get('fixture', {}).get('status', {}).get('short')
        if estado_actual in estados_finalizados:
            # Extraer fecha
            fecha_str = ''
            try:
                fecha_str = pd.to_datetime(match.get('fixture', {}).get('date')).strftime('%Y-%m-%d')
            except Exception:
                # fallback: intentar extraer de filename si existe
                fecha_str = datetime.now().strftime('%Y-%m-%d')

            # Llamamos a la función del driver para insertar/actualizar
            df_hist = football.actualizar_maestro_con_partidos(df_hist, [match], fecha_str, api_to_master, statuses, aliases, unmapped_teams, unmapped_leagues)
            try:
                period = pd.Period(fecha_str[:7], 'M')
                meses_afectados.add(period)
            except Exception:
                pass

    # Guardar históricos por mes solo para los meses afectados
    if not meses_afectados:
        # si no se detectaron meses, guardar todos para ser seguro
        meses_afectados = None

    football.guardar_historico_mensual(df_hist, meses_afectados)

    # Escribir logs
    now = datetime.now().strftime('%Y%m%d')
    if unmapped_teams:
        with open(os.path.join('logs', 'football', f'unmapped_teams_backfill_{now}.json'), 'w', encoding='utf-8') as f:
            json.dump(unmapped_teams, f, ensure_ascii=False, indent=4)
        print(f'Se generó logs/football/unmapped_teams_backfill_{now}.json')

    if unmapped_leagues:
        ul = [{"id": lid, "name": name} for lid, name in sorted(unmapped_leagues, key=lambda x:int(x[0]) if str(x[0]).isdigit() else x[0])]
        with open(os.path.join('logs', 'football', f'unmapped_leagues_backfill_{now}.json'), 'w', encoding='utf-8') as f:
            json.dump(ul, f, ensure_ascii=False, indent=4)
        print(f'Se generó logs/football/unmapped_leagues_backfill_{now}.json')

    print('Backfill completo. Revisa historico_mensual/football y logs/football.')

if __name__ == '__main__':
    main()
