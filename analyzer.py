import numpy as np
import pandas as pd  # <--- ESTA LÍNEA ES LA QUE FALTA
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        self.prom_goles_l = df["FTHG"].mean()
        self.prom_goles_v = df["FTAG"].mean()
        # Cálculo seguro de promedios para evitar NaN globales
        self.prom_corners = (df["HC"].mean() + df["AC"].mean()) / 2
        self.prom_tarjetas = (df["HY"].mean() + df["AY"].mean()) / 2
        self.prom_remates = (df["HS"].mean() + df["AS"].mean()) / 2

    def get_projections(self, local, visita):
        casa = self.df[self.df["HomeTeam"] == local]
        fuera = self.df[self.df["AwayTeam"] == visita]
        # Ajuste de fuerza (Atq/Def)
        atq_l = (casa["FTHG"].mean() / self.prom_goles_l) if not casa.empty else 1.0
        def_v = (fuera["FTHG"].mean() / self.prom_goles_l) if not fuera.empty else 1.0
        
        lambda_l = atq_l * def_v * self.prom_goles_l
        lambda_v = (visita_atq := (fuera["FTAG"].mean() / self.prom_goles_v)) * \
                   (local_def := (casa["FTAG"].mean() / self.prom_goles_v)) * self.prom_goles_v

        # 1. Resultados exactos (Matriz 3x3)
        scoreline = {}
        for L in range(3):
            for V in range(3):
                prob = poisson.pmf(L, lambda_l) * poisson.pmf(V, lambda_v)
                scoreline[f"{L}-{V}"] = prob

        # 2. Métricas de volumen
        # Asumimos que corners/tarjetas dependen del ritmo del partido (goles proyectados)
        ritmo = (lambda_l + lambda_v) / (self.prom_goles_l + self.prom_goles_v)

        # PROTECCIÓN: Si es NaN, usamos el promedio de la liga
        c_l = casa["HC"].mean() if "HC" in casa.columns and not pd.isna(casa["HC"].mean()) else self.prom_corners/2
        c_v = fuera["AC"].mean() if "AC" in fuera.columns and not pd.isna(fuera["AC"].mean()) else self.prom_corners/2
        
        return {
            "local": local, "visita": visita,
            "score_exacto": dict(sorted(scoreline.items(), key=lambda x: x[1], reverse=True)[:3]),
            "corners_proy": round(c_l + c_v, 1), # Suma simple o ajustada
            "tarjetas_proy": round(self.prom_tarjetas, 1), # Ajustar según histórico
            "remates_proy": round(self.prom_remates, 1),
            "mejor_apuesta": f"Result: {max(scoreline, key=scoreline.get)}",
            "score": max(scoreline.values())
        }
        
    def get_top_by_league(self, projections, n=3):
        return sorted(projections, key=lambda x: x['score'], reverse=True)[:n]
