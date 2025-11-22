#!/usr/bin/env python3
import requests
import logging
from datetime import datetime, timedelta, timezone
import time
import json

# ==================== НАСТРОЙКИ ====================
TELEGRAM_BOT_TOKEN = "8397802323:AAEIVNDvG0UWq9mdyA5gqlrPVjycFRanzCI"
TELEGRAM_CHAT_ID = "1959373637"
CITY = "Ufa"
COUNTRY = "Russia"

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('namaz-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

def get_prayer_times():
    """Получаем расписание намазов из API"""
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={CITY}&country={COUNTRY}&method=2"
        logger.info(f"Запрос к API: {url}")
        
        response = requests.get(url)
        data = response.json()
        
        if data['code'] == 200:
            logger.info("✅ Расписание получено успешно")
            return data['data']['timings']
        else:
            logger.error(f"❌ Ошибка API: {data}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка при запросе: {e}")
        return None

def send_telegram_message(message):
    """Отправляем сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info("✅ Сообщение отправлено в Telegram")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def check_prayer_time(timings):
    """Проверяем время до намазов с учетом UTC+5 для Уфы"""
    # Уфа = UTC+5
    utc_plus_5 = timezone(timedelta(hours=5))
    now = datetime.now(utc_plus_5)
    
    current_time = now.strftime("%H:%M")
    logger.info(f"⏰ Текущее время Уфа: {current_time}")
    
    prayers = {
        'Fajr': 'Фаджр',
        'Dhuhr': 'Зухр', 
        'Asr': 'Аср',
        'Maghrib': 'Магриб',
        'Isha': 'Иша'
    }
    
    next_prayer_name = None
    next_prayer_time = None
    min_time_diff = float('inf')
    
    for prayer_key, prayer_name in prayers.items():
        prayer_time = timings[prayer_key]
        
        # Создаем datetime для намаза СЕГОДНЯ в UTC+5
        prayer_dt = datetime.strptime(prayer_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day,
            tzinfo=utc_plus_5
        )
        
        # Если намаз уже прошел сегодня, берем на ЗАВТРА
        if prayer_dt < now:
            prayer_dt += timedelta(days=1)
        
        time_diff = (prayer_dt - now).total_seconds() / 60
        
        # Находим ближайший намаз
        if 0 < time_diff < min_time_diff:
            min_time_diff = time_diff
            next_prayer_name = prayer_name
            next_prayer_time = prayer_time
        
        logger.info(f"🕌 {prayer_name}: {prayer_time} (через {time_diff:.1f} мин)")
        
        # Если до намаза 5 минут или меньше - отправляем уведомление
        if 0 < time_diff <= 5:
            message = f"🕌 ВНИМАНИЕ!\nДо намаза {prayer_name} осталось {time_diff:.0f} минут!\nВремя: {prayer_time}"
            logger.info(f"🚨 УВЕДОМЛЕНИЕ: {message}")
            send_telegram_message(message)
            return True
    
    if next_prayer_name:
        logger.info(f"📊 Ближайший намаз: {next_prayer_name} в {next_prayer_time} (через {min_time_diff:.1f} мин)")
    else:
        logger.info("⏳ Намазов на сегодня не осталось")
    
    return False

def main():
    logger.info("🕌 Бот для намазов запущен!")
    
    # Отправляем тестовое сообщение при запуске
    send_telegram_message("🕌 Бот для намазов запущен! Буду уведомлять за 5 минут до намаза.")
    
    while True:
        # Получаем расписание
        timings = get_prayer_times()
        if timings:
            logger.info("📅 Расписание получено, проверяем время...")
            check_prayer_time(timings)
        else:
            logger.error("Не удалось получить расписание")
        
        # Ждем 1 минуту перед следующей проверкой
        logger.info("⏳ Ждем 1 минуту...")
        time.sleep(60)

if __name__ == "__main__":
    main()