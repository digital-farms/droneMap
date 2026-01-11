# 🛩️ Drone Monitor Map

Професійна інтерактивна карта для моніторингу повітряних загроз в реальному часі з AI-аналізом Telegram-каналів.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎯 Можливості

### Інтерактивна карта
- **Dark Mode** стилізація з кастомними тайлами
- **Векторні області України** (TopoJSON) з підсвічуванням тривог
- **5 типів загроз:** БПЛА, Крилаті ракети, Балістика, Гіперзвук, Ядерна зброя
- **Маркери з напрямком** руху та кількістю (групи)
- **Кластеризація** маркерів при великій кількості цілей
- **Лінії траєкторії** польоту

### AUTO Mode (AI-моніторинг)
- **Telegram-моніторинг** оперативних каналів в реальному часі
- **LLM-аналіз** повідомлень (Claude 3 Haiku через OpenRouter)
- **Автоматичне геокодування** міст та напрямків
- **Розрахунок траєкторій** origin → target з урахуванням heading
- **Синхронізація тривог** з офіційним API alerts.in.ua
- **WebSocket трансляція** для миттєвого оновлення клієнтів
- **Auto-TTL** — автовидалення застарілих загроз (30 хв)

### Адмін-панель
- Додавання загроз кліком на карті
- Групування загроз (x3, x5, тощо)
- Обертання напрямку (ПКМ по маркеру)
- Керування тривогами по областях
- Генерація скріншотів (Playwright)
- Відправка в Telegram-канал

### Viewer Mode (тільки перегляд)
- Read-only інтерфейс без контролів
- Мобільний UI з лічильником загроз
- Кастомні іконки для типів загроз
- WebSocket оновлення в реальному часі
- Індикатор статусу з'єднання

---

## 🏗️ Архітектура

```
droneMap/
├── main.py                 # FastAPI сервер + WebSocket
├── run.py                  # Точка входу (uvicorn)
├── script.js               # Frontend логіка + Leaflet
├── styles.css              # Dark theme стилі
├── index.html              # Головна сторінка
├── viewer.html             # Redirect на /?view=true
├── ukraine-regions.json    # TopoJSON областей
├── icons/                  # SVG іконки загроз
│   ├── drone.svg
│   ├── missile.svg
│   ├── ballistic.svg
│   └── nuclear.svg
├── auto_mode/              # AUTO режим модулі
│   ├── __init__.py
│   ├── config.py           # Конфігурація (env vars)
│   ├── auto_controller.py  # Головний контролер
│   ├── telegram_monitor.py # Моніторинг Telegram
│   ├── alert_monitor.py    # Моніторинг тривог
│   ├── llm_processor.py    # AI-аналіз повідомлень
│   ├── geocoder.py         # Геокодування міст
│   └── geocache.json       # Кеш геокодера
├── render.yaml             # Конфіг для Render.com
└── requirements.txt        # Python залежності
```

---

## ⚙️ Встановлення

### Вимоги
- Python 3.9+
- Chromium (для скріншотів)

### Локальне встановлення

```bash
# 1. Клонувати репозиторій
git clone <repo-url>
cd droneMap

# 2. Створити віртуальне оточення
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 3. Встановити залежності
pip install -r requirements.txt
playwright install chromium

# 4. Налаштувати змінні оточення
cp .env.example .env
# Відредагувати .env
```

### Змінні оточення (.env)

```env
# Telegram Bot (для відправки скріншотів)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Telegram API (для моніторингу каналів в AUTO режимі)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

# OpenRouter (LLM для аналізу повідомлень)
OPENROUTER_API_KEY=your_openrouter_key

# Auto-start AUTO режиму при запуску (для production)
AUTO_START=false
```

### Запуск

```bash
# Розробка (з hot reload)
python run.py

# Або напряму через uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

**URLs:**
- Адмін: http://localhost:8080
- Viewer: http://localhost:8080/?view=true

---

## 🌐 Деплой на Render.com

1. Підключити GitHub репозиторій
2. Встановити Environment Variables:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `TELEGRAM_BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `AUTO_START=true`
3. Deploy автоматично через `render.yaml`

---

## 📡 API Reference

### REST Endpoints

| Method | Endpoint | Опис |
|--------|----------|------|
| `GET` | `/api/state` | Отримати стан (загрози + тривоги) |
| `POST` | `/api/state` | Оновити загрози |
| `POST` | `/api/screenshot` | Згенерувати скріншот |
| `GET` | `/api/auto/status` | Статус AUTO режиму |
| `POST` | `/api/auto/start` | Запустити AUTO режим |
| `POST` | `/api/auto/stop` | Зупинити AUTO режим |

### WebSocket

**Endpoint:** `ws://host/ws`

**Повідомлення від сервера:**
```json
{"type": "threat_add", "data": {"id": 1, "type": "drone", "lat": 50.45, "lng": 30.52, "angle": 225}}
{"type": "threat_remove", "data": {"id": 1}}
{"type": "alert_update", "data": {"region": "Київська", "active": true}}
{"type": "auto_status", "data": {"running": true}}
```

---

## 🔧 Технічний стек

### Backend
- **FastAPI** — асинхронний веб-фреймворк
- **Uvicorn** — ASGI сервер
- **Telethon** — Telegram MTProto клієнт
- **Playwright** — генерація скріншотів
- **httpx/aiohttp** — HTTP клієнти
- **Pydantic** — валідація даних

### Frontend
- **Leaflet.js** — інтерактивні карти
- **Leaflet.markercluster** — кластеризація маркерів
- **Leaflet.rotatedMarker** — обертання іконок
- **TopoJSON** — векторні карти областей
- **WebSocket** — realtime оновлення
- **CSS3** — dark theme, анімації

### AI/LLM
- **OpenRouter API** — доступ до Claude 3 Haiku
- **Структурований промпт** — витяг типу, міста, напрямку
- **Локальний геокеш** — українські міста

---

## 📋 TODO

- [ ] Батчинг повідомлень (30 сек) + дедуплікація
- [ ] Продакшн Telegram-канали по регіонах
- [ ] Історія загроз з таймлайном
- [ ] Push-сповіщення в браузері

---

## 📄 Ліцензія

MIT License
