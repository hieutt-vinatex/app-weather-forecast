# Thiết kế cập nhật dữ liệu buổi tối và báo cáo Telegram hằng ngày

**Ngày:** 2026-11-03  
**Trạng thái:** Đã được người dùng phê duyệt
**Phương án đã chọn:** Hai workflow tách biệt, phối hợp bằng trạng thái an toàn trên `gh-pages`

## Ý định

Hệ thống chỉ cần tạo một snapshot dữ liệu thành công mỗi ngày thay vì cào nguồn
liên tục. Lượt chính bắt đầu lúc 18:45 `Asia/Ho_Chi_Minh`; nếu thất bại, hệ thống
thử lại mỗi giờ đến hết 23:45. Sáng hôm sau, khoảng 09:00, Telegram luôn gửi một
báo cáo về các số chưa xuất hiện từ 20 ngày trở lên.

Nếu toàn bộ lượt cập nhật buổi tối thất bại, báo cáo sáng vừa cảnh báo lỗi vừa
dùng snapshot thành công gần nhất và ghi rõ đó là dữ liệu cũ. Nếu không có số
đạt ngưỡng, hệ thống vẫn gửi tin xác nhận. Mục tiêu vẫn là GitHub-only, chi phí
định kỳ bằng 0 và không cần máy local hoạt động.

## Mục tiêu

- Cập nhật snapshot lần đầu lúc 18:45 mỗi ngày.
- Chỉ cào lại lúc 19:45, 20:45, 21:45, 22:45 và 23:45 khi ngày đó chưa có
  publication thành công.
- Dừng cào ngay sau lần thành công đầu tiên; các schedule còn lại chỉ no-op.
- Gửi một cảnh báo Telegram sau lần cập nhật đầu tiên thất bại; không gửi thêm
  cảnh báo cho từng retry trung gian.
- Khoảng 09:00 sáng hôm sau, gửi đúng một báo cáo cho mỗi target, kể cả khi kỳ dữ
  liệu chưa đổi hoặc không có số đạt ngưỡng.
- Báo cáo mọi số `00`–`99` chưa xuất hiện từ 20 ngày trở lên, không có trần 25
  ngày.
- Số không xuất hiện trong toàn bộ lịch sử hiện có được đưa vào báo cáo với nhãn
  cận dưới, ví dụ `≥90 ngày – không thấy trong dữ liệu hiện có`.
- Giữ snapshot hợp lệ gần nhất khi nguồn lỗi; không công bố dữ liệu rỗng hoặc dở.
- Giữ token, Chat ID và HMAC key ngoài source, artifact, log và file công khai.

## Không nằm trong phạm vi

- Cập nhật mỗi 5 phút hoặc realtime trong cửa sổ quay.
- Cam kết GitHub Actions bắt đầu đúng tuyệt đối tại 18:45 hoặc 09:00. Đây là giờ
  mục tiêu; hosted scheduler có thể chạy trễ.
- Mở rộng lịch sử công khai quá 90 ngày.
- Gửi cảnh báo cho mọi lần retry thất bại.
- Dùng thêm scheduler, database hoặc nền tảng trả phí bên ngoài GitHub.

## Điều tuyệt đối tránh

- Không cào lại sau khi publication của ngày nghiệp vụ đã thành công.
- Không để schedule bị trễ tới rạng sáng rồi chạy incremental cho sai ngày.
- Không gửi lặp cùng loại thông báo trong cùng ngày cho cùng target.
- Không mô tả số chưa từng thấy là vắng chính xác 90 ngày; chỉ được ghi `≥90`.
- Không dùng snapshot cũ mà thiếu nhãn cảnh báo và ngày kỳ dữ liệu.
- Không trao Telegram secrets cho data workflow.

## Các phương án đã cân nhắc

### 1. Hai workflow và trạng thái chung — đã chọn

