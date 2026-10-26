# Фронтенд классификатора по ПП № 1875

React 18 + Vite + TypeScript, компоненты — [Mantine 7](https://mantine.dev). Внешний вид — по мотивам zakupki.gov.ru (ЕИС), где тендерные специалисты работают каждый день: синий `#0065dd`, текст `#334059`, серый фон `#eff0f2`, шрифт Roboto, плоские белые карточки (палитра — `src/theme.ts`, каркас страницы — `src/app.css`). Логотип и название ЕИС не используем — только стиль. Одна страница с двумя вкладками:
- **Проверка** — ввод товаров (строка = товар, до 100) или загрузка Excel/CSV → таблица: код ОКПД2, режим цветом и текстом, пункт ПП (клик — текст пункта), уверенность, «⚠ Проверьте вручную», раскрытие строки с объяснением, всеми пунктами и альтернативами, выгрузка. На телефоне (уже 48em) вместо таблицы — карточки с цветной полосой режима (`ResultCards.tsx`).
  Над результатами — сводка по режимам, она же фильтр (`ResultsSummary.tsx`); файл можно перетащить на форму, «Скачать шаблон» даёт пример CSV; до первой проверки — блок «Как это работает»; последние 10 проверок хранятся в браузере (`history.ts`, localStorage).
- **База НПА** — действующая редакция, загрузка новой (с паролем администратора), история редакций со статусами.

## Запуск

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, работает на заглушках (бейдж «демо»)
npm run dev:api    # то же, но с реальным backend: /api → http://localhost:8000
npm test           # vitest
npm run build      # проверка типов + сборка в dist/
```

### В Docker (вместе с backend)

Из корня репозитория: `docker compose up --build` → сайт на **http://localhost:8080** (сервис `web`: сборка → nginx).
- nginx раздаёт SPA и проксирует `/api/` в `api:8000`; порт API наружу закрыт (`127.0.0.1:8000` — только Swagger на этом компьютере).
- Сайт без backend (на заглушках, например для показа вёрстки): `VITE_USE_MOCKS=true docker compose up --build web`.
- В рабочей сборке заглушки вырезаются целиком (проверено: в бандле нет `mocks.ts`).
- Лимиты в `nginx.conf`: 10 запросов/с на API с одного адреса, пакет и загрузка НПА — 6 в минуту; файлы до 20 МБ; ответ API ждём до 300 с.
- Если сайт откроют через туннель (Cloudflare и т.п.), nginx видит адрес туннеля, а не пользователя — лимиты станут общими; настроить `real_ip` под туннель.

## Заглушки и контракт с backend

В `npm run dev` все вызовы идут в `src/mocks.ts` (`VITE_USE_MOCKS=true` в `.env.development`; в тестах — через `vite.config.ts`).
Заглушки отвечают по ключевым словам (ноутбук, бумага, щебень, халат, тумба, катетер, программа, лифт, хлеб) реальными позициями ПП из `data/npa/pp1875.json` в том же формате, что backend; незнакомый товар даёт низкую уверенность.

Типы в `src/types.ts` повторяют `backend/app/schemas.py` и модели ответов в `backend/app/api/*.py`:

| Вызов | Эндпоинт |
|---|---|
| `getHealth` | `GET /api/health` |
| `classify` | `POST /api/classify {name}` → `ClassificationResult` (503, пока модели грузятся) |
| `classifyBatch` / `classifyFile` | `POST /api/classify/batch` (JSON `{names}` или multipart `file`: .xlsx/.csv/.txt) → 202 `{job_id}` |
| `getJob` | `GET /api/jobs/{id}` → `{job_id, status, total, done, error, results}` |
| `jobExportUrl` | `GET /api/jobs/{id}/export.xlsx` (только после `done`) |
| `getNpaVersions` | `GET /api/npa/versions` → с `source_url` и `warnings` |
| `uploadNpa` | `POST /api/npa/upload` (multipart `file` .json/.xlsx до 20 МБ, `title`, `source_url`) → 202 |
| `getNpaItem` | `GET /api/npa/items/{id}` → поля пункта; текст в окне собирается из них (готового `raw_text` нет) |

Ошибки: фронт показывает `detail` из ответа FastAPI.

**Пароль на загрузку НПА:** если на сервере задан `ADMIN_TOKEN`, `/api/health` отдаёт `npa_upload_protected: true` — страница «База НПА» показывает поле пароля и шлёт его в заголовке `X-Admin-Token`. В заглушках пароль — `1875`.

Выгрузка: у пакета — «Скачать Excel» с backend (`/api/jobs/{id}/export.xlsx`); одиночная проверка (`/api/classify`) задачу не создаёт, поэтому её выгрузка — CSV из браузера (`src/exportCsv.ts`, те же колонки, что в Excel backend).
