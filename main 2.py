import os
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@Trevoga_Kiev_oblast")
ALERTS_API_TOKEN = os.environ["ALERTS_API_TOKEN"]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

ALERTS_URL = "https://api.alerts.in.ua/v1/alerts/active.json"
KYIV_OBLAST_UID = "14"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {ALERTS_API_TOKEN}"})
kyiv_tz = ZoneInfo("Europe/Kyiv")


def get_kyiv_alerts():
    response = session.get(ALERTS_URL, timeout=15)
    response.raise_for_status()
    data = response.json()

    alerts = data.get("alerts", [])
    return [
        alert
        for alert in alerts
        if str(alert.get("location_oblast_uid")) == KYIV_OBLAST_UID
        and alert.get("alert_type") == "air_raid"
    ]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    response.raise_for_status()


def format_kyiv_time(iso_value):
    if not iso_value:
        return datetime.now(kyiv_tz).strftime("%H:%M")
    value = iso_value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value).astimezone(kyiv_tz)
    return dt.strftime("%H:%M")


def build_start_message(alerts):
    locations = []
    for alert in alerts:
        title = alert.get("location_title") or ""
        if title and title not in locations:
            locations.append(title)

    if any(a.get("location_type") == "oblast" for a in alerts):
        scope = "Київська область"
    elif locations:
        scope = ", ".join(locations[:8])
    else:
        scope = "Київська область"

    started = min(
        (a.get("started_at") for a in alerts if a.get("started_at")),
        default=None,
    )

    return (
        "🚨 ПОВІТРЯНА ТРИВОГА\n\n"
        f"📍 {scope}\n"
        f"🕐 Початок: {format_kyiv_time(started)}\n\n"
        "⚠️ Перейдіть у безпечне місце та не ігноруйте сигнал повітряної тривоги."
    )


def build_end_message():
    now = datetime.now(kyiv_tz).strftime("%H:%M")
    return (
        "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
        "📍 Київська область\n"
        f"🕐 Відбій: {now}\n\n"
        "Бережіть себе."
    )


def main():
    logging.info("Bot started. Monitoring Kyiv Oblast.")
    previous_active = None

    while True:
        try:
            alerts = get_kyiv_alerts()
            current_active = len(alerts) > 0

            # First successful poll initializes the state and does not send
            # a duplicate alert for one that was already active before startup.
            if previous_active is None:
                previous_active = current_active
                logging.info("Initial state: %s", "ACTIVE" if current_active else "CLEAR")

            elif current_active and not previous_active:
                send_telegram(build_start_message(alerts))
                logging.info("Alert notification sent.")

            elif not current_active and previous_active:
                send_telegram(build_end_message())
                logging.info("All-clear notification sent.")

            previous_active = current_active

        except requests.HTTPError as exc:
            logging.error("API/HTTP error: %s", exc)
        except requests.RequestException as exc:
            logging.error("Network error: %s", exc)
        except Exception:
            logging.exception("Unexpected error")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
