# Triển khai production GitHub-only, chi phí 0

Đây là runbook production chính thức. Sau lần cấu hình đầu tiên, toàn bộ build,
đồng bộ dữ liệu, phát hành website và gửi Telegram chạy trên GitHub; máy cá nhân
không cần hoạt động.

## Kiến trúc và điều kiện chi phí 0

- Repository public dùng standard hosted runner và GitHub Pages cho website tĩnh.
- Nhánh `develop` chứa source, test và workflow; yêu cầu default branch `develop`
  để lịch và nút chạy thủ công luôn lấy đúng workflow.
- Nhánh `gh-pages` do workflow quản lý: `site/` chứa bundle + JSON công khai;
  `state/` chứa trạng thái cập nhật ngày và ledger Telegram đã HMAC.
- Pages artifact chỉ lấy `gh-pages/site`; `state` không được đưa vào website.
- URL production: <https://hieutt-vinatex.github.io/app-weather-forecast/>.

Mọi file trên nhánh `gh-pages` vẫn phải được coi là công khai. Không commit hoặc
in ra log token, chat ID hay HMAC key.

## Cấu hình bắt buộc

Trong repository, mở **Settings → Secrets and variables → Actions**.

Tạo đúng ba repository secrets, không nhập giá trị vào source:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`
- `NOTIFICATION_LEDGER_HMAC_KEY`

`NOTIFICATION_LEDGER_HMAC_KEY` nên là chuỗi ngẫu nhiên riêng, dài ít nhất 32 ký
tự và không dùng lại bot token. Tạo một repository variable:

- `NOTIFICATION_DRY_RUN=true`

Không tạo biến `VITE_*` chứa secret. Mọi biến Vite đều công khai trong JavaScript.

## Thứ tự bootstrap bắt buộc

Thực hiện đúng thứ tự này để khởi tạo website trước, sau đó mới xuất bản dữ liệu:

1. Chuyển repository sang public trong **Settings → General → Change repository visibility**.
2. Xác nhận `develop` là default branch trong **Settings → Branches**.
3. Chọn Pages Source: GitHub Actions trong **Settings → Pages → Build and deployment**.
4. Tạo ba secret và biến dry-run như phần trên; giữ `NOTIFICATION_DRY_RUN=true`.
5. Push code lên `develop`; không cần tạo hoặc push nhánh `gh-pages` thủ công.
6. Chờ CI và site deploy: workflow **CI** phải xanh, sau đó workflow
   **Deploy GitHub Pages** phải hoàn tất.
7. Chạy full sync tại **Actions → Data sync and Pages deploy → Run workflow**,
   chọn nhánh `develop` và `mode=full`.
8. Kiểm tra 30/60/90 ngày tại URL production; cả ba phạm vi phải có dữ liệu,
   ngày tăng dần và không có lỗi tải manifest.
9. Chạy Telegram dry-run tại **Actions → Telegram notification → Run workflow**,
   chọn `mode=daily` trong khi `NOTIFICATION_DRY_RUN=true`.
10. Bật gửi Telegram thật bằng cách đổi variable thành
    `NOTIFICATION_DRY_RUN=false`, rồi chạy `mode=manual` với group test trước.
11. Theo dõi lịch tự động ít nhất một cửa sổ quay và một cửa sổ Telegram trước
    khi coi cutover hoàn tất.

Nếu nút **Run workflow** không xuất hiện, workflow chưa có trên default branch
hoặc tài khoản hiện tại không có quyền ghi repository.

## Thao tác thủ công trên GitHub Actions

### Làm mới dữ liệu

Mở **Actions → Data sync and Pages deploy → Run workflow**:

- `mode=full`: tải và dựng lại tối đa 90 ngày; dùng cho lần đầu hoặc phục hồi.
- `mode=incremental`: cập nhật hôm qua + hôm nay và giữ lịch sử tốt đã có.

Job chỉ đổi manifest sau khi history và đủ snapshot 30/60/90 vượt qua verifier.
Nếu nguồn lỗi, job xuất bản trạng thái lỗi nhưng giữ manifest trước.

### Gửi Telegram

Mở **Actions → Telegram notification → Run workflow**:

- `mode=daily`: lập báo cáo hằng ngày cho mọi số chưa xuất hiện `>=20 ngày` và
  dùng ledger chống gửi lặp theo từng group.
- `mode=manual`: gửi báo cáo ngay; cố ý không ghi daily ledger nên chạy lại
  có thể tạo thêm một tin.

Hai liên kết tương tự có sẵn trên dashboard; chúng chỉ mở giao diện Actions, không
đưa secret vào trình duyệt.

## Lịch tự động và độ trễ

Tất cả lịch dùng `Asia/Ho_Chi_Minh`:

- Dữ liệu: lượt chính lúc 18:45. Nếu chưa thành công, workflow chạy lại mỗi giờ
  đến 23:45 (19:45–23:45); sau khi thành công, các lượt sau tự no-op.
- Telegram: lượt chính lúc 09:00; các lượt catch-up mỗi 15 phút trong
  09:00–12:00 chỉ gửi cho target chưa nhận, rồi dừng nhờ ledger.

Lịch hosted runner có thể bị trễ khi hệ thống đông. GitHub không đảm bảo bắt đầu chính xác
tại phút đã cấu hình. Runtime guard vẫn gắn lượt dữ liệu với đúng ngày nghiệp vụ;
các lượt retry/catch-up xử lý lần chạy trễ. Dữ liệu hôm qua và lịch sử đã xuất bản
không cần chờ dữ liệu của ngày đang quay.

Với repository public, GitHub có thể tự disable scheduled workflow sau 60 ngày
không có hoạt động repository. Nếu lịch không chạy, kiểm tra banner trong tab
Actions, enable lại workflow và chạy thủ công một lần. Không dùng lịch này cho
tác vụ cần thời điểm chính xác tuyệt đối.

## Hành vi thất bại và Telegram latest-data

- Nếu lượt 18:45 lỗi, workflow Telegram nhận sự kiện hoàn tất. Hệ thống gửi
  cảnh báo ngay lần thất bại đầu tiên. Data workflow tiếp tục thử mỗi giờ đến 23:45;
  các lỗi lặp lại trong cùng ngày không tạo thêm cảnh báo cho target đã nhận.
- Nếu mọi lượt đều thất bại, báo cáo 09:00 vẫn đánh giá snapshot cũ gần nhất và
  ghi cảnh báo “Đang sử dụng dữ liệu cũ” — tức **DỮ LIỆU CŨ** — kèm ngày kỳ dữ
  liệu, số lần thử và mã lỗi. Nếu chưa từng có snapshot hợp lệ, tin sáng ghi rõ
  không thể lập báo cáo dữ liệu.
- Ngưỡng là một chiều: mọi số chưa xuất hiện `>=20 ngày` đều được liệt kê, không
  có giới hạn trên. Nếu không có ứng viên, hệ thống vẫn gửi xác nhận “Không có số
  nào đạt ngưỡng” thay vì im lặng.
- Job không đợi một kỳ mới đang quay. Daily ledger bảo đảm mỗi target chỉ nhận
  một lần cho cùng event; target được lưu dưới dạng HMAC-SHA256, không phải chat
  ID thô.

## Ba file trạng thái cần quan sát

- `site/data/status.json`: trạng thái job an toàn để dashboard đọc; file này nằm
  trong Pages artifact công khai.
- `state/daily-data-update.json`: ngày nghiệp vụ, trạng thái, số lần thử và phiên
  bản đã xuất bản. File không nằm trong Pages artifact nhưng nhánh `gh-pages` của
  repository public vẫn có thể đọc được.
- `state/telegram-ledger.json`: event và định danh target đã HMAC để chống gửi
  lặp; không chứa chat ID thô, token hay HMAC key.

Khi xử lý sự cố, ưu tiên xem Summary/log an toàn của workflow và các trường
`status`, `businessDate`, `attemptCount`, `sourceReferenceDate`. Không sao chép toàn bộ nội dung state
vào issue, chat hoặc log công khai.

## Xác minh sau deploy

1. Mở URL Pages và chọn lần lượt 30, 60, 90 ngày.
2. Đối chiếu ngày mới nhất, trạng thái freshness và bảng lịch sử.
3. Trong Actions, mở log data job và xác nhận version + record count, không có
   secret hay chat ID.
4. Chạy Telegram daily khi dry-run; sau đó gửi manual tới group test.
5. Sau khi bật thật, chạy daily hai lần cho cùng event và xác nhận lần sau là
   no-op/already delivered.

Pages/CDN có thể cần vài phút sau deployment. Nếu vừa full sync xong mà trình
duyệt vẫn thấy manifest cũ, chờ một nhịp cache rồi reload; không chạy nhiều full
sync đồng thời.

## Theo dõi chi phí và vận hành

- Giữ repository public nếu mục tiêu là dùng standard runner miễn phí.
- Không bật larger runner hoặc tính năng trả phí.
- Theo dõi **Actions → Usage** và thời lượng của ba workflow trong tháng đầu.
- Tất cả writer dùng chung concurrency group; workflow đang chạy được xếp hàng,
  không bị hủy giữa chừng.
- Scheduled workflow có thể bị trễ hoặc bị disable theo quy tắc 60 ngày nêu trên.

## Rollback

1. Disable `Data sync and Pages deploy` và `Telegram notification` nếu lỗi đang
   tiếp diễn; đặt `NOTIFICATION_DRY_RUN=true`.
2. Revert về commit tốt gần nhất trên `develop`, push và chờ **CI** +
   **Deploy GitHub Pages**.
3. Nếu bundle tốt nhưng dữ liệu mới sai, giữ hoặc khôi phục manifest trước trên
   `gh-pages`; không xóa version mà manifest/previous pointer còn tham chiếu.
4. Chạy full sync từ source tốt sau khi đã xác định nguyên nhân; lượt thành công
   sẽ khôi phục trạng thái ngày tương ứng.
5. Enable lại lịch, kiểm tra 30/60/90 và dry-run Telegram trước khi gửi thật.

Không force-push `gh-pages`. Workflow tự fetch, nạp lại và reapply thay đổi giới
hạn tối đa ba lần; nếu vẫn xung đột, job dừng để tránh ghi đè state mới hơn.

## Tài liệu liên quan

- [Thiết lập Telegram](./TELEGRAM_GROUP.md)
- [Local tùy chọn và kiểm thử](./INSTALLATION.md)
- [Cấu hình Pages bằng workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [Chạy workflow thủ công](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Sự kiện schedule và các giới hạn](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
