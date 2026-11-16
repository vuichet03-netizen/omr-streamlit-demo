"""Hằng số dùng chung cho toàn bộ dự án OMR.

Mọi tọa độ trong file này (và trong file cấu hình JSON) tính theo "pixel chuẩn":
trang giấy rộng PAGE_W, cao PAGE_H, gốc (0, 0) ở góc trên trái, trục y hướng xuống.
Khi vẽ phiếu để in, nhân tọa độ với SCALE cho nét sắc.
"""

# ---------------------------------------------------------------------------
# 1. Hệ tọa độ chuẩn và 4 marker nắn phiếu
# ---------------------------------------------------------------------------
PAGE_W = 800            # chiều rộng trang (pixel chuẩn)
PAGE_H = 1131           # chiều cao trang (tỉ lệ A4)
SCALE = 3               # hệ số phóng khi vẽ phiếu để in
MARKER_SIZE = 40        # cạnh ô vuông đen đặc ở 4 góc (dùng để nắn phiếu)
SMALL_MARK = 14         # cạnh ô vuông đen nhỏ trang trí (KHÔNG dùng để nắn phiếu)
# Thứ tự: trên-trái, trên-phải, dưới-phải, dưới-trái
MARKER_CENTERS = [(50, 50), (750, 50), (750, 1081), (50, 1081)]
SAFE_MARGIN = 30        # lề an toàn: mọi nội dung nằm trong [30, PAGE - 30]

CONFIG_VERSION = 2      # phiên bản định dạng file cấu hình JSON

# Kích thước giấy A4 (mm) dùng khi xuất PDF
A4_W_MM = 210.0
A4_H_MM = 297.0
MM_PER_INCH = 25.4

# ---------------------------------------------------------------------------
# 2. Giới hạn tham số người dùng
# ---------------------------------------------------------------------------
MIN_QUESTIONS = 10
MIN_CHOICES = 2
MAX_CHOICES = 5
EXAM_NAME_MAX_LEN = 80
CHOICE_LABELS_ALL = "ABCDE"     # nhãn đáp án, lấy num_choices ký tự đầu

# ---------------------------------------------------------------------------
# 3. Nét vẽ (pixel chuẩn)
# ---------------------------------------------------------------------------
LINE_W = 1.5            # đường kẻ khung
THIN_LINE_W = 1.0       # đường chia nhỏ trong hàng ô viết số
BUBBLE_LINE_W = 1.2     # viền ô tròn

# ---------------------------------------------------------------------------
# 4. Cỡ chữ (pixel chuẩn) và chuỗi chữ trên phiếu
# ---------------------------------------------------------------------------
FONT_TITLE = 22
FONT_BODY = 12
FONT_MIN = 8.5          # cỡ chữ nhỏ nhất khi tự co cho vừa chiều rộng
FONT_FIT_STEP = 0.25
FONT_BLOCK_LABEL = 13   # nhãn "7. ..." và "8. ..."
FONT_DIGIT_LABEL = 11   # nhãn chữ số 0-9
FONT_QNUM = 12          # số thứ tự câu
FONT_CHOICE_HEADER = 12 # nhãn A, B, C...
FONT_INSTRUCTION = 10   # dòng hướng dẫn tô phiếu (cỡ nhỏ, in nghiêng)
LINE_HEIGHT_RATIO = 1.25
DOT_CHAR = "."

