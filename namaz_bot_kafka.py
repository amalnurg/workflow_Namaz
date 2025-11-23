#!/usr/bin/env python3
import requests
import logging
from datetime import datetime, timedelta, timezone
import time
import json
from kafka import KafkaProducer

# ==================== НАСТРОЙКИ ====================
TELEGRAM_BOT_TOKEN = "8397802323:AAEIVNDvG0UWq9mdyA5gqlrPVjycFRanzCI"
TELEGRAM_CHAT_ID = "1959373637"
CITY = "Ufa"
COUNTRY = "Russia"
KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC = 'namaz-notifications'

# Глобальная переменная для отслеживания отправленных уведомлений
sent_notifications = {}

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('namaz-bot-kafka.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# ==================== KAFKA PRODUCER ====================
def create_kafka_producer():
    """Создает Kafka producer"""
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BROKER],
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            retries=5
        )
        logger.info("✅ Kafka producer создан")
        return producer
    except Exception as e:
        logger.error(f"❌ Ошибка создания Kafka producer: {e}")
        return None

def send_to_kafka(producer, message_data):
    """Отправляет сообщение в Kafka"""
    try:
        future = producer.send(KAFKA_TOPIC, message_data)
        future.get(timeout=10)
        logger.info(f"✅ Сообщение отправлено в Kafka: {message_data}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Kafka: {e}")
        return False

# ==================== TELEGRAM ====================
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

# ==================== ОСНОВНАЯ ЛОГИКА ====================
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

def check_prayer_time(timings, kafka_producer):
    """Проверяем время до намазов и отправляем уведомления"""
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
        
        prayer_dt = datetime.strptime(prayer_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day,
            tzinfo=utc_plus_5
        )
        
        if prayer_dt < now:
            prayer_dt += timedelta(days=1)
        
        time_diff = (prayer_dt - now).total_seconds() / 60
        
        if 0 < time_diff < min_time_diff:
            min_time_diff = time_diff
            next_prayer_name = prayer_name
            next_prayer_time = prayer_time
        
        logger.info(f"🕌 {prayer_name}: {prayer_time} (через {time_diff:.1f} мин)")
        
        if 0 < time_diff <= 5:
            notification_key = f"{prayer_name}_{now.strftime('%Y-%m-%d')}"
            
            if notification_key not in sent_notifications:
                message = f"""
🕌 ВНИМАНИЕ!

До намаза {prayer_name} осталось {time_diff:.0f} минут!
⏰ Время: {prayer_time}

🚰 Не забудь совершить омовение!
"""
                
                # Создаем сообщение для Kafka
                kafka_message = {
                    'timestamp': now.isoformat(),
                    'prayer_name': prayer_name,
                    'prayer_time': prayer_time,
                    'minutes_remaining': time_diff,
                    'message': message,
                    'type': 'prayer_notification'
                }
                
                # Отправляем в Kafka
                if kafka_producer and send_to_kafka(kafka_producer, kafka_message):
                    logger.info(f"🚨 УВЕДОМЛЕНИЕ отправлено в Kafka: {prayer_name}")
                    # Отправляем в Telegram
                    send_telegram_message(message)
                    sent_notifications[notification_key] = True
                    return True
    
    if next_prayer_name:
        logger.info(f"📊 Ближайший намаз: {next_prayer_name} в {next_prayer_time} (через {min_time_diff:.1f} мин)")
    else:
        logger.info("⏳ Намазов на сегодня не осталось")
    
    return False

def main():
    logger.info("🕌 Бот для намазов с Kafka запущен!")
    
    # Создаем Kafka producer
    kafka_producer = create_kafka_producer()
    
    # Отправляем тестовое сообщение
    test_message = "🕌 Бот для намазов с Kafka запущен! Буду уведомлять за 5 минут до намаза."
    send_telegram_message(test_message)
    
    if kafka_producer:
        test_kafka_msg = {
            'timestamp': datetime.now().isoformat(),
            'type': 'system',
            'message': 'Бот запущен',
            'status': 'started'
        }
        send_to_kafka(kafka_producer, test_kafka_msg)
    
    while True:
        timings = get_prayer_times()
        if timings:
            logger.info("📅 Расписание получено, проверяем время...")
            check_prayer_time(timings, kafka_producer)
        else:
            logger.error("Не удалось получить расписание")
        
        logger.info("⏳ Ждем 1 минуту...")
        time.sleep(60)

if __name__ == "__main__":
    main()