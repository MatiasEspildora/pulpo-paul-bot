import numpy as np
import pandas as pd
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        self.prom_goles_l = df["FTHG"].mean()
        self.prom_goles_v = df["FTAG"].mean()

    def get_projections(self, local, visita):
        casa = self.df[self.df["HomeTeam"] == local]
        fuera = self.df[self.df["AwayTeam"] == visita]

        atq_l = (casa["FTHG"].mean() / self.prom_goles_l) if not casa.empty else 1.0
        def_l = (casa["FTAG"].mean() / self.prom_goles_v) if not casa.empty else 1.0
        atq_v = (fuera["FTAG"].mean() / self.prom_goles_v) if not fuera.empty else 1.0
        def_v = (fuera["FTHG"].mean() / self.prom_goles_l) if not fuera.empty else 1.0

        lambda_l = atq_l * def_v * self.prom_goles_l
        lambda_v = atq_v * def_l * self.prom_goles_v

        # Cálculo de probabilidades
        prob_l, prob_e, prob_v = 0, 0, 0
        for L in range(6):
            for V in range(6):
                p = poisson.pmf(L, lambda_l) * poisson.pmf(V, lambda_v)
                if L > V: prob_l += p
                elif L == V: prob_e += p
                else: prob_v += p
        
        btts = (1 - poisson.pmf(0, lambda_l)) * (1 - poisson.pmf(0, lambda_v))
        over25 = (1 - poisson.cdf(2, lambda_l + lambda_v))

        # Determinar mercado con mayor confianza
        max_prob = max(prob_l, prob_v, btts)
        if prob_l > 0.65: mejor = f"Gana Local ({prob_l:.0%})"
        elif prob_v > 0.65: mejor = f"Gana Visita ({prob_v:.0%})"
        elif btts > 0.70: mejor = f"Ambos Anotan ({btts:.0%})"
        else: mejor = f"Over 2.5 Goles ({over25:.0%})"

        return {
            "local": local, "visita": visita,
            "prob_l": prob_l, "prob_e": prob_e, "prob_v": prob_v,
            "btts": btts, "over25": over25,
            "mejor_apuesta": mejor,
            "score": max_prob # Para ordenar el ranking
        }

    def get_top_by_league(self, projections, n=3):
        return sorted(projections, key=lambda x: x['score'], reverse=True)[:n]
