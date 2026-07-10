import os
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

# 1. Credenciales y Tokens (Seguras mediante Variables de Entorno)
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

# Diccionario de normalización de nombres (español a inglés/estándar)
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


print(
    "🐙 Despertando al Pulpo Paul: Analizando estadísticas y tendencias"
    " clave..."
)

# 2. Cargar el histórico maestro global
archivo_historico = "historico_maestro_global.csv"
if not os.path.exists(archivo_historico):
  print(
      f"❌ Error: No se encuentra el archivo {archivo_historico} en el"
      " repositorio."
  )
  exit()

try:
  df = pd.read_csv(archivo_historico)
except Exception as e:
  print(f"❌ Error al cargar el archivo histórico: {e}")
  exit()

# Promedios globales de la base histórica
prom_goles_l = df["FTHG"].mean()
prom_goles_v = df["FTAG"].mean()
prom_corners_l = df["HC"].mean() if not np.isnan(df["HC"].mean()) else 5.0
prom_corners_v = df["AC"].mean() if not np.isnan(df["AC"].mean()) else 4.0
prom_tarjetas_l = df["HY"].mean() if not np.isnan(df["HY"].mean()) else 2.0
prom_tarjetas_v = df["AY"].mean() if not np.isnan(df["AY"].mean()) else 2.0
prom_remates_l = df["HS"].mean() if not np.isnan(df["HS"].mean()) else 12.0
prom_remates_v = df["AS"].mean() if not np.isnan(df["AS"].mean()) else 10.0


# 3. Motor de Proyección Completo (Goles, Córners, Tarjetas y Remates)
def proyectar_partido_completo(local, visita, df):
  eq_l_norm = normalizar_nombre(local)
  eq_v_norm = normalizar_nombre(visita)

  casa = df[df["HomeTeam"] == eq_l_norm]
  fuera = df[df["AwayTeam"] == eq_v_norm]

  # Factores de ataque y defensa para goles
  atq_l = (
      casa["FTHG"].mean() / prom_goles_l
      if len(casa) > 0 and not np.isnan(casa["FTHG"].mean())
      else 1.0
  )
  def_l = (
      casa["FTAG"].mean() / prom_goles_v
      if len(casa) > 0 and not np.isnan(casa["FTAG"].mean())
      else 1.0
  )
  atq_v = (
      fuera["FTAG"].mean() / prom_goles_v
      if len(fuera) > 0 and not np.isnan(fuera["FTAG"].mean())
      else 1.0
  )
  def_v = (
      fuera["FTHG"].mean() / prom_goles_l
      if len(fuera) > 0 and not np.isnan(fuera["FTHG"].mean())
      else 1.0
  )

  # xG (Goles esperados)
  lambda_l = atq_l * def_v * prom_goles_l
  lambda_v = atq_v * def_l * prom_goles_v

  # Proyecciones secundarias basadas en promedios del equipo
  c_l = (
      casa["HC"].mean()
      if len(casa) > 0 and not np.isnan(casa["HC"].mean())
      else prom_corners_l
  )
  c_v = (
      fuera["AC"].mean()
      if len(fuera) > 0 and not np.isnan(fuera["AC"].mean())
      else prom_corners_v
  )
  t_l = (
      casa["HY"].mean()
      if len(casa) > 0 and not np.isnan(casa["HY"].mean())
      else prom_tarjetas_l
  )
  t_v = (
      fuera["AY"].mean()
      if len(fuera) > 0 and not np.isnan(fuera["AY"].mean())
      else prom_tarjetas_v
  )
  s_l = (
      casa["HS"].mean()
      if len(casa) > 0 and not np.isnan(casa["HS"].mean())
      else prom_remates_l
  )
  s_v = (
      fuera["AS"].mean()
      if len(fuera) > 0 and not np.isnan(fuera["AS"].mean())
      else prom_remates_v
  )

  # Probabilidades de resultados exactos por Poisson
  prob_l, prob_e, prob_v = 0, 0, 0
  for L in range(6):
    for V in range(6):
      p = poisson.pmf(L, lambda_l) * poisson.pmf(V, lambda_v)
      if L > V:
        prob_l += p
      elif L == V:
        prob_e += p
      else:
        prob_v += p

  btts = (1 - poisson.pmf(0, lambda_l)) * (1 - poisson.pmf(0, lambda_v))

  return {
      "lambda_l": lambda_l,
      "lambda_v": lambda_v,
      "prob_l": prob_l * 100,
      "prob_e": prob_e * 100,
      "prob_v": prob_v * 100,
      "btts": btts * 100,
      "corners": c_l + c_v,
      "tarjetas": t_l + t_v,
      "remates": s_l + s_v,
  }


# 4. Conexión en vivo con API-Football para buscar los partidos del día
fecha_hoy = pd.Timestamp.now().strftime("%Y-%m-%d")
url_api_football = f"https://v3.football.api-sports.io/fixtures?date={fecha_hoy}"
headers = {
    "x-rapidapi-key": API_FOOTBALL_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io",
}

respuesta = requests.get(url_api_football, headers=headers)
alertas_enviadas = 0

if respuesta.status_code == 200:
  datos = respuesta.json().get("response", [])
  print(f"🐙 Partidos encontrados hoy ({fecha_hoy}): {len(datos)}")

  for item in datos:
    equipo_L = item["teams"]["home"]["name"]
    equipo_V = item["teams"]["away"]["name"]

    res = proyectar_partido_completo(equipo_L, equipo_V, df)

    mensaje = (
        f"⚽️ **REPORTE PULPO PAUL: {equipo_L} vs {equipo_V}** ⚽️\n\n"
        f"📊 **Proyección de Goles (xG):**\n"
        f"• {equipo_L}: {res['lambda_l']:.2f} | {equipo_V}:"
        f" {res['lambda_v']:.2f}\n"
        f"• Prob. Victoria: {res['prob_l']:.1f}% | Empate:"
        f" {res['prob_e']:.1f}% | {res['prob_v']:.1f}%\n"
        f"• Ambos Anotan (BTTS): {res['btts']:.1f}%\n\n"
        f"⚡ **Tendencias y Mercados Secundarios:**\n"
        f"• Córners Proyectados: ~{res['corners']:.1f}\n"
        f"• Tarjetas Estimadas: ~{res['tarjetas']:.1f}\n"
        f"• Remates Totales Estimados: ~{res['remates']:.1f}"
    )

    if TOKEN_TELEGRAM and CHAT_ID:
      requests.post(
          f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage",
          data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
      )
      alertas_enviadas += 1

  print(f"✅ Reportes enviados: {alertas_enviadas}")
else:
  print("❌ Error al conectar con API-Football para obtener la cartelera.")
