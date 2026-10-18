<!-- run backend -->

./venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload


<!-- run frontend -->

cd /mnt/c/Users/Admin/Desktop/app-weather-forecast/frontend
npm run dev


# Thống kê GĐB XSMB — Realtime Dashboard

Tài liệu nhanh: [Cài đặt và vận hành](docs/INSTALLATION.md) ·
[Telegram Group](docs/TELEGRAM_GROUP.md)

Ứng dụng full‑stack thu thập, **truyền theo thời gian thực (SSE)**, thống kê và trực quan hóa **2 số cuối giải đặc biệt xổ số miền Bắc (XSMB)**.

> ⚠️ **Miễn trừ:** Dữ liệu chỉ dùng cho mục đích **thống kê và tham khảo**, **không phải dự đoán kết quả**, không đảm bảo trúng thưởng và không khuyến khích đặt cược.

- **Backend:** FastAPI + aiohttp + BeautifulSoup4 + Pydantic v2 (package `app/`).
- **Frontend:** React + TypeScript (strict) + Vite + Tailwind + TanStack Query + Apache ECharts (`frontend/`).
- **Realtime:** một background poller trung tâm → Event Broker → **Server‑Sent Events** → TanStack Query cache.

---

## 1. Kiến trúc tổng thể

Một **poller upstream duy nhất** theo dõi trang kết quả của **ngày hiện tại**. Khi (và chỉ khi) 2 số cuối GĐB thay đổi, nó tăng `snapshotVersion`, dựng lại snapshot 30/60/90 ngày và **broadcast** tới mọi client SSE. Không bao giờ có một crawler riêng cho mỗi trình duyệt / mỗi kết nối.

```mermaid
flowchart LR
    subgraph Upstream
      X[xsmn.mobi<br/>xsmb-D-M-Y.html]
    end
    subgraph Backend[FastAPI · 1 worker · in-memory]
      P[Realtime Poller<br/>1s active / 30s idle<br/>backoff+jitter]
      F[Fetcher<br/>aiohttp session<br/>retry · ETag/304]
      C[(History TTL cache<br/>single-flight · 90d)]
      S[Statistics service]
      B{{Event Broker<br/>bounded queue/subscriber<br/>latest-wins}}
      N[Notification Scheduler<br/>09:00 · idempotency · retry]
      R[REST /api/gdb]
      SSE[SSE /api/gdb/stream]
    end
    subgraph Frontend[React + TanStack Query]
      Q[(Query cache)]
      UI[Dashboard · charts · KPI · table]
    end

    X <-->|conditional GET| F
    P --> F
    P -->|only on change| C
    P -->|only on change| B
    F --> C
    C --> S
    R --> Q
    B -->|snapshot/update/heartbeat| SSE --> Q --> UI
    UI -->|POST /api/gdb/refresh| P
    C --> N --> T[Telegram · Zalo OA · Facebook]
```

**Luồng:**
1. Khởi động → tạo một `aiohttp.ClientSession` chung (lifespan), khởi động **1** poller, warm cache 90 ngày ở background (không chặn startup).
2. Frontend tải trang → gọi REST `GET /api/gdb` lấy snapshot khởi tạo → mở SSE `GET /api/gdb/stream?days=…`.
3. Poller parse `.v-gdb`, chuẩn hóa 2 ký tự cuối, so sánh version; chỉ khi đổi mới cập nhật cache + tính lại thống kê + broadcast.
4. Frontend nhận `snapshot`/`update` → `queryClient.setQueryData()` → KPI/chart/table cập nhật ngay, không tải lại trang.
5. Mất SSE → giữ dữ liệu cuối, hiển thị trạng thái reconnect (backoff+jitter) và bật **fallback polling** REST; phục hồi thì tắt fallback.
6. Scheduler backend kiểm tra lúc 09:00 sáng hôm sau; chỉ khi đủ dữ liệu 25 ngày mới gửi cảnh báo, đồng thời lưu trạng thái từng đích để retry không trùng.

---

## 2. Cấu trúc thư mục

