#!/usr/bin/env python3
import os
import glob
import json
import argparse
from datetime import datetime
import pandas as pd
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
os.chdir(REPO_ROOT)

# Asumimos que tu driver/script de basket se llama así, ajusta si es necesario.
from drivers import basketball 

def gather_files(files_list, all_flag):
    if files_list:
        normalized = []
        for f in files_list:
            if not os.path.isabs(f):
                f = os.path.join(REPO_ROOT, f)
            if os.path.exists(f):
                normalized.append(f)
        return normalized
    pattern = os.path.join('resultados', 'basketball', 'basket_partidos_*.json')
    return sorted(glob.glob(pattern))

def dedupe_dataframe(df):
    if df.empty:
        return df

    df = df.copy().fillna("")
    
    # Columnas esperadas en Básquetbol
    columnas_basket = [
        "League", "LeagueId", "Date", "HomeTeamId", "AwayTeamId", 
        "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HasOT", "Home_OT", "Away_OT"
    ]
    
    for col in columnas_basket:
        if col not in df.columns:
            df[col] = "" if col not in ["HasOT", "Home_OT", "Away_OT"] else (False if col == "HasOT" else 0)

    for c in ["League", "LeagueId", "Date", "HomeTeam", "AwayTeam"]:
        df[c] = df[c].astype(str).str.strip()

    def completeness_score(row):
        score = 0
        if row.get("LeagueId"): score += 50
        if row.get("League"): score += 10
        if (row.get("FTHG") not in (None, "")) or (row.get("FTAG") not in (None, "")): score += 20
        if row.get("HomeTeamId") and row.get("AwayTeamId"): score += 60
        if row.get("HasOT"): score += 5
        return score

    group_cols = ["Date", "HomeTeam", "AwayTeam"]
    merged_rows = []
    conflicts = []

    for key, group in df.groupby(group_cols, sort=False):
        records = group.to_dict(orient="records")
        if len(records) == 1:
            merged_rows.append(records[0])
            continue

        scores = [completeness_score(r) for r in records]
        best_idx = int(pd.Series(scores).idxmax())
        best = dict(records[best_idx])

        for i, other in enumerate(records):
            if i == best_idx:
                continue
            for col in columnas_basket:
                bval = best.get(col, "") or ""
                oval = other.get(col, "") or ""
                if (not bval) and oval:
                    best[col] = oval
                elif bval and oval and (str(bval) != str(oval)):
                    conflicts.append({
                        "group_key": {"Date": key[0], "HomeTeam": key[1], "AwayTeam": key[2]},
                        "column": col,
                        "kept_value": bval,
                        "other_value": oval
                    })
        merged_rows.append(best)

    df_new = pd.DataFrame(merged_rows)

    try:
        df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return df_new

def main(args=None):
    parser = argparse.ArgumentParser(description='Recarga historicos desde JSONs en resultados/basketball')
    parser.add_argument('--files', nargs='+', help='Archivos JSON concretos a procesar')
    parser.add_argument('--all', action='store_true', help='Procesar todos los JSON en resultados/basketball')
    parsed = parser.parse_args(args=args)

    files = gather_files(parsed.files, parsed.all)
    if not files:
        print('No se encontraron archivos a procesar.')
        return

    os.makedirs(os.path.join('logs', 'basketball'), exist_ok=True)

    _, _, statuses, _ = basketball.cargar_configuracion_basket()
    df_hist = basketball.cargar_historico_mensual_basket()

    meses_afectados = set()
    lista_partidos = []
    
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            continue

        if isinstance(data, dict) and 'response' in data: lista = data['response']
        else: lista = data

        if isinstance(lista, list): lista_partidos.extend(lista)

    if not lista_partidos:
        print('No se encontraron partidos finalizados.')
        return

    for match in lista_partidos:
        estado_actual = match.get('fixture', {}).get('status', {}).get('short') or match.get('status', {}).get('short')
        
        if estado_actual in statuses.get("finished", []):
            try:
                date_str = match.get('fixture', {}).get('date') or match.get('date')
                fecha_str = pd.to_datetime(date_str).strftime('%Y-%m-%d')
            except Exception:
                fecha_str = datetime.now().strftime('%Y-%m-%d')

            df_hist = basketball.actualizar_maestro_con_partidos(df_hist, [match], fecha_str, statuses)
            try:
                period = pd.Period(fecha_str[:7], 'M')
                meses_afectados.add(period)
            except Exception:
                pass

    df_hist = dedupe_dataframe(df_hist)

    if not meses_afectados:
        meses_afectados = None

    basketball.guardar_historico_mensual_basket(df_hist, meses_afectados)
    print('✅ Backfill completo e inyección de IDs de Básquetbol terminada. Revisa historico_mensual/basketball.')

if __name__ == '__main__':
    main()