Data workflow chỉ đọc nguồn, xuất bản snapshot và ghi trạng thái cập nhật theo
ngày. Telegram workflow giữ secrets gửi tin, được kích hoạt sau data workflow để
xử lý cảnh báo thất bại đầu tiên và được schedule buổi sáng để gửi báo cáo hằng
ngày. Hai workflow phối hợp qua file trạng thái không nhạy cảm trên `gh-pages`.

Ưu điểm là tách quyền rõ ràng, tái sử dụng pipeline hiện có, chống trùng dễ kiểm
thử và không cần dịch vụ mới. Đổi lại, cần một hợp đồng trạng thái mới và xử lý
hai loại trigger trong Telegram workflow.

### 2. Gộp data và Telegram vào một workflow — không chọn

Luồng ngắn hơn nhưng data job phải nhận Telegram secrets và quyền rộng hơn. Một
lỗi cấu hình có thể ảnh hưởng cả publication lẫn notification.

### 3. Cho data workflow gọi Telegram Bot API trực tiếp — không chọn

Sửa ít file nhưng nhân đôi logic gửi, ledger và retry; làm mất ranh giới bảo mật
đã có giữa dữ liệu và kênh thông báo.

## Lịch và runtime guard

### Data workflow

Các schedule dùng `timezone: Asia/Ho_Chi_Minh`:

- `45 18 * * *`: lượt chính 18:45.
- `45 19-23 * * *`: các lượt retry mỗi giờ.

GitHub vẫn tạo retry runs sau khi đã thành công, nhưng bước đầu tiên đọc trạng
thái/ngày của manifest và kết thúc no-op trước khi cào nguồn. Workflow chỉ được
phép cào khi giờ bắt đầu thực tế nằm trong 18:30–23:59. Một scheduled run tới sau
nửa đêm phải no-op; sáng hôm sau sẽ coi publication ngày trước bị thiếu.

`workflow_dispatch` vẫn hỗ trợ `full|incremental` để vận hành thủ công và không
bị runtime guard của schedule chặn. Một manual publication thành công có
`sourceReferenceDate` đúng ngày nghiệp vụ cũng được tính là đã phục hồi ngày đó.

### Telegram workflow

- Mốc mục tiêu đầu tiên: 09:00.
- Có các lượt catch-up cách nhau 15 phút đến 12:00 để chịu được scheduler delay
  hoặc lỗi tạm thời.
- Runtime guard chỉ cho scheduled report chạy trong buổi sáng; run tới quá muộn
  không gửi một báo cáo mang ngày sai.
- Ledger theo ngày gửi bảo đảm các lượt catch-up chỉ tạo tối đa một tin cho mỗi
  target.

Hai workflow tiếp tục dùng concurrency group chung
`github-pages-publication`, `cancel-in-progress: false` để không ghi đè state của
nhau.

## Trạng thái cập nhật dữ liệu

Thêm một file không chứa bí mật trên nhánh `gh-pages`:

`state/daily-data-update.json`

Hợp đồng phiên bản 1 chứa tối thiểu:

- `schemaVersion`
- `businessDate`
- `status`: `pending|failed|succeeded`
- `attemptCount`
- `firstAttemptAt`, `lastAttemptAt`
- `initialFailureAt` nếu có
- `lastReason`: chỉ dùng mã lý do an toàn
- `publishedVersion`, `sourceReferenceDate` khi thành công

File `state/` không nằm trong Pages artifact, nhưng nhánh repository là public
nên mọi trường vẫn phải được coi là công khai. Không lưu URL lỗi, response body,
exception text, token, Chat ID hoặc target key thô.

Trạng thái được cập nhật cùng giao dịch push `gh-pages` với `site/data`. Nếu job
thất bại, active manifest không đổi nhưng `status.json` và daily state được cập
nhật. Nếu job thành công, manifest version mới và daily state `succeeded` được
đẩy cùng nhau.