```
app/
  main.py                 # FastAPI app + lifespan (session, poller, broker)
  config.py               # Pydantic-settings, validate khi startup
  api/
    deps.py               # validate days (30/60/90), DI
    gdb_router.py         # GET /api/gdb, POST /api/gdb/refresh
    realtime_router.py    # GET /api/gdb/stream (SSE), /api/health, /api/realtime/status
  schemas/gdb.py          # Response models (camelCase, dùng chung REST + SSE)
  services/
    gdb_service.py        # fetch+parse+cache+assemble snapshot
    statistics_service.py # thống kê mô tả (thuần, deterministic)
    realtime_service.py   # poller trung tâm + backoff + manual refresh
  notifications/          # scheduler, Telegram/Zalo/Facebook adapters, state store
  realtime/
    broker.py             # pub/sub in-memory, queue giới hạn, latest-wins
    state.py              # trạng thái realtime dùng chung
  cache/simple_cache.py   # TTLCache + SingleFlight (chống stampede)
  utils/
    fetcher.py            # aiohttp, retry/backoff/jitter, conditional GET, 304
    parser.py             # parse .v-gdb → 2 ký tự cuối (không bịa dữ liệu)
    date_helper.py        # range 30/60/90, weekday VN, tz, build URL
tests/                    # pytest (50 test, không chạm mạng thật)
scripts/
  smoke_realtime.py       # chứng minh 6 tính chất realtime (offline)
  smoke_multiclient.py    # nhiều SSE client với 1 poller (server đang chạy)
frontend/
  src/
    api/{client,sse}.ts   # REST client + SSE wrapper typed (reconnect)
    hooks/                # useGdbSnapshot, useGdbRealtime, useManualRefresh, useDaysParam
    components/           # StatusBadge, KpiCards, charts/*, HistoryTable, ...
    features/dashboard/   # Dashboard + DashboardHeader
    types/gdb.ts          # types mirror backend
    utils/                # format, theme (light/dark), chartTheme
```

---

## 3. Cài đặt & chạy

### Yêu cầu
- Python **3.11+** (đã test trên 3.13)
- Node **18+** (đã test trên Node 24)

### Backend

```bash
# tại thư mục gốc
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash
# hoặc: source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp .env.example .env                 # tùy chỉnh nếu cần

# chạy dev (auto-reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# chạy "production" in-memory — BẮT BUỘC 1 worker
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> Trên Windows, IANA timezone cần gói `tzdata` (đã có trong `requirements.txt`).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env                 # trỏ VITE_API_BASE_URL tới backend
npm run dev                          # http://localhost:5173
```

### Test / Lint / Build

```bash
# Backend
source venv/Scripts/activate
python -m pytest -q                  # 61 test
python scripts/smoke_realtime.py     # 6 tính chất realtime (offline)

# Frontend
cd frontend
npm run lint                         # eslint, 0 warning
npm test                             # vitest, 30 test
npm run build                        # tsc + vite build
```

---

## 4. API REST

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/gdb?days=30\|60\|90` | Snapshot: `data` + `statistics` + `meta`. `days` mặc định 30; giá trị khác → `422`. |
| GET | `/api/gdb/stream?days=30\|60\|90` | **SSE** stream realtime. |
| POST | `/api/gdb/refresh` | Ép kiểm tra upstream (dùng chung lock với poller). Có cooldown → `429` + `Retry-After`. |
| GET | `/api/health` | Health + observability (không crawl upstream). |
| GET | `/api/realtime/status` | Alias quan sát worker realtime. |
| GET | `/api/notifications/status` | Trạng thái scheduler/kênh đã cấu hình; không trả token hoặc ID đầy đủ. |
| POST | `/api/notifications/test` | Gửi tin kiểm tra; bắt buộc header `X-Notification-Token`. |
| POST | `/api/notifications/send-now` | Làm mới dữ liệu, tính 19–25 ngày và gửi báo cáo ngay; bắt buộc header quản trị. |

**Quy tắc `days`:** chỉ `30/60/90`; phạm vi N ngày gồm **hôm nay và N‑1 ngày trước** theo `Asia/Ho_Chi_Minh`; nếu hôm nay chưa có kết quả thì `meta.partial=true` và liệt kê `missingDates`. Dữ liệu `data` sắp xếp **tăng dần theo ngày**.

**Mã trạng thái:** partial nhưng có ≥1 bản ghi → `200` (kèm `meta.partial`). Upstream chết hoàn toàn & chưa từng có state → `503`. Không dùng `404` để đại diện lỗi upstream.

Response model (tóm tắt): xem `app/schemas/gdb.py`. `snapshot` và `update` của SSE **dùng chung** type với REST.

## 5. SSE events

`Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.

