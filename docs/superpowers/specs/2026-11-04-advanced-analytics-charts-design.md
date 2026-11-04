# Thiết kế bổ sung biểu đồ phân tích nâng cao

**Ngày:** 2026-11-04  
**Trạng thái:** Đã thống nhất phạm vi theo menu giải; các quyết định triển khai còn lại được chốt để ưu tiên hiệu năng.

## Ý định

Bảo đảm dashboard có đủ sáu dạng biểu đồ người dùng yêu cầu, giữ nguyên các biểu đồ cũ và làm cho các biểu đồ mới thay đổi đồng bộ theo menu `Tất cả giải / ĐB / G1…G7`.

## Hiện trạng

- Đã có và đang hiển thị: Frequency Bar Chart, Heatmap 00–99, Trend Line Chart.
- Gap hiện chỉ tồn tại dưới dạng timeline ngày vắng của một số trong khu vực cảnh báo, chưa phải biểu đồ so sánh khoảng cách cho 00–99 theo giải đang chọn.
- `HistoryScatterChart.tsx` đã tồn tại nhưng chỉ đọc `record.gdb` và chưa được gắn vào dashboard.
- Chưa có Transition Matrix.
- Dữ liệu 30/60/90 ngày và toàn bộ kết quả từng giải đã có trong snapshot; không cần mở rộng API.

## Mục tiêu

- Giữ nguyên mọi biểu đồ và chức năng hiện có.
- Bổ sung Gap Chart, Scatter Plot và Transition Matrix vào dashboard.
- Cả ba biểu đồ mới dùng cùng `PrizeScope` đang được chọn.
- Không thêm request mạng, không đổi hợp đồng backend và không thêm thư viện runtime.
- Khi người dùng chưa mở phân tích nâng cao, không tạo thêm ECharts canvas và không chạy phép tính mới.
- Hỗ trợ light/dark theme, màn hình nhỏ, tooltip và nhãn trợ năng như các biểu đồ hiện tại.

## Không thuộc phạm vi

- Không dự đoán kết quả tương lai hoặc diễn giải thống kê thành xác suất trúng.
- Không thay đổi Frequency Bar, Heatmap, Trend, Digit Bar, Even/Odd hoặc Absence Monitor hiện có.
- Không thêm khoảng thời gian ngoài 30/60/90 ngày.
- Không tạo ma trận 100×100 cho các cặp 00–99.

## Các phương án đã cân nhắc

### A. Tính phía frontend và chỉ mount khi mở — chọn

Tái sử dụng `records` trong snapshot, đặt ba biểu đồ trong khu vực “Phân tích nâng cao” đóng mặc định, dùng hàm thuần có `useMemo` khi mở. Phương án này không tăng payload/API, tránh ba chart instance lúc tải trang và phù hợp quy mô tối đa 90 ngày × 27 kết quả.

### B. Tính phía frontend và luôn hiển thị

Đơn giản hơn một chút nhưng tạo thêm ba canvas, phép tính và resize observer ngay khi dashboard tải. Điều này đi ngược yêu cầu không ảnh hưởng hiệu năng.

### C. Tính sẵn ở backend

Giảm một lượng tính toán rất nhỏ ở trình duyệt nhưng làm phình snapshot, hợp đồng Python/TypeScript, cache và dữ liệu phát realtime cho mọi người kể cả khi không mở biểu đồ. Chi phí hệ thống lớn hơn lợi ích ở tập dữ liệu hiện tại.

## Thiết kế giao diện

Khu vực mới nằm sau các danh sách “Xuất hiện nhiều / Ít” và trước bảng lịch sử:

```text
┌ Phân tích nâng cao · Giải đang chọn                 [Mở phân tích] ┐
└────────────────────────────────────────────────────────────────────┘

Khi mở:
┌ Khoảng cách xuất hiện 00–99 ┐ ┌ Phân tán theo kỳ                 ┐
│ Hiện tại / lớn nhất          │ │ ngày × giá trị 00–99             │
└──────────────────────────────┘ └──────────────────────────────────┘
┌ Ma trận chuyển tiếp chữ số cuối 0–9                              ┐
│ 10 hàng FROM × 10 cột TO; màu theo tỷ lệ trong từng hàng          │
└────────────────────────────────────────────────────────────────────┘
```

