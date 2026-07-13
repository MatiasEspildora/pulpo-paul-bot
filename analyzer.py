import pandas as pd
import numpy as np
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        if 'Date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['Date'], errors='coerce')

    def get_team_stats(self, team_name):
        """
        Calcula estadísticas de forma flexible. 
        Si hay datos estadísticos detallados (córners, tarjetas, remates), los retorna.
        Si están vacíos (NaN), calcula el promedio de goles a favor y en contra recientes.
        """
        matches = self.df[(self.df["HomeTeam"] == team_name) | (self.df["AwayTeam"] == team_name)]
        matches = matches.dropna(subset=["FTHG", "FTAG"])
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"has_details": False, "goles_favor": 0.0, "goles_contra": 0.0, "count": 0}
            
        # Verificamos si la primera fila reciente tiene datos reales de córners (HC/AC)
        primer_row = recent.iloc[0]
        tiene_detalles = False
        if primer_row["HomeTeam"] == team_name:
            if pd.notna(primer_row.get("HC")) or pd.notna(primer_row.get("HS")):
                tiene_detalles = True
        else:
            if pd.notna(primer_row.get("AC")) or pd.notna(primer_row.get("AS")):
                tiene_detalles = True


        goles_favor, goles_contra = [], []
        for _, row in recent.iterrows():
            if row["HomeTeam"] == team_name:
                    goles_favor.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
                    goles_contra.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                else:
                    goles_favor.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                    goles_contra.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)

        if tiene_detalles:
            corners, tarjetas, remates = [], [], []
            for _, row in recent.iterrows():
                if row["HomeTeam"] == team_name:
                    corners.append(row["HC"] if pd.notna(row["HC"]) else 0)
                    tarjetas.append((row["HY"] if pd.notna(row["HY"]) else 0) + (row["HR"] if pd.notna(row["HR"]) else 0))
                    remates.append(row["HS"] if pd.notna(row["HS"]) else 0)
                else:
                    corners.append(row["AC"] if pd.notna(row["AC"]) else 0)
                    tarjetas.append((row["AY"] if pd.notna(row["AY"]) else 0) + (row["AR"] if pd.notna(row["AR"]) else 0))
                    remates.append(row["AS"] if pd.notna(row["AS"]) else 0)
                    
            return {
                "has_details": True,
                "goles_favor": float(np.nanmean(goles_favor)) if goles_favor else 0.0,
                "goles_contra": float(np.nanmean(goles_contra)) if goles_contra else 0.0,
                "corners": float(np.nanmean(corners)) if corners else 0.0,
                "tarjetas": float(np.nanmean(tarjetas)) if tarjetas else 0.0,
                "remates": float(np.nanmean(remates)) if remates else 0.0,
                "count": count,
            }        

    def get_projections(self, home_team, away_team):
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

    # --- MODELO PREDICTIVO ESPECÍFICO PARA BASKETBALL ---
    def get_basketball_team_stats(self, team_name):
        """Calcula promedios de puntos anotados y recibidos en los últimos 5 partidos de básquetbol."""
        matches = self.df[(self.df["HomeTeam"] == team_name) | (self.df["AwayTeam"] == team_name)]
        matches = matches.dropna(subset=["FTHG", "FTAG"]) # FTHG = Puntos Local, FTAG = Puntos Visita
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"puntos_favor": 0, "puntos_contra": 0, "count": 0}
            
        puntos_favor, puntos_contra = [], []
        for _, row in recent.iterrows():
            if row["HomeTeam"] == team_name:
                puntos_favor.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0)
                puntos_contra.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0)
            else:
                puntos_favor.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0)
                puntos_contra.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0)
                
        return {
            "puntos_favor": float(np.nanmean(puntos_favor)) if puntos_favor else 0,
            "puntos_contra": float(np.nanmean(puntos_contra)) if puntos_contra else 0,
            "count": count,
        }

    def get_basketball_projections(self, home_team, away_team, match_data=None):
        """
        Modelo predictivo para básquetbol basado en la expectativa de anotación combinada.
        Incluye detección opcional de tiempo extra si se pasa el objeto del partido.
        """
        home_matches = self.df[self.df['HomeTeam'] == home_team].dropna(subset=['FTHG', 'FTAG'])
        away_matches = self.df[self.df['AwayTeam'] == away_team].dropna(subset=['FTHG', 'FTAG'])

        home_avg_scored = home_matches['FTHG'].mean() if not home_matches.empty else 105.0
        home_avg_conceded = home_matches['FTAG'].mean() if not home_matches.empty else 102.0
        away_avg_scored = away_matches['FTAG'].mean() if not away_matches.empty else 103.0
        away_avg_conceded = away_matches['FTHG'].mean() if not away_matches.empty else 104.0

        exp_home_score = (home_avg_scored + away_avg_conceded) / 2
        exp_away_score = (away_avg_scored + home_avg_conceded) / 2
        total_projected_points = exp_home_score + exp_away_score

        diff = exp_home_score - exp_away_score
        prob_home = 1 / (1 + np.exp(-diff / 10))
        prob_away = 1 - prob_home

        # Detección segura de OT si viene el JSON del partido
        has_overtime = False
        if match_data:
            ot_home = match_data.get("scores", {}).get("home", {}).get("over_time")
            ot_away = match_data.get("scores", {}).get("away", {}).get("over_time")
            has_overtime = (ot_home is not None and ot_home > 0) or (ot_away is not None and ot_away > 0)

        return {
            'local': home_team,
            'visita': away_team,
            'prob_home': prob_home,
            'prob_away': prob_away,
            'probs': [prob_home, 0.0, prob_away],
            'puntos_proyectados': total_projected_points,
            'has_overtime': has_overtime,
            'score_value': max(prob_home, prob_away)
        }

    def get_basketball_overtime_stats(self, team_name):
        """Analiza la frecuencia de overtimes y puntos en tiempo extra en los últimos 5 partidos."""
        matches = self.df[(self.df["HomeTeam"] == team_name) | (self.df["AwayTeam"] == team_name)]
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"partidos_ot": 0, "promedio_puntos_ot": 0.0, "total_partidos": 0}

        partidos_ot = 0
        puntos_ot_lista = []
        
        for _, row in recent.iterrows():
            # Suponiendo que manejas una columna o indicador de prórroga, 
            # o si viene el dato crudo en el objeto de la API almacenado.
            # Verificamos si el estatus o marcador indica tiempo extra:
            is_ot = row.get("Status") == "AOT" if "Status" in row else False
            if is_ot:
                partidos_ot += 1
                # Si tienes el registro de puntos en OT, lo sumamos; si no, contamos la frecuencia
                pts_extra = row.get("ExtraPoints", 0.0)
                if pd.notna(pts_extra):
                    puntos_ot_lista.append(float(pts_extra))

        return {
            "partidos_ot": partidos_ot,
            "promedio_puntos_ot": float(np.nanmean(puntos_ot_lista)) if puntos_ot_lista else 0.0,
            "total_partidos": count
        }

    def get_top_by_league(self, proyecciones, n=3):
        sorted_projs = sorted(proyecciones, key=lambda x: x['score_value'], reverse=True)
        return sorted_projs[:n]
