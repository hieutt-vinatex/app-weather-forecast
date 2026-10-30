# Cài đặt, kiểm thử và đường local legacy

Production được chọn là Vercel + Cloudflare Worker/KV + GitHub Actions. Làm theo
[CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md) để deploy mà không cần chạy ứng dụng
trên máy cá nhân.

Tài liệu này chỉ dành cho phát triển, test và đối chiếu backend FastAPI/Docker cũ.

## 1. Yêu cầu phát triển

- Python 3.11+
- Node.js 20
- Git
- Docker + Docker Compose chỉ khi cần kiểm tra đường container legacy

## 2. Cài dependency

Tại thư mục repository:

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env

cd frontend
npm install --no-package-lock
cp .env.example .env

cd ../cloudflare/worker
npm ci
```

Trên macOS/Linux, thay `./venv/Scripts/python.exe` bằng `./venv/bin/python`.
Không điền secret production vào file local hoặc commit `.env`.

## 3. Chạy toàn bộ kiểm tra

```bash
./venv/Scripts/python.exe -m pytest -q

cd frontend
npm test
npm run lint
npm run build

cd ../cloudflare/worker
npm test
npm run typecheck
```

Workflow CI dùng Python 3.12 và Node 20, nên kết quả local cần khớp hai phiên bản
này trước khi merge.

## 4. Chạy FastAPI local legacy

Phần này không dùng cho production cloud. Các URL loopback bên dưới chỉ là ví dụ
local an toàn.

Trong `.env`, giữ cấu hình development, bật notification dry-run và tự tạo
`NOTIFICATION_ADMIN_TOKEN` riêng cho local. Sau đó chạy:

```bash
./venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

Ở terminal khác:

```bash
cd frontend
npm run dev
```

Frontend local mặc định truy cập `http://localhost:5173`; backend legacy dùng
`http://localhost:8000`. Scheduler/cache của đường này nằm trong bộ nhớ và chỉ
hỗ trợ một Uvicorn worker.

## 5. Docker Compose local legacy

Docker Compose được giữ để kiểm tra parity, không phải đường deploy đã chọn:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

Không public container legacy trực tiếp ra Internet. Nếu buộc phải dùng ngoài
local, phải bổ sung HTTPS, secret store, backup state và vận hành server liên tục;
những yêu cầu đó trái với mục tiêu chi phí 0 của kiến trúc đã duyệt.

## 6. Cấu hình Telegram

- Production cloud: xem [TELEGRAM_GROUP.md](./TELEGRAM_GROUP.md).
- Local legacy: `.env.example` vẫn liệt kê biến tương thích; luôn giữ
  `NOTIFICATION_DRY_RUN=true` cho đến khi kiểm tra đúng group.

Không commit `.env`, bot token, chat ID riêng tư, Cloudflare token hoặc khóa quản
trị. Nếu một secret từng xuất hiện trong commit/log, phải thu hồi và tạo lại thay
vì chỉ xóa dòng đó.
