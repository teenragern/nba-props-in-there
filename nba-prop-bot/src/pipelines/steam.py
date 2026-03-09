import pandas as pd
from src.data.db import DatabaseClient

def check_steam():
    db = DatabaseClient()
    with db.get_conn() as conn:
        query = """
        SELECT player_name, market, timestamp, implied_prob, bookmaker
        FROM line_history
        WHERE timestamp >= datetime('now', '-2 hour')
        """
        try:
            df = pd.read_sql_query(query, conn)
        except:
            print("No line history available.")
            return

    if df.empty:
        print("No line history available.")
        return

    print("\n===========================================")
    print("         PHASE 5 STEAM DETECTION           ")
    print("===========================================")
    
    # Group by prop
    for (player, mkt), group in df.groupby(['player_name', 'market']):
        if len(group) < 3: continue
        
        # Sort chronologically
        group = group.sort_values(by='timestamp')
        first = group.groupby('bookmaker').first()
        last = group.groupby('bookmaker').last()
        
        deltas = last['implied_prob'] - first['implied_prob']
        steams_up = deltas[deltas > 0.02]
        steams_down = deltas[deltas < -0.02]
        
        if len(steams_up) >= 3:
            books = ", ".join(steams_up.index)
            print(f"🔥 STEAM DETECTED (UP) for {player} {mkt} at {books}")
        elif len(steams_down) >= 3:
            books = ", ".join(steams_down.index)
            print(f"📉 STEAM DETECTED (DOWN) for {player} {mkt} at {books}")
            
    print("===========================================\n")

if __name__ == "__main__":
    check_steam()
