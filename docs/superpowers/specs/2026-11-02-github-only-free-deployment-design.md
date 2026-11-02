# Thiết kế triển khai GitHub-only miễn phí

**Ngày:** 2026-11-02  
**Trạng thái:** Đã được người dùng phê duyệt

**Phương án đã chọn:** GitHub Pages bằng custom GitHub Actions + nhánh trạng
thái/xuất bản `gh-pages`

## Ý định và lý do

Dự án hiện đã được tách theo hướng static-first, nhưng bản triển khai hiện tại vẫn
cần ba nền tảng: Vercel cho React, Cloudflare Worker/KV cho API và dữ liệu, GitHub
Actions cho các job đồng bộ và Telegram. Mục tiêu mới là giảm vận hành xuống một
nền tảng duy nhất, giữ chi phí định kỳ bằng 0, không cần máy local chạy liên tục,
và sửa ít mã nhất có thể.

GitHub sẽ đảm nhiệm toàn bộ phần production: GitHub Pages phục vụ dashboard và
các snapshot JSON thông qua custom Actions deployment; GitHub Actions đồng bộ
dữ liệu, phát hành website, gửi Telegram theo lịch và cung cấp thao tác chạy thủ
công. Đổi lại, dashboard không còn hai nút quản trị trực tiếp và dữ liệu ngày
đang quay có thể chậm khoảng 10–15 phút do phải chờ workflow và GitHub Pages
phát hành bản mới.

## Mục tiêu

- Chỉ dùng GitHub để lưu mã, chạy tác vụ, lưu dữ liệu đã phát hành và phục vụ
  website production.
- Giữ chi phí định kỳ bằng 0 trong giới hạn GitHub Free dành cho repository công
  khai.
- Dashboard tiếp tục cung cấp snapshot 30, 60 và 90 ngày, biểu đồ, thống kê theo
  giải, trạng thái độ mới và dữ liệu các ngày trước mà không phải đợi cào lại.
- Cập nhật ngày đang quay theo lịch hiện có; chấp nhận độ trễ hiển thị điển hình
  khoảng 10–15 phút.
- Telegram tự chạy vào buổi sáng, không cần dashboard hoặc máy local đang mở.
- Nếu dữ liệu mới nhất không phải của hôm nay, Telegram vẫn đánh giá bộ dữ liệu
  hợp lệ mới nhất hiện có; nội dung luôn ghi rõ “Kỳ dữ liệu”.
- Cho phép “Làm mới dữ liệu” và “Gửi Telegram ngay” bằng nút **Run workflow**
  trong GitHub Actions.
- Giữ bí mật Telegram trong GitHub Actions Secrets và không đưa `chat_id`, token
  hoặc khóa vào website, log hay file công khai.
- Tận dụng lại pipeline Python, hợp đồng `SnapshotResponse`, logic thống kê,
  kiểm tra độ đầy đủ và bộ gửi Telegram hiện có.

## Không nằm trong phạm vi

- Cập nhật realtime từng giây, SSE hoặc một backend luôn chạy.
- Cam kết job chạy đúng tuyệt đối đến từng phút; lịch GitHub Actions là best
  effort và đôi khi có thể bị trễ.
- Backend API có chức năng ghi hoặc endpoint quản trị từ trình duyệt.
- Duy trì hai nút quản trị và ô nhập khóa trên dashboard.
- Dữ liệu lâu hơn 90 ngày hoặc truy vấn tùy ý một ngày chưa có trong snapshot.
- SLA, tải lớn, sản phẩm thương mại nhiều người dùng hoặc hạ tầng có hỗ trợ trả
  phí.
- Đưa Zalo hoặc trạng thái refresh-token của nhà cung cấp khác vào nhánh công
  khai. Thiết kế production GitHub-only này bảo đảm Telegram; kênh khác cần kho
  trạng thái bí mật riêng nếu được bổ sung sau.

## Điều tuyệt đối tránh

- Không ghi secret vào nhánh `develop`, `gh-pages`, artifact, cache, bundle Vite
  hoặc log Actions.
- Không cào nguồn dữ liệu mỗi khi người dùng mở dashboard.
- Không thay thế snapshot đang hoạt động bằng dữ liệu sinh dở, rỗng hoặc không
  qua kiểm tra hợp đồng.
