# Gửi thông báo tự động vào Telegram Group

Production dùng GitHub Actions để gửi Telegram; không cần mở trình duyệt, chạy
FastAPI hoặc giữ máy cá nhân hoạt động. Thiết lập cloud tổng thể nằm tại
[CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md).

## 1. Tạo bot và thêm vào group

1. Mở Telegram, nhắn `@BotFather`, gửi `/newbot` và làm theo hướng dẫn.
2. Lưu bot token thẳng vào password manager; không gửi qua chat/email và không
   commit vào repository.
3. Mở group đích → **Add members** → thêm bot.
4. Cho bot quyền **Send messages**. Bot không cần quyền admin nếu group cho thành
   viên gửi tin.
5. Gửi `/start@ten_bot_cua_ban` trong group để tạo update mới.

## 2. Lấy Group Chat ID an toàn

Có thể dùng một shell tạm thời chỉ để đọc `getUpdates`; lệnh không chạy ứng dụng
local và không ghi token vào command history:

```bash
read -rsp "Telegram Bot Token: " TG_TOKEN
echo
curl -sS "https://api.telegram.org/bot${TG_TOKEN}/getUpdates"
unset TG_TOKEN
```

Trong JSON, tìm object có `chat.title` đúng group và lấy `chat.id`. Group ID thường
là số âm; supergroup thường có tiền tố `-100`. Nếu `result` rỗng, gửi một lệnh mới
trong group rồi gọi lại. Nếu bot đang dùng webhook, tạm ngắt webhook hoặc đọc
update từ hệ thống webhook hiện tại.

Không dán toàn bộ response `getUpdates` vào issue/log vì có thể chứa thông tin
người dùng và nội dung tin nhắn.

## 3. Lưu cấu hình trên GitHub

Mở repository **Settings → Secrets and variables → Actions**.

Tạo repository secrets, không ghi giá trị vào file:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`

Nhiều group được phân tách bằng dấu phẩy trong `TELEGRAM_CHAT_IDS`.

Tạo repository variable:

- `NOTIFICATION_DRY_RUN=true`

Job Telegram còn dùng ba Cloudflare secrets đã cấu hình theo tài liệu cloud:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_KV_NAMESPACE_ID`
- `CLOUDFLARE_API_TOKEN`

## 4. Dry-run trước khi gửi thật

1. Chạy full sync thành công để KV có snapshot hợp lệ.
2. Mở **Actions → Cloud Telegram notification → Run workflow**.
3. Chọn `mode=scheduled` và chạy khi `NOTIFICATION_DRY_RUN=true`.
4. Kiểm tra log: đúng kỳ tham chiếu, khoảng 19–25 ngày và số ứng viên; log không
   được chứa bot token hoặc chat ID đầy đủ.
5. Nếu dữ liệu chưa đủ 25 ngày hoặc kỳ chưa hoàn tất, job chủ động không gửi.

Dry-run không gọi Telegram và không chứng minh quyền gửi của bot. Bước gửi thật
nên dùng group test trước.

## 5. Gửi test thật và bật lịch

1. Đổi GitHub variable `NOTIFICATION_DRY_RUN=false`.
2. Chạy workflow với `mode=manual`.
3. Xác nhận group test nhận đúng một báo cáo.
4. Chuyển `TELEGRAM_CHAT_IDS` sang group production nếu cần và chạy lại một lần.
5. Giữ workflow **Cloud Telegram notification** enabled.

Lịch hiện tại chạy mỗi 15 phút từ 09:07 đến 12:07 theo
`Asia/Ho_Chi_Minh`. Sau một lần scheduled gửi thành công, state trong Workers KV
khiến các lần thử sau trở thành no-op. Nếu một đích lỗi, retry chỉ nhắm phần chưa
thành công.

## 6. Gửi thủ công từ dashboard

Trong thẻ **Thao tác quản trị trên cloud**:

1. nhập `NOTIFICATION_ADMIN_TOKEN`;
2. bấm **Gửi Telegram ngay**;
3. chờ trạng thái `Đã xếp hàng → Đang chạy trên cloud → Đã hoàn tất`.

Khóa quản trị chỉ tồn tại trong bộ nhớ tab và mất khi reload. Mỗi lần bấm gửi thủ
công là một yêu cầu mới; bấm lại có thể tạo thêm một tin nhắn Telegram. Worker có
cooldown để chặn hai job cùng loại chạy đồng thời nhưng không chống lặp có chủ ý.

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `chat not found` | Kiểm tra bot đã ở trong group, quyền Send messages và chat ID. |
| Telegram `401` | Thu hồi token sai/cũ, tạo token mới ở BotFather rồi cập nhật GitHub secret. |
| Không có ứng viên | Kiểm tra full sync, độ đầy đủ 25 ngày và khoảng 19–25 ngày. |
| Workflow dry-run mãi | Đặt repository variable `NOTIFICATION_DRY_RUN=false`, không tạo secret cùng tên. |
| UI trả `401` | `NOTIFICATION_ADMIN_TOKEN` nhập vào khác Worker secret. |
| UI trả `403` | Origin Vercel chưa nằm chính xác trong `ALLOWED_ORIGINS`. |
| UI trả `429` | Một job Telegram đang queued/running; chờ job hiện tại kết thúc. |
| `getUpdates` rỗng | Gửi update mới hoặc kiểm tra webhook của bot. |

Đường FastAPI notification cũ chỉ còn phục vụ local parity; production không đọc
`TELEGRAM_BOT_TOKEN` từ `.env` trên một server thường trực.