| Event | Khi nào | `data` |
|---|---|---|
| `snapshot` | Ngay khi client kết nối/kết nối lại | `SnapshotResponse` đầy đủ |
| `update` | Khi dữ liệu nguồn thay đổi | `SnapshotResponse` đầy đủ (version mới) |
| `heartbeat` | Mặc định mỗi 15s | `{ sentAt, snapshotVersion }` |
| `warning` | Cảnh báo (partial…) khi phù hợp | payload cảnh báo |

Mỗi event có `id:` = `snapshotVersion` và kết thúc bằng hai dòng trống. Frontend bỏ qua payload sai định dạng hoặc version cũ.

---

## 6. Biến môi trường

### Backend (`.env`)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `APP_ENV` / `APP_HOST` / `APP_PORT` | development / 0.0.0.0 / 8000 | Runtime |
| `LOG_LEVEL` | INFO | Log level |
| `CORS_ORIGINS` | http://localhost:5173 | Danh sách origin (phẩy). Không dùng wildcard + credentials |
| `SOURCE_BASE_URL` | https://xsmn.mobi | Nguồn |
| `SOURCE_TIMEOUT_SECONDS` / `SOURCE_CONNECT_TIMEOUT_SECONDS` | 8 / 3 | Timeout tổng / kết nối |
| `SOURCE_MAX_RETRIES` | 3 | Số lần retry |
| `SOURCE_MAX_CONCURRENCY` | 10 | Giới hạn concurrency crawl lịch sử |
| `HISTORY_CACHE_TTL_SECONDS` | 300 | TTL cache lịch sử |
| `REALTIME_ENABLED` | true | Bật/tắt poller |
| `REALTIME_TIMEZONE` | Asia/Ho_Chi_Minh | Timezone nghiệp vụ |
| `REALTIME_ACTIVE_START` / `REALTIME_ACTIVE_END` | 17:45 / 19:00 | Khung giờ poll nhanh |
| `REALTIME_ACTIVE_POLL_SECONDS` | 1.0 | Chu kỳ trong khung active (≥ MIN) |
| `REALTIME_IDLE_POLL_SECONDS` | 30.0 | Chu kỳ ngoài khung active |
| `REALTIME_HEARTBEAT_SECONDS` | 15 | Nhịp heartbeat |
| `REALTIME_MIN_POLL_SECONDS` | 1.0 | Chặn dưới chu kỳ (không cho < 1s) |
| `MANUAL_REFRESH_COOLDOWN_SECONDS` | 5 | Cooldown nút làm mới |
| `NOTIFICATIONS_ENABLED` / `NOTIFICATION_DRY_RUN` | false / true | Bật scheduler / chỉ ghi log, chưa gửi thật |
| `NOTIFICATION_MIN_DAYS` / `NOTIFICATION_MAX_DAYS` | 19 / 25 | Khoảng ngày chưa xuất hiện cần cảnh báo |
| `NOTIFICATION_SEND_TIME` | 09:00 | Giờ gửi vào sáng hôm sau, theo `REALTIME_TIMEZONE` |
| `NOTIFICATION_STATE_PATH` | .data/notification-state.json | Lưu chống gửi trùng và token Zalo đã refresh |
| `NOTIFICATION_ADMIN_TOKEN` | rỗng | Bảo vệ API gửi thử/gửi ngay; rỗng thì endpoint trả `404` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_IDS` | rỗng | Bot token và danh sách chat ID, cách nhau bằng dấu phẩy |
| `ZALO_*` | rỗng | Access/refresh token, App ID/secret và OA user ID |
| `FACEBOOK_*` | rỗng | Page access token, Messenger PSID và tùy chọn đăng lên Page feed |

Cấu hình được **validate khi startup** (timezone hợp lệ, `ACTIVE_START < ACTIVE_END`, poll ≥ MIN…) — sai là fail‑fast.

### Frontend (`frontend/.env`)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_BASE_URL` | http://localhost:8000 | Base URL backend (không hardcode ở nơi khác) |
| `VITE_SSE_RECONNECT_BASE_MS` | 1000 | Backoff cơ sở khi reconnect SSE |
| `VITE_SSE_RECONNECT_MAX_MS` | 30000 | Trần backoff |
| `VITE_FALLBACK_POLL_MS` | 15000 | Chu kỳ fallback polling khi mất SSE |

