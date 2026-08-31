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
        recent = matches.head(15)

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

    def get_projections(self, home_team, away_team, home_id, away_id, league_id=None):
        def get_form_tracker(df_subset, team_id):
            if df_subset.empty: return "N/A", 0.0
            form = []
            pts = 0
            for _, row in df_subset.iterrows():
                hg = row.get("FTHG")
                ag = row.get("FTAG")
                if pd.isna(hg) or pd.isna(ag): continue
                if row["HomeTeamId"] == team_id:
                    if hg > ag: form.append('V'); pts += 3
                    elif hg == ag: form.append('E'); pts += 1
                    else: form.append('D')
                else:
                    if ag > hg: form.append('V'); pts += 3
                    elif ag == hg: form.append('E'); pts += 1
                    else: form.append('D')
            
            form.reverse()
            form_str = "[" + "-".join(form) + "]"
            ppg = pts / len(form) if form else 0.0
            return form_str, round(ppg, 1)

        def get_avg_goals_decay(df_subset, team_id, is_ht=False):
            if df_subset.empty: return 1.2 if not is_ht else 0.5, 1.2 if not is_ht else 0.5
            
            base_weights = [0.15, 0.12, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02]
            goles_f, goles_c = [], []
            
            col_fthg = "HTHG" if is_ht else "FTHG"
            col_ftag = "HTAG" if is_ht else "FTAG"

            for _, row in df_subset.iterrows():
                h_val = row.get(col_fthg)
                a_val = row.get(col_ftag)
                if pd.isna(h_val) or pd.isna(a_val):
                    h_val, a_val = 0.0, 0.0

                if row["HomeTeamId"] == team_id:
                    goles_f.append(float(h_val))
                    goles_c.append(float(a_val))
                else:
                    goles_f.append(float(a_val))
                    goles_c.append(float(h_val))
            
            w = base_weights[:len(goles_f)]
            w_sum = sum(w)
            w = [x / w_sum for x in w]
            
            avg_f = sum(g * w_i for g, w_i in zip(goles_f, w))
            avg_c = sum(g * w_i for g, w_i in zip(goles_c, w))
            return float(avg_f), float(avg_c)

        # 1. FORMA GLOBAL (15 partidos)
        home_global = self.df[(self.df['HomeTeamId'] == home_id) | (self.df['AwayTeamId'] == home_id)]
        home_global = home_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)

        away_global = self.df[(self.df['HomeTeamId'] == away_id) | (self.df['AwayTeamId'] == away_id)]
        away_global = away_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)
        
        home_form_str, home_ppg = get_form_tracker(home_global, home_id)
        away_form_str, away_ppg = get_form_tracker(away_global, away_id)

        # 2. FORMA CASA/FUERA
        home_venue = self.df[self.df['HomeTeamId'] == home_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)
        away_venue = self.df[self.df['AwayTeamId'] == away_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)

        home_venue_form_str, home_venue_ppg = get_form_tracker(home_venue, home_id)
        away_venue_form_str, away_venue_ppg = get_form_tracker(away_venue, away_id)

        # 3. CARA A CARA (H2H)
        h2h_df = self.df[((self.df['HomeTeamId'] == home_id) & (self.df['AwayTeamId'] == away_id)) | 
                         ((self.df['HomeTeamId'] == away_id) & (self.df['AwayTeamId'] == home_id))]
        h2h_df = h2h_df.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        # Base calculations (Global + Venue)
        hg_f_glob, hg_c_glob = get_avg_goals_decay(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_goals_decay(away_global, away_id)

        hg_f_ven, hg_c_ven = get_avg_goals_decay(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_goals_decay(away_venue, away_id)

        # Matrices de factores dinámicos
        home_scored_factors = [hg_f_glob, hg_f_ven]
        home_concede_factors = [hg_c_glob, hg_c_ven]
        away_scored_factors = [ag_f_glob, ag_f_ven]
        away_concede_factors = [ag_c_glob, ag_c_ven]

        # Inyección de Torneo (Si se proporciona el LeagueId)
        if league_id:
            home_league = home_global[home_global['LeagueId'] == league_id]
            if not home_league.empty:
                hl_f, hl_c = get_avg_goals_decay(home_league, home_id)
                home_scored_factors.extend([hl_f, hl_f]) # Peso doble al torneo actual
                home_concede_factors.extend([hl_c, hl_c])
                
            away_league = away_global[away_global['LeagueId'] == league_id]
            if not away_league.empty:
                al_f, al_c = get_avg_goals_decay(away_league, away_id)
                away_scored_factors.extend([al_f, al_f]) # Peso doble al torneo actual
                away_concede_factors.extend([al_c, al_c])

        # Inyección de Cara a Cara (H2H)
        if not h2h_df.empty:
            h2h_hf, h2h_hc = get_avg_goals_decay(h2h_df, home_id)
            h2h_af, h2h_ac = get_avg_goals_decay(h2h_df, away_id)
            
            home_scored_factors.append(h2h_hf)
            home_concede_factors.append(h2h_hc)
            away_scored_factors.append(h2h_af)
            away_concede_factors.append(h2h_ac)

        # Promedios finales integrados
        home_scored_avg = np.mean(home_scored_factors)
        home_concede_avg = np.mean(home_concede_factors)
        away_scored_avg = np.mean(away_scored_factors)
        away_concede_avg = np.mean(away_concede_factors)

        # Medio Tiempo (Mantenemos promedio Global + Venue para simpleza en HT)
        hht_f_glob, hht_c_glob = get_avg_goals_decay(home_global, home_id, is_ht=True)
        aht_f_glob, aht_c_glob = get_avg_goals_decay(away_global, away_id, is_ht=True)
        hht_f_ven, hht_c_ven = get_avg_goals_decay(home_venue, home_id, is_ht=True)
        aht_f_ven, aht_c_ven = get_avg_goals_decay(away_venue, away_id, is_ht=True)

        home_ht_scored_avg = (hht_f_glob + hht_f_ven) / 2
        home_ht_concede_avg = (hht_c_glob + hht_c_ven) / 2
        away_ht_scored_avg = (aht_f_glob + aht_f_ven) / 2
        away_ht_concede_avg = (aht_c_glob + aht_c_ven) / 2

        # Algoritmo Poisson
        lambda_home = (home_scored_avg + away_concede_avg) / 2
        lambda_away = (away_scored_avg + home_concede_avg) / 2
        
        lambda_home_ht = (home_ht_scored_avg + away_ht_concede_avg) / 2
        lambda_away_ht = (away_ht_scored_avg + home_ht_concede_avg) / 2

        max_goals = 8
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
        prob_under_5_5 = poisson.cdf(5, lam_total)
        
        prob_over_0_5_ht = 1 - poisson.cdf(0, lam_ht_total)
        prob_under_1_5_ht = poisson.cdf(1, lam_ht_total) 

        home_under_0_5 = p_home[0]
        home_over_0_5 = 1 - home_under_0_5
        home_under_1_5 = sum(p_home[:2])
        home_over_1_5 = 1 - home_under_1_5
        home_under_2_5 = sum(p_home[:3])
        home_over_2_5 = 1 - home_under_2_5

        away_under_0_5 = p_away[0]
        away_over_0_5 = 1 - away_under_0_5
        away_under_1_5 = sum(p_away[:2])
        away_over_1_5 = 1 - away_under_1_5
        away_under_2_5 = sum(p_away[:3])
        away_over_2_5 = 1 - away_under_2_5
        
        home_clean_sheet = p_away[0]
        away_clean_sheet = p_home[0]

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
            'prob_12': prob_12,
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
            'over_5_5': 1 - prob_under_5_5,
            'under_5_5': prob_under_5_5,
            'prob_over_0_5_ht': prob_over_0_5_ht,
            'prob_under_1_5_ht': prob_under_1_5_ht,
            'home_over_0_5': home_over_0_5,
            'home_over_1_5': home_over_1_5,
            'home_over_2_5': home_over_2_5,
            'away_over_0_5': away_over_0_5,
            'away_over_1_5': away_over_1_5,
            'away_over_2_5': away_over_2_5,
            'home_clean_sheet': home_clean_sheet,
            'away_clean_sheet': away_clean_sheet,
            'home_form': home_form_str,
            'home_ppg': home_ppg,
            'away_form': away_form_str,
            'away_ppg': away_ppg,
            'home_venue_form': home_venue_form_str,
            'home_venue_ppg': home_venue_ppg,
            'away_venue_form': away_venue_form_str,
            'away_venue_ppg': away_venue_ppg
        }

    def get_basketball_team_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.dropna(subset=["FTHG", "FTAG"]) 
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(15)

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

    def get_basketball_projections(self, home_team, away_team, home_id, away_id, league_id=None, match_data=None):
        def get_form_tracker(df_subset, team_id):
            if df_subset.empty: return "N/A", 0.0
            form = []
            pts = 0
            for _, row in df_subset.iterrows():
                hg = row.get("FTHG")
                ag = row.get("FTAG")
                if pd.isna(hg) or pd.isna(ag): continue
                if row["HomeTeamId"] == team_id:
                    if hg > ag: form.append('V'); pts += 3
                    elif hg == ag: form.append('E'); pts += 1
                    else: form.append('D')
                else:
                    if ag > hg: form.append('V'); pts += 3
                    elif ag == hg: form.append('E'); pts += 1
                    else: form.append('D')
            
            form.reverse()
            form_str = "[" + "-".join(form) + "]"
            ppg = pts / len(form) if form else 0.0
            return form_str, round(ppg, 1)

        def get_avg_points_decay(df_subset, team_id):
            if df_subset.empty: return 105.0, 105.0
            
            base_weights = [0.15, 0.12, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02]
            pts_f, pts_c = [], []
            
            for _, row in df_subset.iterrows():
                h_val = row.get("FTHG")
                a_val = row.get("FTAG")
                if pd.isna(h_val) or pd.isna(a_val):
                    h_val, a_val = 0.0, 0.0

                if row["HomeTeamId"] == team_id:
                    pts_f.append(float(h_val))
                    pts_c.append(float(a_val))
                else:
                    pts_f.append(float(a_val))
                    pts_c.append(float(h_val))
                    
            w = base_weights[:len(pts_f)]
            w_sum = sum(w)
            w = [x / w_sum for x in w]
            
            avg_f = sum(p * w_i for p, w_i in zip(pts_f, w))
            avg_c = sum(p * w_i for p, w_i in zip(pts_c, w))
            return float(avg_f), float(avg_c)

        home_global = self.df[(self.df['HomeTeamId'] == home_id) | (self.df['AwayTeamId'] == home_id)]
        home_global = home_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)
        
        away_global = self.df[(self.df['HomeTeamId'] == away_id) | (self.df['AwayTeamId'] == away_id)]
        away_global = away_global.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)

        home_form_str, home_ppg = get_form_tracker(home_global, home_id)
        away_form_str, away_ppg = get_form_tracker(away_global, away_id)

        home_venue = self.df[self.df['HomeTeamId'] == home_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)
        away_venue = self.df[self.df['AwayTeamId'] == away_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(15)

        home_venue_form_str, home_venue_ppg = get_form_tracker(home_venue, home_id)
        away_venue_form_str, away_venue_ppg = get_form_tracker(away_venue, away_id)

        h2h_df = self.df[((self.df['HomeTeamId'] == home_id) & (self.df['AwayTeamId'] == away_id)) | 
                         ((self.df['HomeTeamId'] == away_id) & (self.df['AwayTeamId'] == home_id))]
        h2h_df = h2h_df.dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(5)

        hg_f_glob, hg_c_glob = get_avg_points_decay(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_points_decay(away_global, away_id)

        hg_f_ven, hg_c_ven = get_avg_points_decay(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_points_decay(away_venue, away_id)

        home_scored_factors = [hg_f_glob, hg_f_ven]
        home_concede_factors = [hg_c_glob, hg_c_ven]
        away_scored_factors = [ag_f_glob, ag_f_ven]
        away_concede_factors = [ag_c_glob, ag_c_ven]

        if league_id:
            home_league = home_global[home_global['LeagueId'] == league_id]
            if not home_league.empty:
                hl_f, hl_c = get_avg_points_decay(home_league, home_id)
                home_scored_factors.extend([hl_f, hl_f]) 
                home_concede_factors.extend([hl_c, hl_c])
                
            away_league = away_global[away_global['LeagueId'] == league_id]
            if not away_league.empty:
                al_f, al_c = get_avg_points_decay(away_league, away_id)
                away_scored_factors.extend([al_f, al_f])
                away_concede_factors.extend([al_c, al_c])

        if not h2h_df.empty:
            h2h_hf, h2h_hc = get_avg_points_decay(h2h_df, home_id)
            h2h_af, h2h_ac = get_avg_points_decay(h2h_df, away_id)
            
            home_scored_factors.append(h2h_hf)
            home_concede_factors.append(h2h_hc)
            away_scored_factors.append(h2h_af)
            away_concede_factors.append(h2h_ac)

        exp_home_score = (np.mean(home_scored_factors) + np.mean(away_concede_factors)) / 2
        exp_away_score = (np.mean(away_scored_factors) + np.mean(home_concede_factors)) / 2
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
            'score_value': max(prob_home, prob_away),
            'home_form': home_form_str,
            'home_ppg': home_ppg,
            'away_form': away_form_str,
            'away_ppg': away_ppg,
            'home_venue_form': home_venue_form_str,
            'home_venue_ppg': home_venue_ppg,
            'away_venue_form': away_venue_form_str,
            'away_venue_ppg': away_venue_ppg
        }

    def get_basketball_overtime_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.sort_values(by="Date", ascending=False)
        recent = matches.head(15)

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
