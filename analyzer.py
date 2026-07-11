import pandas as pd
import numpy as np
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        if 'Date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['Date'], errors='coerce')

    def get_team_stats(self, team_name):
        # Filtramos los últimos 5 partidos del equipo donde hubo resultado real
        matches = self.df[
            (self.df["HomeTeam"] == team_name) | (self.df["AwayTeam"] == team_name)
        ]
        matches = matches.dropna(subset=["FTHG", "FTAG"])
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"corners": 0, "tarjetas": 0, "remates": 0, "count": 0}
            
        corners = []
        tarjetas = []
        remates = []
        
        for _, row in recent.iterrows():
            if row["HomeTeam"] == team_name:
                corners.append(row["HC"] if pd.notna(row["HC"]) else 0)
                hy = row["HY"] if pd.notna(row["HY"]) else 0
                hr = row["HR"] if pd.notna(row["HR"]) else 0
                tarjetas.append(hy + hr)
                remates.append(row["HS"] if pd.notna(row["HS"]) else 0)
            else:
                corners.append(row["AC"] if pd.notna(row["AC"]) else 0)
                ay = row["AY"] if pd.notna(row["AY"]) else 0
                ar = row['AR'] if pd.notna(row['AR']) else 0
                tarjetas.append(ay + ar)
                remates.append(row["AS"] if pd.notna(row["AS"]) else 0)
                
        return {
            "corners": float(np.nanmean(corners)) if corners else 0,
            "tarjetas": float(np.nanmean(tarjetas)) if tarjetas else 0,
            "remates": float(np.nanmean(remates)) if remates else 0,
            "count": count,
        }

    def get_projections(self, home_team, away_team):
        # Obtener estadísticas recientes
        home_matches = self.df[self.df['HomeTeam'] == home_team].dropna(subset=['FTHG', 'FTAG'])
        away_matches = self.df[self.df['AwayTeam'] == away_team].dropna(subset=['FTHG', 'FTAG'])

        home_scored_avg = home_matches['FTHG'].mean() if not home_matches.empty else 1.2
        home_concede_avg = home_matches['FTAG'].mean() if not home_matches.empty else 1.0
        away_scored_avg = away_matches['FTAG'].mean() if not away_matches.empty else 1.1
        away_concede_avg = away_matches['FTHG'].mean() if not away_matches.empty else 1.2

        lambda_home = (home_scored_avg + away_concede_avg) / 2
        lambda_away = (away_scored_avg + home_concede_avg) / 2

        max_goals = 5
        p_home = [poisson.pmf(i, lambda_home) for i in range(max_goals + 1)]
        p_away = [poisson.pmf(j, lambda_away) for j in range(max_goals + 1)]

        prob_home = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i > j)
        prob_draw = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i == j)
        prob_away = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i < j)

        btts = (1 - p_home[0]) * (1 - p_away[0])

        score_probs = []
        for i in range(3):
            for j in range(3):
                score_probs.append((f"{i}-{j}", p_home[i] * p_away[j]))
        score_probs.sort(key=lambda x: x[1], reverse=True)
        top_scores = [s[0] for s in score_probs[:3]]

        return {
            'local': home_team,
            'visita': away_team,
            'probs': [prob_home, prob_draw, prob_away],
            'btts': btts,
            'scores': top_scores,
            'score_value': max(prob_home, prob_draw, prob_away)
        }

    def get_top_by_league(self, proyecciones, n=3):
        sorted_projs = sorted(proyecciones, key=lambda x: x['score_value'], reverse=True)
        return sorted_projs[:n]