Nút dùng `aria-expanded` và `aria-controls`. Nội dung bị tháo khỏi DOM khi đóng để giải phóng ECharts instances qua cleanup hiện có.

## Định nghĩa dữ liệu

### Scatter Plot

- Mỗi điểm là một cặp `ngày + số đuôi 00–99` trong `resultsForScope(record, scope)`.
- Các kết quả trùng cùng ngày và cùng số được gộp thành một điểm có `count`; kích thước điểm biểu thị số lần trùng.
- Trục X là ngày, trục Y cố định 0–99. Tooltip nêu ngày, số và số lần.
- Records được sắp theo ISO date trong hàm tính để không phụ thuộc thứ tự đầu vào.

### Gap Chart

- Khoảng cách đo bằng **số kỳ hợp lệ**, không phải số ngày lịch.
- Một kỳ hợp lệ khi giải đang chọn có đủ số kết quả mong đợi theo `PRIZES`; với `all` là đủ 27 kết quả. Kỳ thiếu dữ liệu không làm tăng khoảng cách.
- Với từng số 00–99, tính `currentGap` (số kỳ hợp lệ liên tiếp chưa xuất hiện tính tới kỳ mới nhất) và `maxGap` (khoảng vắng lớn nhất trong phạm vi).
- Số chưa từng xuất hiện được đánh dấu `observed: false`; tooltip hiển thị khoảng cách dưới dạng cận dưới `≥ N kỳ`.
- Hiển thị đủ 00–99 với hai series “Hiện tại” và “Lớn nhất”, có data zoom để tránh nhãn dày trên màn hình nhỏ.

### Transition Matrix

- Dùng ma trận 10×10 chữ số cuối như hình tham chiếu, không dùng 100×100.
- Chuỗi được tạo theo ngày tăng dần; trong một kỳ, kết quả giữ thứ tự chính thức từ `resultsForScope` (`ĐB`, G1…G7 và thứ tự nguồn trong từng giải).
- Mỗi cặp kết quả kề nhau tạo một chuyển tiếp từ chữ số hàng đơn vị của số trước sang chữ số hàng đơn vị của số sau, kể cả ranh giới giữa hai kỳ có dữ liệu kế tiếp.
- Mỗi ô chứa `count` và `rowPercentage = count / tổng chuyển tiếp đi ra từ chữ số FROM`.
- Khi một hàng không có chuyển tiếp, mọi tỷ lệ là 0; không phát sinh `NaN` hoặc `Infinity`.

## Kiến trúc và hiệu năng

- `frontend/src/utils/advancedAnalytics.ts` chứa toàn bộ phép tính thuần, độc lập ECharts và có unit test.
- Mỗi chart component chỉ chuyển kết quả tính sang `EChartsOption`; `useMemo` phụ thuộc `records`, `scope`, `theme`.
- `AdvancedAnalyticsSection` sở hữu trạng thái mở/đóng và chỉ mount chart khi mở.
- Độ phức tạp tính toán tuyến tính theo số kết quả, cộng hằng số 100 ô/số; tối đa hiện tại khoảng 2.430 kết quả.
- Tiếp tục dùng Canvas, animation tắt, `lazyUpdate`, `ResizeObserver` và dispose trong `EChart.tsx`.
- Không thêm dependency và không sửa backend/snapshot.

## Kiểm thử và tiêu chí hoàn thành

- Unit tests khóa phạm vi giải, thứ tự ngày, kết quả trùng, kỳ thiếu dữ liệu, số chưa xuất hiện và dữ liệu rỗng/một phần tử.
- Component tests xác nhận khu vực đóng không mount chart, mở thì mount đúng ba chart, đổi menu giải cập nhật nội dung.
- Toàn bộ frontend tests, lint và production build phải qua.
- Production build không tạo thêm vendor dependency; ECharts chunk không tăng quá 5% so với baseline khoảng 1.012 KiB.
- Kiểm tra thủ công 30/60/90 ngày, mọi scope, light/dark và mobile; các biểu đồ cũ vẫn xuất hiện và hoạt động như trước.
