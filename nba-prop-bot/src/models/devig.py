from typing import Tuple

def decimal_to_implied_prob(odds: float) -> float:
    if odds <= 1.0: return 0.0
    return 1.0 / odds

def devig_two_way(prob_over_raw: float, prob_under_raw: float) -> Tuple[float, float]:
    total = prob_over_raw + prob_under_raw
    if total == 0: return 0.0, 0.0
    return prob_over_raw / total, prob_under_raw / total
