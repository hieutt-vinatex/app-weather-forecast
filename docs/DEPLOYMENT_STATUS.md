# Trạng thái triển khai GitHub-only

Cập nhật lần cuối: **2026-11-03** (`Asia/Ho_Chi_Minh`).

## Production hiện tại

- Dashboard: <https://hieutt-vinatex.github.io/app-weather-forecast/>
- Source branch/default branch: `develop`
- Commit ứng dụng đã xác minh tại cutover: `6d5b0623381d01903bb5147406502a12040d2e50`
- Nền tảng: GitHub Pages + GitHub Actions
- Telegram production: đã bật gửi thật; manual và cơ chế chống trùng của phiên
  bản trước đã được kiểm tra.

Không có token, Chat ID hoặc HMAC key nào được ghi trong tài liệu này.

## Dữ liệu đã xác minh

- Phiên bản publication đầu tiên: `20261102T140956823975Z`
- Phiên bản sau full sync kiểm tra rollback: `20261102T142829849363Z`
- `previousPublication` của phiên bản mới trỏ về đúng phiên bản đầu tiên.
- Manifest, status, history và snapshot 30/60/90 đều hợp lệ trên production.
- Snapshot chứa đúng 30/60/90 bản ghi; ngày mới nhất là `2026-11-02`.
- Dashboard và các tài nguyên dưới base path `/app-weather-forecast/` trả HTTP 200.

## Baseline production đã xác minh trước thay đổi Native

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

Các run trên là bằng chứng baseline ngày 2026-11-02, không phải bằng chứng cho lịch
Native mới.

## Triển khai Native mới

Đã hoàn tất trong source `develop`:

- Một lượt cập nhật chính lúc 18:45; nếu thất bại thì retry mỗi giờ đến 23:45.
- Cảnh báo Telegram sau lần cập nhật thất bại đầu tiên.
- Báo cáo từ 09:00 với catch-up đến 12:00, ngưỡng `>=20 ngày`, chống gửi lặp theo
  target và vẫn gửi xác nhận khi không có số đạt ngưỡng.
- Nếu tối không cập nhật được, báo cáo sáng dùng snapshot cũ và ghi rõ dữ liệu cũ.
- Workflow dùng chung mutex, không force-push và chỉ ghi đúng phạm vi dữ liệu/state.

Kiểm thử local đã qua toàn bộ backend và `actionlint`. Trạng thái này chỉ xác nhận
mã và cấu hình workflow; **Chưa xác nhận production cho lịch Native mới** cho đến
khi có run URL và tin Telegram thực tế.

## Việc vận hành còn chờ quan sát

Cần quan sát đủ chu kỳ mới trước khi đóng cutover:

- [ ] Lượt dữ liệu 18:45 thành công hoặc retry 19:45–23:45 phục hồi, kèm run URL.
- [ ] Báo cáo Telegram 09:00 hoặc một lượt catch-up trước 12:00 tới đúng group.
- [ ] Một tình huống không có ứng viên vẫn gửi xác nhận (có thể kiểm tra bằng
  fixture/dry-run trước, production chỉ khi dữ liệu tự nhiên phù hợp).

Lịch GitHub Actions có thể khởi động trễ; xem
[runbook production](./CLOUD_DEPLOYMENT.md) để biết runtime guard, các lượt
catch-up và cách chạy thủ công.
