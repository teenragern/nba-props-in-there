import time
import schedule
from src.utils.logging_utils import get_logger
from src.clients.telegram_bot import TelegramBotClient
from src.pipelines.sync_events import sync_events
from src.pipelines.scan_props import scan_props
from src.pipelines.update_clv import update_clv_lines
from src.pipelines.settle_results import settle_alerts
from src.pipelines.analytics import generate_analytics
from src.pipelines.calibration import check_calibration
from src.pipelines.tune import run_tuning
from src.data.db import DatabaseClient
from src.pipelines.market_stats import analyze_market_stats
from src.pipelines.steam import check_steam
from src.pipelines.exposure import check_exposure
from src.pipelines.timing_analysis import analyze_timing

logger = get_logger(__name__)
bot = TelegramBotClient()

def notify(job_name, func, *args):
    logger.info(f"Executing scheduled job: {job_name}")
    bot.send_message(f"⏳ <b>Starting Scheduled Job:</b> {job_name}")
    try:
        func(*args)
        bot.send_message(f"✅ <b>Finished Scheduled Job:</b> {job_name}")
    except Exception as e:
        logger.error(f"Scheduled {job_name} failed: {e}")
        bot.send_message(f"❌ <b>Failed Scheduled Job:</b> {job_name}\n\nError: {e}")

def job_sync(): notify("Sync", sync_events)
def job_scan(): notify("Scan", scan_props)
def job_clv(): notify("Update CLV", update_clv_lines)
def job_settle(): notify("Settle", settle_alerts)
def job_stats(): notify("Stats", generate_analytics)
def job_calibration(): notify("Calibration", check_calibration)
def job_tune(): notify("Tune", run_tuning, DatabaseClient())
def job_market_stats(): notify("Market Stats", analyze_market_stats)
def job_steam(): notify("Steam", check_steam)
def job_exposure(): notify("Exposure", check_exposure)
def job_timing_analysis(): notify("Timing Analysis", analyze_timing)

def start_scheduler():
    logger.info("Starting NBA Prop Bot automated scheduler...")
    
    # Run sync daily at 9:00 AM
    schedule.every().day.at("09:00").do(job_sync)
    
    # Run settle daily at 04:00 AM (after previous day NBA games finish)
    schedule.every().day.at("04:00").do(job_settle)
    
    # Run scan every 60 minutes
    schedule.every(60).minutes.do(job_scan)
    
    # Run CLV updates every 120 minutes (2 hours)
    schedule.every(120).minutes.do(job_clv)

    # NEW JOBS:
    
    # Run steam check every 15 minutes
    schedule.every(15).minutes.do(job_steam)
    
    # Run exposure check every 6 hours
    schedule.every(6).hours.do(job_exposure)
    
    # Run analytics and modeling updates daily after the morning sync
    schedule.every().day.at("09:30").do(job_stats)
    schedule.every().day.at("10:00").do(job_calibration)
    schedule.every().day.at("10:30").do(job_tune)
    schedule.every().day.at("11:00").do(job_market_stats)
    schedule.every().day.at("11:30").do(job_timing_analysis)
    
    # Run a sync immediately on startup just to ensure slate is fresh
    job_sync()

    logger.info("Scheduler loops configured. Entering wait state...")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    start_scheduler()
