import os
import glob
import json
import pandas as pd
import numpy as np

# 🔥 Importamos la lógica real de Bender desde tu proyecto
try:
    from analyzer import MatchAnalyzer
except ImportError:
    print("❌ No se encontró 'analyzer.py' en el directorio. Asegúrate de correr este script en la raíz de tu proyecto.")
    exit(1)

def diagnosticar(fecha, home_id, away_id):
    print(f"🔍 [DIAGNÓSTICO PROFUNDO] Evaluando partido {home_id} vs {away_id} en la fecha {fecha}...\n")
    
    # 1. Buscar en el JSON del día
    json_path = f"resultados/football/partidos_{fecha}.json"
    if not os.path.exists(json_path):
        print(f"❌ No se encontró el archivo de cartelera: {json_path}")
        return
        
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            datos_dia = json.load(f)
    except Exception as e:
        print(f"❌ Error leyendo {json_path}: {e}")
        return
        
    match = None
    for m in datos_dia:
        h_fixture = str(m.get("teams", {}).get("home", {}).get("id"))
        a_fixture = str(m.get("teams", {}).get("away", {}).get("id"))
        if h_fixture == str(home_id) and a_fixture == str(away_id):
            match = m
            break
            
    if not match:
        print(f"❌ No se encontró el partido {home_id} vs {away_id} en el JSON del {fecha}.")
        return
        
    # 2. Desglosar propiedades
    h_name = match["teams"]["home"]["name"]
    a_name = match["teams"]["away"]["name"]
    status_short = match.get("fixture", {}).get("status", {}).get("short")
    pais = match.get("league", {}).get("country", "World")
    liga = match.get("league", {}).get("name", "Unknown")
    ronda = str(match.get("league", {}).get("round", "")).lower()
    referee = str(match.get("fixture", {}).get("referee") or "Desconocido").strip()
    league_id = match.get("league", {}).get("id")
    
    es_seleccion = (pais == "World")
    es_eliminatoria = any(w in ronda for w in ["round", "quarter", "semi", "final", "elimination", "playoff", "qualifying"])
    
    print(f"✅ Partido: {h_name} vs {a_name}")
    print(f"   - Estado: {status_short} (¿Upcoming?: {status_short in ['NS', 'TBD', 'PEN']})")
    print(f"   - Es Selección: {es_seleccion} | Es Eliminatoria: {es_eliminatoria}\n")
    
    # 3. Cargar Base Histórica y Configurar MatchAnalyzer
    print("📂 Cargando base de datos histórica y montando MatchAnalyzer...")
    archivos = glob.glob("historico_mensual/football/historico_*.csv")
    if not archivos:
        print("❌ No hay archivos históricos.")
        return
        
    dfs = [pd.read_csv(f) for f in archivos]
    df = pd.concat(dfs, ignore_index=True)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    print(f"✅ {len(df)} registros cargados.\n")

    analyzer = MatchAnalyzer(df)

    # 4. Obtener Estadísticas Puras (Lo que usará el quirófano táctico)
    stats_home = analyzer.get_team_stats(h_name, home_id, league_id=str(league_id), es_eliminatoria=es_eliminatoria, es_seleccion=es_seleccion)
    stats_away = analyzer.get_team_stats(a_name, away_id, league_id=str(league_id), es_eliminatoria=es_eliminatoria, es_seleccion=es_seleccion)
    
    print(f"📊 ESTADÍSTICAS RECOLECTADAS PARA EL QUIRÓFANO TÁCTICO:")
    print(f"   - {h_name}: {stats_home.get('count')} partidos | Detalle completo: {stats_home.get('has_details')}")
    print(f"     Goles: {stats_home.get('goles_favor'):.1f}F-{stats_home.get('goles_contra'):.1f}C | Remates: {stats_home.get('remates_f'):.1f}F | Córners: {stats_home.get('corners_f'):.1f}F")
    
    print(f"   - {a_name}: {stats_away.get('count')} partidos | Detalle completo: {stats_away.get('has_details')}")
    print(f"     Goles: {stats_away.get('goles_favor'):.1f}F-{stats_away.get('goles_contra'):.1f}C | Remates: {stats_away.get('remates_f'):.1f}F | Córners: {stats_away.get('corners_f'):.1f}F\n")

    if not stats_home.get('has_details') or not stats_away.get('has_details'):
        print("   ⚠️ ALERTA: Uno o ambos equipos NO tienen datos de remates/córners. El partido será excluido automáticamente del Quirófano Táctico.\n")

    # 5. Calcular Proyecciones y Cuotas Base
    print("⚙️ CALCULANDO PROYECCIONES DE POISSON...\n")
    try:
        raw_proj = analyzer.get_projections(
            h_name, a_name, home_id, away_id, 
            league_id=str(league_id), 
            es_eliminatoria=es_eliminatoria,
            referee=referee,
            es_seleccion=es_seleccion
        )
        
        prob_matrix = raw_proj.get('prob_matrix')
        if prob_matrix is not None:
            ph = float(np.sum(np.tril(prob_matrix, -1)))
            pd_draw = float(np.sum(np.diag(prob_matrix)))
            pa = float(np.sum(np.triu(prob_matrix, 1)))
            
            btts = float(np.sum(prob_matrix[1:, 1:]))
            over_1_5 = float(1 - (prob_matrix[0,0] + prob_matrix[1,0] + prob_matrix[0,1]))
            
            print(f"🎯 CUOTAS PRINCIPALES:")
            print(f"   - Gana {h_name} (1): {ph:.1%}")
            print(f"   - Empate (X): {pd_draw:.1%}")
            print(f"   - Gana {a_name} (2): {pa:.1%}")
            print(f"   - Ambos Anotan: {btts:.1%}")
            print(f"   - +1.5 Goles: {over_1_5:.1%}\n")
            
            # Verificación de corte de Bender
            print("⚖️ VEREDICTO DEL FILTRO ELITE (notifier.py):")
            corte_ganador = max(ph, pa) >= 0.90
            corte_doble = max(ph + pd_draw, pa + pd_draw) >= 0.80
            corte_goles = over_1_5 >= 0.80 or (1-over_1_5) >= 0.85 # Aproximación rápida
            
            if corte_ganador or corte_doble or corte_goles:
                print("   ✅ El partido tiene cuotas suficientemente extremas para entrar al top de Bender.")
            else:
                print("   ❌ El partido es DEMASIADO PAREJO. Ninguna cuota principal supera el 80%-90%. Por eso Bender lo ocultó.")
        else:
            print("   ❌ Error: No se pudo generar la matriz de probabilidad.")
            
    except Exception as e:
        print(f"❌ Error al calcular proyecciones: {e}")

if __name__ == "__main__":
    diagnosticar("2026-09-25", 777, 2)
