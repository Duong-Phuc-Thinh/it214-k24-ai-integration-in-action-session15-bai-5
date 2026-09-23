# BÀI TẬP 5: XỬ LÝ LỖI VỚI GIAO DỊCH BÙ & SEMANTIC LOCK

## 1. Giới thiệu bài tập
Ứng dụng này triển khai mô hình **Saga Orchestrator** tích hợp **Semantic Lock** và **Compensating Transaction** trong quy trình đặt bàn ăn trực tuyến:
- **Semantic Lock**: Tránh tình trạng tranh chấp tài nguyên (dirty read/write) bằng cách giữ bàn ở trạng thái trung gian `RESERVED` trước khi giao dịch thanh toán kết thúc.
- **Compensating Transaction (Giao dịch bù trừ)**: Khi có lỗi phát sinh ở bước sau (Xác nhận đặt bàn thất bại), hệ thống sẽ kích hoạt tiến trình đảo ngược nghiệp vụ một cách an toàn (Hoàn tiền - tạo bản ghi `REFUND` thay vì xóa dòng dữ liệu cũ, đồng thời giải phóng lock).

## 2. Giải thích cơ chế kỹ thuật

### Semantic Lock là gì và tại sao cần?
Trong mô hình microservices, quy trình đặt chỗ và thanh toán thường mất một khoảng thời gian chờ đợi. Nếu chúng ta chuyển ngay từ `AVAILABLE` sang `BOOKED`, trải nghiệm người dùng sẽ bị ảnh hưởng nếu thanh toán thất bại. Ngược lại, nếu không khóa bàn, nhiều khách hàng sẽ cùng thanh toán cho một bàn ăn dẫn đến xung đột (Double Booking).
Trạng thái trung gian `RESERVED` đóng vai trò là một **Semantic Lock** (khóa ngữ nghĩa) để thông báo cho người dùng khác biết bàn đang tạm thời được giữ và có thời gian hết hạn (timeout), giúp bảo đảm tính nhất quán của hệ thống.

### Tại sao cần Compensating Transaction thay vì xóa dữ liệu?
Trong kế toán và kiểm toán, mọi biến động dòng tiền phải được ghi nhận rõ ràng (Audit Trail). Khi giao dịch thất bại và khách hàng được hoàn tiền, việc xóa bản ghi thanh toán cũ (`PAYMENT`) là một hành vi trái quy tắc an toàn tài chính. Thay vào đó, ta tạo ra một bản ghi bù trừ mới có thuộc tính loại `REFUND` mang giá trị dương tương ứng để đối soát minh bạch.

## 3. Hướng dẫn chạy chương trình
Chương trình viết bằng **Python** thuần và không yêu cầu thư viện bên ngoài.

```bash
# Chạy file main.py bằng Python 3
python main.py
```

Kết quả in ra màn hình sẽ hiển thị chính xác toàn bộ log điều phối của Orchestrator bao gồm bước Semantic Lock, xử lý lỗi và kích hoạt tiến trình bù trừ (refund + giải phóng lock).