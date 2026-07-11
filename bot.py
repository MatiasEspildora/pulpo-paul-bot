import os
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

# 1. Configuración de credenciales desde Variables de Entorno
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

# Diccionario de normalización
traduccion_equipos = {
    "Noruega": "Norway",
    "Inglaterra": "England",
    "Alemania": "Germany",
    "España": "Spain",
    "Francia": "France",
    "Argentina": "Argentina",
    "Brasil": "Brazil",
    "Chile": "Chile",
}

def normalizar_nombre(nombre):
    return traduccion_equipos.get(nombre, nombre)

print("🐙 Pulpo Paul: Cargando base de datos...")

# 2. Cargar histórico
archivo_historico = "historico_maestro_global.csv"
if not os.path.exists(archivo_historico):
    print(f"❌ Error: {archivo_historico} no encontrado.")
    exit()

df = pd.read_csv(archivo_historico)

# Promedios globales
prom_goles_l = df["FTHG"].mean()
prom_goles_v = df["FTAG"].mean()
prom_corners_l = df["HC"].mean() if "HC" in df.columns else 5.0
prom_corners_v = df["AC"].mean() if "AC" in df.columns else 4.0
prom_tarjetas_l = df["HY"].mean() if "HY" in df.columns else 2.0
prom_tarjetas_v = df["AY"].mean() if "AY" in df.columns else 2.0
prom_remates_l = df["HS"].mean() if "HS" in df.columns else 12.0
prom_remates_v = df["AS"].mean() if "AS" in df.columns else 10.0

def proyectar_partido(local, visita, df):
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

    # Poisson
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
        "btts": btts*100
    }

# 3. Consulta API
fecha_hoy = pd.Timestamp.now().strftime("%Y-%m-%d")
url = f"https://v3.football.api-sports.io/fixtures?date={fecha_hoy}"
headers = {"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    datos = resp.json().get("response", [])
    print(f"🐙 Partidos encontrados: {len(datos)}")

    # DEBBUG: Procesamos solo los primeros 5 para verificar nombres
    for item in datos[:5]:
        local = item["teams"]["home"]["name"]
        visita = item["teams"]["away"]["name"]
        liga = item["league"]["name"]
        
        print(f"DEBUG: Analizando {local} vs {visita} en {liga}")
        
        res = proyectar_partido(local, visita, df)
        
        mensaje = (f"⚽️ **{local} vs {visita}** ({liga})\n"
                   f"📊 xG: {res['lambda_l']:.2f} - {res['lambda_v']:.2f}\n"
                   f"📈 Prob: L:{res['prob_l']:.0f}% E:{res['prob_e']:.0f}% V:{res['prob_v']:.0f}%")
        
        if TOKEN_TELEGRAM:
            requests.post(f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage",
                          data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
            print(f"✅ Reporte enviado para {local}")
else:
    print(f"❌ Error API: {resp.text}")
