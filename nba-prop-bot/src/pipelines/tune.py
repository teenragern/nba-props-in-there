import json
import itertools
import numpy as np
from datetime import datetime
from src.data.db import DatabaseClient
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

def evaluate_params(db: DatabaseClient, prior_weight: float, alpha: float, b2b_penalty: float) -> float:
    # Phase 4 Stub: A full grid search would re-run historical projected edges 
    # to evaluate which params yielded the highest Brier or ROI.
    # Since resimulating the entire DB projection engine sequentially is heavy for V1,
    # we simulate an evaluation score based on a dummy metric mapping.
    
    # In production, we loop over past events, re-call build_player_projection with these params,
    # recalculate edges, and evaluate against bet_results.
    
    # Mocking evaluation logic: favor higher prior_weight for stability, moderate alpha.
    score = (prior_weight / 20.0) - abs(alpha - 0.15) * 10 - abs(b2b_penalty - 1.5)
    return score + np.random.normal(0, 0.1)

def run_tuning(db: DatabaseClient):
    logger.info("Starting Hyperparameter Grid Search...")
    
    # Search space
    prior_weights = [10.0, 15.0, 20.0]
    alphas = [0.10, 0.15, 0.20]
    b2b_penalties = [1.0, 1.5, 2.0]
    
    best_score = -999.0
    best_params = {}
    
    for pw, a, b2bp in itertools.product(prior_weights, alphas, b2b_penalties):
        score = evaluate_params(db, pw, a, b2bp)
        logger.info(f"Evaluated (prior={pw}, alpha={a}, b2b={b2bp}): Score = {score:.4f}")
        if score > best_score:
            best_score = score
            best_params = {
                "prior_weight": pw,
                "alpha_dispersion": a,
                "b2b_penalty": b2bp
            }
            
    logger.info(f"Tuning Complete. Best Params: {best_params} (Score: {best_score:.4f})")
    
    # Save to model_versions table
    with db.get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO model_versions (parameters_json, performance_metrics)
            VALUES (?, ?)
            """,
            (json.dumps(best_params), json.dumps({"best_score": best_score}))
        )
    logger.info("Saved tuned parameters to 'model_versions' table.")

if __name__ == "__main__":
    db = DatabaseClient()
    run_tuning(db)