- Không để hai workflow cùng ghi `gh-pages` và làm mất dữ liệu của nhau.
- Không gửi lặp Telegram chỉ vì workflow retry hoặc job buổi sáng chạy nhiều
  lần.
- Không bắt người dùng chạy máy local để website, đồng bộ dữ liệu hoặc Telegram
  hoạt động.

## Ràng buộc và quyết định đã xác nhận

- Repository production là repository GitHub hiện tại và nhánh mã chính cho quy
  trình này là `develop`.
- GitHub Pages của repository công khai và standard GitHub-hosted runners của
  Actions được dùng trong phần miễn phí; nếu repository chuyển sang private hoặc
  điều khoản GitHub thay đổi thì phải đánh giá lại.
- `develop` hiện là default branch. Đây cũng là điều kiện để scheduled workflows
  chạy theo quy tắc của GitHub.
- Website có URL dạng
  `https://<owner>.github.io/app-weather-forecast/`, nên frontend phải hoạt động
  đúng với base path `/app-weather-forecast/` thay vì giả định chạy ở `/`.
- Múi giờ nghiệp vụ là `Asia/Ho_Chi_Minh`.
- Khoảng lịch sử tối đa là 90 ngày. Dữ liệu hôm qua và ngày cũ đã xuất bản được
  đọc ngay từ file tĩnh; chỉ ngày đang quay chịu độ trễ 10–15 phút đã được chấp
  nhận.
- Telegram có thể gửi vào bất kỳ thời điểm hợp lý nào trong buổi sáng. Workflow
  thử định kỳ từ khoảng 09:07 đến 12:07 và dừng có hiệu lực sau khi sự kiện đó đã
  được ghi nhận thành công.
- Khi snapshot mới nhất cũ hơn ngày hiện tại, job Telegram dùng snapshot hợp lệ
  mới nhất thay vì chờ dữ liệu hôm nay. Một kỳ dữ liệu đã gửi thành công cho một
  người nhận sẽ không tự gửi lại vào sáng khác nếu chưa xuất hiện kỳ dữ liệu mới.
- Gửi thủ công luôn tạo một báo cáo mới từ snapshot mới nhất và có thể tạo thêm
  tin nhắn; giao diện GitHub Actions phải ghi rõ điều này.
- Delivery Telegram dùng best-effort at-least-once. Một lỗi đúng vào khoảng giữa
  lúc Telegram nhận tin và lúc ledger được commit có thể hiếm khi tạo tin trùng;
  ưu tiên retry thay vì âm thầm mất tin.
- GitHub Actions và Pages có thể trễ. Website phải giữ snapshot hợp lệ cuối cùng
  và hiển thị `current`, `delayed` hoặc `stale`; không hiển thị giả là realtime.
- Freshness dùng đúng các ngưỡng đã thống nhất: trong 17:45–19:00, `current` khi
  tuổi dữ liệu không quá 10 phút, `delayed` khi trên 10 đến 20 phút và `stale`
  khi trên 20 phút; ngoài cửa sổ đó, các ngưỡng tương ứng là không quá 26 giờ,
  trên 26 đến 48 giờ và trên 48 giờ. Một refresh lỗi hạ kết quả đang `current`
  xuống `delayed`, còn ngưỡng tuổi dữ liệu vẫn quyết định `stale`.

## Các phương án đã cân nhắc

### 1. GitHub Pages custom Actions và dữ liệu trên `gh-pages` — đã chọn

`gh-pages` chứa bundle website, dữ liệu JSON đang hoạt động và ledger. Actions
đọc lịch sử đã phát hành, chạy pipeline Python, kiểm tra kết quả rồi commit phiên
bản mới vào cùng nhánh. Một custom Pages deployment đóng gói phần website/dữ
liệu bằng các Actions chính thức; Telegram đọc đúng dữ liệu đó và lưu ledger
chống trùng đã ẩn danh trên nhánh.

Đây là phương án phù hợp nhất vì chỉ có một nền tảng, không cần dịch vụ ngoài,
giữ pipeline hiện tại và tạo đường vận hành thủ công ngay trong Actions. Custom
workflow được chọn thay cho Pages build trực tiếp từ branch vì nhịp 5 phút có
thể tạo 12 bản/giờ, vượt soft limit 10 build/giờ của cơ chế branch; GitHub nêu rõ
giới hạn này không áp dụng khi build/publish bằng custom Actions. Đánh đổi là mỗi
lần dữ liệu đổi vẫn phải chờ Pages deployment, nhánh có nhiều commit, và mọi
trạng thái lưu trên nhánh phải an toàn khi công khai.

