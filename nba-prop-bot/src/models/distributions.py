from scipy.stats import poisson, norm, nbinom
import numpy as np
import pandas as pd
from typing import Dict, Optional

def get_market_col(market: str) -> str:
    market_map = {
        "player_points": "PTS",
        "player_rebounds": "REB",
        "player_assists": "AST",
        "player_threes": "FG3M",
        "player_points_rebounds_assists": "PRA"
    }
    return market_map.get(market, "")

def poisson_over_under(mean: float, line: float) -> Dict[str, float]:
    if mean <= 0: return {"prob_over": 0.0, "prob_under": 1.0}
    prob_under = poisson.cdf(np.floor(line), mu=mean)
    return {"prob_over": 1.0 - prob_under, "prob_under": prob_under}

def negative_binomial_over_under(mean: float, variance: float, line: float) -> Dict[str, float]:
    if mean <= 0: return {"prob_over": 0.0, "prob_under": 1.0}
    if variance <= mean:
        return poisson_over_under(mean, line) # Fallback to Poisson if not overdispersed
    
    # nbinom parameters: n (number of successes), p (probability of success)
    p = mean / variance
    n = (mean ** 2) / (variance - mean)
    
    prob_under = nbinom.cdf(np.floor(line), n, p)
    return {"prob_over": 1.0 - prob_under, "prob_under": prob_under}

def normal_over_under(mean: float, variance: float, line: float) -> Dict[str, float]:
    if mean <= 0: return {"prob_over": 0.0, "prob_under": 1.0}
    prob_under = norm.cdf(line, loc=mean, scale=np.sqrt(variance))
    return {"prob_over": 1.0 - prob_under, "prob_under": prob_under}

def bootstrap_over_under(logs: pd.DataFrame, col: str, line: float, num_draws: int = 10000) -> Dict[str, float]:
    if logs.empty or len(logs) < 10:
        return {} # Return empty to signal fallback
    
    if col == "PRA":
        # Check if columns exist
        if not all(c in logs.columns for c in ['PTS', 'REB', 'AST']): return {}
        data = (logs['PTS'] + logs['REB'] + logs['AST']).values
    else:
        if col not in logs.columns:
            return {}
        data = logs[col].values
        
    if len(data) == 0:
        return {}
        
    draws = np.random.choice(data, size=num_draws, replace=True)
    prob_over = np.mean(draws > line)
    return {"prob_over": float(prob_over), "prob_under": float(1.0 - prob_over)}

DISPERSION_ALPHAS = {
    'player_rebounds': 0.15,
    'player_assists': 0.12,
    'player_threes': 0.20
}

def get_probability_distribution(market: str, mean: float, line: float, logs: Optional[pd.DataFrame] = None, variance_scale: float = 1.0) -> Dict[str, float]:
    if mean <= 0: return {"prob_over": 0.0, "prob_under": 1.0}
    
    if market in ['player_points', 'player_points_rebounds_assists']:
        # Phase 4 Empirical Bootstrap
        if logs is not None and not logs.empty:
            col = get_market_col(market)
            recent_20 = logs.head(20)
            bootstrapped = bootstrap_over_under(recent_20, col, line)
            if bootstrapped:
                return bootstrapped
                
        # Phase 4 Normal Fallback with Variance Scale
        variance = max(mean * 1.25, 4.0) * variance_scale
        return normal_over_under(mean, variance, line)
        
    elif market in ['player_rebounds', 'player_assists', 'player_threes']:
        # Phase 4 Negative Binomial
        alpha = DISPERSION_ALPHAS.get(market, 0.1)
        variance = (mean + (alpha * (mean ** 2))) * variance_scale
        return negative_binomial_over_under(mean, variance, line)
    else:
        variance = max(mean * 1.25, 4.0) * variance_scale
        return normal_over_under(mean, variance, line)
