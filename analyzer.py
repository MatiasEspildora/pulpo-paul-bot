import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

class MatchAnalyzer:
    def __init__(self, df):
        self.df = df
        if 'Date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['Date'], errors='coerce')

    def _apply_knockout_context(self, h_id, a_id, league_id, home_xg, away_xg):
        if self.df.empty or pd.isna(league_id) or pd.isna(h_id) or pd.isna(a_id):
            return home_xg * 0.95, away_xg * 0.95, 0
            
        h_id, a_id = str(h_id), str(a_id)
        hace_45_dias = datetime.now() - timedelta(days=45)
        
        mask_h2h_reciente = (
            (self.df['LeagueId'].astype(str) == str(league_id)) & 
            (self.df['Date'] >= hace_45_dias) &
            (
                ((self.df['HomeTeamId'].astype(str) == h_id) & (self.df['AwayTeamId'].astype(str) == a_id)) |
                ((self.df['HomeTeamId'].astype(str) == a_id) & (self.df['AwayTeamId'].astype(str) == h_id))
            )
        )
        
        partido_ida = self.df[mask_h2h_reciente].sort_values(by='Date', ascending=False)
        
        if partido_ida.empty:
            return home_xg * 0.90, away_xg * 0.90, 0
            
        ida = partido_ida.iloc[0]
        if str(ida['HomeTeamId']) == h_id:
            dif_global = ida['FTHG'] - ida['FTAG']
        else:
            dif_global = ida['FTAG'] - ida['FTHG']
            
        if dif_global <= -2:
            return home_xg * 1.35, away_xg * 1.30, dif_global
        elif dif_global >= 2:
            return home_xg * 1.30, away_xg * 1.35, dif_global
        elif dif_global == -1:
            return home_xg * 1.15, away_xg * 1.10, dif_global
        elif dif_global == 1:
            return home_xg * 1.10, away_xg * 1.15, dif_global
        else:
            return home_xg * 0.95, away_xg * 0.95, dif_global

    def _calculate_exact_scores(self, home_xg, away_xg, max_goals=8):
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                matrix[i, j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg)
                
        rho = -0.15 
        tau_00 = 1 - (home_xg * away_xg * rho)
        tau_10 = 1 + (away_xg * rho)
        tau_01 = 1 + (home_xg * rho)
        tau_11 = 1 - rho
        
        matrix[0, 0] *= tau_00
        matrix[1, 0] *= max(tau_10, 0)
        matrix[0, 1] *= max(tau_01, 0)
        matrix[1, 1] *= tau_11
        
        return matrix / matrix.sum()

    def _calculate_corners_matrix(self, home_corners_lambda, away_corners_lambda, max_corners=15):
        matrix = np.zeros((max_corners + 1, max_corners + 1))
        for i in range(max_corners + 1):
            for j in range(max_corners + 1):
                matrix[i, j] = poisson.pmf(i, home_corners_lambda) * poisson.pmf(j, away_corners_lambda)
        return matrix / matrix.sum()
    
    def _calculate_cards_matrix(self, home_cards_lambda, away_cards_lambda, max_cards=10):
        matrix = np.zeros((max_cards + 1, max_cards + 1))
        for i in range(max_cards + 1):
            for j in range(max_cards + 1):
                matrix[i, j] = poisson.pmf(i, home_cards_lambda) * poisson.pmf(j, away_cards_lambda)
        return matrix / matrix.sum()

    def _get_filtered_matches(self, team_id, league_id, es_eliminatoria):
        base_matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        base_matches = base_matches.dropna(subset=["FTHG", "FTAG"]).sort_values(by="Date", ascending=False)
        
        if not es_eliminatoria and pd.notna(league_id):
            liga_matches = base_matches[base_matches["LeagueId"].astype(str) == str(league_id)]
            if len(liga_matches) >= 3: return liga_matches
        return base_matches

    def get_team_stats(self, team_name, team_id, league_id=None, es_eliminatoria=False):
        matches = self._get_filtered_matches(team_id, league_id, es_eliminatoria)
        recent = matches.head(10)
        count = len(recent)
        
        if recent.empty or count == 0:
            return {"has_details": False, "goles_favor": 0.0, "goles_contra": 0.0, "count": 0}

        goles_favor, goles_contra = [], []
        corners_f, corners_c = [], []
        tarjetas_f, tarjetas_c = [], []
        remates_f, remates_c = [], []

        for _, row in recent.iterrows():
            es_local = (row["HomeTeamId"] == team_id)
            
            # 1. Goles (Siempre presentes)
            goles_favor.append(row["FTHG"] if es_local else row["FTAG"])
            goles_contra.append(row["FTAG"] if es_local else row["FTHG"])

            # 2. Extracción Táctica Aislada (Se ignora si es NaN, sin inyectar ceros)
            if es_local:
                if pd.notna(row.get("HC")): corners_f.append(float(row["HC"]))
                if pd.notna(row.get("AC")): corners_c.append(float(row["AC"]))
                if pd.notna(row.get("HS")): remates_f.append(float(row["HS"]))
                if pd.notna(row.get("AS")): remates_c.append(float(row["AS"]))
                
                t_f = (float(row.get("HY", 0)) if pd.notna(row.get("HY")) else 0) + (float(row.get("HR", 0)) if pd.notna(row.get("HR")) else 0)
                t_c = (float(row.get("AY", 0)) if pd.notna(row.get("AY")) else 0) + (float(row.get("AR", 0)) if pd.notna(row.get("AR")) else 0)
                if pd.notna(row.get("HY")) or pd.notna(row.get("HR")): tarjetas_f.append(t_f)
                if pd.notna(row.get("AY")) or pd.notna(row.get("AR")): tarjetas_c.append(t_c)
            else:
                if pd.notna(row.get("AC")): corners_f.append(float(row["AC"]))
                if pd.notna(row.get("HC")): corners_c.append(float(row["HC"]))
                if pd.notna(row.get("AS")): remates_f.append(float(row["AS"]))
                if pd.notna(row.get("HS")): remates_c.append(float(row["HS"]))
                
                t_f = (float(row.get("AY", 0)) if pd.notna(row.get("AY")) else 0) + (float(row.get("AR", 0)) if pd.notna(row.get("AR")) else 0)
                t_c = (float(row.get("HY", 0)) if pd.notna(row.get("HY")) else 0) + (float(row.get("HR", 0)) if pd.notna(row.get("HR")) else 0)
                if pd.notna(row.get("AY")) or pd.notna(row.get("AR")): tarjetas_f.append(t_f)
                if pd.notna(row.get("HY")) or pd.notna(row.get("HR")): tarjetas_c.append(t_c)
            
        tiene_detalles = len(corners_f) > 0 or len(remates_f) > 0

        return {
            "has_details": tiene_detalles,
            "goles_favor": float(np.nanmean(goles_favor)) if goles_favor else 0.0,
            "goles_contra": float(np.nanmean(goles_contra)) if goles_contra else 0.0,
            "corners_f": float(np.nanmean(corners_f)) if corners_f else 0.0,
            "corners_c": float(np.nanmean(corners_c)) if corners_c else 0.0,
            "tarjetas_f": float(np.nanmean(tarjetas_f)) if tarjetas_f else 0.0,
            "tarjetas_c": float(np.nanmean(tarjetas_c)) if tarjetas_c else 0.0,
            "remates_f": float(np.nanmean(remates_f)) if remates_f else 0.0,
            "remates_c": float(np.nanmean(remates_c)) if remates_c else 0.0,
            "count": count,
        }

    def get_projections(self, home_team, away_team, home_id, away_id, league_id=None, es_eliminatoria=False):
        def get_form_tracker(df_subset, team_id):
            if df_subset.empty: return "N/A", 0.0
            form, pts = [], 0
            for _, row in df_subset.iterrows():
                hg, ag = row.get("FTHG"), row.get("FTAG")
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
            return "[" + "-".join(form) + "]", round(pts / len(form) if form else 0.0, 1)

        def get_avg_goals_decay(df_subset, team_id, is_ht=False):
            if df_subset.empty: return 1.2 if not is_ht else 0.5, 1.2 if not is_ht else 0.5
            
            goles_f, goles_c = [], []
            pesos = []
            col_fthg, col_ftag = ("HTHG", "HTAG") if is_ht else ("FTHG", "FTAG")
            
            decay_lambda = 0.0077
            hoy = pd.Timestamp.now().normalize()

            for _, row in df_subset.iterrows():
                h_val = row.get(col_fthg, 0.0)
                a_val = row.get(col_ftag, 0.0)
                if pd.isna(h_val) or pd.isna(a_val): h_val, a_val = 0.0, 0.0

                if row["HomeTeamId"] == team_id:
                    goles_f.append(float(h_val)); goles_c.append(float(a_val))
                else:
                    goles_f.append(float(a_val)); goles_c.append(float(h_val))
                
                fecha_partido = row.get("Date")
                dias_diff = 30 if pd.isna(fecha_partido) else max(0, (hoy - fecha_partido).days)
                peso = np.exp(-decay_lambda * dias_diff)
                pesos.append(peso)
            
            suma_pesos = sum(pesos)
            if suma_pesos == 0:
                return 1.2 if not is_ht else 0.5, 1.2 if not is_ht else 0.5
                
            pesos_norm = [p / suma_pesos for p in pesos]
            avg_f = sum(g * w for g, w in zip(goles_f, pesos_norm))
            avg_c = sum(g * w for g, w in zip(goles_c, pesos_norm))
            return avg_f, avg_c

        def get_tactical_dominance_index(df_subset, team_id):
            if df_subset.empty: return False, 0.5
            sf, sa, cf, ca, count = 0, 0, 0, 0, 0
            for _, row in df_subset.iterrows():
                if pd.isna(row.get("HS")): continue
                count += 1
                if row["HomeTeamId"] == team_id:
                    sf += float(row.get("HS", 0)); sa += float(row.get("AS", 0))
                    cf += float(row.get("HC", 0)); ca += float(row.get("AC", 0))
                else:
                    sf += float(row.get("AS", 0)); sa += float(row.get("HS", 0))
                    cf += float(row.get("AC", 0)); ca += float(row.get("HC", 0))
                    
            if count >= 3:
                shots_ratio = sf / (sf + sa) if (sf + sa) > 0 else 0.5
                corners_ratio = cf / (cf + ca) if (cf + ca) > 0 else 0.5
                return True, (shots_ratio * 0.75) + (corners_ratio * 0.25)
            return False, 0.5

        home_matches = self._get_filtered_matches(home_id, league_id, es_eliminatoria)
        away_matches = self._get_filtered_matches(away_id, league_id, es_eliminatoria)

        home_global = home_matches.head(10)
        away_global = away_matches.head(10)
        home_venue = home_matches[home_matches['HomeTeamId'] == home_id].head(10)
        away_venue = away_matches[away_matches['AwayTeamId'] == away_id].head(10)

        home_form_str, home_ppg = get_form_tracker(home_global, home_id)
        away_form_str, away_ppg = get_form_tracker(away_global, away_id)
        home_venue_form_str, home_venue_ppg = get_form_tracker(home_venue, home_id)
        away_venue_form_str, away_venue_ppg = get_form_tracker(away_venue, away_id)

        hg_f_glob, hg_c_glob = get_avg_goals_decay(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_goals_decay(away_global, away_id)
        hht_f_glob, hht_c_glob = get_avg_goals_decay(home_global, home_id, is_ht=True)
        aht_f_glob, aht_c_glob = get_avg_goals_decay(away_global, away_id, is_ht=True)
        hg_f_ven, hg_c_ven = get_avg_goals_decay(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_goals_decay(away_venue, away_id)
        hht_f_ven, hht_c_ven = get_avg_goals_decay(home_venue, home_id, is_ht=True)
        aht_f_ven, aht_c_ven = get_avg_goals_decay(away_venue, away_id, is_ht=True)

        home_scored_avg = (hg_f_glob + hg_f_ven) / 2
        away_concede_avg = (ag_c_glob + ag_c_ven) / 2
        away_scored_avg = (ag_f_glob + ag_f_ven) / 2
        home_concede_avg = (hg_c_glob + hg_c_ven) / 2

        home_ht_scored_avg = (hht_f_glob + hht_f_ven) / 2
        away_ht_concede_avg = (aht_c_glob + aht_c_ven) / 2
        away_ht_scored_avg = (aht_f_glob + aht_f_ven) / 2
        home_ht_concede_avg = (hht_c_glob + hht_c_ven) / 2

        lambda_home_base = (home_scored_avg + away_concede_avg) / 2
        lambda_away_base = (away_scored_avg + home_concede_avg) / 2
        
        dif_global = 0
        if es_eliminatoria:
            lambda_home, lambda_away, dif_global = self._apply_knockout_context(home_id, away_id, league_id, lambda_home_base, lambda_away_base)
        else:
            lambda_home, lambda_away = lambda_home_base, lambda_away_base
            
        h_has_tac, h_tac_idx = get_tactical_dominance_index(home_global, home_id)
        a_has_tac, a_tac_idx = get_tactical_dominance_index(away_global, away_id)
        
        tactical_mod_home, tactical_mod_away = 1.0, 1.0
        if h_has_tac and a_has_tac:
            diff = h_tac_idx - a_tac_idx
            mod = max(-0.20, min(0.20, diff * 0.35)) 
            tactical_mod_home += mod
            tactical_mod_away -= mod
            lambda_home *= tactical_mod_home
            lambda_away *= tactical_mod_away
            
        lambda_home_ht = (home_ht_scored_avg + away_ht_concede_avg) / 2
        lambda_away_ht = (away_ht_scored_avg + home_ht_concede_avg) / 2

        prob_matrix = self._calculate_exact_scores(lambda_home, lambda_away, max_goals=8)

        corners_matrix, cards_matrix = None, None
        stats_home = self.get_team_stats(home_team, home_id, league_id, es_eliminatoria)
        stats_away = self.get_team_stats(away_team, away_id, league_id, es_eliminatoria)

        if stats_home.get('count', 0) >= 5 and stats_away.get('count', 0) >= 5 and stats_home.get('has_details') and stats_away.get('has_details'):
            # MATRIZ CRUZADA: CÓRNERS (For Local + Against Away)
            lam_c_home = (stats_home.get('corners_f', 4.5) + stats_away.get('corners_c', 4.5)) / 2
            lam_c_away = (stats_away.get('corners_f', 4.5) + stats_home.get('corners_c', 4.5)) / 2
            corners_matrix = self._calculate_corners_matrix(lam_c_home, lam_c_away, max_corners=15)

            # MATRIZ CRUZADA: TARJETAS (For Local + Against Away)
            lam_t_home = (stats_home.get('tarjetas_f', 2.0) + stats_away.get('tarjetas_c', 2.0)) / 2
            lam_t_away = (stats_away.get('tarjetas_f', 2.0) + stats_home.get('tarjetas_c', 2.0)) / 2
            cards_matrix = self._calculate_cards_matrix(lam_t_home, lam_t_away, max_cards=10)

        return {
            'local': home_team, 'visita': away_team,
            'local_id': home_id, 'visita_id': away_id,
            'league_id': league_id, 'es_eliminatoria': es_eliminatoria, 
            'dif_global': dif_global,
            'home_form': home_form_str, 'home_ppg': home_ppg,
            'away_form': away_form_str, 'away_ppg': away_ppg,
            'home_venue_form': home_venue_form_str, 'home_venue_ppg': home_venue_ppg,
            'away_venue_form': away_venue_form_str, 'away_venue_ppg': away_venue_ppg,
            'prob_matrix': prob_matrix,
            'corners_matrix': corners_matrix,
            'cards_matrix': cards_matrix, 
            'lambda_home_ht': lambda_home_ht,
            'lambda_away_ht': lambda_away_ht,
            'tactics_applied': h_has_tac and a_has_tac,
            'tactical_mod_home': round(tactical_mod_home, 2),
            'tactical_mod_away': round(tactical_mod_away, 2)
        }

    def get_basketball_team_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)]
        matches = matches.dropna(subset=["FTHG", "FTAG"]).sort_values(by="Date", ascending=False)
        recent = matches.head(10)
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
            form, pts = [], 0
            for _, row in df_subset.iterrows():
                hg, ag = row.get("FTHG"), row.get("FTAG")
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
            return "[" + "-".join(form) + "]", round(pts / len(form) if form else 0.0, 1)

        def get_avg_points_decay(df_subset, team_id):
            if df_subset.empty: return 105.0, 105.0
            base_weights = [0.15, 0.12, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.05, 0.04]
            pts_f, pts_c = [], []
            for _, row in df_subset.iterrows():
                h_val, a_val = row.get("FTHG"), row.get("FTAG")
                if pd.isna(h_val) or pd.isna(a_val): h_val, a_val = 0.0, 0.0
                if row["HomeTeamId"] == team_id:
                    pts_f.append(float(h_val)); pts_c.append(float(a_val))
                else:
                    pts_f.append(float(a_val)); pts_c.append(float(h_val))
            w = base_weights[:len(pts_f)]
            w_sum = sum(w)
            w = [x / w_sum for x in w]
            return float(sum(p * w_i for p, w_i in zip(pts_f, w))), float(sum(p * w_i for p, w_i in zip(pts_c, w)))

        home_global = self.df[(self.df['HomeTeamId'] == home_id) | (self.df['AwayTeamId'] == home_id)].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(10)
        away_global = self.df[(self.df['HomeTeamId'] == away_id) | (self.df['AwayTeamId'] == away_id)].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(10)
        home_venue = self.df[self.df['HomeTeamId'] == home_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(10)
        away_venue = self.df[self.df['AwayTeamId'] == away_id].dropna(subset=['FTHG', 'FTAG']).sort_values(by="Date", ascending=False).head(10)

        home_form_str, home_ppg = get_form_tracker(home_global, home_id)
        away_form_str, away_ppg = get_form_tracker(away_global, away_id)
        home_venue_form_str, home_venue_ppg = get_form_tracker(home_venue, home_id)
        away_venue_form_str, away_venue_ppg = get_form_tracker(away_venue, away_id)

        hg_f_glob, hg_c_glob = get_avg_points_decay(home_global, home_id)
        ag_f_glob, ag_c_glob = get_avg_points_decay(away_global, away_id)
        hg_f_ven, hg_c_ven = get_avg_points_decay(home_venue, home_id)
        ag_f_ven, ag_c_ven = get_avg_points_decay(away_venue, away_id)

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
            'local': home_team, 'visita': away_team, 'local_id': home_id, 'visita_id': away_id,   
            'prob_home': prob_home, 'prob_away': prob_away, 'probs': [prob_home, 0.0, prob_away],
            'puntos_proyectados': total_projected_points, 'has_overtime': has_overtime,
            'score_value': max(prob_home, prob_away),
            'home_form': home_form_str, 'home_ppg': home_ppg, 'away_form': away_form_str, 'away_ppg': away_ppg,
            'home_venue_form': home_venue_form_str, 'home_venue_ppg': home_venue_ppg,
            'away_venue_form': away_venue_form_str, 'away_venue_ppg': away_venue_ppg
        }

    def get_basketball_overtime_stats(self, team_name, team_id):
        matches = self.df[(self.df["HomeTeamId"] == team_id) | (self.df["AwayTeamId"] == team_id)].sort_values(by="Date", ascending=False).head(10)
        count = len(matches)
        if matches.empty or count == 0:
            return {"partidos_ot": 0, "promedio_puntos_ot": 0.0, "total_partidos": 0}

        partidos_ot = 0
        puntos_ot_lista = []
        for _, row in matches.iterrows():
            if row.get("Status") == "AOT" if "Status" in row else False:
                partidos_ot += 1
                pts_extra = row.get("ExtraPoints", 0.0)
                if pd.notna(pts_extra): puntos_ot_lista.append(float(pts_extra))

        return {
            "partidos_ot": partidos_ot,
            "promedio_puntos_ot": float(np.nanmean(puntos_ot_lista)) if puntos_ot_lista else 0.0,
            "total_partidos": count
        }

    def get_top_by_league(self, proyecciones, n=None):
        sorted_projs = sorted(proyecciones, key=lambda x: x.get('score_value', 0), reverse=True)
        return sorted_projs[:n] if n else sorted_projs
