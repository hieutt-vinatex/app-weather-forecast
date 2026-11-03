# Dashboard thống kê XSMB

Ứng dụng thu thập kết quả ĐB, G1–G7, dựng thống kê hai số cuối cho 30/60/90 ngày
và gửi báo cáo số chưa xuất hiện qua Telegram.

> Dữ liệu chỉ phục vụ thống kê và tham khảo, không phải dự đoán kết quả và không
> khuyến khích đặt cược.

## Production: một nền tảng GitHub, chi phí 0

Production không cần máy cá nhân hay server chạy liên tục:

```text
GitHub Actions ──đồng bộ──> nhánh gh-pages/site/data
       │                         │
       ├──gửi Telegram           └──GitHub Pages ──> Dashboard
       └──lưu ledger HMAC──> nhánh gh-pages/state
```

- GitHub Pages phục vụ bundle React và snapshot tĩnh theo version.
- GitHub Actions cập nhật một lần lúc 18:45, tự thử lại mỗi giờ đến 23:45 nếu
  thất bại, rồi gửi báo cáo Telegram từ 09:00 sáng hôm sau.
- Dashboard chỉ tải file tĩnh; token bot và chat ID không đi vào bundle hay
  Pages artifact.
- Hai thao tác thủ công **Làm mới dữ liệu** và **Gửi Telegram ngay** mở workflow
  tương ứng trong tab Actions.

URL production dự kiến:
<https://hieutt-vinatex.github.io/app-weather-forecast/>.

Hướng dẫn triển khai đầy đủ: [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md).

## Hành vi dữ liệu

- Dữ liệu hôm qua và các ngày trước hiển thị ngay từ snapshot gần nhất; người
  dùng không cần chờ dữ liệu của ngày đang quay.
- Kết quả ngày hiện tại được xuất bản sau lượt 18:45 thành công. Nếu nguồn lỗi,
  snapshot trước vẫn xem được trong khi các lượt 19:45–23:45 tự phục hồi.
- Dashboard tự đọc manifest mới theo chu kỳ 30 giây khi tab đang hoạt động và
  chậm hơn khi tab ở nền.
- Khi đồng bộ lỗi, manifest đang hoạt động không đổi; lịch sử hợp lệ gần nhất vẫn
  được giữ và trạng thái chuyển sang chậm cập nhật.
- Có thể chọn lại phạm vi 30/60/90 ngày bất kỳ lúc nào.
- Báo cáo Telegram liệt kê toàn bộ số chưa xuất hiện `>=20 ngày`. Nếu cập nhật
  tối thất bại, báo cáo sáng vẫn dùng snapshot cũ, ghi rõ **DỮ LIỆU CŨ**; kể cả
  khi không có số đạt ngưỡng vẫn gửi xác nhận “Không có số nào đạt ngưỡng”.

## Thành phần chính

```text
.github/workflows/       CI, Pages deploy, data sync và Telegram
app/cloud/               job dữ liệu, publication và notification state
frontend/                React + TypeScript + Vite dashboard
scripts/cloud_job.py     entrypoint job hữu hạn cho GitHub Actions
scripts/prepare_pages.py ghép bundle với dữ liệu xuất bản
tests/                   kiểm thử Python và hợp đồng workflow/tài liệu
```

## Kiểm tra trước khi phát hành

```bash
python -m pytest -q

cd frontend
npm test
npm run lint
npm run build
```

CI chạy Python 3.12, Node 20 và kiểm tra syntax của mọi workflow.

## Telegram

Thiết lập BotFather, group, ba repository secrets, dry-run và lịch gửi tại
[docs/TELEGRAM_GROUP.md](docs/TELEGRAM_GROUP.md). Ledger chỉ lưu định danh target
đã HMAC; không lưu chat ID thô hoặc token.

## Phát triển local

FastAPI local là tùy chọn để đối chiếu logic backend cũ; production không gọi
FastAPI. Việc deploy, đồng bộ dữ liệu và gửi Telegram đều thực hiện trong GitHub
sau khi cấu hình ban đầu. Xem [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Tài liệu

- [Triển khai GitHub-only](docs/CLOUD_DEPLOYMENT.md)
- [Telegram Group](docs/TELEGRAM_GROUP.md)
- [Cài đặt và kiểm thử local tùy chọn](docs/INSTALLATION.md)
- [Thiết kế đã duyệt](docs/superpowers/specs/2026-11-02-github-only-free-deployment-design.md)
