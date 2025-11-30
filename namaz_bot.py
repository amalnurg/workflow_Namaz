cat > namaz_bot_fixed.py << 'EOF'
#!/usr/bin/env python3
import requests
import logging
from datetime import datetime, timedelta, timezone
import time
import json
import os

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

def save_sent_notifications(sent_notifications):
    """Сохраняем отправленные уведомления в файл"""
    try:
        with open('sent_notifications.json', 'w') as f:
            json.dump(sent_notifications, f)
        logger.info("💾 Состояние уведомлений сохранено")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения уведомлений: {e}")

def load_sent_notifications():
    """Загружаем отправленные уведомления из файл"""
    try:
        if os.path.exists('sent_notifications.json'):
            with open('sent_notifications.json', 'r') as f:
                notifications = json.load(f)
                logger.info(f"📁 Загружено {len(notifications)} уведомлений из файла")
                return notifications
        else:
            logger.info("📁 Файл уведомлений не найден, начинаем с чистого листа")
            return {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки уведомлений: {e}")
        return {}

def cleanup_old_notifications(sent_notifications):
    """Очищаем устаревшие уведомления (вчерашние и старые)"""
    utc_plus_5 = timezone(timedelta(hours=5))
    today = datetime.now(utc_plus_5).strftime("%Y-%m-%d")
    
    cleaned_count = 0
    for key in list(sent_notifications.keys()):
        # Удаляем уведомления за предыдущие дни
        if key.endswith(today) == False and "_cooldown" not in key:
            # Проверяем, что это дата (формат "Намаз_2024-01-01")
            if any(prayer in key for prayer in ['Фаджр', 'Зухр', 'Аср', 'Магриб', 'Иша']):
                del sent_notifications[key]
                cleaned_count += 1
        
        # Удаляем устаревшие cooldown-ключи (старше 2 часов)
        if "_cooldown" in key:
            cooldown_time = sent_notifications[key].get('timestamp', 0)
            current_time = time.time()
            if current_time - cooldown_time > 7200:  # 2 часа в секундах
                del sent_notifications[key]
                cleaned_count += 1
    
    if cleaned_count > 0:
        logger.info(f"🧹 Очищено {cleaned_count} устаревших уведомлений")
    
    return sent_notifications

def check_prayer_time(timings, sent_notifications):
    """Проверяем время до намазов с улучшенной логикой предотвращения спама"""
    # Уфа = UTC+5
    utc_plus_5 = timezone(timedelta(hours=5))
    now = datetime.now(utc_plus_5)
    
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
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
    
    # Сначала находим ближайший намаз
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
    
    # Улучшенная логика уведомлений - ТОЛЬКО ДЛЯ БЛИЖАЙШЕГО НАМАЗА
    notification_sent = False
    
    if next_prayer_name and 0 < min_time_diff <= 5:
        notification_key = f"{next_prayer_name}_{current_date}"
        cooldown_key = f"{next_prayer_name}_cooldown"
        
        # Проверяем несколько условий для предотвращения спама:
        # 1. Не отправляли ли уже уведомление для этого намаза сегодня
        # 2. Не отправляли ли уведомление в последние 30 минут (cooldown)
        
        notification_sent_today = notification_key in sent_notifications
        cooldown_active = cooldown_key in sent_notifications
        
        if not notification_sent_today and not cooldown_active:
            message = f"🕌 ВНИМАНИЕ!\n\nДо намаза {next_prayer_name} осталось {min_time_diff:.0f} минут!\n⏰ Время: {next_prayer_time}\n\n🚰 Не забудь совершить омовение!"
            logger.info(f"🚨 УВЕДОМЛЕНИЕ: {message}")
            
            if send_telegram_message(message):
                # Сохраняем как отправленное на сегодня
                sent_notifications[notification_key] = {
                    'sent_at': current_time,
                    'timestamp': time.time()
                }
                # Добавляем защиту от повторения на 30 минут
                sent_notifications[cooldown_key] = {
                    'set_at': current_time,
                    'timestamp': time.time()
                }
                notification_sent = True
                logger.info(f"✅ Уведомление для {next_prayer_name} отправлено и сохранено")
                
        elif cooldown_active:
            cooldown_data = sent_notifications[cooldown_key]
            logger.info(f"⏳ Уведомление для {next_prayer_name} уже было отправлено недавно (в {cooldown_data.get('set_at', 'unknown')})")
        else:
            notification_data = sent_notifications[notification_key]
            logger.info(f"📨 Уведомление для {next_prayer_name} уже было отправлено сегодня (в {notification_data.get('sent_at', 'unknown')})")
    
    elif next_prayer_name:
        logger.info(f"📊 Ближайший намаз: {next_prayer_name} в {next_prayer_time} (через {min_time_diff:.1f} мин)")
    else:
        logger.info("⏳ Намазов на сегодня не осталось")
    
    return notification_sent, sent_notifications

def main():
    logger.info("🕌 Бот для намазов запущен!")
    
    # Отправляем тестовое сообщение при запуске
    send_telegram_message("🕌 Бот для намазов запущен! Буду уведомлять за 5 минут до намаза.")
    
    # Восстанавливаем отправленные уведомления из файла
    sent_notifications = load_sent_notifications()
    
    # Очищаем старые уведомления при запуске
    sent_notifications = cleanup_old_notifications(sent_notifications)
    save_sent_notifications(sent_notifications)
    
    # Счетчик для периодической очистка
    cleanup_counter = 0
    
    while True:
        try:
            # Получаем расписание
            timings = get_prayer_times()
            if timings:
                logger.info("📅 Расписание получено, проверяем время...")
                notification_sent, sent_notifications = check_prayer_time(timings, sent_notifications)
                
                # Сохраняем состояние после каждой проверки, если было отправлено уведомление
                if notification_sent:
                    save_sent_notifications(sent_notifications)
                
                # Очищаем старые уведомления каждые 12 часов (720 проверок)
                cleanup_counter += 1
                if cleanup_counter >= 720:
                    sent_notifications = cleanup_old_notifications(sent_notifications)
                    save_sent_notifications(sent_notifications)
                    cleanup_counter = 0
                    logger.info("🔄 Выполнена периодическая очистка устаревших уведомлений")
            else:
                logger.error("❌ Не удалось получить расписание")
            
            # Ждем 1 минуту перед следующей проверкой
            logger.info("⏳ Ждем 1 минуту...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка в основном цикле: {e}")
            logger.info("⏳ Ждем 1 минуту перед повторной попыткой...")
            time.sleep(60)

if __name__ == "__main__":
    main()
EOF