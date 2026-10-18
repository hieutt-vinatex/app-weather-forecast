# Gửi thông báo tự động vào Telegram Group

## 1. Tạo bot

1. Mở Telegram và nhắn cho `@BotFather`.
2. Gửi `/newbot` và làm theo hướng dẫn.
3. Lưu Bot Token. Không commit hoặc gửi token qua chat/email.

## 2. Thêm bot vào group

1. Mở group → **Add members** → chọn bot.
2. Đảm bảo bot có quyền **Send messages**.
3. Trong group, gửi:

```text
/start@ten_bot_cua_ban
```

Bot không cần quyền admin nếu group cho thành viên gửi tin bình thường.

## 3. Lấy Group Chat ID

Chạy bằng Bash/WSL:

```bash
read -rsp "Telegram Bot Token: " TG_TOKEN
echo
curl -sS "https://api.telegram.org/bot${TG_TOKEN}/getUpdates"
unset TG_TOKEN
```

Tìm object có `chat.title` đúng tên group và lấy `chat.id`:

```json
{
  "chat": {
    "id": -1001234567890,
    "title": "Tên group",
    "type": "supergroup"
  }
}
```

Group ID thường là số âm; supergroup thường bắt đầu bằng `-100`. Nếu `result`
rỗng, gửi lại lệnh trong group rồi gọi `getUpdates` lần nữa.

## 4. Cấu hình `.env`

```dotenv
NOTIFICATIONS_ENABLED=true
NOTIFICATION_DRY_RUN=true
NOTIFICATION_MIN_DAYS=19
NOTIFICATION_MAX_DAYS=25
NOTIFICATION_SEND_TIME=09:00
NOTIFICATION_ADMIN_TOKEN=chuoi-ngau-nhien-dai

TELEGRAM_BOT_TOKEN=bot-token-tu-botfather
TELEGRAM_CHAT_IDS=-1001234567890
```

Nhiều group dùng dấu phẩy:

```dotenv
TELEGRAM_CHAT_IDS=-1001234567890,-1009876543210
```

Restart backend sau khi sửa `.env`.

## 5. Thử cấu hình

Kiểm tra backend đã nhận group:

```bash
curl http://localhost:8000/api/notifications/status
```

Gửi dry-run; lệnh này chưa gọi Telegram vì `NOTIFICATION_DRY_RUN=true`:

```bash
curl -X POST http://localhost:8000/api/notifications/test \
  -H "X-Notification-Token: gia-tri-NOTIFICATION_ADMIN_TOKEN"
```

Nếu response có `success: true`, đổi:

```dotenv
NOTIFICATION_DRY_RUN=false
```

Restart backend và gọi lại `/api/notifications/test`. Group sẽ nhận tin kiểm tra.

## 6. Gửi tự động và gửi ngay

- Tự động: backend kiểm tra lúc `09:00` sáng hôm sau. Chỉ gửi khi dữ liệu 25 ngày
  đầy đủ và có số chưa xuất hiện từ 19–25 ngày.
- Gửi ngay: trên dashboard, nhập `NOTIFICATION_ADMIN_TOKEN` rồi bấm
  **Gửi thông báo 19–25 ngày ngay**.
- Gửi ngay bằng API:

```bash
curl -X POST http://localhost:8000/api/notifications/send-now \
  -H "X-Notification-Token: gia-tri-NOTIFICATION_ADMIN_TOKEN"
```

## 7. Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `chat not found` | Kiểm tra Group ID, bot đã được thêm vào group và có quyền gửi tin. |
| Telegram `401` | Bot Token sai hoặc đã bị thu hồi; tạo token mới trong BotFather. |
| `configuredTargetCount: 0` | Thiếu `TELEGRAM_BOT_TOKEN` hoặc `TELEGRAM_CHAT_IDS`; restart backend. |
| API `401` | `X-Notification-Token` khác `NOTIFICATION_ADMIN_TOKEN`. |
| API `404` | `NOTIFICATION_ADMIN_TOKEN` đang trống hoặc backend chưa restart. |
| `getUpdates` rỗng | Gửi lệnh mới trong group rồi thử lại; kiểm tra bot có đang dùng webhook không. |

