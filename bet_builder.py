import numpy as np
from scipy.stats import poisson

class BetBuilderEngine:
    @staticmethod
    def _get_joint_prob(matrix, condition_func):
        prob = 0.0
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                if condition_func(i, j): prob += matrix[i, j]
        return prob

    @classmethod
    def generar_mercados(cls, raw_data):
        matrix = raw_data['prob_matrix']
        lam_home_ht = raw_data['lambda_home_ht']
        lam_away_ht = raw_data['lambda_away_ht']

        prob_home = np.tril(matrix, -1).sum()
        prob_draw = np.diag(matrix).sum()
        prob_away = np.triu(matrix, 1).sum()

        prob_1X = prob_home + prob_draw
        prob_X2 = prob_away + prob_draw
        prob_12 = prob_home + prob_away

        suma_sin_empate = prob_home + prob_away
        prob_DNB_L = (prob_home / suma_sin_empate) if suma_sin_empate > 0 else 0
        prob_DNB_V = (prob_away / suma_sin_empate) if suma_sin_empate > 0 else 0

        under_0_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 0)
        under_1_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 1)
        under_2_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 2)
        under_3_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 3)
        under_4_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 4)
        under_5_5 = cls._get_joint_prob(matrix, lambda i, j: i + j <= 5)

        btts_yes = matrix[1:, 1:].sum()
        btts_no = 1 - btts_yes

        lam_ht_total = lam_home_ht + lam_away_ht
        prob_over_0_5_ht = 1 - poisson.cdf(0, lam_ht_total)
        prob_under_1_5_ht = poisson.cdf(1, lam_ht_total)

        p_home_marginal = matrix.sum(axis=1)
        p_away_marginal = matrix.sum(axis=0)

        home_under_0_5 = p_home_marginal[0]
        away_under_0_5 = p_away_marginal[0]

        score_probs = []
        for i in range(3):
            for j in range(3):
                score_probs.append((f"{i}-{j}", matrix[i, j]))
        score_probs.sort(key=lambda x: x[1], reverse=True)
        top_scores = [s[0] for s in score_probs[:3]]

        raw_sgbb = {
            '1X_U25': cls._get_joint_prob(matrix, lambda i, j: i >= j and i+j <= 2),
            '1X_U35': cls._get_joint_prob(matrix, lambda i, j: i >= j and i+j <= 3),
            '1X_U45': cls._get_joint_prob(matrix, lambda i, j: i >= j and i+j <= 4),
            '1X_O15': cls._get_joint_prob(matrix, lambda i, j: i >= j and i+j >= 2),
            '1X_O25': cls._get_joint_prob(matrix, lambda i, j: i >= j and i+j >= 3),
            'X2_U25': cls._get_joint_prob(matrix, lambda i, j: j >= i and i+j <= 2),
            'X2_U35': cls._get_joint_prob(matrix, lambda i, j: j >= i and i+j <= 3),
            'X2_U45': cls._get_joint_prob(matrix, lambda i, j: j >= i and i+j <= 4),
            'X2_O15': cls._get_joint_prob(matrix, lambda i, j: j >= i and i+j >= 2),
            'X2_O25': cls._get_joint_prob(matrix, lambda i, j: j >= i and i+j >= 3),
            '1_U35': cls._get_joint_prob(matrix, lambda i, j: i > j and i+j <= 3),
            '1_O15': cls._get_joint_prob(matrix, lambda i, j: i > j and i+j >= 2),
            '2_U35': cls._get_joint_prob(matrix, lambda i, j: j > i and i+j <= 3),
            '2_O15': cls._get_joint_prob(matrix, lambda i, j: j > i and i+j >= 2),
            'BTTS_O25': cls._get_joint_prob(matrix, lambda i, j: i > 0 and j > 0 and i+j >= 3),
            'BTTS_No_U25': cls._get_joint_prob(matrix, lambda i, j: (i == 0 or j == 0) and i+j <= 2),
            'BTTS_No_U35': cls._get_joint_prob(matrix, lambda i, j: (i == 0 or j == 0) and i+j <= 3),
            '1X_BTTS_Yes': cls._get_joint_prob(matrix, lambda i, j: i >= j and i > 0 and j > 0),
            'X2_BTTS_Yes': cls._get_joint_prob(matrix, lambda i, j: j >= i and i > 0 and j > 0),
        }

        sgbb_titanio = {}
        for combo, prob in raw_sgbb.items():
            if combo.startswith('1_') or combo.startswith('2_') or 'BTTS_No' in combo:
                if prob >= 0.90: sgbb_titanio[combo] = prob
            else:
                if prob >= 0.80: sgbb_titanio[combo] = prob

        safe_btts_no = btts_no if btts_no >= 0.90 else 0.0

        corners_markets = {'over_8_5_corners': 0.0, 'over_9_5_corners': 0.0}
        if 'corners_matrix' in raw_data and raw_data['corners_matrix'] is not None:
            c_matrix = raw_data['corners_matrix']
            under_8_5_c = cls._get_joint_prob(c_matrix, lambda i, j: i + j <= 8)
            under_9_5_c = cls._get_joint_prob(c_matrix, lambda i, j: i + j <= 9)
            corners_markets = {
                'under_8_5_corners': under_8_5_c, 'over_8_5_corners': 1 - under_8_5_c,
                'under_9_5_corners': under_9_5_c, 'over_9_5_corners': 1 - under_9_5_c,
            }

        cards_markets = {'over_4_5_cards': 0.0, 'over_5_5_cards': 0.0}
        if 'cards_matrix' in raw_data and raw_data['cards_matrix'] is not None:
            t_matrix = raw_data['cards_matrix']
            under_3_5_t = cls._get_joint_prob(t_matrix, lambda i, j: i + j <= 3)
            under_4_5_t = cls._get_joint_prob(t_matrix, lambda i, j: i + j <= 4)
            under_5_5_t = cls._get_joint_prob(t_matrix, lambda i, j: i + j <= 5)
            cards_markets = {
                'under_3_5_cards': under_3_5_t, 'over_3_5_cards': 1 - under_3_5_t,
                'under_4_5_cards': under_4_5_t, 'over_4_5_cards': 1 - under_4_5_t,
                'under_5_5_cards': under_5_5_t, 'over_5_5_cards': 1 - under_5_5_t,
            }

        result = raw_data.copy()
        result.update({
            'probs': [prob_home, prob_draw, prob_away],
            'btts': btts_yes, 'btts_no': safe_btts_no,
            'scores': top_scores, 'score_value': max(prob_home, prob_draw, prob_away), 
            'prob_1X': prob_1X, 'prob_X2': prob_X2, 'prob_12': prob_12,
            'prob_DNB_L': prob_DNB_L, 'prob_DNB_V': prob_DNB_V,
            'over_0_5': 1 - under_0_5, 'under_0_5': under_0_5,
            'over_1_5': 1 - under_1_5, 'under_1_5': under_1_5,
            'over_2_5': 1 - under_2_5, 'under_2_5': under_2_5,
            'over_3_5': 1 - under_3_5, 'under_3_5': under_3_5,
            'over_4_5': 1 - under_4_5, 'under_4_5': under_4_5,
            'over_5_5': 1 - under_5_5, 'under_5_5': under_5_5,
            'prob_over_0_5_ht': prob_over_0_5_ht, 'prob_under_1_5_ht': prob_under_1_5_ht,
            'home_over_0_5': 1 - home_under_0_5, 'home_over_1_5': 1 - p_home_marginal[:2].sum(), 'home_over_2_5': 1 - p_home_marginal[:3].sum(),
            'away_over_0_5': 1 - away_under_0_5, 'away_over_1_5': 1 - p_away_marginal[:2].sum(), 'away_over_2_5': 1 - p_away_marginal[:3].sum(),
            'home_clean_sheet': away_under_0_5, 'away_clean_sheet': home_under_0_5,
            'sgbb': sgbb_titanio,
            **corners_markets, **cards_markets
        })
        
        result.pop('prob_matrix', None)
        result.pop('corners_matrix', None)
        result.pop('cards_matrix', None)
        return result
