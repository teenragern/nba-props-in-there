from typing import List, Dict, Any
from src.config import MIN_PROJECTED_MINUTES
from src.models.distributions import get_probability_distribution

def get_market_feedback_factor(market: str) -> float:
    # Phase 3 Stub: After 100+ settled bets, we query db here to see if we over-estimate
    # For now, return bounded small random or static bias correction between 0.85 and 1.15
    return 1.0 

def rank_edges(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    
    for c in candidates:
        model_prob = c.get('model_prob', 0)
        implied_prob = c.get('implied_prob', 0)
        odds = c.get('odds', 0)
        proj_mins = c.get('projected_minutes', 0)
        status = c.get('injury_status', 'healthy').lower()
        market = c.get('market', '')
        mean = c.get('mean', 0)
        line = c.get('line', 0)
        side = c.get('side', '')
        var_scale = c.get('variance_scale', 1.0)
        
        if proj_mins < MIN_PROJECTED_MINUTES: continue
            
        edge = model_prob - implied_prob
        
        # Phase 4 Edge Stability Filter
        c['fragile'] = False
        if mean > 0 and model_prob > 0 and side:
            dist_up = get_probability_distribution(market, mean * 1.05, line, variance_scale=var_scale)
            dist_down = get_probability_distribution(market, mean * 0.95, line, variance_scale=var_scale)
            
            prob_up = dist_up.get(f'prob_{side.lower()}', model_prob)
            prob_down = dist_down.get(f'prob_{side.lower()}', model_prob)
            
            edge_up = prob_up - implied_prob
            edge_down = prob_down - implied_prob
            
            if (edge > 0 and (edge_up < 0 or edge_down < 0)) or (edge < 0 and (edge_up > 0 or edge_down > 0)):
                edge *= 0.70 # Reduce edge weight by 30%
                c['fragile'] = True
                
        # Phase 5 Microstructure Adjustments
        steam = c.get('steam_flag', False)
        velocity = c.get('velocity', 0.0)
        dispersion = c.get('dispersion', 0.0)
        book_role = c.get('book_role', 'neutral')
        
        if steam and edge > 0:
            edge *= 1.10 # Align with steam
        elif velocity < -0.02 and edge > 0:
            edge *= 0.80 # Fade against anti-steam
            
        if dispersion > 0.04:
            edge *= 1.05 # Inefficient
        elif dispersion > 0.0 and dispersion < 0.015:
            edge *= 0.90 # Block thin edges in perfectly efficient lines
            
        if book_role == 'sharp':
            edge *= 1.10 # Validated against sharp bookmaker
            
        # Phase 3: Feedback Loop Matrix
        factor = get_market_feedback_factor(market)
        edge = edge * factor
        
        ev = (model_prob * odds) - 1.0
        ev = ev * factor
        
        if "questionable" in status or "gtd" in status:
            edge *= 0.8
            ev *= 0.8
        elif "doubtful" in status:
            edge *= 0.5
            ev *= 0.5
        elif "out" in status:
            continue
            
        c['edge'] = edge
        c['ev'] = ev
        c['feedback_factor_applied'] = factor
        
        # Phase 5: Cross-Market Consistency Check (Risk-Adjusted EV)
        variance = (mean * 1.25) * var_scale if mean > 0 else 1.0
        c['risk_adjusted_ev'] = ev / variance if variance > 0 else ev
        
        ranked.append(c)
        
    # Phase 5: Sort by risk-adjusted EV
    ranked.sort(key=lambda x: x.get('risk_adjusted_ev', 0), reverse=True)
    return ranked
