import os
import glob
import json
import argparse
import pandas as pd

def diagnosticar(fecha, home_id, away_id):
    print(f"🔍 [DIAGNÓSTICO] Buscando partido en {fecha} para equipos {home_id} vs {away_id}...\n")
    
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
        
    # 2. Desglosar propiedades del partido (Lógica football.py)
    h_name = match["teams"]["home"]["name"]
    a_name = match["teams"]["away"]["name"]
    status_short = match.get("fixture", {}).get("status", {}).get("short")
    pais = match.get("league", {}).get("country", "World")
    liga = match.get("league", {}).get("name", "Unknown")
    ronda = str(match.get("league", {}).get("round", "")).lower()
    
    es_seleccion = (pais == "World")
    es_eliminatoria = any(w in ronda for w in ["round", "quarter", "semi", "final", "elimination", "playoff", "qualifying"])
    
    print(f"✅ Partido encontrado: {h_name} vs {a_name}")
    print(f"   - Estado: {status_short} (¿Es considerado 'upcoming'? {status_short in ['NS', 'TBD', 'PEN']})")
    print(f"   - Liga: {pais} - {liga}")
    print(f"   - Es Selección (Doble Ruta): {es_seleccion}")
    print(f"   - Es Eliminatoria/Copa: {es_eliminatoria}\n")
    
    # 3. Revisar Históricos de MatchAnalyzer
    print("📂 Cargando históricos...")
    archivos = glob.glob("historico_mensual/football/historico_*.csv")
    if not archivos:
        print("❌ No hay archivos históricos en historico_mensual/football/")
        return
        
    dfs = [pd.read_csv(f) for f in archivos]
    df = pd.concat(dfs, ignore_index=True)
    print(f"✅ {len(df)} registros históricos cargados en total.\n")
    
    def get_filtered_matches(team_id, team_name):
        # Filtro estricto por ID (Lo que usa Bender)
        mask_id = (df["HomeTeamId"].astype(str) == str(team_id)) | (df["AwayTeamId"].astype(str) == str(team_id))
        base_id = df[mask_id].dropna(subset=["FTHG", "FTAG"])
        
        # Filtro por Nombre (Para auditar si el equipo existe pero sin ID)
        mask_name = (df["HomeTeam"] == team_name) | (df["AwayTeam"] == team_name)
        base_name = df[mask_name].dropna(subset=["FTHG", "FTAG"])
        
        return base_id, base_name

    h_matches_id, h_matches_name = get_filtered_matches(home_id, h_name)
    a_matches_id, a_matches_name = get_filtered_matches(away_id, a_name)
    
    min_partidos = 3 if es_eliminatoria else 5
    
    print(f"📊 Historial para {h_name} (ID: {home_id}):")
    print(f"   - Válidos por ID oficial: {len(h_matches_id)}")
    print(f"   - Válidos por Nombre: {len(h_matches_name)}")
    if len(h_matches_id) == 0 and len(h_matches_name) > 0:
        print("   ⚠️ ALERTA: Tienes partidos de este equipo, pero no se les asignó su ID numérico en el CSV.")
        
    print(f"\n📊 Historial para {a_name} (ID: {away_id}):")
    print(f"   - Válidos por ID oficial: {len(a_matches_id)}")
    print(f"   - Válidos por Nombre: {len(a_matches_name)}")
    if len(a_matches_id) == 0 and len(a_matches_name) > 0:
        print("   ⚠️ ALERTA: Tienes partidos de este equipo, pero no se les asignó su ID numérico en el CSV.")

    print(f"\n⚖️ Mínimo requerido por MatchAnalyzer: {min_partidos} partidos (por ID).")
    if len(h_matches_id) >= min_partidos and len(a_matches_id) >= min_partidos:
        print("\n✅ VEREDICTO: EL PARTIDO CUMPLE EL HISTORIAL.")
        print("El problema de omisión no es por falta de datos. Podría ser un filtro de Blacklist o el horario de generación ('upcoming').")
    else:
        print("\n❌ VEREDICTO: PARTIDO DESCARTADO POR HISTORIAL.")
        print("Bender lo ignoró porque no alcanzó el mínimo de partidos usando su ID oficial.")

if __name__ == "__main__":
    #parser = argparse.ArgumentParser(description="Auditor de partidos para Bender V4.0")
    #parser.add_argument("--fecha", required=True, help="Fecha del partido en el JSON (ej. 2026-09-25)")
    #parser.add_argument("--home", required=True, help="ID del equipo local (ej. 777)")
    #parser.add_argument("--away", required=True, help="ID del equipo visita (ej. 2)")
    #args = parser.parse_args()
    
    #diagnosticar(args.fecha, args.home, args.away)
    diagnosticar("2026-09-25",777,2)
