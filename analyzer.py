import numpy as np
import pandas as pd
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        self.prom_goles_l = df["FTHG"].mean()
        self.prom_goles_v = df["FTAG"].mean()

    def get_team_stats(self, equipo):
        # Filtra partidos del equipo (local o visita) y toma los últimos 5
        partidos = self.df[(self.df["HomeTeam"] == equipo) | (self.df["AwayTeam"] == equipo)]
        ultimos = partidos.tail(5)
        
        # Si no hay datos, retorna valores base o 0
        if ultimos.empty:
            return {"corners": 0.0, "tarjetas": 0.0, "remates": 0.0}
            
        return {
            "corners": ultimos[["HC", "AC"]].mean().mean(),
            "tarjetas": ultimos[["HY", "AY"]].mean().mean(),
            "remates": ultimos[["HS", "AS"]].mean().mean()
        }

    def get_projections(self, local, visita):
        casa = self.df[self.df["HomeTeam"] == local]
        fuera = self.df[self.df["AwayTeam"] == visita]

        atq_l = (casa["FTHG"].mean() / self.prom_goles_l) if not casa.empty else 1.0
        def_v = (fuera["FTAG"].mean() / self.prom_goles_v) if not fuera.empty else 1.0
        atq_v = (fuera["FTAG"].mean() / self.prom_goles_v) if not fuera.empty else 1.0
        def_l = (casa["FTHG"].mean() / self.prom_goles_l) if not casa.empty else 1.0

        lambda_l = atq_l * def_v * self.prom_goles_l
        lambda_v = atq_v * def_l * self.prom_goles_v

        matriz = np.array([[poisson.pmf(i, lambda_l) * poisson.pmf(j, lambda_v) 
                           for j in range(6)] for i in range(6)])
        
        prob_l = np.sum(np.tril(matriz, -1))
        prob_e = np.sum(np.diag(matriz))
        prob_v = np.sum(np.triu(matriz, 1))
        btts = (1 - poisson.pmf(0, lambda_l)) * (1 - poisson.pmf(0, lambda_v))
        
        indices = np.unravel_index(np.argsort(matriz.ravel())[-3:][::-1], matriz.shape)
        scores = [f"{i}-{j}" for i, j in zip(indices[0], indices[1])]

        return {
            "local": local, "visita": visita,
            "probs": [prob_l, prob_e, prob_v],
            "btts": btts,
            "scores": scores,
            "score_rank": max(prob_l, prob_v, btts)
        }

    def get_top_by_league(self, projections, n=3):
        return sorted(projections, key=lambda x: x['score_rank'], reverse=True)[:n]
