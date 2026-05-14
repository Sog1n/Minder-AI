# Tài liệu Yêu cầu Nghiệp vụ (BRD) - Hệ thống Tích hợp Tri thức Minder AI

## 1. Tổng quan Dự án (Executive Summary)
Minder AI đang phát triển một trợ lý AI giao tiếp bằng giọng nói (voice-first) đóng vai trò như một "đồng nghiệp kỳ cựu" dành cho công nhân nhà máy. Trợ lý này cần nắm vững cả các quy trình trên giấy tờ (SOP) lẫn những "kiến thức truyền miệng" (tribal wisdom) mà công nhân đúc kết được qua nhiều năm làm việc trên sàn nhà máy.

## 2. Mục tiêu Dự án (Project Objectives)
* Thiết kế một hệ thống tự động học hỏi từ các cuộc hội thoại hàng ngày của công nhân nhằm thu thập, xác minh và tích hợp những kiến thức không có trong văn bản vào một cơ sở dữ liệu chung.
* Cung cấp lại nguồn tri thức này cho toàn bộ công nhân để hỗ trợ họ trong các cuộc hội thoại tiếp theo.
* Xây dựng một lợi thế cạnh tranh (moat) thực sự cho sản phẩm, vượt ra khỏi giới hạn của một ứng dụng "wrapper" LLM thông thường.

## 3. Các Thách thức Thực tế & Ràng buộc Hệ thống (The Real Problems to Solve)
Đây là 5 vấn đề cốt lõi mà bất kỳ quyết định thiết kế kiến trúc nào cũng phải giải quyết triệt để nhằm đảm bảo hệ thống có thể hoạt động hiệu quả trong môi trường thực tế.

* **3.1. Phân biệt Sự thật và Nhiễu (Fact vs. Noise):** Phân nửa các cuộc hội thoại là nhiễu (noise). Làm sao để biết một "sự thật" được trích xuất là thực sự đúng, khi một công nhân có thể đang bị sai, đang nói đùa, đang than vãn, hoặc đang cố tình "thử" (testing) AI? Yêu cầu hệ thống phải có một cơ chế (verification logic) để đánh giá bối cảnh và độ tin cậy của thông tin đầu vào trước khi quyết định ghi nhận nó thành tri thức.
* **3.2. Giải quyết Mâu thuẫn (Contradiction Reconciliation):** Làm thế nào để đối soát và giải quyết các thông tin mâu thuẫn? Ví dụ: Công nhân A nói máy sấy chạy ở 80°C, công nhân B nói 75°C, trong khi tài liệu SOP ghi 78°C thì ai sẽ là người chiến thắng (who wins)? Yêu cầu hệ thống phải xây dựng chiến lược phân giải xung đột rõ ràng và logic đối chiếu khi có sự khác biệt.
* **3.3. Ngăn ngừa Tự "đầu độc" Dữ liệu (System Poisoning Prevention):** Làm sao để tránh việc hệ thống tự "đầu độc" chính nó? Nếu AI học sai từ một lần sửa đổi, nó sẽ lặp lại câu trả lời sai đó một cách tự tin với công nhân tiếp theo, người này có thể lại sửa tiếp, tạo ra một vòng lặp "nhiễu nuôi nhiễu" (noise feeding noise). Yêu cầu thiết lập các trạng thái của thông tin (chờ duyệt, đã xác minh, bị cách ly) để kiểm soát sự lây lan của thông tin sai lệch.
* **3.4. Ràng buộc Vận hành Thực tế (Production Constraints):** Làm sao để hệ thống chạy được trong môi trường thực tế (production)? Độ trễ (latency budget) cho quá trình truy xuất dữ liệu (retrieval) phải dưới 1 giây (sub-second). Chi phí vận hành cho mỗi cuộc hội thoại không được vượt quá vài xu (pennies). Hệ thống phải phục vụ quy mô nhà máy có 50 công nhân thực hiện 200 cuộc hội thoại mỗi ngày.
* **3.5. Chứng minh Năng lực Học hỏi (Proving the Learning Process):** Việc đánh giá "AI đã tốt lên" không thể chỉ dựa vào cảm giác (vibe). Làm sao để chứng minh hệ thống đang thực sự học hỏi? Cần thiết lập một tín hiệu có thể đo lường được (measurable signal) để lượng hóa sự cải thiện của AI qua các cuộc hội thoại tiếp theo.

## 4. Yêu cầu Chức năng (Functional Requirements)

### 4.1. Thu nhận Kiến thức (Knowledge Acquisition)
* Hệ thống phải có khả năng biến đổi dữ liệu hội thoại thô thành các tri thức có cấu trúc và có khả năng truy xuất.
* Phải định nghĩa rõ ràng mô hình dữ liệu (Data Model) sẽ sử dụng (ví dụ: semantic parsing, knowledge graph, vector store, hoặc mô hình lai).
* Cách thức biểu diễn và lưu trữ dữ liệu phải hỗ trợ trực tiếp cho quá trình giải quyết mâu thuẫn và đối chiếu thông tin sau này, không chỉ đơn thuần phục vụ tìm kiếm.

### 4.2. Tính Nhất quán và Tích hợp (Consistency and Integration)
* Cần có logic xác minh (verification logic) để phân biệt thông tin hữu ích với những lời nói đùa, than vãn hoặc nhiễu dữ liệu.
* Thiết lập chiến lược giải quyết xung đột khi thông tin mới mâu thuẫn với thông tin cũ hoặc tài liệu chuẩn.
* Xây dựng bộ quy tắc rõ ràng để phân loại thông tin:
  * Thông tin nào được tự động chấp nhận (accepted).
  * Thông tin nào bị cách ly để theo dõi thêm (quarantined).
  * Thông tin nào cần báo cáo lên cấp quản lý để con người phân xử (escalated to a human).

### 4.3. Vòng lặp Phản hồi (Feedback Loop)
* Đảm bảo kiến thức sau khi được tích hợp sẽ được triển khai vào trợ lý AI để sử dụng.
* Phải cung cấp các chỉ số đo lường (measurable signals) cụ thể để đánh giá và chứng minh được sự cải thiện của hệ thống qua các cuộc hội thoại tiếp theo.

## 5. Yêu cầu Phi chức năng (Non-Functional Requirements)

| Tiêu chí | Yêu cầu Chi tiết |
| :--- | :--- |
| **Độ trễ (Latency)** | Thời gian phản hồi và truy xuất dữ liệu phải dưới 1 giây (sub-second). |
| **Chi phí Vận hành (Cost)** | Chi phí xử lý cho mỗi cuộc hội thoại không được vượt quá vài xu (pennies). |
| **Khả năng Chịu tải (Scalability)** | Hệ thống phải xử lý mượt mà cường độ 200 cuộc hội thoại mỗi ngày từ 50 công nhân. |

## 6. Phạm vi Ngoài dự án (Out of Scope)
* Việc thu thập, đọc hiểu các kiến thức đã được văn bản hóa (SOP, sổ tay đào tạo, quy trình chuẩn) đã được giải quyết và không nằm trong phạm vi bài kiểm tra này.
* Hệ thống mặc định đã có sẵn module chuyển giọng nói thành văn bản, do đó bạn chỉ cần tập trung xử lý dữ liệu đầu vào là các đoạn văn bản hội thoại (transcript), không cần thiết kế bộ xử lý tín hiệu âm thanh.