TEXT_TITLE = "PHIẾU TRẢ LỜI TRẮC NGHIỆM"
TEXT_EXAM_LABEL = "Kỳ thi:"
TEXT_SUBJECT_LABEL = "Bài thi:"
TEXT_DATE_PART = "Ngày thi: ....../....../ ........"   # chỗ năm chỉ có dấu chấm
TEXT_DATE_GAP = "   "
TEXT_ID_LABEL = "7. Mã số sinh viên"
TEXT_CODE_LABEL = "8. Mã đề"
TEXT_CBCT_1 = "Họ tên, chữ kí CBCT 1"
TEXT_CBCT_2 = "Họ tên, chữ kí CBCT 2"
TEXT_SCORE = "Điểm"
TEXT_INFO_LINES = (
    "1. Hội đồng thi:",
    "2. Điểm thi:",
    "3. Phòng thi số:",
    "4. Lớp:",
    "5. Họ và tên thí sinh:",
)
TEXT_BIRTH_LINE = "6. Ngày sinh: ....../....../........ (Nam / Nữ)."
TEXT_INSTRUCTION = (
    "Tô kín ô có đáp án đúng bằng bút chì. Không tô ngoài ô, không dùng bút mực."
)

# ---------------------------------------------------------------------------
# 5. Tiêu đề và hai dòng đầu phiếu
# ---------------------------------------------------------------------------
TITLE_CY = 32                   # tâm y của tiêu đề (căn giữa trang)
HEADER_TEXT_X = 85              # x bắt đầu của dòng "Kỳ thi" và "Bài thi"
EXAM_LINE_Y = 56
EXAM_LINE_MAX_X = 700           # dòng "Kỳ thi" không vượt quá x này (tránh marker phải)
SUBJECT_DATE_LINE_Y = 78
DATE_LINE_MAX_X = 390           # dòng "Bài thi ... Ngày thi" không chạm nhãn mục 7
DATE_LINE_MIN_DOTS = 6          # số dấu chấm tối thiểu sau "Bài thi:"
ID_LABEL_X = 402
CODE_LABEL_X = 662
BLOCK_LABEL_Y = 88              # tâm y của nhãn "7. ..." và "8. ..."

# ---------------------------------------------------------------------------
# 6. Khung thông tin (x 57-748, y 97-336), chia 4 cột
# ---------------------------------------------------------------------------
INFO_LEFT = 57
INFO_TOP = 97
INFO_RIGHT = 748
INFO_BOTTOM = 336
INFO_COL_DIVIDERS_X = (157, 398, 658)   # 3 đường dọc -> 4 cột
CBCT_SPLIT_Y = (185, 274)               # 2 đường ngang trong cột 1
INFO_LINE_Y = (117, 157, 197, 237, 277, 317)   # tâm y 6 dòng thông tin ở cột 2
INFO_TEXT_PAD_LEFT = 8
INFO_TEXT_PAD_RIGHT = 6
CBCT_TEXT_PAD = 6
SCORE_UNDERLINE_OFFSET = 0.65   # khoảng cách gạch chân "Điểm" so với tâm chữ (x cỡ chữ); chữ nằm sát mép trên ô

# ---------------------------------------------------------------------------
# 7. Khối mã số sinh viên (cột 3) và mã đề (cột 4)
# ---------------------------------------------------------------------------
ID_DIGITS = 11                  # số cột chữ số của mã số sinh viên
CODE_DIGITS = 3                 # số cột chữ số của mã đề
DIGIT_VALUES = 10               # mỗi cột có 10 ô: 0-9
DIGIT_COL_PITCH = 21            # khoảng cách ngang giữa các cột ô
DIGIT_ROW_Y0 = 139              # tâm y của dòng chữ số 0
DIGIT_ROW_PITCH = 20.6          # khoảng cách dọc giữa các dòng chữ số
ID_BUBBLE_RADIUS = 7            # bán kính ô tròn mã số sinh viên và mã đề
ID_LABEL_CX = 408               # tâm x cột nhãn 0-9 của mã số sinh viên
ID_FIRST_COL_CX = 432.5         # tâm x cột ô đầu tiên của mã số sinh viên
CODE_LABEL_CX = 668
CODE_FIRST_COL_CX = 692.5
WRITE_BOX_TOP = 101             # hàng ô vuông trống để viết số
WRITE_BOX_BOTTOM = 121
DIGIT_MARK_Y = 104              # y trên của ô vuông đen nhỏ ở góc khối
ID_MARK_X = 402
CODE_MARK_X = 662

