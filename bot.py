import os
import numpy as np
import pandas as pd
from scipy.stats import poisson

# 1. Cargar el histórico maestro global
archivo_historico = "historico_maestro_global.csv"

if not os.path.exists(archivo_historico):
    print(f"⚠️ No se encuentra el archivo {archivo_historico}. Asegúrate de subirlo a la misma carpeta en GitHub.")
    exit()

df = pd.read_csv(archivo_historico)
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

# 2. Calcular los promedios globales de la liga/torneo para el modelo de Poisson
goles_local_global = df["FTHG"].mean()
goles_visita_global = df["FTAG"].mean()

print(f"📊 Promedio general de goles local: {goles_local_global:.2f}")
print(f"📊 Promedio general de goles visita: {goles_visita_global:.2f}")


# 3. Función para calcular la fuerza de ataque y defensa de un equipo
def obtener_fuerza_equipo(df, equipo):
  # Partidos como local
  casa = df[df["HomeTeam"] == equipo]
  goles_a_favor_casa = casa["FTHG"].mean() if len(casa) > 0 else goles_local_global
  goles_en_contra_casa = (
      casa["FTAG"].mean() if len(casa) > 0 else goles_visita_global
  )

  # Partidos como visitante
  fuera = df[df["AwayTeam"] == equipo]
  goles_a_favor_fuera = (
      fuera["FTAG"].mean() if len(fuera) > 0 else goles_visita_global
  )
  goles_en_contra_fuera = (
      fuera["FTHG"].mean() if len(fuera) > 0 else goles_local_global
  )

  # Índices de fuerza relativos al promedio global
  ataque = (
      (goles_a_favor_casa + goles_a_favor_fuera) / 2
  ) / goles_local_global
  defensa = (
      (goles_en_contra_casa + goles_en_contra_fuera) / 2
  ) / goles_visita_global

  return ataque, defensa


# 4. Motor de predicción con Distribución de Poisson
def predecir_partido(df, local, visita, max_goles=5):
  atq_l, def_v = obtener_fuerza_equipo(df, local)
  atq_v, def_l = obtener_fuerza_equipo(df, visita)

  # Goles esperados (Expected Goals - xG)
  lambda_local = atq_l * def_v * goles_local_global
  lambda_visita = atq_v * def_l * goles_visita_global

  # Matriz de probabilidades de goles
  matriz_prob = np.outer(
      poisson.pmf(np.arange(max_goles + 1), lambda_local),
      poisson.pmf(np.arange(max_goles + 1), lambda_visita),
  )

  prob_local_gana = np.sum(np.tril(matriz_prob, -1))
  prob_empate = np.sum(np.diag(matriz_prob))
  prob_visita_gana = np.sum(np.triu(matriz_prob, 1))

  # Probabilidad de Ambos Anotan (BTTS) y Más de 2.5 goles
  prob_ambos_anotan = (1 - poisson.pmf(0, lambda_local)) * (
      1 - poisson.pmf(0, lambda_visita)
  )
  prob_mas_2_5 = 1 - np.sum(matriz_prob[:3, :3])  # suma de estados con < 3 goles

  print(f"\n⚽ ANÁLISIS: {local} vs {visita}")
  print(f"   - Goles esperados xG: {local} ({lambda_local:.2f}) - {visita} ({lambda_visita:.2f})")
  print(f"   - Prob. Victoria {local}: {prob_local_gana*100:.1f}%")
  print(f"   - Prob. Empate: {prob_empate*100:.1f}%")
  print(f"   - Prob. Victoria {visita}: {prob_visita_gana*100:.1f}%")
  print(f"   - Prob. Ambos Anotan (BTTS): {prob_ambos_anotan*100:.1f}%")
  print(f"   - Prob. Más de 2.5 Goles: {prob_mas_2_5*100:.1f}%")


# Ejemplo de prueba manual con el histórico cargado (puedes cambiar los equipos según los partidos de hoy)
# Si es una selección del Mundial (ej. Noruega vs Inglaterra), asegúrate de que los nombres coincidan con los de la base de selecciones.
try:
  predecir_partido(df, "Norway", "England")
except Exception as e:
  print(f"⚠️ Nota de ejecución de ejemplo: {e}")
