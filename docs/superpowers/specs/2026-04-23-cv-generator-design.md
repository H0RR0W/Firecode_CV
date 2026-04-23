# CV Generator — Design Spec
**Date:** 2026-04-23
**Project:** FIRECODE CV Generator
**Status:** Approved

---

## Context

FIRECODE нужен внутренний веб-инструмент для команды HR/рекрутеров (2–10 человек), который автоматизирует генерацию структурированных CV в фирменном формате FIRECODE (docx). Генерация происходит через DeepSeek API по свободному текстовому промпту. Все CV хранятся в общей базе и доступны всей команде. Администратор управляет пользователями и API-ключом.

---

## Tech Stack

| Слой | Технология |
|------|-----------|
| Backend | Python 3.11+ + FastAPI + Jinja2 |
| Auth | Сессии через `itsdangerous` (подписанные cookie), bcrypt (пароли) |
| База данных | SQLite (встроенный `sqlite3`) |
| DOCX | `python-docx` |
| AI | DeepSeek API (OpenAI-совместимый) через `httpx` |
| Frontend | Vanilla JS + CSS (без build step) |
| Запуск | `python main.py` — один процесс |

---

## Структура проекта

```
Int_for_CV/
├── main.py                  # FastAPI app, все роуты
├── database.py              # SQLite init + CRUD (users, cvs, settings)
├── auth.py                  # bcrypt, сессии, декораторы require_login / require_admin
├── cv_generator.py          # DeepSeek API вызов + python-docx генерация
├── config.py                # пути, константы
├── templates/
│   ├── base.html            # общий layout (шапка, вкладки, тема)
│   ├── login.html           # страница входа
│   ├── index.html           # главная (вкладки: Создать + Список)
│   ├── cv_detail.html       # страница /cv/{id}: форма + превью + перегенерация
│   └── admin/
│       ├── base.html        # admin layout (sidebar)
│       ├── stats.html       # статистика
│       ├── users.html       # управление пользователями
│       └── settings.html    # API ключ + модель
├── static/
│   ├── style.css            # дизайн-система Firecode (CSS-переменные, темы)
│   └── app.js               # переключение вкладок, inline regen, UI логика
├── storage/
│   ├── firecode_logo.png    # логотип для header docx (из шаблона Алексея К.)
│   └── cvs/                 # сгенерированные .docx файлы (cv_{id}.docx)
└── cv_data.db               # SQLite: users + cvs + settings + action_log
```

---

## База данных (SQLite)

### Таблица `users`
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
login TEXT UNIQUE NOT NULL
password_hash TEXT NOT NULL        -- bcrypt
role TEXT NOT NULL DEFAULT 'user'  -- 'admin' | 'user'
created_at TEXT NOT NULL
last_login TEXT
```

**Seed при первом запуске:** `admin / admin` с ролью `admin`.

### Таблица `cvs`
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
created_by INTEGER REFERENCES users(id)
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
prompt TEXT NOT NULL               -- исходный промпт генерации
name TEXT NOT NULL                 -- имя кандидата
specialization TEXT NOT NULL       -- специализация
experience TEXT                    -- "19 лет 11 месяцев"
languages TEXT                     -- "PHP, Python, JS"
frameworks TEXT
libraries TEXT
other_skills TEXT
projects TEXT NOT NULL             -- JSON array (см. ниже)
docx_path TEXT NOT NULL            -- storage/cvs/cv_{id}.docx
```

**projects JSON-элемент:**
```json
{
  "name": "Интернет-компания",
  "role": "CTO",
  "team": "200+ Backend, Frontend",
  "duration": "98 месяцев",
  "description": "...",
  "implementation": ["пункт 1", "пункт 2"],
  "tech_stack": "Python, PHP, Docker"
}
```

### Таблица `settings`
```sql
key TEXT PRIMARY KEY
value TEXT NOT NULL
updated_by INTEGER REFERENCES users(id)
updated_at TEXT
```
Ключи: `deepseek_api_key`, `deepseek_model` (default: `deepseek-chat`).

### Таблица `action_log`
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
user_id INTEGER REFERENCES users(id)
action TEXT NOT NULL   -- 'generate' | 'edit' | 'download' | 'delete' | 'regen_field'
cv_id INTEGER
detail TEXT
created_at TEXT NOT NULL
```

---

## API Endpoints

### Auth
| Method | Path | Описание |
|--------|------|----------|
| GET | `/login` | Страница входа |
| POST | `/login` | Аутентификация → cookie сессия |
| GET | `/logout` | Выход, удаление сессии |

### Основное приложение (require_login)
| Method | Path | Описание |
|--------|------|----------|
| GET | `/` | Главная (вкладки: Создать / Список) |
| POST | `/api/generate` | Генерация CV: промпт → DeepSeek → docx → сохранить |
| GET | `/api/cvs` | Список CV с фильтрами (name, spec, stack, date) |
| GET | `/cv/{id}` | Страница редактирования CV |
| PUT | `/api/cvs/{id}` | Сохранить изменения полей → перегенерировать docx |
| POST | `/api/cvs/{id}/regen-field` | Перегенерировать одно поле через DeepSeek |
| GET | `/api/cvs/{id}/download` | Скачать docx |
| DELETE | `/api/cvs/{id}` | Удалить CV (только admin) |

### Админ панель (require_admin)
| Method | Path | Описание |
|--------|------|----------|
| GET | `/admin` | → redirect `/admin/stats` |
| GET | `/admin/stats` | Статистика |
| GET | `/admin/users` | Список пользователей |
| POST | `/admin/users` | Создать пользователя |
| POST | `/admin/users/{id}/password` | Изменить пароль пользователя |
| DELETE | `/admin/users/{id}` | Удалить пользователя |
| GET | `/admin/settings` | API ключ + модель |
| POST | `/admin/settings` | Сохранить API ключ + модель |

---

## Генерация CV (cv_generator.py)

### Шаг 1 — DeepSeek API
Системный промпт инструктирует модель вернуть строго JSON следующей структуры:
```json
{
  "name": "Алексей К.",
  "specialization": "PHP Developer",
  "experience": "19 лет 11 месяцев",
  "languages": "PHP, Python, JavaScript",
  "frameworks": "Django, DRF, Node.js",
  "libraries": "MySQL, PostgreSQL, Redis",
  "other_skills": "Docker, Linux, Nginx",
  "projects": [...]
}
```

### Шаг 2 — DOCX генерация (python-docx)
Точно воспроизводит структуру шаблона из `Алексей К. - PHP.docx`:
- **Header**: изображение `firecode_logo.png` (1368701 × 190500 EMU)
- **Заголовок**: `{name} — {specialization}`, Arial Bold 13pt
- **Таблица навыков**: одна колонка, ширина 10256 DXA, серые границы `#BFBFBF`
  - Строки: Опыт, Языки, Фреймворки, Библиотеки, Также опыт
  - Заголовки строк: Arial Bold; значения: Nunito Regular