Nếu schedule 18:45 bị GitHub bỏ hoàn toàn, lượt retry đầu tiên thực sự chạy sẽ
khởi tạo state và được coi là lần thử đầu. Nếu lần đó thất bại, Telegram vẫn gửi
một cảnh báo “cập nhật buổi tối thất bại”; nội dung không khẳng định job đã bắt
đầu đúng 18:45.

## Luồng cảnh báo thất bại buổi tối

Telegram workflow bổ sung trigger `workflow_run` sau khi
`Data sync and Pages deploy` hoàn tất. Nó checkout `gh-pages`, đọc daily state và
chỉ gửi khi:

- ngày nghiệp vụ chưa thành công;
- đã có lần thất bại đầu tiên;
- failure alert của ngày/target chưa được ghi ledger.

Tin cảnh báo nêu ngày cần cập nhật, mã lý do an toàn, kỳ dữ liệu hợp lệ gần nhất
và thông báo hệ thống sẽ retry mỗi giờ đến 23:45. Các `workflow_run` sau đó chỉ
retry việc giao cảnh báo đầu tiên nếu lần gửi Telegram trước thất bại; chúng
không tạo tin thất bại mới cho từng data attempt.

Event key an toàn có dạng logic:

`data-update-failure:<business-date>:<HMAC target>`

## Báo cáo Telegram 09:00

Báo cáo được khóa theo ngày gửi thay vì theo kỳ dữ liệu:

`daily-report:<report-date>:20-plus:<HMAC target>`

Do đó cùng một snapshot có thể được báo cáo vào hai ngày khác nhau, nhưng retry
trong cùng ngày không gửi trùng.

### Khi cập nhật tối trước thành công

Tin nhắn gồm:

- ngày gửi báo cáo;
- `Kỳ dữ liệu: DD/MM/YYYY`;
- danh sách số chưa xuất hiện `>=20 ngày`, nhóm theo số ngày;
- nhóm số chưa từng thấy trong toàn bộ lịch sử với nhãn cận dưới;
- tổng số ứng viên và ghi chú dữ liệu chỉ dùng cho thống kê.

### Khi cập nhật tối trước thất bại hoặc bị thiếu

Tin nhắn vẫn được gửi và gồm:

- cảnh báo rằng dữ liệu kỳ dự kiến không cập nhật thành công;
- số lần thử và mã lý do an toàn gần nhất nếu có;
- dòng nổi bật `Đang sử dụng dữ liệu cũ`;
- ngày kỳ dữ liệu của snapshot thành công gần nhất;
- toàn bộ báo cáo `>=20 ngày` tính trên snapshot cũ.

Nếu không có snapshot hợp lệ nào, tin 09:00 chỉ báo không có dữ liệu để lập báo
cáo, không tự tạo số liệu.

### Khi không có ứng viên

Vẫn gửi một tin xác nhận:

`Không có số nào chưa xuất hiện từ 20 ngày trở lên trong kỳ dữ liệu này.`

Nếu đang dùng snapshot cũ, phần cảnh báo thất bại vẫn xuất hiện trước dòng xác
nhận này.

## Cách tính số chưa xuất hiện

- Chỉ dùng các kỳ `drawComplete=true` tới `referenceDate`.
- Duyệt đủ `00`–`99`, không chỉ các số từng xuất hiện.
- Với số đã thấy, `daysAbsent = referenceDate - lastSeen`; chọn khi `>=20`.
- Với số chưa thấy, tính độ phủ lịch sử theo ngày hoàn chỉnh sớm nhất và mới
  nhất. Chỉ chọn khi độ phủ ít nhất 20 ngày và hiển thị dạng cận dưới, ví dụ
  `≥90 ngày – không thấy trong dữ liệu hiện có`.
- Không dùng ngày tương lai, kỳ chưa hoàn chỉnh hoặc statistics cache để suy ra
  lần xuất hiện cuối.

Manual Telegram dùng cùng quy tắc `>=20` và dữ liệu mới nhất, nhưng giữ hành vi
hiện tại: chạy thủ công có thể gửi thêm một tin và không tiêu thụ daily-report
ledger.

