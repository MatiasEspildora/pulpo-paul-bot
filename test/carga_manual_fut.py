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

from drivers import football

def gather_files(files_list, all_flag):
    if files_list:
        normalized = []
        for f in files_list:
            if not os.path.isabs(f):
                f = os.path.join(REPO_ROOT, f)
            if os.path.exists(f):
                normalized.append(f)
        return normalized
    pattern = os.path.join('resultados', 'football', 'partidos_*.json')
    return sorted(glob.glob(pattern))


def dedupe_dataframe(df):
    if df.empty:
        return df

    df = df.copy().fillna("")
    # ✅ Añadidas columnas de ID
    for col in ["League", "LeagueId", "Country", "Date", "HomeTeamId", "AwayTeamId", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]:
        if col not in df.columns:
            df[col] = ""

    for c in ["League", "LeagueId", "Country", "Date", "HomeTeam", "AwayTeam"]:
        df[c] = df[c].astype(str).str.strip()

    def completeness_score(row):
        score = 0
        if row.get("LeagueId"): score += 50
        if row.get("Country"): score += 30
        if row.get("League"): score += 10
        if (row.get("FTHG") not in (None, "")) or (row.get("FTAG") not in (None, "")): score += 20
        # ✅ Priorizar filas que sí tengan IDs nativos
        if row.get("HomeTeamId") and row.get("AwayTeamId"): score += 60
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
            # ✅ Añadidas columnas de ID a la fusión de rescate
            for col in ["League", "LeagueId", "Country", "HomeTeamId", "AwayTeamId", "FTHG", "FTAG", "HC", "AC", "HY", "AY", "HR", "AR", "HS", "AS"]:
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
    parser = argparse.ArgumentParser(description='Recarga historicos desde JSONs en resultados/football')
    parser.add_argument('--files', nargs='+', help='Archivos JSON concretos a procesar')
    parser.add_argument('--all', action='store_true', help='Procesar todos los JSON en resultados/football')
    parsed = parser.parse_args(args=args)

    files = gather_files(parsed.files, parsed.all)
    if not files:
        print('No se encontraron archivos a procesar.')
        return

    os.makedirs(os.path.join('logs', 'football'), exist_ok=True)

    # ✅ Actualizado a la nueva firma
    _, _, statuses, _ = football.cargar_configuracion()
    df_hist = football.cargar_historico_mensual()

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

    estados_finalizados = ['FT', 'AET', 'PEN']

    for match in lista_partidos:
        estado_actual = match.get('fixture', {}).get('status', {}).get('short')
        if estado_actual in estados_finalizados:
            try:
                fecha_str = pd.to_datetime(match.get('fixture', {}).get('date')).strftime('%Y-%m-%d')
            except Exception:
                fecha_str = datetime.now().strftime('%Y-%m-%d')

            # ✅ Actualizado a la nueva firma (ya no se pasan aliases ni ligas_permitidas)
            df_hist = football.actualizar_maestro_con_partidos(df_hist, [match], fecha_str, statuses)
            try:
                period = pd.Period(fecha_str[:7], 'M')
                meses_afectados.add(period)
            except Exception:
                pass

    df_hist = dedupe_dataframe(df_hist)

    if not meses_afectados:
        meses_afectados = None

    football.guardar_historico_mensual(df_hist, meses_afectados)
    print('Backfill completo e inyección de IDs terminada. Revisa historico_mensual/football.')

if __name__ == '__main__':
    main()