# ---------------------------------------------------------------------------
# 8. Dòng hướng dẫn và các khối câu hỏi
# ---------------------------------------------------------------------------
INSTRUCTION_X = 60      # x bắt đầu dòng hướng dẫn (cùng lề trái với khối câu)
INSTRUCTION_Y = 353     # tâm y dòng hướng dẫn (khe giữa khung thông tin và khối câu)
QUESTIONS_PER_BLOCK = 10
BLOCKS_PER_ROW = 4
MAX_BLOCK_ROWS = 2
MAX_QUESTIONS = QUESTIONS_PER_BLOCK * BLOCKS_PER_ROW * MAX_BLOCK_ROWS   # 80
BLOCK_X0 = 57                   # x trái của khối đầu tiên mỗi hàng
BLOCK_W = 163
BLOCK_GAP_X = 13
BLOCK_X_LEFTS = tuple(BLOCK_X0 + i * (BLOCK_W + BLOCK_GAP_X) for i in range(BLOCKS_PER_ROW))
BLOCKS_TOP = 368                # y đỉnh của hàng khối đầu tiên
BLOCKS_BOTTOM = 1040            # y đáy tối đa của hàng khối cuối
BAND_GAP = 15                   # khoảng trống dọc giữa hai hàng khối
BLOCK_HEADER_H = 26             # chiều cao hàng tiêu đề (A, B, C...)
BLOCK_BOTTOM_PAD = 10           # đệm dưới cùng của khối
ROW_PITCH_MAX = 36
BLOCK_BUBBLE_OFFSET_X = 44      # tâm x cột ô đầu tiên = x_left + 44
CHOICE_PITCH_MAX = 34.5
CHOICE_SPAN_MAX = 105           # tổng khoảng cách từ cột đầu đến cột cuối tối đa
BUBBLE_RADIUS_MAX = 9
BUBBLE_RADIUS_RATIO = 0.32
QNUM_OFFSET_X = 16              # tâm x của số thứ tự câu = x_left + 16
BLOCK_MARK_INSET_X = 6          # ô vuông đen nhỏ cách mép trái/trên của khối
BLOCK_MARK_INSET_Y = 6
MIN_ROW_PITCH = 24              # ngưỡng chấp nhận được của bố cục
MIN_CHOICE_PITCH = 24
MIN_BUBBLE_RADIUS = 7
TOO_DENSE_MESSAGE = "Quá nhiều câu hoặc đáp án, hãy giảm số câu hoặc số đáp án"

# ---------------------------------------------------------------------------
# 9. Dữ liệu thực nghiệm (make_ground_truth.py, build_manifest.py, evaluate.py)
# ---------------------------------------------------------------------------
IMAGES_SUBDIR = "images"                    # data/images/: ảnh chụp phiếu
GROUND_TRUTH_FILE = "ground_truth.csv"
GROUND_TRUTH_ID_FILE = "ground_truth_id.csv"
MANIFEST_FILE = "manifest.csv"
GROUND_TRUTH_FIELDS = ("template", "sheet_id", "q", "expected")
GROUND_TRUTH_ID_FIELDS = ("template", "sheet_id", "student_id", "exam_code")
MANIFEST_FIELDS = ("image", "template", "sheet_id", "condition")
# Tên ảnh: {template}_{sheet_id}_{condition}_{n}.jpg, nên slug không được chứa dấu "_"
TEMPLATE_SLUG_PATTERN = r"[A-Za-z0-9-]+"
SHEET_ID_PREFIX = "s"
SHEET_ID_WIDTH = 2                          # s01, s02, ...
SHEET_ID_PATTERN = r"s\d+"
CONDITIONS = ("binhthuong", "nghieng", "thieusang", "bongdo", "tonhat", "nenlonxon")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")    # so khớp không phân biệt hoa thường
