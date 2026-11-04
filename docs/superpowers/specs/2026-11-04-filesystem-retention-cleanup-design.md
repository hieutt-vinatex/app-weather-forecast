# Thiết kế sửa lỗi retention trên GitHub Pages

**Ngày:** 2026-11-04

## Ý định

Khôi phục việc xuất bản snapshot thứ tư trở đi để dữ liệu mới, gồm ngày
03/11/2026, có thể được kiểm tra và đẩy lên `gh-pages`. Giới hạn an toàn ba
phiên bản vẫn được giữ nguyên.

## Nguyên nhân gốc

`SnapshotPublisher` xóa bốn file JSON của phiên bản cũ nhưng
`FilesystemJsonStore.delete()` không xóa thư mục phiên bản sau khi nó rỗng.
Trình xác minh đếm thư mục nên thấy bốn phiên bản và chặn xuất bản. Lỗi chỉ lộ
ra khi tạo snapshot thứ tư; test hiện tại chỉ đếm storage key nên bỏ sót thư
mục rỗng.

## Phương án

### 1. Dọn thư mục phiên bản rỗng trong filesystem store — đã chọn

Sau khi xóa một key versioned, thử xóa đúng thư mục cha bằng `rmdir()`. Lệnh
chỉ thành công khi thư mục rỗng, vì vậy không xóa file lạ và không ảnh hưởng
các thư mục ngoài `site/data/versions/<version>`.

### 2. Bỏ qua thư mục rỗng trong verifier — không chọn

Có thể cho deploy đi tiếp nhưng để lại artifact rác trong publication workspace
và che giấu việc cleanup chưa hoàn tất.

### 3. Dọn bằng shell trong workflow — không chọn

Làm logic retention phụ thuộc GitHub Actions thay vì storage abstraction và
không bảo vệ các caller khác của filesystem store.

## Phạm vi và kiểm thử

- Thêm regression test xuất bản bốn lần và yêu cầu chỉ còn đúng ba thư mục
  phiên bản, mỗi thư mục chứa đủ bốn payload.
- Sửa tối thiểu `FilesystemJsonStore.delete()`; thao tác với key không tồn tại
  tiếp tục idempotent.
- Không thay đổi cron, parser, schema, giới hạn retention hoặc dữ liệu Telegram.
- Chạy toàn bộ backend, frontend, actionlint; push thẳng `develop` và quan sát
  CI/Pages. Chu kỳ dữ liệu thực chỉ được xác nhận khi full/scheduled sync mới
  thành công và manifest production chứa bản ghi 03/11 hoàn chỉnh.