### 2. GitHub Pages với một nhánh dữ liệu riêng qua `raw.githubusercontent.com`

Phương án này tách deploy website khỏi cập nhật dữ liệu, nhưng cache của raw URL
khó kiểm soát hơn, CORS/base URL phức tạp hơn và vẫn phải xử lý đồng bộ hai nhánh.
Nó không giảm đáng kể lượng code so với phương án 1 nên bị loại.

### 3. Commit snapshot vào `develop` hoặc thư mục `docs/`

Đây là cách ít cấu hình nhất, nhưng dữ liệu thay đổi liên tục sẽ làm nhiễu lịch
sử mã nguồn, kích hoạt CI/deploy vòng lặp và tăng rủi ro xung đột với phát triển
ứng dụng. Phương án này bị loại.

## Kiến trúc đích

```text
GitHub Actions: data sync (schedule / Run workflow)
        |
        | Python fetch + parse + statistics + validate
        v
nhánh gh-pages: data versions + manifest + static React bundle
        |                                  |
        | custom Pages artifact            v
        +--------------------------> GitHub Pages dashboard
        |
        v
GitHub Actions: Telegram (schedule / Run workflow)
        |
        | Telegram token và chat IDs chỉ lấy từ Actions Secrets
        v
Telegram Bot API
```

Không có request production nào gọi FastAPI, Cloudflare Worker hoặc Vercel.
Trình duyệt chỉ tải các file JSON đã được kiểm tra và phát hành.

## Mô hình nhánh và bố cục dữ liệu

Nhánh `develop` tiếp tục chứa mã nguồn, test và workflow. Nhánh `gh-pages` là
nhánh trạng thái/xuất bản do Actions quản lý, có cấu trúc logic:

```text
/
  site/
    index.html
    assets/...
    404.html
    .nojekyll
    data/
      manifest.json
      status.json
      versions/<version>/history.json
      versions/<version>/snapshot-30.json
      versions/<version>/snapshot-60.json
      versions/<version>/snapshot-90.json
  state/
    telegram-ledger.json
```

Mọi nội dung của `gh-pages` được coi là công khai dù `state/` không được đóng gói
vào Pages artifact. `history.json` chỉ chứa kết quả xổ số đã chuẩn hóa.
`telegram-ledger.json` chỉ chứa event key, thời gian và định danh người nhận đã
HMAC-SHA256 bằng một secret riêng; không lưu `chat_id`, bot token, tên người nhận
hoặc provider token. Ledger giữ tối đa 120 ngày.

`site/data/status.json` chỉ chứa trạng thái job dữ liệu đã làm sạch. Nó được cập
nhật cả khi sync thất bại để frontend có thể hạ một kết quả còn mới từ `current`
xuống `delayed`, trong khi `manifest.json` và các snapshot active vẫn giữ nguyên.

Publication tiếp tục theo nguyên tắc manifest-last:

1. Job tải manifest và history đang hoạt động từ checkout
   `gh-pages/site/data`.
2. Job sinh một version mới trong thư mục tạm, kiểm tra schema, đủ ba range và
   bảo đảm có ít nhất một bản ghi hợp lệ.
3. Job chép toàn bộ version mới vào
   `site/data/versions/<version>/`.
4. Job thay `site/data/manifest.json` sau cùng bằng thao tác atomic trên
   filesystem.
5. Job commit và push một lần. Nếu bất kỳ bước nào lỗi, nhánh vẫn giữ manifest
   cũ.
6. Sau khi commit thành công, chỉ giữ ba version gần nhất. Manifest giữ con trỏ
   version trước để frontend có thể fallback nếu CDN tạm thời thấy file lệch
   thời điểm.

Các file snapshot ổn định không được ghi đè từng phần. Lịch sử Git của nhánh là
lớp rollback bổ sung; không force-push trong vận hành bình thường.

## Các workflow GitHub Actions

### 1. CI

Workflow CI hiện có tiếp tục chạy Python, frontend lint/test/build và kiểm tra
workflow. Code chỉ được phát hành khi các kiểm tra liên quan thành công.

