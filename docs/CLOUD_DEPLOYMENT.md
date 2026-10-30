# Triển khai cloud chi phí 0

Đây là đường triển khai production được chọn. Ứng dụng không cần FastAPI,
scheduler hoặc máy cá nhân chạy liên tục:

- Vercel phục vụ React/Vite dưới dạng static SPA.
- Cloudflare Worker đọc snapshot từ Workers KV và nhận thao tác quản trị.
- GitHub Actions chạy job đồng bộ dữ liệu hữu hạn và gửi Telegram.
- Trình duyệt polling snapshot bằng ETag; lịch sử 30/60/90 ngày vẫn xem được khi
  job hiện tại đang chậm hoặc lỗi.

Mục tiêu là 0 đồng cho dự án cá nhân quy mô nhỏ. Hạn mức miễn phí có thể thay đổi;
phần [Giám sát chi phí](#10-giám-sát-chi-phí-0) nêu các điểm cần theo dõi.

## 1. Chuẩn bị tài khoản

Cần ba tài khoản có thể đăng nhập bằng dashboard:

1. GitHub chứa repository này và bật Actions.
2. Cloudflare Workers Free.
3. Vercel Hobby cho dự án cá nhân, phi thương mại.

Không đưa token, chat ID hoặc khóa quản trị vào commit, issue, log hay cửa sổ chat.
Nên dùng password manager để tạo/lưu khóa quản trị dài, ngẫu nhiên.

## 2. Danh sách cấu hình bắt buộc

Các tên dưới đây là chính xác; bảng cố ý không chứa giá trị.

| Nơi lưu | Tên |
|---|---|
| GitHub Actions secret | `CLOUDFLARE_ACCOUNT_ID` |
| GitHub Actions secret | `CLOUDFLARE_API_TOKEN` |
| GitHub Actions secret | `CLOUDFLARE_KV_NAMESPACE_ID` |
| GitHub Actions secret | `TELEGRAM_BOT_TOKEN` |
| GitHub Actions secret | `TELEGRAM_CHAT_IDS` |
| Cloudflare Worker secret | `NOTIFICATION_ADMIN_TOKEN` |
| Cloudflare Worker secret | `GITHUB_DISPATCH_TOKEN` |
| Cloudflare Worker variable | `GITHUB_OWNER` |
| Cloudflare Worker variable | `GITHUB_REPO` |

Biến không bí mật bổ sung:

| Nơi lưu | Tên | Mục đích |
|---|---|---|
| GitHub Actions variable | `ALLOWED_ORIGINS` | Danh sách origin Vercel, cách nhau bằng dấu phẩy |
| GitHub Actions variable | `NOTIFICATION_DRY_RUN` | Giữ `true` đến khi kiểm tra xong Telegram |
| Vercel environment variable | `VITE_API_BASE_URL` | URL HTTPS của Cloudflare Worker, không có dấu `/` cuối |

Các biến `VITE_*` đều được đóng gói vào JavaScript công khai. Tuyệt đối không đặt
bí mật trong Vercel/Vite.

## 3. Tạo Cloudflare KV và token CI

Thực hiện trong Cloudflare dashboard:

1. Chọn đúng account, mở **Storage & Databases → KV** và tạo một namespace KV
   chuẩn, ví dụ đặt tên để nhận biết staging. Không chọn KV Instant đang beta.
2. Ghi lại Account ID và Namespace ID vào password manager.
3. Mở **My Profile → API Tokens → Create Token**. Dùng quyền tối thiểu đủ để:
   - triển khai Worker;
   - đọc/ghi Workers KV từ job GitHub Actions.
4. Giới hạn token vào đúng account. Nếu Worker chưa tồn tại, lần triển khai đầu cần
   quyền tạo Worker; sau đó có thể thay bằng token chỉ có quyền sửa Worker đó và
   đọc/ghi KV.

Cloudflare mô tả cách tạo/bind namespace trong
[Workers KV](https://developers.cloudflare.com/kv/get-started/) và khuyến nghị API
token cho CI trong
[GitHub Actions deployment](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/).

## 4. Cấu hình GitHub Actions và triển khai Worker

Trong repository GitHub, mở **Settings → Secrets and variables → Actions**.

### Secrets

Tạo năm repository secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_KV_NAMESPACE_ID`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`

### Variables

Tạo hai repository variables:

- `ALLOWED_ORIGINS`: origin Vercel chính xác, phân tách bằng dấu phẩy; không dùng
  wildcard. Có thể cập nhật sau khi Vercel cấp URL đầu tiên.
- `NOTIFICATION_DRY_RUN`: đặt `true`.

GitHub hướng dẫn vị trí tạo secret/variable tại
[Using secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
và [Using variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables).

Khi code đã nằm trên nhánh `develop`, workflow **CI** chạy trước; nếu xanh,
**Deploy Cloudflare Worker** tự triển khai `cloudflare/worker` và bind namespace
`SNAPSHOTS`. Mở tab **Actions** để xác nhận cả hai workflow thành công. URL mặc
định có dạng HTTPS trên miền `workers.dev`.

Nếu repository dùng nhánh production khác `develop`, đổi đồng thời bộ lọc nhánh
trong `.github/workflows/ci.yml`, `.github/workflows/deploy-worker.yml` và thiết
lập Production Branch của Vercel trước khi bật lịch.

## 5. Cấu hình bí mật của Worker

Sau lần deploy đầu, mở Cloudflare **Workers & Pages → app-weather-forecast-api →
Settings → Variables and Secrets**.

Thêm dưới dạng **Secret**:

- `NOTIFICATION_ADMIN_TOKEN`
- `GITHUB_DISPATCH_TOKEN`

Thêm dưới dạng variable thường:

- `GITHUB_OWNER`
- `GITHUB_REPO`

`GITHUB_DISPATCH_TOKEN` nên là fine-grained personal access token chỉ truy cập
repository này, với quyền **Contents: Read and write**. Endpoint
`repository_dispatch` yêu cầu quyền Contents write; không cấp quyền organization
hoặc repository khác. Xem
[GitHub repository dispatch](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event).

Cloudflare che giá trị secret trong dashboard. `wrangler deploy --keep-vars` của
workflow giữ lại các secret đã nhập khi deploy phiên bản code mới. Không đặt bốn
giá trị này vào `wrangler.jsonc`.

## 6. Chạy full sync staging

Trước khi kết nối frontend:

1. Mở **Actions → Cloud data sync → Run workflow**.
2. Chọn nhánh chứa workflow và `mode=full`.
3. Chờ job thành công; log phải cho biết số bản ghi và phiên bản, không có token.
4. Mở URL Worker:
   - `/api/health`
   - `/api/gdb?days=30`
   - `/api/gdb?days=60`
   - `/api/gdb?days=90`
5. Xác nhận ba snapshot có dữ liệu, ngày tăng dần và metadata freshness.

Nếu `Run workflow` không xuất hiện, workflow phải tồn tại trên default branch và
tài khoản cần quyền ghi repository. GitHub mô tả thao tác tại
[Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow?tool=webui).

Namespace staging có thể được giữ làm production sau khi smoke test. Nếu muốn
tách namespace production, tạo namespace thứ hai, cập nhật
`CLOUDFLARE_KV_NAMESPACE_ID`, chạy lại full sync rồi deploy Worker lại; không xóa
namespace cũ trước khi cutover hoàn tất.

## 7. Kết nối Vercel

Trong Vercel dashboard:

1. **Add New → Project**, import repository GitHub.
2. Chọn **Root Directory** là `frontend`.
3. Framework Preset: **Vite**.
4. Build Command: `npm run build`.
5. Output Directory: `dist`.
6. Node.js Version: **20.x**. `frontend/package.json` cũng ghim `20.x`.
7. Tạo duy nhất biến bắt buộc `VITE_API_BASE_URL` cho Production và Preview,
   trỏ tới URL Worker HTTPS.
8. Deploy. `frontend/vercel.json` đã cấu hình SPA fallback về `/index.html`.

Thiết lập này theo tài liệu chính thức
[Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite) và
[Vercel project settings](https://vercel.com/docs/project-configuration/project-settings).

Sau deploy đầu tiên, lấy production origin và branch-preview origin ổn định rồi:

1. cập nhật GitHub variable `ALLOWED_ORIGINS` bằng danh sách origin chính xác;
2. re-run job **Deploy Cloudflare Worker** gần nhất để áp dụng;
3. thêm origin preview mới chỉ khi thật sự cần thao tác trên preview.

Preview không nằm trong allowlist sẽ không gọi được Worker từ trình duyệt. Đây là
hành vi bảo mật chủ ý, không dùng `*` để khắc phục.

## 8. Smoke test preview và Telegram dry-run

Trên URL Vercel preview:

1. mở các lựa chọn 30/60/90 ngày;
2. xác nhận bảng lịch sử vẫn hiện khi badge là chậm/cũ;
3. chuyển tab nền rồi quay lại và kiểm tra snapshot được tải lại;
4. trong DevTools Network, xác nhận chỉ có REST/304, không có EventSource;
5. nhập sai khóa quản trị và xác nhận nhận lỗi an toàn;
6. nhập khóa đúng, bấm **Làm mới dữ liệu**, quan sát
   `Đã xếp hàng → Đang chạy trên cloud → Đã hoàn tất`;
7. tải lại trang và xác nhận ô khóa trống; khóa không xuất hiện trong Local Storage,
   Session Storage hoặc URL request.

Giữ `NOTIFICATION_DRY_RUN=true`, sau đó mở **Actions → Cloud Telegram
notification → Run workflow** với `mode=scheduled`. Kiểm tra log đánh giá đúng kỳ
và danh sách ứng viên nhưng không gọi Telegram thật.

Để thử gửi thật, nên dùng bot/group test trước:

1. đổi `NOTIFICATION_DRY_RUN=false`;
2. chạy workflow với `mode=manual`;
3. xác nhận group nhận đúng một báo cáo;
4. bấm lại trong UI chỉ khi chấp nhận có thêm một tin nhắn — manual send cố ý cho
   phép lặp.

## 9. Bật production và lịch tự động

Sau khi smoke test đạt:

1. đặt Production Branch của Vercel là nhánh production đã chọn;
2. promote deployment đã kiểm tra hoặc deploy commit đó lên production;
3. giữ `ALLOWED_ORIGINS` chỉ gồm các origin cần thiết;
4. bật lại các workflow nếu trước đó đã disable;
5. chỉ đặt `NOTIFICATION_DRY_RUN=false` khi Telegram đã được kiểm tra.

Lịch hiện tại, theo `Asia/Ho_Chi_Minh`:

- Full sync: 03:17 mỗi ngày.
- Incremental sync: mỗi 5 phút trong cửa sổ 17:47–19:02.
- Telegram: mỗi 15 phút từ 09:07 đến 12:07; sau lần gửi thành công, các lần sau
  trở thành no-op.

Kết quả ngày đang quay thường chậm khoảng 5–10 phút. Dữ liệu hôm qua và lịch sử
đã xuất bản không phải chờ job hiện tại; frontend tiếp tục hiển thị snapshot gần
nhất.

## 10. Giám sát chi phí 0

- **Vercel:** dùng Hobby chỉ cho dự án cá nhân/phi thương mại. Frontend này là
  static, không dùng Vercel Functions. Theo dõi trang **Usage**; Hobby sẽ bị tạm
  dừng khi vượt phần miễn phí thay vì tự chuyển sang on-demand billing. Xem
  [Vercel Hobby](https://vercel.com/docs/plans/hobby).
- **Cloudflare:** theo dõi Workers & Pages Analytics và KV Analytics. Workers Free
  hiện có giới hạn request/ngày; KV Free có giới hạn read/write/ngày và dung lượng.
  Xem số hiện hành tại [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
  và [KV limits](https://developers.cloudflare.com/kv/platform/limits/).
- **GitHub Actions:** repository public dùng standard runner miễn phí; repository
  private dùng quota theo plan. Lịch hiện tại tạo nhiều job ngắn mỗi ngày, vì vậy
  kiểm tra **Settings → Billing → Actions** hằng tuần trong tháng đầu. Xem
  [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
- Không bật Vercel Pro, Cloudflare Workers Paid hoặc GitHub larger runners nếu mục
  tiêu vẫn là 0 đồng.

## 11. Logs, xoay khóa và rollback

### Logs

- GitHub Actions: log phase, ngày nguồn, số record, version và kết quả Telegram đã
  mask; không log header/token/chat ID đầy đủ.
- Cloudflare: Worker Logs/Observability cho lỗi API và dispatch.
- Vercel: Deployment/Build logs; frontend static không có server runtime log.

### Xoay khóa

1. Tạo token mới tại nhà cung cấp.
2. Cập nhật đúng GitHub secret hoặc Cloudflare Worker secret.
3. Chạy smoke test tương ứng.
4. Thu hồi token cũ sau khi test thành công.

Xoay `NOTIFICATION_ADMIN_TOKEN` chỉ ở Cloudflare và password manager; người dùng
phải nhập lại khóa mới trên dashboard. Xoay bot token phải cập nhật
`TELEGRAM_BOT_TOKEN` trước khi thu hồi token cũ ở BotFather.

### Rollback

1. Disable hai workflow schedule nếu dữ liệu hoặc Telegram bất thường.
2. Vercel: promote deployment production tốt gần nhất.
3. Cloudflare: rollback Worker deployment tốt gần nhất trong dashboard.
4. Nếu lỗi do snapshot mới, trỏ lại namespace/manifest đã kiểm tra hoặc chạy full
   sync từ commit tốt; không xóa namespace/manifest cũ trước khi phục hồi.
5. Giữ `NOTIFICATION_DRY_RUN=true` trong lúc điều tra Telegram.

FastAPI/Docker còn trong repository chỉ để phát triển local và đối chiếu parity;
không phải đường production được chọn. Xem [INSTALLATION.md](./INSTALLATION.md).
