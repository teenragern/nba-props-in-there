# NBA Prop Bot V1

A production-ready NBA player prop betting bot that scans for edges by building baseline projections and comparing them to live sportsbook odds.

## Features
- Fetches real-time odds from The Odds API
- Syncs necessary stats and game logs from the official NBA stats API wrapper (`nba_api`)
- Builds simple minutes and rate-based projections for player points, rebounds, assists, threes, and PRA
- Evaluates statistical distributions (Poisson, Normal) to find fair over/under odds
- Applies penalties for projected low minutes or injury uncertainty
- Alerts you on Telegram when actionable edges are found

## Prerequisites
- Python 3.11
- Telegram Bot Token and Chat ID
- The Odds API Key (Starter tier recommended for quota constraints)

## Setup

1. **Environment Setup**
    ```sh
    python -m venv venv
    venv\Scripts\activate  # Windows
    pip install -r requirements.txt
    ```

2. **Configuration**
    Copy `.env.example` to `.env` and fill in your details:
    ```sh
    cp .env.example .env
    ```

3. **Initialize Database Flow**
    The SQLite database and schema will automatically build when the script runs for the first time.

## Usage

The bot comes with a CLI entrypoint `main.py` which provides 4 commands:

- `python main.py sync` - Synchronizes today's events, the injury report, and baseline team stats to the local database. Run this once every few hours.
- `python main.py scan` - Scans all available player props for the day's games, computes edges, and dispatches Telegram alerts. Run this frequently (e.g. every 10 mins).
- `python main.py run` - Runs a `sync` followed immediately by a `scan`.
- `python main.py settle` - Settles yesterday's alerts against actual results (Stub for V1).

## Quota-Saving Strategy
For V1, since we are using the $30/month Odds API plan:
- Event syncing separates the broad schedule from the intensive prop odds.
- We pull only the specific markets `player_points`, `player_rebounds`, `player_assists`, `player_threes`, `player_points_rebounds_assists`.
- Player info and stats are fetched via `nba_api` (free) to avoid paying for advanced endpoints on other services.
- A local database cache prevents redundant API hits for unchanged injury reports or events.

## Model Logic
- **Minutes**: Recent average scaled down severely by Doubtful/Questionable states.
- **Rates**: Recent stat production per minute.
- **Distributions**:
  - Rebounds, Assists, Threes: Poisson (discrete events).
  - Points, PRA: Normal distribution.
- **Devig**: Standard multiplicative vig removal.
- **Edge Rank**: Probability delta with custom minor penalties for minutes stability and injury uncertainty.

## Known Limitations
1. Injury parsing is largely stubbed out. The official NBA API does not expose injuries cleanly; a robust production version usually scrapes CBS or ESPN or pays for a dedicated sports feed.
2. The statistical distributions strictly use historical standard deviation and a naive Poisson without opponent pace adjustments in this baseline V1 iteration.
3. Does not support correlation matrices for SGP betting. Single props only.
