# Gửi thông báo vào Telegram Group

Production dùng GitHub Actions. Máy cá nhân, FastAPI và trình duyệt không cần mở
để lịch buổi sáng hoạt động.

## 1. Tạo bot và thêm vào group

1. Trong Telegram, nhắn `@BotFather`, gửi `/newbot` và làm theo hướng dẫn.
2. Lưu bot token trong password manager; không gửi token qua chat/email và không
   commit vào repository.
3. Mở group đích → **Add members** → thêm bot.
4. Cho bot quyền **Send messages**. Bot không cần quyền admin nếu group cho thành
   viên gửi tin.
5. Gửi một lệnh cho bot trong group để tạo update mới.

## 2. Lấy Group Chat ID an toàn

Có thể dùng một terminal tạm chỉ để đọc Bot API; thao tác này không chạy dự án:

```bash
read -rsp "Telegram Bot Token: " TG_TOKEN
echo
curl -sS "https://api.telegram.org/bot${TG_TOKEN}/getUpdates"
unset TG_TOKEN
```

Tìm object có `chat.title` đúng group rồi lấy `chat.id`. Group ID thường là số âm.
Nếu `result` rỗng, gửi một lệnh mới trong group rồi gọi lại. Không dán toàn bộ
response vào issue hoặc log vì có thể chứa dữ liệu người dùng.

## 3. Lưu cấu hình trong GitHub

Mở **Settings → Secrets and variables → Actions** và tạo ba repository secrets:

- `TELEGRAM_BOT_TOKEN`: token từ BotFather.
- `TELEGRAM_CHAT_IDS`: một hoặc nhiều group ID, phân tách bằng dấu phẩy.
- `NOTIFICATION_LEDGER_HMAC_KEY`: chuỗi ngẫu nhiên riêng dài ít nhất 32 ký tự.

Tạo repository variable `NOTIFICATION_DRY_RUN=true`. Ledger chỉ lưu event, thời
gian và khóa target HMAC; không lưu bot token, tên group hoặc chat ID thô.

## 4. Dry-run trước khi gửi thật

1. Bảo đảm workflow full sync đã thành công và dashboard có dữ liệu.
2. Mở **Actions → Telegram notification → Run workflow**.
3. Chọn `mode=daily`, giữ `NOTIFICATION_DRY_RUN=true`.
4. Kiểm tra log cho biết trạng thái đánh giá nhưng không chứa token/chat ID và
   group không nhận tin.
5. Nếu dữ liệu không có ứng viên `>=20 ngày`, kết quả no-match là bình thường;
   khi bật gửi thật, group vẫn nhận xác nhận “Không có số nào đạt ngưỡng”.

Dry-run không chứng minh bot có quyền gửi, vì vậy bước gửi thật nên dùng group test.

## 5. Gửi thật và bật lịch

1. Đổi variable thành `NOTIFICATION_DRY_RUN=false`.
2. Chạy **Actions → Telegram notification → Run workflow** với `mode=manual`.
3. Xác nhận group test nhận đúng một báo cáo.
4. Cập nhật `TELEGRAM_CHAT_IDS` sang group production nếu cần và thử lại.
5. Giữ workflow enabled để lượt 09:00 và catch-up 09:00–12:00 hoạt động.

Lượt chính chạy lúc 09:00; lịch catch-up thử mỗi 15 phút đến 12:00 vì GitHub
Actions có thể bị trễ và không đảm bảo bắt đầu chính xác. Daily mode dùng dữ liệu mới nhất đã xuất bản.
Job không cần chờ dữ liệu của ngày đang quay. Sau lần gửi thành công, ledger khiến
các lần sau cùng event trở thành no-op. Manual mode cố ý có thể gửi lặp.

Nếu lượt dữ liệu 18:45 thất bại, bot gửi cảnh báo đầu tiên và hệ thống thử lại mỗi
giờ đến 23:45. Nếu cả tối chưa phục hồi, báo cáo sáng vẫn dựa trên snapshot cũ,
ghi rõ **DỮ LIỆU CŨ**, ngày kỳ dữ liệu và lỗi cập nhật.

## 6. Gửi thủ công từ dashboard

Thẻ **Quản trị qua GitHub Actions** có liên kết **Gửi Telegram ngay**. Liên kết mở
workflow; chọn `mode=manual` rồi bấm **Run workflow**. Dashboard không có ô token,
không gọi API quản trị và không lưu secret.

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `chat not found` | Kiểm tra bot đã ở group, quyền Send messages và chat ID. |
| Telegram `401` | Tạo token mới ở BotFather, cập nhật secret rồi thu hồi token cũ. |
| Thiếu HMAC key | Tạo `NOTIFICATION_LEDGER_HMAC_KEY` đúng tên trong repository secrets. |
| Workflow luôn dry-run | Đổi repository variable thành `false`; không tạo secret cùng tên. |
| Không có ứng viên | Kiểm tra snapshot và độ đầy đủ; ngưỡng là mọi số `>=20 ngày`. |
| Lịch không chạy | Enable lại workflow; lịch public có thể bị disable sau 60 ngày không hoạt động. |
| `getUpdates` rỗng | Gửi update mới hoặc kiểm tra webhook hiện tại của bot. |

Nếu token hoặc chat ID từng xuất hiện trong commit/log, hãy thu hồi/đổi giá trị;
chỉ xóa dòng khỏi file không loại được dữ liệu khỏi lịch sử Git.