- **Раздел «Ключевые проекты»**: заголовок Arial Bold
- **На каждый проект**: отдельная таблица с 6 строками (Описание, Роль, Команда, Что реализовывал, Стек, Длительность)
  - «Что реализовывал»: каждый пункт с bullet `•`

### Перегенерация поля (`/api/cvs/{id}/regen-field`)
```json
// Request
{
  "field": "implementation",      // какое поле
  "project_index": 0,             // индекс проекта (если поле внутри проекта)
  "hint": "акцент на highload",   // необязательная подсказка
  "context": { ... }              // автоматически собранный контекст проекта
}
```
Модель получает контекст (название, роль, стек, описание проекта) и возвращает только значение поля.
После ответа значение **подставляется в поле формы в UI**, но **не сохраняется** ни в БД, ни в docx. Сохранение в БД + перегенерация docx происходят только при нажатии «Сохранить» (PUT `/api/cvs/{id}`).

---

## Аутентификация и сессии

- **Сессии**: подписанный cookie `session` через `itsdangerous.URLSafeTimedSerializer`
- **Пароли**: `bcrypt` (cost factor 12)
- **Время жизни сессии**: 8 часов (рабочий день)
- **Seed**: при `database.py` init проверяется наличие пользователя `admin`. Если нет — создаётся с паролем `admin` и ролью `admin`
- **require_login**: декоратор/dependency для всех защищённых роутов → redirect `/login`
- **require_admin**: дополнительная проверка роли → 403 если не admin
- Обычный пользователь **не может** удалять CV (кнопка скрыта, API возвращает 403)

---

## UI / Frontend

### Дизайн-система
Воспроизводит стиль сайта firecode.ru:
- **Шрифт**: Inter Variable (Google Fonts)
- **Цвета (тёмная тема)**: фон `#000` / `#0a0a0a`, граница `#1d1d1d`, акцент `#8300ea`
- **Цвета (светлая тема)**: фон `#f3f7ff` / `#fff`, граница `#e2e8f0`
- **Кнопки**: pill-shape `border-radius: 100px`; primary — градиент `#1d1d1d → #8300ea`
- **Карточки**: `border-radius: 15px`, hover `translateY(-2px)` + градиентная полоска сверху
- **Переключатель темы**: toggle в правом углу шапки, сохраняется в `localStorage`

### Ключевые UI-паттерны
- **Вкладки**: Создать CV / Список CV (без перезагрузки страницы)
- **Инлайн-перегенерация**: кнопка `⚡ AI` в label каждого поля → открывает панель с контекстом + подсказкой → shimmer-анимация загрузки → результат подставляется в поле
- **Аккордеон проектов**: каждый проект сворачивается/разворачивается; в развёрнутом виде — все поля с кнопками `⚡ AI`
- **Превью CV**: правая колонка на странице `/cv/{id}`, sticky, показывает структуру CV в реальном времени

---

## Фильтрация CV (GET /api/cvs)

Query params: `?name=&spec=&stack=&sort=desc`
- `name` — поиск по полю `name` (LIKE)
- `spec` — точное совпадение специализации
- `stack` — поиск по полям `languages + frameworks + libraries` (LIKE)
- `sort` — `desc` (новые первыми) / `asc`

---

## Безопасность

- Все пути (кроме `/login`) защищены аутентификацией
- API-ключ DeepSeek хранится в таблице `settings`, **не** в коде / env
- Пароли только bcrypt-хэши, никогда не возвращаются в ответах
- CSRF-защита через `itsdangerous` (токен в форме) для POST-запросов форм
- Удаление CV — только admin (и на уровне UI, и на уровне API)

---

## Верификация (как проверить что всё работает)

1. `pip install fastapi uvicorn jinja2 python-docx bcrypt itsdangerous httpx`
2. `python main.py` → открыть `http://localhost:8000`
3. Войти как `admin` / `admin` → попасть на главную
4. Создать тестовый CV через промпт → убедиться что docx создался в `storage/cvs/`
5. Открыть CV → нажать `⚡ AI` на любом поле → увидеть shimmer → результат в поле
6. Нажать «Сохранить» → скачать docx → открыть в Word
7. Перейти `/admin/users` → создать пользователя → войти под ним → убедиться что нет кнопки «Удалить»
8. Как admin удалить CV → убедиться что файл удалён из `storage/cvs/`
9. `/admin/settings` → сохранить API ключ → снова сгенерировать CV
