import pandas as pd
import numpy as np
from scipy.stats import poisson
import requests

# 1. Credenciales Listas
TOKEN_TELEGRAM = "8459090797:AAGFC4uO7gAi1oglp7uSEcpmWrJKWghl9sQ"
CHAT_ID = "6738814628"
API_KEY_ODDS = "87a957dd05a36893ddc6c0901b344cda"

print("🐙 Buscando cuotas en Betano y calculando valor...")

# Función de Poisson
def calcular_poisson(equipo_local, equipo_visita, df):
    promedio_local = df['FTHG'].mean()
    promedio_visita = df['FTAG'].mean()
    fuerza_ataque_local = (df[df['HomeTeam'] == equipo_local]['FTHG'].mean()) / promedio_local
    fuerza_defensa_local = (df[df['HomeTeam'] == equipo_local]['FTAG'].mean()) / promedio_visita
    fuerza_ataque_visita = (df[df['AwayTeam'] == equipo_visita]['FTAG'].mean()) / promedio_visita
    fuerza_defensa_visita = (df[df['AwayTeam'] == equipo_visita]['FTHG'].mean()) / promedio_local
    
    lambda_local = fuerza_ataque_local * fuerza_defensa_visita * promedio_local
    lambda_visita = fuerza_ataque_visita * fuerza_defensa_local * promedio_visita
    
    prob_local, prob_empate, prob_visita = 0, 0, 0
    for L in range(6):
        for V in range(6):
            prob = poisson.pmf(L, lambda_local) * poisson.pmf(V, lambda_visita)
            if L > V: prob_local += prob
            elif L == V: prob_empate += prob
            else: prob_visita += prob
            
    return prob_local * 100, prob_empate * 100, prob_visita * 100

# 2. Descargar cuotas de The Odds API (Betano)
url_odds = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={API_KEY_ODDS}&regions=eu&markets=h2h&bookmakers=betano"
respuesta_odds = requests.get(url_odds)

if respuesta_odds.status_code == 200:
    partidos = respuesta_odds.json()
    
    # 3. Descargar histórico para el modelo
    url_csv = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    df = pd.read_csv(url_csv)
    
    # Mapeo simple de nombres (Para evitar errores si Betano llama "Man City" y la API "Manchester City")
    diccionario_equipos = {"Arsenal": "Arsenal", "Manchester City": "Man City", "Liverpool": "Liverpool"}
    
    alertas_enviadas = 0

    for partido in partidos:
        equipo_L = partido['home_team']
        equipo_V = partido['away_team']
        
        if equipo_L in diccionario_equipos and equipo_V in diccionario_equipos:
            eq_L_stats = diccionario_equipos[equipo_L]
            eq_V_stats = diccionario_equipos[equipo_V]
            
            try:
                # Extraer cuotas específicas de Betano
                cuotas = partido['bookmakers'][0]['markets'][0]['outcomes']
                cuota_L = next(item['price'] for item in cuotas if item['name'] == equipo_L)
                
                # Cálculo matemático de Poisson
                prob_L_modelo, prob_E, prob_V = calcular_poisson(eq_L_stats, eq_V_stats, df)
                
                # Calcular probabilidad implícita de Betano
                prob_L_betano = (1 / cuota_L) * 100
                
                # EL FILTRO DE VALOR: Tu predicción > Predicción de Betano
                if prob_L_modelo > prob_L_betano:
                    ventaja = prob_L_modelo - prob_L_betano
                    
                    mensaje = (
                        f"🚨 **ALERTA DE VALOR (BETANO)** 🚨\n\n"
                        f"⚽️ {equipo_L} vs {equipo_V}\n\n"
                        f"📊 **Análisis Local ({equipo_L}):**\n"
                        f"🐙 Prob. Pulpo Paul: {prob_L_modelo:.1f}%\n"
                        f"🏦 Prob. Betano: {prob_L_betano:.1f}% (Cuota {cuota_L})\n"
                        f"🔥 **Ventaja Matemática (Edge): +{ventaja:.1f}%**"
                    )
                    
                    requests.post(f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage", data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
                    alertas_enviadas += 1
            except Exception as e:
                # Si Betano no ha publicado cuotas aún para ese partido
                pass

    if alertas_enviadas == 0:
        print("🐙 El Pulpo analizó Betano. No hay apuestas de valor en este momento.")
else:
    print("❌ Error conectando con The Odds API. Revisa tu conexión.")
