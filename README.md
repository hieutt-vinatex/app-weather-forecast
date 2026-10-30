# Dashboard thống kê XSMB

Ứng dụng thu thập kết quả ĐB, G1–G7, dựng thống kê hai số cuối cho 30/60/90 ngày
và gửi báo cáo số chưa xuất hiện qua Telegram.

> Dữ liệu chỉ phục vụ thống kê và tham khảo, không phải dự đoán kết quả và không
> khuyến khích đặt cược.

## Production được chọn: static-first cloud

Hệ thống production không cần máy cá nhân hoặc server FastAPI chạy liên tục:

```text
GitHub Actions ──crawl/tính toán──> Cloudflare Workers KV
       │                                  │
       └──Telegram buổi sáng              └──Cloudflare Worker API
                                                    │
                                             Vercel React SPA
```

- GitHub Actions chạy full sync hằng ngày và incremental sync khoảng 5 phút trong
  giờ quay.
- Cloudflare Worker phục vụ snapshot versioned 30/60/90 ngày, ETag/304, freshness
  và chuyển thao tác quản trị sang job hữu hạn.
- Vercel phục vụ frontend tĩnh; trình duyệt polling thích ứng, dừng khi tab ẩn hoặc
  offline.
- Telegram thử lại trong buổi sáng; state trong KV ngăn lịch tự động gửi lặp sau
  khi đã thành công.

Hướng dẫn đầy đủ, theo dashboard và ưu tiên chi phí 0:
[docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md).

## Hành vi dữ liệu

- Lịch sử đã xuất bản của hôm qua và các ngày trước hiển thị ngay, không phải chờ
  job của ngày đang quay.
- Kết quả ngày đang quay thường có độ trễ khoảng 5–10 phút trong kiến trúc miễn phí.
- Badge hiển thị rõ `Dữ liệu hiện tại`, `Đang cập nhật`, `Chậm cập nhật`,
  `Dữ liệu đã cũ` hoặc `Ngoại tuyến`.
- Khi sync lỗi, snapshot hợp lệ gần nhất và bảng lịch sử vẫn được giữ nguyên.
- Khóa quản trị chỉ nằm trong bộ nhớ tab, không ghi vào browser storage hoặc URL.

## Thành phần chính

```text
.github/workflows/        CI, data sync, Telegram, Worker deployment
app/cloud/                domain jobs hữu hạn, KV publication, notification state
cloudflare/worker/        public/admin API trên Workers KV
frontend/                 React + TypeScript + Vite dashboard
scripts/cloud_job.py      entrypoint cho GitHub Actions
tests/                    Python tests
docs/                     cloud setup và đường local legacy
```

## Kiểm tra trước khi phát hành

```bash
python -m pytest -q

cd frontend
npm test
npm run lint
npm run build

cd ../cloudflare/worker
npm test
npm run typecheck
```

CI chạy các cổng trên và kiểm tra syntax của toàn bộ workflow. Snapshot cloud có
thêm contract verifier ở `scripts/verify_cloud_contract.py`.

## Telegram

Thiết lập BotFather, group chat ID, dry-run và lịch gửi được mô tả tại
[docs/TELEGRAM_GROUP.md](docs/TELEGRAM_GROUP.md). Token chỉ được lưu trong GitHub
Actions secrets; frontend không nhận hoặc đọc bot token.

## FastAPI/Docker local legacy

`app/main.py`, Docker Compose, scheduler in-memory và các route SSE cũ được giữ
tạm thời để phát triển local/đối chiếu parity. Đây không phải kiến trúc production
được chọn và không nên dùng cho deploy miễn phí. Xem
[docs/INSTALLATION.md](docs/INSTALLATION.md) nếu cần chạy đường legacy này.

## Tài liệu

- [Triển khai cloud chi phí 0](docs/CLOUD_DEPLOYMENT.md)
- [Cài đặt local legacy và chạy test](docs/INSTALLATION.md)
- [Telegram Group](docs/TELEGRAM_GROUP.md)
- [Thiết kế static-first](docs/superpowers/specs/2026-10-29-static-first-cloud-deployment-design.md)