---

## 7. Thông báo Telegram, Zalo và Facebook

Scheduler chạy ở backend nên không cần mở trình duyệt. Sau mỗi kỳ quay hoàn tất, hệ thống chờ đến `NOTIFICATION_SEND_TIME` của sáng hôm sau, kiểm tra các số có lần xuất hiện gần nhất cách kỳ dữ liệu từ 19 đến 25 ngày, rồi gửi một lần cho từng đích nhận.

Để tránh cảnh báo sai, hệ thống chỉ gửi khi tất cả kỳ trong cửa sổ 25 ngày đều có đủ ĐB + G1–G7. Kết quả gửi được lưu riêng theo kỳ/rule/đích nhận; nếu Telegram thành công nhưng Zalo lỗi, lần retry chỉ gửi lại Zalo. File state được ghi atomic và Docker Compose mount ra `./data`, nên restart không gửi trùng.

### Cấu hình chung

Thêm vào `.env`:

```dotenv
NOTIFICATIONS_ENABLED=true
NOTIFICATION_DRY_RUN=true
NOTIFICATION_MIN_DAYS=19
NOTIFICATION_MAX_DAYS=25
NOTIFICATION_SEND_TIME=09:00
NOTIFICATION_ADMIN_TOKEN=thay-bang-mot-chuoi-dai-ngau-nhien
```

Giữ `NOTIFICATION_DRY_RUN=true` cho lần chạy đầu. Khi `/api/notifications/status` hiển thị đúng kênh và số đích nhận, đổi thành `false` rồi restart backend.

### Telegram

1. Tạo bot bằng `@BotFather`, lấy bot token.
2. Người nhận nhắn `/start` cho bot; dùng `getUpdates` của Bot API để lấy `chat.id`. Với group/channel, thêm bot và cấp quyền gửi tin.
3. Cấu hình:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace_me
TELEGRAM_CHAT_IDS=123456789,-1001234567890
```

### Zalo Official Account

Ứng dụng Zalo phải liên kết với OA, được cấp quyền nhắn tin và người nhận phải có quan hệ tương tác phù hợp với chính sách OA. Có thể cung cấp access token trực tiếp; để production tự gia hạn token, cấu hình thêm refresh token, App ID và App secret:

```dotenv
ZALO_ACCESS_TOKEN=replace_me
ZALO_REFRESH_TOKEN=replace_me
ZALO_APP_ID=replace_me
ZALO_APP_SECRET=replace_me
ZALO_RECIPIENT_IDS=oa_user_id_1,oa_user_id_2
```

Token mới do Zalo trả về được lưu trong `NOTIFICATION_STATE_PATH`. File này chứa bí mật và không được commit; ứng dụng đặt quyền `0600` khi hệ điều hành hỗ trợ.

### Facebook

Messenger dùng Page ID, Page access token và Page-scoped user ID (PSID). Tin chủ động vẫn chịu cửa sổ nhắn tin/quyền và chính sách của Meta; nếu cần một đầu ra Facebook ổn định ngoài cửa sổ Messenger, có thể bật đăng cùng nội dung lên Page feed (và cấp quyền quản lý bài viết cho app).

```dotenv
FACEBOOK_GRAPH_API_VERSION=v26.0
FACEBOOK_PAGE_ACCESS_TOKEN=replace_me
FACEBOOK_PAGE_ID=replace_me
FACEBOOK_MESSENGER_RECIPIENT_IDS=psid_1,psid_2

# Tùy chọn đăng lên Page feed
FACEBOOK_PUBLISH_TO_PAGE=true
```

### Kiểm tra cấu hình

```bash
curl http://localhost:8000/api/notifications/status

curl -X POST http://localhost:8000/api/notifications/test \
  -H "X-Notification-Token: thay-bang-mot-chuoi-dai-ngau-nhien"
