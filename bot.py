import os
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime
from scipy.stats import poisson

# ==========================================
# 1. CREDENCIALES Y CONFIGURACIÓN
# ==========================================
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

traduccion_equipos = {
    "Noruega": "Norway", "Inglaterra": "England", "Alemania": "Germany",
    "España": "Spain", "Francia": "France", "Argentina": "Argentina",
    "Brasil": "Brazil", "Chile": "Chile"
}

def normalizar_nombre(nombre):
    return traduccion_equipos.get(nombre, nombre)

print("🐙 Pulpo Paul: Despertando y cargando base de datos...")

# ==========================================
# 2. CARGA DE HISTÓRICO Y PROMEDIOS
# ==========================================
archivo_historico = "historico_maestro_global.csv"
if not os.path.exists(archivo_historico):
    print(f"❌ Error: No se encontró {archivo_historico}.")
    exit()

df = pd.read_csv(archivo_historico)

prom_goles_l = df["FTHG"].mean()
prom_goles_v = df["FTAG"].mean()
prom_corners_l = df["HC"].mean() if "HC" in df.columns else 5.0
prom_corners_v = df["AC"].mean() if "AC" in df.columns else 4.0
prom_tarjetas_l = df["HY"].mean() if "HY" in df.columns else 2.0
prom_tarjetas_v = df["AY"].mean() if "AY" in df.columns else 2.0
prom_remates_l = df["HS"].mean() if "HS" in df.columns else 12.0
prom_remates_v = df["AS"].mean() if "AS" in df.columns else 10.0

# ==========================================
# 3. MOTOR MATEMÁTICO (POISSON)
# ==========================================
def proyectar_partido_completo(local, visita, df):
    eq_l = normalizar_nombre(local)
    eq_v = normalizar_nombre(visita)

    casa = df[df["HomeTeam"] == eq_l]
    fuera = df[df["AwayTeam"] == eq_v]

    atq_l = (casa["FTHG"].mean() / prom_goles_l) if len(casa) > 0 and not np.isnan(casa["FTHG"].mean()) else 1.0
    def_l = (casa["FTAG"].mean() / prom_goles_v) if len(casa) > 0 and not np.isnan(casa["FTAG"].mean()) else 1.0
    atq_v = (fuera["FTAG"].mean() / prom_goles_v) if len(fuera) > 0 and not np.isnan(fuera["FTAG"].mean()) else 1.0
    def_v = (fuera["FTHG"].mean() / prom_goles_l) if len(fuera) > 0 and not np.isnan(fuera["FTHG"].mean()) else 1.0

    lambda_l = atq_l * def_v * prom_goles_l
    lambda_v = atq_v * def_l * prom_goles_v

    prob_l, prob_e, prob_v = 0, 0, 0
    for L in range(6):
        for V in range(6):
            p = poisson.pmf(L, lambda_l) * poisson.pmf(V, lambda_v)
            if L > V: prob_l += p
            elif L == V: prob_e += p
            else: prob_v += p
            
    btts = (1 - poisson.pmf(0, lambda_l)) * (1 - poisson.pmf(0, lambda_v))
    
    return {
        "lambda_l": lambda_l, "lambda_v": lambda_v,
        "prob_l": prob_l*100, "prob_e": prob_e*100, "prob_v": prob_v*100,
        "btts": btts*100,
        "corners": prom_corners_l + prom_corners_v,
        "tarjetas": prom_tarjetas_l + prom_tarjetas_v,
        "remates": prom_remates_l + prom_remates_v
    }

# ==========================================
# 4. CONEXIÓN API Y GUARDADO DE JSON
# ==========================================
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
fecha_str = datetime.now().strftime("%Y%m%d")

carpeta = "resultados"
nombre_archivo = f"partidos_{fecha_str}.json"
ruta_completa = os.path.join(carpeta, nombre_archivo)

if not os.path.exists(carpeta):
    os.makedirs(carpeta)
    print(f"📁 Carpeta '{carpeta}' creada.")

url = f"https://v3.football.api-sports.io/fixtures?date={fecha_hoy}"
headers = {"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

resp = requests.get(url, headers=headers)

if resp.status_code == 200:
    datos_completos = resp.json()
    partidos = datos_completos.get("response", [])
    
    # Guardar el archivo físico
    with open(ruta_completa, 'w', encoding='utf-8') as f:
        json.dump(datos_completos, f, ensure_ascii=False, indent=4)
    print(f"✅ JSON guardado: {ruta_completa} ({len(partidos)} partidos)")

    # ==========================================
    # 5. ANÁLISIS Y ENVÍO (DEBUGEANDO LOS PRIMEROS 5)
    # ==========================================
    for item in partidos[:5]:
        local = item["teams"]["home"]["name"]
        visita = item["teams"]["away"]["name"]
        liga = item["league"]["name"]
        
        print(f"DEBUG: Analizando {local} vs {visita} ({liga})")
        
        res = proyectar_partido_completo(local, visita, df)
        
        mensaje = (
            f"⚽️ **{local} vs {visita}**\n"
            f"🏆 *Liga:* {liga}\n\n"
            f"📊 **Proyección (xG):** {local} {res['lambda_l']:.2f} - {res['lambda_v']:.2f} {visita}\n"
            f"📈 **Probabilidades:** L:{res['prob_l']:.0f}% | E:{res['prob_e']:.0f}% | V:{res['prob_v']:.0f}%\n"
            f"🎯 **Ambos Anotan:** {res['btts']:.0f}%"
        )
        
        if TOKEN_TELEGRAM and CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage",
                data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
            )
else:
    print(f"❌ Error al conectar con API-Football (Status {resp.status_code}): {resp.text}")