### 2. Phát hành website

Khi `develop` có commit đã qua CI, workflow build frontend bằng Node 20, đặt Vite
base path đúng repository, checkout `gh-pages`, thay bundle trong `site/` nhưng
giữ nguyên `site/data/` và `state/`, rồi commit/push. `404.html` là bản sao phù
hợp của entry SPA và `.nojekyll` được tạo rõ ràng.

Pages Settings dùng **Source: GitHub Actions**, không dùng “Deploy from a
branch”. Sau mỗi thay đổi site hoặc data, chính workflow tạo Pages artifact từ
`gh-pages/site/` bằng `actions/upload-pages-artifact` và triển khai bằng
`actions/deploy-pages`. Không dựa vào commit do `GITHUB_TOKEN` tự kích hoạt một
Pages build khác. Job deploy có `pages: write`, `id-token: write` và environment
`github-pages`; job build/ghi nhánh không nhận hai quyền này.

### 3. Đồng bộ dữ liệu

- Full sync mỗi ngày ở phút thấp tải để hòa giải tối đa 90 ngày.
- Incremental sync chạy khoảng mỗi năm phút trong cửa sổ quay hiện tại; tổng độ
  trễ nhìn thấy có thể là 10–15 phút vì queue và Pages propagation.
- `workflow_dispatch` có lựa chọn `full` hoặc `incremental`, thay cho nút “Làm
  mới dữ liệu” trên dashboard.
- Job đọc history từ `gh-pages`, tái sử dụng `run_data_job` và
  `SnapshotPublisher` qua một `FilesystemJsonStore`, rồi phát hành version mới.
- Nếu nguồn lỗi, schema sai hoặc current draw không hợp lệ, job thất bại và
  snapshot cũ vẫn phục vụ bình thường; job vẫn phát hành `status.json` an toàn
  với `status=failed` nhưng không thay active manifest.
- Sau khi commit data thành công, cùng workflow upload `gh-pages/site/` và chạy
  custom Pages deployment; nếu deployment lỗi, nhánh vẫn giữ version mới và lần
  chạy tiếp theo có thể phát hành lại.

### 4. Telegram

- Job tự động thử từ khoảng 09:07 đến 12:07 `Asia/Ho_Chi_Minh` theo lịch hiện có.
- Job tải manifest và snapshot 90 ngày mới nhất từ checkout `gh-pages`; không
  chờ một đồng bộ mới trong cùng lần chạy.
- Việc đánh giá dùng kỳ hoàn chỉnh mới nhất, kể cả khi kỳ đó cũ hơn hôm qua, và
  nội dung tin luôn ghi rõ ngày dữ liệu. Quy tắc cần đủ dữ liệu cho thống kê
  vắng 19–25 ngày vẫn được giữ; không biến trang bị thiếu thành cảnh báo sai.
- Scheduled job dùng event key theo kỳ dữ liệu và ledger theo từng target. Nếu
  kỳ/target đã gửi thành công, lần thử sau là no-op. Target lỗi được retry ở lần
  sau trong cửa sổ buổi sáng.
- `workflow_dispatch` có mode `scheduled` và `manual`; mode `manual` thay nút
  “Gửi Telegram ngay”, bỏ qua cổng thời gian nhưng vẫn kiểm tra độ đầy đủ.
- Manual mode dùng namespace request riêng và không đánh dấu event scheduled là
  đã gửi. Vì vậy một lần gửi thủ công trước giờ tự động không làm mất bản tin tự
  động; giao diện Actions phải cảnh báo rõ rằng người nhận có thể nhận thêm một
  tin cho cùng kỳ dữ liệu.
- `NOTIFICATION_DRY_RUN` mặc định `true` cho đến khi smoke test production thành
  công; sau đó người dùng đặt repository variable thành `false`.

### Điều phối ghi nhánh

Mọi workflow ghi `gh-pages` dùng cùng một concurrency group ở cấp repository,
`cancel-in-progress: false`. Trước khi push, workflow fetch lại remote và chỉ
push fast-forward; nếu remote đổi ngoài dự kiến thì job reload, áp dụng lại thay
đổi tối đa một số lần hữu hạn rồi thất bại an toàn. Điều này ngăn deploy frontend,
data sync và Telegram ledger ghi đè lẫn nhau. Các Pages deployment dùng một
concurrency group riêng để bản mới hơn được ưu tiên và không có hai deployment
cùng thay production environment.