## Bảo mật và quyền

- Data workflow giữ `contents: write`, `pages: write`, `id-token: write` nhưng
  không nhận Telegram secrets.
- Telegram workflow chỉ cần `contents: write` và ba secret hiện có.
- `workflow_run` chỉ xử lý workflow/branch tên cố định và không chạy code từ
  nhánh không tin cậy.
- Target trong ledger tiếp tục là HMAC-SHA256; không lưu hoặc log Chat ID.
- Mọi lý do lỗi được ánh xạ thành enum an toàn như `invalid_upstream_data`,
  `job_timeout`, `cloud_storage_error`.

Delivery Telegram tiếp tục theo chính sách best-effort at-least-once đã được phê
duyệt ở thiết kế production trước: chỉ ghi ledger sau khi provider báo thành
công. Nếu Telegram đã nhận tin nhưng request timeout hoặc runner dừng trước khi
commit ledger, lượt catch-up được phép retry và hiếm khi có thể tạo tin trùng.
Ưu tiên này tránh âm thầm mất cảnh báo hoặc báo cáo; không pre-record delivery
trước khi gửi.

## Thay đổi dự kiến

- `.github/workflows/data-sync.yml`: lịch mới, runtime guard, skip-after-success
  và daily state.
- `.github/workflows/telegram.yml`: lịch 09:00/catch-up, `workflow_run`, mode
  cảnh báo data failure và daily dedupe.
- `app/cloud/data_jobs.py` cùng contracts/store: trạng thái cập nhật theo ngày.
- `app/cloud/notification_jobs.py`: failure alert, daily report và event keys
  mới.
- `app/notifications/models.py`: ngưỡng min-only, đủ `00`–`99`, cận dưới cho số
  chưa thấy và formatter mới.
- Tests workflow, data jobs, notification jobs, state/contract verifier.
- `.env.example`, runbook Telegram/cloud và deployment status.

## Kiểm thử bắt buộc

- 18:45 thành công: publication đúng ngày, state succeeded, mọi retry sau no-op.
- 18:45 thất bại: active manifest giữ nguyên, cảnh báo Telegram gửi đúng một
  lần, retry 19:45 có thể phục hồi.
- Tất cả lượt thất bại: 09:00 gửi cảnh báo + báo cáo từ snapshot cũ.
- Schedule chạy trễ ngoài runtime window: không cào và không ghi nhầm ngày.
- Cùng daily report chạy nhiều lần: mỗi target nhận đúng một tin trong ngày.
- Hai ngày liên tiếp dùng cùng snapshot: mỗi ngày vẫn nhận một tin.
- Không có ứng viên: vẫn gửi xác nhận không có số.
- Số vắng 20, 21, trên 25 ngày được chọn; số vắng 19 ngày không được chọn.
- Số không thấy trong đủ 90 ngày có nhãn `≥90`; độ phủ dưới 20 ngày không được
  kết luận.
- Gửi một target thành công và target khác thất bại: ledger chỉ đánh dấu target
  thành công và retry target còn lại.
- Contract verifier không cho state/ledger chứa token, Chat ID hoặc exception
  thô.

## Triển khai và rollback

1. Chạy toàn bộ Python/frontend/workflow contract tests và actionlint.
2. Push `develop`, chờ CI và Pages deploy xanh.
3. Giữ Telegram dry-run cho một chu kỳ mô phỏng/manual, kiểm tra message và
   state không chứa bí mật.
4. Bật gửi thật, quan sát một chu kỳ 18:45 và 09:00.
5. Chỉ sau chu kỳ thật thành công mới tiếp tục dọn provider code cũ.

Rollback bằng cách revert commit workflow/logic trên `develop`; active manifest
và các snapshot versioned vẫn còn trên `gh-pages`. Các event key mới có prefix
riêng nên không xung đột ledger cũ `2026-11-02:19-25`.

