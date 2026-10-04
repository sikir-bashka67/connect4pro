# Connect4Pro

Backend API проекта Connect4Pro на Django REST Framework.

## Установка

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

API: `http://127.0.0.1:8000/api/`

## Важные endpoints

- `POST /api/register/` — регистрация клиента (роль и Premium назначаются не через открытую регистрацию)
- `/api/ads/` — объявления клиентов
- `/api/provider-services/` — услуги провайдеров
- `/api/financing/` — гранты и инвестиции
- `/api/events/` — мероприятия
- `/api/database-resources/` — Premium-базы
- `/api/applications/` — заявки клиентов
- `POST /api/calculator/` — калькулятор вероятности
- `GET /api/analytics/` — аналитика администратора