## Thay đổi frontend

- `fetchSnapshot(days)` đọc URL tương đối được tạo từ `import.meta.env.BASE_URL`,
  manifest và file snapshot versioned thay vì `/api/gdb`.
- Mỗi lần poll manifest thêm cache-buster có giới hạn theo chu kỳ; snapshot
  versioned được cache dài vì bất biến.
- Kiểm tra cấu trúc `SnapshotResponse` hiện có được giữ. Khi active version chưa
  tải được, client thử version trước từ manifest rồi mới báo lỗi.
- Trạng thái freshness hiện do client tính từ `generatedAt`, thời gian hiện tại
  và cửa sổ quay, với cùng ngưỡng đã phê duyệt trước đây. Không dùng đồng hồ
  client để thay đổi dữ liệu, chỉ để gắn nhãn độ mới.
- Xóa `AdminOperations`, ô nhập khóa, hai hook thao tác cloud và các kiểu API chỉ
  dùng cho operation. Dashboard có thể hiển thị một liên kết nhỏ “Quản trị qua
  GitHub Actions” tới trang workflow, nhưng không chứa credential hoặc thao tác
  ghi trực tiếp.
- Polling tiếp tục theo nhịp nhanh trong cửa sổ quay và chậm ngoài cửa sổ; tải
  file tĩnh thất bại tạm thời không xóa dữ liệu đang có trong React Query cache.

## Thay đổi Python và lưu trữ

- Thêm `FilesystemJsonStore` triển khai `JsonStore`, ánh xạ các logical key hiện
  có sang file JSON bên trong thư mục publication checkout.
- Giữ `SnapshotPublisher`, nhưng bổ sung mapping tên file và thao tác thay
  manifest an toàn cho filesystem. Không đưa lệnh Git vào lớp domain.
- CLI chuẩn bị một thư mục staging, chạy job, xác minh output và trả exit code;
  workflow riêng chịu trách nhiệm commit/push.
- Telegram state store dùng target key HMAC thay vì identifier có thể đoán. Secret
  `NOTIFICATION_LEDGER_HMAC_KEY` chỉ tồn tại trong Actions.
- Điều chỉnh đánh giá scheduled để “dữ liệu mới nhất” không bị loại chỉ vì kỳ
  hoàn chỉnh đã cũ, nhưng vẫn dùng event key theo kỳ nên không spam lại cùng dữ
  liệu mỗi sáng.
- Adapter Cloudflare KV và Worker có thể được giữ tạm trong một commit chuyển
  tiếp để giảm rủi ro rollback, nhưng không còn nằm trên production path; sau
  smoke test GitHub Pages sẽ xóa cấu hình deploy và tài liệu vận hành Cloudflare/
  Vercel. Xóa hẳn code legacy chỉ khi test tương đương đã chuyển xong.

## Secrets, permissions và bảo mật

