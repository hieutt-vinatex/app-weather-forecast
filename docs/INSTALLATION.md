# Cài đặt và vận hành hệ thống

Tài liệu nhanh cho developer. Phiên bản hiện tại sử dụng Telegram cho thông báo.

## 1. Yêu cầu

- Python 3.11+
- Node.js 18+
- Git
- Docker + Docker Compose nếu triển khai bằng container

## 2. Chạy local

Tại thư mục dự án:

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env

cd frontend
npm install
cp .env.example .env
cd ..
```

Các biến tối thiểu trong `.env`:

```dotenv
APP_ENV=development
CORS_ORIGINS=http://localhost:5173
REALTIME_ENABLED=true
REALTIME_TIMEZONE=Asia/Ho_Chi_Minh

NOTIFICATIONS_ENABLED=true
NOTIFICATION_DRY_RUN=true
NOTIFICATION_MIN_DAYS=19
NOTIFICATION_MAX_DAYS=25
NOTIFICATION_SEND_TIME=09:00
NOTIFICATION_ADMIN_TOKEN=mot-chuoi-ngau-nhien-dai
```

Tạo `NOTIFICATION_ADMIN_TOKEN`:

```bash
./venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Cấu hình Telegram theo [TELEGRAM_GROUP.md](./TELEGRAM_GROUP.md).

Chạy backend:

```bash
./venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 --reload
```

Chạy frontend ở terminal khác:

```bash
cd frontend
npm run dev
```

Truy cập `http://localhost:5173`.

## 3. Kiểm tra hệ thống

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/notifications/status
```

Kết quả notification đúng cần có:

```json
{
  "enabled": true,
  "running": true,
  "configuredChannels": ["telegram"],
  "configuredTargetCount": 1
}
```

Chạy test trước khi deploy:

```bash
./venv/Scripts/python.exe -m pytest -q

cd frontend
npm test
npm run lint
npm run build
```

## 4. Chạy production bằng Docker

1. Tạo `.env` từ `.env.example` và điền cấu hình thật.
2. Nếu dùng domain, sửa `CORS_ORIGINS` trong `docker-compose.yml` thành URL frontend.
3. Khởi động:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

Frontend: `http://localhost:8080`  
Backend: `http://localhost:8000`

Thư mục `./data` được mount vào container để giữ trạng thái chống gửi trùng qua
các lần restart.

## 5. Lưu ý production

- Backend phải chạy đúng **1 Uvicorn worker** vì scheduler/cache đang dùng bộ nhớ.
- Không commit `.env`, Bot Token hoặc `NOTIFICATION_ADMIN_TOKEN`.
- Đặt backend sau HTTPS/reverse proxy khi public Internet.
- Server cần được chạy liên tục và cho phép kết nối HTTPS ra Telegram.
- Sau khi sửa `.env`, luôn restart backend.

