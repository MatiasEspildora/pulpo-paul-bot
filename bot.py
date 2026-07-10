import pandas as pd
import numpy as np
from scipy.stats import poisson
import requests
from datetime import datetime

# 1. Tus Credenciales
TOKEN_TELEGRAM = "8459090797:AAGFC4uO7gAi1oglp7uSEcpmWrJKWghl9sQ"
CHAT_ID = "6738814628"
API_KEY_ODDS = "87a957dd05a36893ddc6c0901b344cda"

print("🐙 El Pulpo Paul ha despertado en la nube...")

# 2. Función de Poisson para calcular probabilidades
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
            
    return prob_local * 100, prob_empate * 100, prob_visita * 100, lambda_local, lambda_visita

# 3. Descargar cuotas de Betano vía The Odds API
url_odds = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={API_KEY_ODDS}&regions=eu&markets=h2h&bookmakers=betano"
respuesta_odds = requests.get(url_odds)

# 4. Cargar base de datos histórica actualizada (Temporada actual)
url_csv = "https://www.football-data.co.uk/mmz4281/2526/E0.csv"
df_historico = pd.read_csv(url_csv)

# Diccionario para emparejar nombres de equipos
diccionario_equipos = {
    "Arsenal": "Arsenal", 
    "Manchester City": "Man City", 
    "Liverpool": "Liverpool",
    "Chelsea": "Chelsea",
    "Manchester United": "Man United",
    "Tottenham Hotspur": "Tottenham"
}

resumen_diario = "🐙 **Reporte Diario del Pulpo Paul** 🐙\n\n"
partidos_analizados = 0

if respuesta_odds.status_code == 200:
    partidos = respuesta_odds.json()
    
    for partido in partidos:
        equipo_L = partido['home_team']
        equipo_V = partido['away_team']
        
        if equipo_L in diccionario_equipos and equipo_V in diccionario_equipos:
            eq_L_stats = diccionario_equipos[equipo_L]
            eq_V_stats = diccionario_equipos[equipo_V]
            
            try:
                cuotas = partido['bookmakers'][0]['markets'][0]['outcomes']
                cuota_L = next(item['price'] for item in cuotas if item['name'] == equipo_L)
                
                # Cálculos
                prob_L_modelo, prob_E, prob_V, lam_L, lam_V = calcular_poisson(eq_L_stats, eq_V_stats, df_historico)
                prob_L_betano = (1 / cuota_L) * 100
                
                resumen_diario += f"⚽️ {equipo_L} vs {equipo_V}\n"
                resumen_diario += f"🏠 Mi modelo (Local): {prob_L_modelo:.1f}% | Betano: {prob_L_betano:.1f}% (Cuota {cuota_L})\n"
                
                if prob_L_modelo > prob_L_betano:
                    ventaja = prob_L_modelo - prob_L_betano
                    resumen_diario += f"🔥 ¡VALUE BET DETECTADA! Ventaja: +{ventaja:.1f}%\n"
                
                resumen_diario += "-------------------\n"
                partidos_analizados += 1
            except Exception:
                pass

    if partidos_analizados > 0:
        resumen_diario += f"\n📅 Analizado el {datetime.now().strftime('%d-%m-%Y')} a las 08:00 AM."
    else:
        resumen_diario = "🐙 El Pulpo revisó Betano hoy, pero no hay partidos de la Premier listos para analizar en este momento."

    # Enviar reporte consolidado a Telegram
    requests.post(f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage", data={"chat_id": CHAT_ID, "text": resumen_diario, "parse_mode": "Markdown"})
    print("✅ ¡Reporte automatizado enviado con éxito a Telegram!")
else:
    print("❌ Error al conectar con The Odds API.")
