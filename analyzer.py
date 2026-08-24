import pandas as pd
import numpy as np
from scipy.stats import poisson

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        if 'Date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['Date'], errors='coerce')

    def get_team_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.dropna(subset=["FTHG", "FTAG"])
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"has_details": False, "goles_favor": 0.0, "goles_contra": 0.0, "count": 0}

        primer_row = recent.iloc[0]
        tiene_detalles = False
        if primer_row["HomeTeamId"] == team_id:
            if pd.notna(primer_row.get("HC")) or pd.notna(primer_row.get("HS")):
                tiene_detalles = True
        else:
            if pd.notna(primer_row.get("AC")) or pd.notna(primer_row.get("AS")):
                tiene_detalles = True

        goles_favor, goles_contra = [], []
        corners, tarjetas, remates = [], [], []

        for _, row in recent.iterrows():
            if row["HomeTeamId"] == team_id:
                goles_favor.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
                goles_contra.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
            else:
                goles_favor.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                goles_contra.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)

        if tiene_detalles:
            for _, row in recent.iterrows():
                if row["HomeTeamId"] == team_id:
                    corners.append(row["HC"] if pd.notna(row["HC"]) else 0)
                    tarjetas.append((row["HY"] if pd.notna(row["HY"]) else 0) + (row["HR"] if pd.notna(row["HR"]) else 0))
                    remates.append(row["HS"] if pd.notna(row["HS"]) else 0)
                else:
                    corners.append(row["AC"] if pd.notna(row["AC"]) else 0)
                    tarjetas.append((row["AY"] if pd.notna(row["AY"]) else 0) + (row["AR"] if pd.notna(row["AR"]) else 0))
                    remates.append(row["AS"] if pd.notna(row["AS"]) else 0)
            
        return {
            "has_details": tiene_detalles,
            "goles_favor": float(np.nanmean(goles_favor)) if goles_favor else 0.0,
            "goles_contra": float(np.nanmean(goles_contra)) if goles_contra else 0.0,
            "corners": float(np.nanmean(corners)) if corners else 0.0,
            "tarjetas": float(np.nanmean(tarjetas)) if tarjetas else 0.0,
            "remates": float(np.nanmean(remates)) if remates else 0.0,
            "count": count,
        }

    def get_projections(self, home_team, away_team, home_id, away_id):
        def get_avg_goals(df_subset, team_id):
            if df_subset.empty: return 1.2, 1.2 
            goles_f, goles_c = [], []
            for _, row in df_subset.iterrows():
                if row["HomeTeamId"] == team_id:
                    goles_f.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
                    goles_c.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                else:
                    goles_f.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                    goles_c.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
            return float(np.nanmean(goles_f)), float(np.nanmean(goles_c))

        def get_avg_ht_goals(df_subset, team_id):
            if df_subset.empty: return 0.5, 0.5 
            goles_f, goles_c = [], []
            for _, row in df_subset.iterrows():
                h_f = row.get("HTHG")
                a_f = row.get("HTAG")
                if row["HomeTeamId"] == team_id:
                    goles_f.append(h_f if pd.notna(h_f) else 0.0)
                    goles_c.append(a_f if pd.notna(a_f) else 0.0)
                else:
                    goles_f.append(a_f if pd.notna(a_f) else 0.0)
                    goles_c.append(h_f if pd.notna(h_f) else 0.0)
            return float(np.nanmean(goles_f)), float(np.nanmean(goles_c))

        home_global = self.df[(self.df['HomeTeamId'] == home_id) | (self.df['AwayTeamId'] == home_id)]
        home_global = home_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        away_global = self.df[(self.df['HomeTeamId'] == away_id) | (self.df['AwayTeamId'] == away_id)]
        away_global = away_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        hg_f_glob, hg_c_glob = get_avg_goals(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_goals(away_global, away_id)

        hht_f_glob, hht_c_glob = get_avg_ht_goals(home_global, home_id)
        aht_f_glob, aht_c_glob = get_avg_ht_goals(away_global, away_id)

        home_venue = self.df[self.df['HomeTeamId'] == home_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)
        away_venue = self.df[self.df['AwayTeamId'] == away_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        hg_f_ven, hg_c_ven = get_avg_goals(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_goals(away_venue, away_id)

        hht_f_ven, hht_c_ven = get_avg_ht_goals(home_venue, home_id)
        aht_f_ven, aht_c_ven = get_avg_ht_goals(away_venue, away_id)

        home_scored_avg = (hg_f_glob + hg_f_ven) / 2
        home_concede_avg = (hg_c_glob + hg_c_ven) / 2
        away_scored_avg = (ag_f_glob + ag_f_ven) / 2
        away_concede_avg = (ag_c_glob + ag_c_ven) / 2

        home_ht_scored_avg = (hht_f_glob + hht_f_ven) / 2
        home_ht_concede_avg = (hht_c_glob + hht_c_ven) / 2
        away_ht_scored_avg = (aht_f_glob + aht_f_ven) / 2
        away_ht_concede_avg = (aht_c_glob + aht_c_ven) / 2

        lambda_home = (home_scored_avg + away_concede_avg) / 2
        lambda_away = (away_scored_avg + home_concede_avg) / 2
        
        lambda_home_ht = (home_ht_scored_avg + away_ht_concede_avg) / 2
        lambda_away_ht = (away_ht_scored_avg + home_ht_concede_avg) / 2

        max_goals = 5
        p_home = [poisson.pmf(i, lambda_home) for i in range(max_goals + 1)]
        p_away = [poisson.pmf(j, lambda_away) for j in range(max_goals + 1)]

        prob_home = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i > j)
        prob_draw = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i == j)
        prob_away = sum(p_home[i] * p_away[j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i < j)
        
        btts_yes = (1 - p_home[0]) * (1 - p_away[0])
        btts_no = 1 - btts_yes

        score_probs = []
        for i in range(3):
            for j in range(3):
                score_probs.append((f"{i}-{j}", p_home[i] * p_away[j]))
        score_probs.sort(key=lambda x: x[1], reverse=True)
        top_scores = [s[0] for s in score_probs[:3]]

        # --- MERCADOS DERIVADOS (Ahora incluye el 12) ---
        prob_1X = prob_home + prob_draw
        prob_X2 = prob_away + prob_draw
        prob_12 = prob_home + prob_away
        
        suma_sin_empate = prob_home + prob_away
        prob_DNB_L = (prob_home / suma_sin_empate) if suma_sin_empate > 0 else 0
        prob_DNB_V = (prob_away / suma_sin_empate) if suma_sin_empate > 0 else 0

        lam_total = lambda_home + lambda_away
        lam_ht_total = lambda_home_ht + lambda_away_ht
        
        prob_under_0_5 = poisson.cdf(0, lam_total)
        prob_under_1_5 = poisson.cdf(1, lam_total)
        prob_under_2_5 = poisson.cdf(2, lam_total)
        prob_under_3_5 = poisson.cdf(3, lam_total)
        prob_under_4_5 = poisson.cdf(4, lam_total)
        
        prob_over_0_5_ht = 1 - poisson.cdf(0, lam_ht_total)

        return {
            'local': home_team,
            'visita': away_team,
            'local_id': home_id,
            'visita_id': away_id,
            'probs': [prob_home, prob_draw, prob_away],
            'btts': btts_yes,
            'btts_no': btts_no,
            'scores': top_scores,
            'score_value': max(prob_home, prob_draw, prob_away),
            'prob_1X': prob_1X,
            'prob_X2': prob_X2,
            'prob_12': prob_12, # Inyectado para Bender
            'prob_DNB_L': prob_DNB_L,
            'prob_DNB_V': prob_DNB_V,
            'over_0_5': 1 - prob_under_0_5,
            'under_0_5': prob_under_0_5,
            'over_1_5': 1 - prob_under_1_5,
            'under_1_5': prob_under_1_5,
            'over_2_5': 1 - prob_under_2_5,
            'under_2_5': prob_under_2_5,
            'over_3_5': 1 - prob_under_3_5,
            'under_3_5': prob_under_3_5,
            'over_4_5': 1 - prob_under_4_5,
            'under_4_5': prob_under_4_5,
            'prob_over_0_5_ht': prob_over_0_5_ht
        }

    def get_basketball_team_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.dropna(subset=["FTHG", "FTAG"]) 
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"puntos_favor": 0, "puntos_contra": 0, "count": 0}

        puntos_favor, puntos_contra = [], []
        for _, row in recent.iterrows():
            if row["HomeTeamId"] == team_id:
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

    def get_basketball_projections(self, home_team, away_team, home_id, away_id, match_data=None):
        def get_avg_points(df_subset, team_id):
            if df_subset.empty: return 105.0, 105.0
            pts_f, pts_c = [], []
            for _, row in df_subset.iterrows():
                if row["HomeTeamId"] == team_id:
                    pts_f.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
                    pts_c.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                else:
                    pts_f.append(row["FTAG"] if pd.notna(row["FTAG"]) else 0.0)
                    pts_c.append(row["FTHG"] if pd.notna(row["FTHG"]) else 0.0)
            return float(np.nanmean(pts_f)), float(np.nanmean(pts_c))

        home_global = self.df[(self.df['HomeTeamId'] == home_id) | (self.df['AwayTeamId'] == home_id)]
        home_global = home_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)
        
        away_global = self.df[(self.df['HomeTeamId'] == away_id) | (self.df['AwayTeamId'] == away_id)]
        away_global = away_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        hg_f_glob, hg_c_glob = get_avg_points(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_points(away_global, away_id)

        home_venue = self.df[self.df['HomeTeamId'] == home_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)
        away_venue = self.df[self.df['AwayTeamId'] == away_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        hg_f_ven, hg_c_ven = get_avg_points(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_points(away_venue, away_id)

        home_avg_scored = (hg_f_glob + hg_f_ven) / 2
        home_avg_conceded = (hg_c_glob + hg_c_ven) / 2
        
        away_avg_scored = (ag_f_glob + ag_f_ven) / 2
        away_avg_conceded = (ag_c_glob + ag_c_ven) / 2

        exp_home_score = (home_avg_scored + away_avg_conceded) / 2
        exp_away_score = (away_avg_scored + home_avg_conceded) / 2
        total_projected_points = exp_home_score + exp_away_score

        diff = exp_home_score - exp_away_score
        prob_home = 1 / (1 + np.exp(-diff / 10))
        prob_away = 1 - prob_home

        has_overtime = False
        if match_data:
            ot_home = match_data.get("scores", {}).get("home", {}).get("over_time")
            ot_away = match_data.get("scores", {}).get("away", {}).get("over_time")
            has_overtime = (ot_home is not None and ot_home > 0) or (ot_away is not None and ot_away > 0)

        return {
            'local': home_team,
            'visita': away_team,
            'local_id': home_id,    
            'visita_id': away_id,   
            'prob_home': prob_home,
            'prob_away': prob_away,
            'probs': [prob_home, 0.0, prob_away],
            'puntos_proyectados': total_projected_points,
            'has_overtime': has_overtime,
            'score_value': max(prob_home, prob_away)
        }

    def get_basketball_overtime_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(5)

        count = len(recent)
        if recent.empty or count == 0:
            return {"partidos_ot": 0, "promedio_puntos_ot": 0.0, "total_partidos": 0}

        partidos_ot = 0
        puntos_ot_lista = []

        for _, row in recent.iterrows():
            is_ot = row.get("Status") == "AOT" if "Status" in row else False
            if is_ot:
                partidos_ot += 1
                pts_extra = row.get("ExtraPoints", 0.0)
                if pd.notna(pts_extra):
                    puntos_ot_lista.append(float(pts_extra))

        return {
            "partidos_ot": partidos_ot,
            "promedio_puntos_ot": float(np.nanmean(puntos_ot_lista)) if puntos_ot_lista else 0.0,
            "total_partidos": count
        }

    def get_top_by_league(self, proyecciones, n=None):
        sorted_projs = sorted(proyecciones, key=lambda x: x['score_value'], reverse=True)
        return sorted_projs[:n] if n else sorted_projs
