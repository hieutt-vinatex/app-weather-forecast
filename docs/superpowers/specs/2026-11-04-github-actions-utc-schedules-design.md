# Thiết kế sửa lịch GitHub Actions sang UTC tường minh

**Ngày:** 2026-11-04

**Trạng thái:** Người dùng đã chọn phương án UTC và yêu cầu triển khai Native

## Ý định

Khôi phục đúng lịch nghiệp vụ đã duyệt: cập nhật dữ liệu lúc 18:45 và retry đến
23:45 theo giờ Việt Nam; gửi Telegram từ 09:00 và catch-up đến 12:00 sáng hôm
sau. Hệ thống vẫn chạy GitHub-only, không cần máy local và không thêm dịch vụ.

## Bằng chứng sự cố

Các schedule có `timezone: Asia/Ho_Chi_Minh` đã chạy lệch khoảng bảy giờ trong
production. Telegram chạy vào 19:12/19:41 ngày 03/11 thay vì buổi sáng; data job
chạy vào 01:38/02:48 ngày 04/11 thay vì buổi tối. Runtime guard đã chặn an toàn,
vì vậy workflow xanh nhưng không cập nhật và không gửi báo cáo.

## Phương án

### 1. Cron UTC tường minh — đã chọn

Xóa trường `timezone` và đổi trực tiếp các biểu thức cron từ UTC+7 sang UTC:

- Data 18:45 Việt Nam → `45 11 * * *` UTC.
- Data 19:45–23:45 Việt Nam → `45 12-16 * * *` UTC.
- Telegram 09:00–11:45 Việt Nam → `0-45/15 2-4 * * *` UTC.
- Telegram 12:00 Việt Nam → `0 5 * * *` UTC.

Runtime guard và ngày nghiệp vụ tiếp tục dùng `Asia/Ho_Chi_Minh`; chỉ tầng kích
hoạt GitHub Actions dùng UTC. Việt Nam không có DST nên phép đổi này ổn định.

### 2. Giữ timezone và thêm lịch UTC dự phòng — không chọn

Có nguy cơ tạo run trùng, tăng tải Actions và làm khó phân biệt schedule nào là
nguồn thật của một event.

### 3. Scheduler bên ngoài — không chọn

Phá vỡ kiến trúc một nền tảng, tăng cấu hình và không cần thiết cho múi giờ UTC+7
cố định.

## Phạm vi thay đổi

- Chỉ sửa cron trong hai workflow và hợp đồng kiểm thử tương ứng.
- Runbook tiếp tục trình bày giờ nghiệp vụ Việt Nam, đồng thời ghi rõ cron source
  được khai báo theo UTC.
- Deployment status ghi nhận sự cố 04/11 và giữ chu kỳ 18:45 → 09:00 ở trạng thái
  chưa quan sát sau bản sửa.
- Không thay đổi logic dữ liệu, Telegram, secrets, ledger hay quyền workflow.

## Điều tuyệt đối tránh

- Không đổi runtime guard sang UTC.
- Không thêm lịch song song có thể gửi trùng.
- Không đánh dấu rollout hoàn tất trước khi quan sát một run data buổi tối và một
  báo cáo Telegram buổi sáng theo lịch mới.
- Không gửi Telegram thủ công trong lúc triển khai nếu chưa có yêu cầu riêng.

## Kiểm thử và rollout

- Contract tests pin đúng bốn biểu thức cron UTC và cấm `timezone:` trong hai
  workflow.
- Documentation tests pin cả giờ nghiệp vụ và giải thích UTC.
- Chạy toàn bộ pytest, frontend test/lint/build và actionlint.
- Push `develop`, chờ CI và Pages deploy xanh; quan sát chu kỳ production kế tiếp.
