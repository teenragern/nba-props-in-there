from datetime import datetime

def get_current_season() -> str:
    now = datetime.now()
    if now.month > 9:
        return f"{now.year}-{str(now.year+1)[-2:]}"
    else:
        return f"{now.year-1}-{str(now.year)[-2:]}"
