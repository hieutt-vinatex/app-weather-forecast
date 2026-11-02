# Cài đặt và kiểm thử local tùy chọn

Production chạy bằng GitHub Actions + GitHub Pages; local không bắt buộc cho production.
Tài liệu này chỉ dành cho phát triển, kiểm thử hoặc đối chiếu logic.

## Yêu cầu

- Python 3.12 khuyến nghị
- Node.js 20
- Git
- Docker chỉ cần khi chạy `actionlint` giống CI

## Cài dependency

Tại thư mục repository:

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

cd frontend
npm ci
```

Trên macOS/Linux, thay `./.venv/Scripts/python.exe` bằng `./.venv/bin/python`.
Không điền secret production vào `.env` hoặc commit file môi trường.

## Chạy kiểm thử

```bash
./.venv/Scripts/python.exe -m pytest -q

cd frontend
npm test
npm run lint
npm run build

cd ..
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest
```

CI dùng đúng Python 3.12 và Node 20.

## Xem site tĩnh local (tùy chọn)

Sau khi đã có một publication test trong `.local-publication/`:

```bash
cd frontend
npm run build
cd ..
python scripts/prepare_pages.py \
  --publication-root .local-publication \
  --dist-root frontend/dist
cp -a .local-publication/site/data frontend/dist/data
cd frontend
npm run preview -- --host 127.0.0.1 --port 4173
```

Mở `http://127.0.0.1:4173/app-weather-forecast/`. Không dùng secret production
để tạo fixture local.

## FastAPI local legacy (tùy chọn)

FastAPI local chỉ để test các service cũ và không bắt buộc cho production:

```bash
cp .env.example .env
./.venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

Chỉ bind loopback. Không public server local ra Internet và không giả định state
in-memory phù hợp cho nhiều worker.

## Telegram local

Ưu tiên kiểm tra Telegram bằng workflow dry-run. Nếu cần unit/integration test
local, giữ `NOTIFICATION_DRY_RUN=true` và dùng bot/group test. Không commit `.env`,
bot token, chat ID hoặc HMAC key.

Xem quy trình production tại [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md) và hướng
dẫn BotFather/group tại [TELEGRAM_GROUP.md](./TELEGRAM_GROUP.md).