```

Lệnh test tôn trọng `NOTIFICATION_DRY_RUN`. API không bao giờ trả token và chỉ hiển thị bốn ký tự cuối của ID đích nhận.

### Nút gửi báo cáo ngay

Trong thẻ **Theo dõi số chưa xuất hiện**, nhập giá trị `NOTIFICATION_ADMIN_TOKEN`
vào ô khóa quản trị và bấm **Gửi thông báo 19–25 ngày ngay**. Backend sẽ kiểm tra
nguồn tại thời điểm bấm, chọn kỳ quay hoàn tất mới nhất, tính lại toàn bộ ĐB + G1–G7
và gửi tới tất cả kênh đã cấu hình. Khóa chỉ nằm trong bộ nhớ trang và mất khi tải lại.

Có thể gọi trực tiếp cùng chức năng:

```bash
curl -X POST http://localhost:8000/api/notifications/send-now \
  -H "X-Notification-Token: thay-bang-mot-chuoi-dai-ngau-nhien"
```

Mỗi lần bấm là một yêu cầu gửi mới, không bị chống trùng của lịch 09:00 bỏ qua. Nếu
không có số phù hợp, kênh nhận vẫn nhận một báo cáo xác nhận không có kết quả.

---

## 8. Cache, partial & stale

- **History cache:** tối đa 90 ngày, TTL 300s; chỉ cache ngày **thành công**; **single‑flight** để nhiều cache‑miss đồng thời chỉ crawl một lần (chống stampede). Concurrency giới hạn bằng semaphore.
- **Realtime state:** tách khỏi TTL lịch sử; poller cập nhật state ngày hiện tại, chỉ tăng `snapshotVersion` khi dữ liệu nghiệp vụ đổi.
- **Conditional request:** dùng `If-None-Match`/`If-Modified-Since`; `304 Not Modified` → không parse lại.
- **Partial:** thiếu ngày → `meta.partial=true`, kèm `availableRecords`, `failedCount`, `missingDates`, `errors`. Vẫn `200` nếu có ≥1 bản ghi.
- **Stale‑while‑serve:** khi upstream lỗi, poller **giữ giá trị hôm nay gần nhất** và ghi `lastError` thay vì làm trắng dashboard.

## 9. Giới hạn

- **Phụ thuộc HTML nguồn:** parser bám selector `.v-gdb`. Nếu website đổi cấu trúc, ngày đó bị đánh dấu `no_result`/`parse_failure` (không bịa dữ liệu) — cần cập nhật `app/utils/parser.py`.
- **In‑memory:** cache + broker + subscriber nằm trong RAM. **Restart là mất** (chấp nhận được); trạng thái chống gửi trùng của notification được lưu ra file. Vì vậy **chạy 1 Uvicorn worker** — nhiều worker sẽ có nhiều poller/cache/scheduler rời rạc.
- **Scale ngang:** để chạy nhiều worker/instance cần chuyển **cache, lock và pub/sub sang Redis** (Redis TTL cache, Redis lock cho single‑flight, Redis Pub/Sub cho broadcast). Route SSE giữ nguyên, chỉ đổi nguồn sự kiện.

---

## 10. Reverse proxy (Nginx) cho SSE

SSE cần **tắt buffering** để đẩy sự kiện tức thời:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}
```

Backend cũng gửi `X-Accel-Buffering: no` để chắc chắn Nginx không buffer stream.

---

## 11. Kết quả kiểm thử (thực đo)

- **Backend:** `pytest` → **61 passed** (date range/timezone, parser ĐB + G1–G7, timeout/retry/cache, REST/SSE, realtime và notification evaluation/idempotency/API protection/token refresh).
- **`scripts/smoke_realtime.py`** → **PASS** cả 6 tính chất (1 poller cho nhiều client; đổi giá trị ⇒ cùng version mới; không đổi ⇒ không broadcast lặp; client chậm không chặn; backoff tăng khi lỗi; phục hồi về cadence).
- **`scripts/smoke_multiclient.py`** (server thật) → **PASS**: 5 SSE client đều nhận snapshot ban đầu từ **một** poller (`currentGdb` lấy thật từ xsmn.mobi, 90 ngày cache).
- **Frontend:** `tsc` OK · `eslint` 0 warning · `vitest` → **30 passed** · `vite build` OK (echarts tách chunk riêng).

---

## 12. Ghi chú triển khai (`docker-compose`)

Xem `docker-compose.yml` (tùy chọn) — backend 1 worker + frontend build tĩnh sau Nginx đã tắt buffering cho `/api/`. Compose đọc bí mật từ `.env` và mount `./data:/app/data` để giữ trạng thái notification qua restart/redeploy.
