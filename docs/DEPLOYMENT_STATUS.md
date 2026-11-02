# Trạng thái triển khai GitHub-only

Cập nhật lần cuối: **2026-11-02** (`Asia/Ho_Chi_Minh`).

## Production hiện tại

- Dashboard: <https://hieutt-vinatex.github.io/app-weather-forecast/>
- Source branch/default branch: `develop`
- Commit ứng dụng đã xác minh tại cutover: `6d5b0623381d01903bb5147406502a12040d2e50`
- Nền tảng: GitHub Pages + GitHub Actions
- Telegram production: đã bật gửi thật; manual và scheduled đều đã được kiểm tra.

Không có token, Chat ID hoặc HMAC key nào được ghi trong tài liệu này.

## Dữ liệu đã xác minh

- Phiên bản publication đầu tiên: `20261102T140956823975Z`
- Phiên bản sau full sync kiểm tra rollback: `20261102T142829849363Z`
- `previousPublication` của phiên bản mới trỏ về đúng phiên bản đầu tiên.
- Manifest, status, history và snapshot 30/60/90 đều hợp lệ trên production.
- Snapshot chứa đúng 30/60/90 bản ghi; ngày mới nhất là `2026-11-02`.
- Dashboard và các tài nguyên dưới base path `/app-weather-forecast/` trả HTTP 200.

## Workflow đã xác minh

- [CI trên commit production](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41411321006): thành công.
- [Bootstrap GitHub Pages](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41411402672): thành công sau khi chọn Pages Source là GitHub Actions.
- [Full sync đầu tiên](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41459247272): thành công.
- [Telegram scheduled dry-run](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41459626202): thành công.
- [Telegram manual dry-run](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41459785072): thành công.
- [Telegram manual gửi thật](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41461177883): thành công; người nhận xác nhận có nội dung “Kỳ dữ liệu”.
- [Telegram scheduled gửi thật](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41461865827): `delivered`.
- [Telegram scheduled kiểm tra chống trùng](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41462011756): `already_delivered`, không gửi lại.
- [Full sync xác minh phiên bản trước](https://github.com/hieutt-vinatex/app-weather-forecast/actions/runs/41462205479): thành công.

Biến `NOTIFICATION_DRY_RUN` đang là `false` để lịch Telegram production có thể gửi thật. Ledger chỉ lưu target đã HMAC hóa và lần chạy lại cùng event không gửi trùng.

## Việc vận hành còn chờ quan sát

Chưa có run mang sự kiện `schedule` vì workflow được bật sau các khung giờ tự động ngày 2026-11-02. Cần quan sát đủ hai trường hợp trước khi đóng cutover và dọn mã provider cũ:

1. Một lượt incremental tự động trong cửa sổ 17:47–19:02.
2. Một lượt Telegram tự động trong cửa sổ 09:07–12:07.

Full sync tự động lúc 03:17 cũng nên được kiểm tra trong lần vận hành kế tiếp. Lịch GitHub Actions có thể khởi động trễ; xem [runbook production](./CLOUD_DEPLOYMENT.md) để biết giới hạn và cách chạy thủ công.

Mã Cloudflare/Vercel cũ hiện được giữ lại làm đường rollback. Không xóa tài nguyên bên ngoài cho đến khi hoàn tất quan sát lịch tự động và hết thời gian rollback mong muốn.