Các secret production cần thiết:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`
- `NOTIFICATION_LEDGER_HMAC_KEY` — chuỗi ngẫu nhiên dài, độc lập bot token

Repository variable:

- `NOTIFICATION_DRY_RUN=true|false`

Workflow thông thường có `contents: read`. Chỉ step/job xuất bản dùng
`contents: write`; Telegram không được cấp write nếu không cần cập nhật ledger,
và job cập nhật ledger chỉ ghi qua checkout đã giới hạn đường dẫn. Không dùng
secret trong pull request từ fork. Dependency Actions được pin tối thiểu theo
major đã kiểm soát, và log không in environment chứa secret.

Vì `gh-pages` công khai, test bảo mật phải quét output và khẳng định không chứa
giá trị `TELEGRAM_CHAT_IDS`, bot token, recipient display hoặc config provider.

## Xử lý lỗi và rollback

- **Nguồn dữ liệu lỗi:** giữ nguyên manifest active; workflow đỏ và dashboard
  chuyển `delayed/stale` theo tuổi dữ liệu.
- **Pages/CDN chưa đồng bộ:** frontend fallback về previous version trong
  manifest hoặc dữ liệu React Query đang cache.
- **Telegram lỗi một target:** ghi thành công từng target; retry chỉ target còn
  thiếu.
- **Commit ledger lỗi sau khi Telegram nhận:** job thất bại để retry; chấp nhận
  xác suất rất nhỏ tin trùng theo quyết định at-least-once.
- **Xung đột nhánh:** fetch/reapply hữu hạn; không force-push và không bỏ snapshot
  cũ.
- **Bundle frontend lỗi:** không thay website đang hoạt động.
- **Rollback ứng dụng:** revert commit `develop` và chạy lại workflow phát hành.
- **Rollback dữ liệu:** trỏ manifest về một trong ba version còn giữ hoặc revert
  commit `gh-pages` gần nhất qua workflow bảo trì.

## Chuyển đổi production

1. Viết test cho filesystem store, publication branch, frontend static client,
   Telegram latest-data behavior và HMAC ledger.
2. Triển khai store/CLI và workflow ghi `gh-pages` trong dry-run hoặc nhánh test.
3. Chạy full sync bằng Actions và kiểm tra ba snapshot cùng manifest.
4. Build dashboard với base path GitHub Pages, chọn **Source: GitHub Actions**
   trong Pages Settings, kiểm tra 30/60/90 ngày và refresh trực tiếp route.
5. Cấu hình ba secret, giữ `NOTIFICATION_DRY_RUN=true`, chạy cả scheduled/manual
   Telegram và kiểm tra log không lộ dữ liệu nhạy cảm.
6. Đặt `NOTIFICATION_DRY_RUN=false`, gửi một tin manual được kiểm soát, sau đó
   chạy lại để xác minh scheduled ledger chống trùng.
7. Bỏ hai nút dashboard và ngắt production path Vercel/Cloudflare.
8. Theo dõi ít nhất một full sync, một cửa sổ quay incremental và một buổi sáng
   Telegram trước khi xóa cấu hình legacy.

Những bước cần đăng nhập GitHub — bật Pages, nhập Secrets/Variables và có thể xác
nhận môi trường deployment — cần người dùng thực hiện trên giao diện tài khoản;
không gửi giá trị secret qua chat hoặc commit.

## Tiêu chí nghiệm thu

- Custom Pages workflow triển khai được hơn 10 lần trong một giờ thử nghiệm có
  kiểm soát mà không phụ thuộc branch-build soft limit; URL tải được dashboard
  và refresh route trực tiếp không 404.
- Cả ba lựa chọn 30/60/90 trả đúng hợp đồng và dữ liệu ngày cũ mở ngay.
- Incremental sync phát hành dữ liệu ngày đang quay trong độ trễ đã chấp nhận và
  không phá snapshot cũ khi nguồn lỗi.
- Full sync có thể bootstrap từ nhánh chưa có dữ liệu.
- “Run workflow” thực hiện được full/incremental refresh và manual Telegram mà
  không cần máy local.
- Scheduled Telegram dùng snapshot hợp lệ mới nhất, ghi rõ kỳ dữ liệu, gửi từng
  target đúng một lần cho mỗi kỳ trong vận hành bình thường và retry target lỗi.
- Không secret hoặc raw `chat_id` nào xuất hiện trong bundle, nhánh, artifact hay
  log.
- Các workflow ghi `gh-pages` không làm mất `data/`, `state/` hoặc bundle của
  workflow khác.
- Python tests, frontend tests/lint/build và actionlint đều đạt trên Node 20 và
  Python 3.12.
- Tài liệu triển khai mô tả đầy đủ cách bật Pages, đặt secrets, chạy bootstrap,
  gửi test, xem log, rollback và cảnh báo lịch Actions có thể trễ.

## Các quyết định để người triển khai tự xử lý

- Tên class/file cụ thể của filesystem store và helper branch publication, miễn
  giữ ranh giới domain/CLI/workflow nêu trên.
- Thư viện hoặc shell helper dùng để copy bundle, với điều kiện không làm mất
  `data/` và `state/`.
- Cách trình bày liên kết GitHub Actions trên dashboard sao cho nhỏ gọn và không
  giống một nút thao tác trực tiếp.
- Số lần retry hữu hạn cho push conflict và Telegram network retry, theo timeout
  workflow hiện có.

## Tài liệu nền tảng

- [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Using custom workflows with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Configuring a Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [GitHub Actions billing and usage](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [Events that trigger workflows](https://docs.github.com/en/actions/reference/events-that-trigger-workflows)
- [Managing scheduled workflow state](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)

