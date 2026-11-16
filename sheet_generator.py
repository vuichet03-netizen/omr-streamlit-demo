"""Sinh phiếu trả lời trắc nghiệm (PIL) và file cấu hình JSON tương ứng.

Nguyên tắc cốt lõi: mỗi ô tròn được VẼ và GHI tọa độ trong cùng một vòng lặp,
dùng chung công thức bố cục (xem constants.py). Vì vậy file cấu hình tự sinh
không thể lệch so với phiếu đã vẽ.

Yêu cầu: Pillow >= 10.1. matplotlib là tùy chọn (chỉ dùng để tìm font DejaVu).
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from numbers import Integral, Real
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import constants as C

# Hình chữ nhật (x0, y0, x1, y1) theo pixel chuẩn
Rect = tuple[float, float, float, float]


# ===========================================================================
# 1. Kiểm tra tham số và tính bố cục khối câu hỏi
# ===========================================================================
def _read_int_param(params: dict, key: str, label: str, low: int, high: int) -> int:
    """Đọc một tham số nguyên trong khoảng [low, high]; sai thì raise ValueError tiếng Việt."""
    if key not in params:
        raise ValueError(
            f"Thiếu tham số '{key}' ({label}). Hãy truyền một số nguyên từ {low} đến {high}."
        )
    value = params[key]
    is_number = isinstance(value, (Integral, Real)) and not isinstance(value, bool)
    if is_number and not isinstance(value, Integral) and float(value).is_integer():
        value = int(value)  # chấp nhận 40.0 như 40
    if not (is_number and isinstance(value, Integral)):
        raise ValueError(
            f"{label} phải là số nguyên (bạn nhập: {value!r}). "
            f"Hãy nhập một số nguyên từ {low} đến {high}."
        )
    value = int(value)
    if not low <= value <= high:
        action = "giảm" if value > high else "tăng"
        raise ValueError(
            f"{label} phải nằm trong khoảng {low} đến {high} (bạn nhập: {value}). "
            f"Hãy {action} {label.lower()} cho phù hợp."
        )
    return value


def validate_params(params: dict) -> dict:
    """Kiểm tra tham số đầu vào, trả về dict đã chuẩn hóa (exam_name, num_questions, num_choices)."""
    if not isinstance(params, dict):
        raise ValueError("Tham số phiếu phải là một dict gồm exam_name, num_questions, num_choices.")
    num_questions = _read_int_param(
        params, "num_questions", "Số câu hỏi", C.MIN_QUESTIONS, C.MAX_QUESTIONS
    )
    num_choices = _read_int_param(
        params, "num_choices", "Số đáp án mỗi câu", C.MIN_CHOICES, C.MAX_CHOICES
    )
    exam_name = params.get("exam_name", "")
    if exam_name is None:
        exam_name = ""
    if not isinstance(exam_name, str):
        raise ValueError("Tên kỳ thi (exam_name) phải là chuỗi ký tự.")
    exam_name = " ".join(exam_name.split())  # gộp khoảng trắng, bỏ xuống dòng
    if len(exam_name) > C.EXAM_NAME_MAX_LEN:
        raise ValueError(
            f"Tên kỳ thi dài {len(exam_name)} ký tự, tối đa {C.EXAM_NAME_MAX_LEN}. "
            "Hãy rút gọn tên kỳ thi."
        )
    return {"exam_name": exam_name, "num_questions": num_questions, "num_choices": num_choices}


@dataclass(frozen=True)
class QuestionLayout:
    """Các đại lượng bố cục dùng chung cho mọi khối câu hỏi."""

    num_blocks: int
    bands: int              # số hàng khối
    band_h: float           # chiều cao một hàng khối đầy đủ (đủ 10 câu)
    row_pitch: float        # khoảng cách dọc giữa các câu
    choice_pitch: float     # khoảng cách ngang giữa các đáp án
    bubble_radius: float


def compute_question_layout(num_questions: int, num_choices: int) -> QuestionLayout:
    """Tính row_pitch, choice_pitch, bán kính ô từ số câu và số đáp án."""
    num_blocks = math.ceil(num_questions / C.QUESTIONS_PER_BLOCK)
    bands = math.ceil(num_blocks / C.BLOCKS_PER_ROW)
    usable_h = C.BLOCKS_BOTTOM - C.BLOCKS_TOP
    band_h_max = (usable_h - (bands - 1) * C.BAND_GAP) / bands
    chrome_h = C.BLOCK_HEADER_H + C.BLOCK_BOTTOM_PAD
    row_pitch = min(C.ROW_PITCH_MAX, (band_h_max - chrome_h) / C.QUESTIONS_PER_BLOCK)
    choice_pitch = min(C.CHOICE_PITCH_MAX, C.CHOICE_SPAN_MAX / (num_choices - 1))
    bubble_radius = round(
        min(C.BUBBLE_RADIUS_MAX, C.BUBBLE_RADIUS_RATIO * min(row_pitch, choice_pitch)), 2
    )
    if (
        row_pitch < C.MIN_ROW_PITCH
        or choice_pitch < C.MIN_CHOICE_PITCH
        or bubble_radius < C.MIN_BUBBLE_RADIUS
    ):
        raise ValueError(C.TOO_DENSE_MESSAGE)
    band_h = C.BLOCK_HEADER_H + C.QUESTIONS_PER_BLOCK * row_pitch + C.BLOCK_BOTTOM_PAD
    return QuestionLayout(num_blocks, bands, band_h, row_pitch, choice_pitch, bubble_radius)


def digit_row_y(digit: int) -> float:
    """Tâm y của dòng chữ số `digit` (0-9) trong khối mã số sinh viên / mã đề."""
    return C.DIGIT_ROW_Y0 + C.DIGIT_ROW_PITCH * digit


def digit_col_cx(first_col_cx: float, col: int) -> float:
    """Tâm x của cột chữ số thứ `col` trong một khối chữ số."""
    return first_col_cx + C.DIGIT_COL_PITCH * col


def choice_cx(x_left: float, choice_index: int, layout: QuestionLayout) -> float:
    """Tâm x của đáp án thứ `choice_index` trong khối có cạnh trái x_left."""
    return x_left + C.BLOCK_BUBBLE_OFFSET_X + layout.choice_pitch * choice_index


# ===========================================================================
# 2. Font chữ và canvas vẽ
# ===========================================================================
def _strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt (dùng khi không tìm được font hỗ trợ)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


@lru_cache(maxsize=1)
def find_font_paths() -> tuple[str | None, str | None, str | None]:
    """Tìm font TTF (thường, đậm, nghiêng) hỗ trợ tiếng Việt; (None, None, None) nếu không có."""
    candidates: list[tuple[str, str, str]] = []
    try:  # DejaVu Sans đi kèm matplotlib, chạy được trên mọi hệ điều hành
        from matplotlib import font_manager

        regular = font_manager.findfont(
            font_manager.FontProperties(family="DejaVu Sans"), fallback_to_default=False
        )
        bold = font_manager.findfont(
            font_manager.FontProperties(family="DejaVu Sans", weight="bold"),
            fallback_to_default=False,
        )
        try:
            italic = font_manager.findfont(
                font_manager.FontProperties(family="DejaVu Sans", style="italic"),
                fallback_to_default=False,
            )
        except Exception:
            italic = regular
        candidates.append((regular, bold, italic))
    except Exception:  # matplotlib không có hoặc không thấy font
        pass
    candidates += [
        ("arial.ttf", "arialbd.ttf", "ariali.ttf"),  # Windows
        ("/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Italic.ttf"),  # macOS
        ("/Library/Fonts/Arial.ttf",
         "/Library/Fonts/Arial Bold.ttf",
         "/Library/Fonts/Arial Italic.ttf"),  # macOS
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),  # Linux
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf"),
    ]
    for regular, bold, italic in candidates:
        try:
            ImageFont.truetype(regular, 20)
        except OSError:
            continue
        try:
            ImageFont.truetype(bold, 20)
        except OSError:
            bold = regular  # không có bản đậm thì dùng bản thường
        try:
            ImageFont.truetype(italic, 20)
        except OSError:
            italic = regular  # không có bản nghiêng thì dùng bản thường
        return regular, bold, italic
    return None, None, None


class FontProvider:
    """Cấp font theo cỡ chữ (pixel chuẩn) và đo độ rộng chữ theo pixel chuẩn."""

    def __init__(self) -> None:
        self.regular_path, self.bold_path, self.italic_path = find_font_paths()
        self.has_vietnamese = self.regular_path is not None
        self._cache: dict[tuple[int, bool, bool], ImageFont.FreeTypeFont] = {}

    def get(self, size: float, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        """Font ứng với cỡ chữ `size` (pixel chuẩn), đã nhân SCALE."""
        px = max(1, round(size * C.SCALE))
        key = (px, bold, italic)
        if key not in self._cache:
            if italic:
                path = self.italic_path
            elif bold:
                path = self.bold_path
            else:
                path = self.regular_path
            if path is None:
                try:
                    self._cache[key] = ImageFont.load_default(px)  # Pillow >= 10.1
                except TypeError:
                    self._cache[key] = ImageFont.load_default()
            else:
                self._cache[key] = ImageFont.truetype(path, px)
        return self._cache[key]

    def text(self, text: str) -> str:
        """Chuỗi sẽ được vẽ: giữ dấu nếu có font phù hợp, ngược lại bỏ dấu."""
        return text if self.has_vietnamese else _strip_diacritics(text)

    def width(self, text: str, size: float, bold: bool = False, italic: bool = False) -> float:
        """Độ rộng chuỗi (pixel chuẩn) khi vẽ với cỡ chữ `size`."""
        return self.get(size, bold, italic).getlength(self.text(text)) / C.SCALE


class SheetCanvas:
    """Canvas vẽ phiếu: nhận tọa độ chuẩn, tự nhân SCALE khi vẽ."""

    def __init__(self, fonts: FontProvider) -> None:
        self.fonts = fonts
        self.image = Image.new("RGB", (C.PAGE_W * C.SCALE, C.PAGE_H * C.SCALE), "white")
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def _px(value: float) -> int:
        """Đổi một tọa độ chuẩn sang pixel ảnh."""
        return round(value * C.SCALE)

    @staticmethod
    def _stroke(width: float) -> int:
        """Đổi độ dày nét (pixel chuẩn) sang pixel ảnh, tối thiểu 1."""
        return max(1, round(width * C.SCALE))

    def line(self, x0: float, y0: float, x1: float, y1: float, width: float = C.LINE_W) -> None:
        """Vẽ đoạn thẳng đen."""
        self.draw.line(
            [(self._px(x0), self._px(y0)), (self._px(x1), self._px(y1))],
            fill="black", width=self._stroke(width),
        )

    def rect(self, x0: float, y0: float, x1: float, y1: float, width: float = C.LINE_W) -> None:
        """Vẽ viền hình chữ nhật (nét vẽ nằm phía trong biên)."""
        self.draw.rectangle(
            [self._px(x0), self._px(y0), self._px(x1) - 1, self._px(y1) - 1],
            outline="black", width=self._stroke(width),
        )

    def fill_rect(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Tô đen đặc hình chữ nhật."""
        self.draw.rectangle(
            [self._px(x0), self._px(y0), self._px(x1) - 1, self._px(y1) - 1], fill="black"
        )

    def circle(self, cx: float, cy: float, radius: float, width: float = C.BUBBLE_LINE_W) -> None:
        """Vẽ viền ô tròn, ruột để trắng."""
        self.draw.ellipse(
            [self._px(cx - radius), self._px(cy - radius),
             self._px(cx + radius) - 1, self._px(cy + radius) - 1],
            outline="black", width=self._stroke(width),
        )

    def text(self, x: float, y: float, text: str, size: float,
             bold: bool = False, italic: bool = False, anchor: str = "lm") -> None:
        """Vẽ chữ; anchor 'lm' = trái-giữa, 'mm' = giữa-giữa (theo tọa độ chuẩn)."""
        self.draw.text(
            (x * C.SCALE, y * C.SCALE), self.fonts.text(text),
            fill="black", font=self.fonts.get(size, bold, italic), anchor=anchor,
        )


# ===========================================================================
# 3. Tiện ích chữ: co cỡ chữ, ngắt dòng, dòng chấm chấm
# ===========================================================================
def fit_font_size(fonts: FontProvider, text: str, max_width: float,
                  start: float = C.FONT_BODY, minimum: float = C.FONT_MIN,
                  bold: bool = False, italic: bool = False) -> float:
    """Giảm dần cỡ chữ từ `start` đến khi `text` vừa `max_width` (không nhỏ hơn `minimum`)."""
    size = start
    while size > minimum and fonts.width(text, size, bold, italic) > max_width:
        size -= C.FONT_FIT_STEP
    return max(size, minimum)


def wrap_text(fonts: FontProvider, text: str, max_width: float, size: float) -> list[str]:
    """Ngắt `text` thành các dòng theo từ sao cho mỗi dòng không vượt `max_width`."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or fonts.width(trial, size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_wrapped_text(fonts: FontProvider, text: str, max_width: float) -> tuple[list[str], float]:
    """Chọn cỡ chữ lớn nhất sao cho mọi dòng sau khi ngắt đều vừa `max_width`."""
    size = C.FONT_BODY
    while True:
        lines = wrap_text(fonts, text, max_width, size)
        if all(fonts.width(line, size) <= max_width for line in lines) or size <= C.FONT_MIN:
            return lines, size
        size -= C.FONT_FIT_STEP


def draw_dotted_line(canvas: SheetCanvas, x: float, y: float, label: str,
                     x_end: float, size: float) -> None:
    """Vẽ `label` rồi nối dấu chấm tới x_end."""
    fonts = canvas.fonts
    used = fonts.width(label + " ", size)
    dot_w = fonts.width(C.DOT_CHAR, size)
    num_dots = max(0, int((x_end - x - used) / dot_w))
    canvas.text(x, y, label + " " + C.DOT_CHAR * num_dots, size)


# ===========================================================================
# 4. Các phần tĩnh của phiếu: marker, tiêu đề, khung thông tin
# ===========================================================================
@dataclass
class SheetLayout:
    """Vùng hình học thực tế đã vẽ, dùng để kiểm tra bố cục (không ghi vào JSON)."""

    marker_rects: list[Rect] = field(default_factory=list)
    small_marks: list[Rect] = field(default_factory=list)
    question_blocks: list[Rect] = field(default_factory=list)
    info_rect: Rect = (C.INFO_LEFT, C.INFO_TOP, C.INFO_RIGHT, C.INFO_BOTTOM)
    id_rect: Rect | None = None
    code_rect: Rect | None = None


def draw_corner_markers(canvas: SheetCanvas, layout: SheetLayout) -> None:
    """Vẽ 4 ô vuông đen đặc MARKER_SIZE tại MARKER_CENTERS."""
    half = C.MARKER_SIZE / 2
    for cx, cy in C.MARKER_CENTERS:
        rect = (cx - half, cy - half, cx + half, cy + half)
        canvas.fill_rect(*rect)
        layout.marker_rects.append(rect)


def draw_small_mark(canvas: SheetCanvas, layout: SheetLayout, x: float, y: float) -> None:
    """Vẽ ô vuông đen nhỏ SMALL_MARK có góc trên trái tại (x, y)."""
    rect = (x, y, x + C.SMALL_MARK, y + C.SMALL_MARK)
    canvas.fill_rect(*rect)
    layout.small_marks.append(rect)


def draw_title(canvas: SheetCanvas) -> None:
    """In tiêu đề đậm, căn giữa trang."""
    canvas.text(C.PAGE_W / 2, C.TITLE_CY, C.TEXT_TITLE, C.FONT_TITLE, bold=True, anchor="mm")


def draw_exam_line(canvas: SheetCanvas) -> None:
    """Dòng 'Kỳ thi: ....' để thí sinh tự ghi, giống dòng 'Bài thi'."""
    draw_dotted_line(
        canvas, C.HEADER_TEXT_X, C.EXAM_LINE_Y,
        C.TEXT_EXAM_LABEL, C.EXAM_LINE_MAX_X, C.FONT_BODY,
    )


def compose_subject_date_line(fonts: FontProvider) -> tuple[str, float]:
    """Ghép dòng 'Bài thi: ..... Ngày thi: ...' vừa tới DATE_LINE_MAX_X; trả về (chuỗi, cỡ chữ)."""
    max_width = C.DATE_LINE_MAX_X - C.HEADER_TEXT_X
    head = C.TEXT_SUBJECT_LABEL + " "
    tail = C.TEXT_DATE_GAP + C.TEXT_DATE_PART
    size = C.FONT_BODY
    while True:
        free = max_width - fonts.width(head + tail, size)
        num_dots = int(free / fonts.width(C.DOT_CHAR, size))
        if num_dots >= C.DATE_LINE_MIN_DOTS or size <= C.FONT_MIN:
            break
        size -= C.FONT_FIT_STEP
    return head + C.DOT_CHAR * max(num_dots, 1) + tail, size


def draw_subject_date_line(canvas: SheetCanvas) -> None:
    """Dòng 'Bài thi: ...  Ngày thi: ....../....../ ........'."""
    text, size = compose_subject_date_line(canvas.fonts)
    canvas.text(C.HEADER_TEXT_X, C.SUBJECT_DATE_LINE_Y, text, size)


def draw_block_labels(canvas: SheetCanvas) -> None:
    """In nhãn '7. Mã số sinh viên' và '8. Mã đề' ngay trên hai khối chữ số."""
    canvas.text(C.ID_LABEL_X, C.BLOCK_LABEL_Y, C.TEXT_ID_LABEL, C.FONT_BLOCK_LABEL)
    canvas.text(C.CODE_LABEL_X, C.BLOCK_LABEL_Y, C.TEXT_CODE_LABEL, C.FONT_BLOCK_LABEL)


def draw_info_frame(canvas: SheetCanvas) -> None:
    """Vẽ khung thông tin, 3 đường dọc chia 4 cột và 2 đường ngang ở cột 1."""
    canvas.rect(C.INFO_LEFT, C.INFO_TOP, C.INFO_RIGHT, C.INFO_BOTTOM)
    for x in C.INFO_COL_DIVIDERS_X:
        canvas.line(x, C.INFO_TOP, x, C.INFO_BOTTOM)
    for y in C.CBCT_SPLIT_Y:
        canvas.line(C.INFO_LEFT, y, C.INFO_COL_DIVIDERS_X[0], y)


def draw_cbct_cells(canvas: SheetCanvas) -> None:
    """Cột 1: hai ô 'Họ tên, chữ kí CBCT' (tự xuống dòng) và ô 'Điểm' sát mép trên."""
    fonts = canvas.fonts
    col_right = C.INFO_COL_DIVIDERS_X[0]
    max_width = col_right - C.INFO_LEFT - 2 * C.CBCT_TEXT_PAD
    cell_tops = (C.INFO_TOP, C.CBCT_SPLIT_Y[0])
    for top, text in zip(cell_tops, (C.TEXT_CBCT_1, C.TEXT_CBCT_2)):
        lines, size = fit_wrapped_text(fonts, text, max_width)
        for i, line in enumerate(lines):
            y = top + C.CBCT_TEXT_PAD + size * C.LINE_HEIGHT_RATIO * (i + 0.5)
            canvas.text(C.INFO_LEFT + C.CBCT_TEXT_PAD, y, line, size)
    # Ô "Điểm": căn giữa ngang, sát mép trên; phần dưới để trống viết điểm
    cx = (C.INFO_LEFT + col_right) / 2
    cy = C.CBCT_SPLIT_Y[1] + C.CBCT_TEXT_PAD + C.FONT_BODY * C.LINE_HEIGHT_RATIO * 0.5
    canvas.text(cx, cy, C.TEXT_SCORE, C.FONT_BODY, anchor="mm")
    half_w = fonts.width(C.TEXT_SCORE, C.FONT_BODY) / 2
    underline_y = cy + C.FONT_BODY * C.SCORE_UNDERLINE_OFFSET
    canvas.line(cx - half_w, underline_y, cx + half_w, underline_y, C.THIN_LINE_W)


def draw_info_lines(canvas: SheetCanvas) -> None:
    """Cột 2: 6 dòng thông tin đánh số; cỡ chữ chung co theo dòng dài nhất (dòng 6)."""
    col_left, col_right = C.INFO_COL_DIVIDERS_X[0], C.INFO_COL_DIVIDERS_X[1]
    x = col_left + C.INFO_TEXT_PAD_LEFT
    x_end = col_right - C.INFO_TEXT_PAD_RIGHT
    size = fit_font_size(canvas.fonts, C.TEXT_BIRTH_LINE, x_end - x)
    for y, label in zip(C.INFO_LINE_Y, C.TEXT_INFO_LINES):
        draw_dotted_line(canvas, x, y, label, x_end, size)
    canvas.text(x, C.INFO_LINE_Y[len(C.TEXT_INFO_LINES)], C.TEXT_BIRTH_LINE, size)


# ===========================================================================
# 5. Ô tròn: VẼ và GHI tọa độ cùng một chỗ
# ===========================================================================
def place_bubble(canvas: SheetCanvas, cx: float, cy: float, radius: float, extra: dict) -> dict:
    """Vẽ một ô tròn tại (cx, cy) và trả về bản ghi cấu hình của chính ô đó.

    Đây là nơi DUY NHẤT vừa vẽ vừa ghi tọa độ: tọa độ được làm tròn 2 chữ số
    trước khi vẽ, nên số ghi trong JSON đúng bằng số đã dùng để vẽ.
    """
    cx, cy = round(cx, 2), round(cy, 2)
    canvas.circle(cx, cy, radius)
    return {**extra, "cx": cx, "cy": cy}


@dataclass(frozen=True)
class DigitBlockSpec:
    """Mô tả một khối chữ số (mã số sinh viên hoặc mã đề)."""

    num_cols: int
    left: float
    right: float
    label_cx: float
    first_col_cx: float
    mark_x: float


ID_BLOCK_SPEC = DigitBlockSpec(
    C.ID_DIGITS, C.INFO_COL_DIVIDERS_X[1], C.INFO_COL_DIVIDERS_X[2],
    C.ID_LABEL_CX, C.ID_FIRST_COL_CX, C.ID_MARK_X,
)
CODE_BLOCK_SPEC = DigitBlockSpec(
    C.CODE_DIGITS, C.INFO_COL_DIVIDERS_X[2], C.INFO_RIGHT,
    C.CODE_LABEL_CX, C.CODE_FIRST_COL_CX, C.CODE_MARK_X,
)


def draw_digit_block(canvas: SheetCanvas, layout: SheetLayout, spec: DigitBlockSpec) -> list[dict]:
    """Vẽ một khối chữ số (nhãn 0-9, hàng ô viết số, ô đen nhỏ, ô tròn); trả về mục `digits` của JSON."""
    # Nhãn 0-9: dùng chung digit_row_y với vòng lặp ô tròn bên dưới
    for d in range(C.DIGIT_VALUES):
        canvas.text(spec.label_cx, digit_row_y(d), str(d), C.FONT_DIGIT_LABEL, bold=True, anchor="mm")
    # Hàng ô vuông trống để thí sinh viết số, thẳng hàng với các cột ô tròn
    box_x0 = spec.first_col_cx - C.DIGIT_COL_PITCH / 2
    box_x1 = box_x0 + spec.num_cols * C.DIGIT_COL_PITCH
    canvas.rect(box_x0, C.WRITE_BOX_TOP, box_x1, C.WRITE_BOX_BOTTOM)
    for k in range(1, spec.num_cols):
        x = box_x0 + k * C.DIGIT_COL_PITCH
        canvas.line(x, C.WRITE_BOX_TOP, x, C.WRITE_BOX_BOTTOM, C.THIN_LINE_W)
    draw_small_mark(canvas, layout, spec.mark_x, C.DIGIT_MARK_Y)
    # Ô tròn: vẽ và ghi tọa độ trong cùng vòng lặp
    digits = []
    for k in range(spec.num_cols):
        cx = digit_col_cx(spec.first_col_cx, k)
        bubbles = [
            place_bubble(canvas, cx, digit_row_y(d), C.ID_BUBBLE_RADIUS, {"value": d})
            for d in range(C.DIGIT_VALUES)
        ]
        digits.append({"pos": k, "bubbles": bubbles})
    return digits


# ===========================================================================
# 6. Khối câu hỏi PHẦN I
# ===========================================================================
def draw_instruction(canvas: SheetCanvas) -> None:
    """In dòng hướng dẫn tô phiếu (cỡ nhỏ, nghiêng) ngay trên các khối câu hỏi."""
    max_width = C.INFO_RIGHT - C.INSTRUCTION_X
    size = fit_font_size(
        canvas.fonts, C.TEXT_INSTRUCTION, max_width,
        start=C.FONT_INSTRUCTION, italic=True,
    )
    canvas.text(C.INSTRUCTION_X, C.INSTRUCTION_Y, C.TEXT_INSTRUCTION, size, italic=True)


def draw_question_blocks(canvas: SheetCanvas, layout: SheetLayout, params: dict,
                         ql: QuestionLayout) -> list[dict]:
    """Vẽ các khối câu hỏi; trả về danh sách `questions` của JSON."""
    num_questions, num_choices = params["num_questions"], params["num_choices"]
    labels = list(C.CHOICE_LABELS_ALL[:num_choices])
    questions: list[dict] = []
    for block in range(ql.num_blocks):
        band, col = divmod(block, C.BLOCKS_PER_ROW)
        x_left = C.BLOCK_X_LEFTS[col]
        y_top = C.BLOCKS_TOP + band * (ql.band_h + C.BAND_GAP)
        first = block * C.QUESTIONS_PER_BLOCK
        count = min(C.QUESTIONS_PER_BLOCK, num_questions - first)  # khối cuối có thể ngắn hơn
        block_h = C.BLOCK_HEADER_H + count * ql.row_pitch + C.BLOCK_BOTTOM_PAD
        rect = (x_left, y_top, x_left + C.BLOCK_W, y_top + block_h)
        canvas.rect(*rect)
        layout.question_blocks.append(rect)
        draw_small_mark(canvas, layout, x_left + C.BLOCK_MARK_INSET_X, y_top + C.BLOCK_MARK_INSET_Y)
        # Hàng tiêu đề A, B, C...: dùng chung choice_cx với ô tròn
        for j, label in enumerate(labels):
            canvas.text(choice_cx(x_left, j, ql), y_top + C.BLOCK_HEADER_H / 2, label,
                        C.FONT_CHOICE_HEADER, bold=True, anchor="mm")
        # Từng câu: vẽ số thứ tự và các ô tròn, đồng thời ghi tọa độ
        for i in range(count):
            q = first + i + 1
            cy = y_top + C.BLOCK_HEADER_H + ql.row_pitch * (i + 0.5)
            canvas.text(x_left + C.QNUM_OFFSET_X, cy, str(q), C.FONT_QNUM, bold=True, anchor="mm")
            bubbles = [
                place_bubble(canvas, choice_cx(x_left, j, ql), cy, ql.bubble_radius, {"label": label})
                for j, label in enumerate(labels)
            ]
            questions.append({"q": q, "bubbles": bubbles})
    return questions


# ===========================================================================
# 7. Ghép phiếu và cấu hình
# ===========================================================================
def build_config(params: dict, ql: QuestionLayout, questions: list[dict],
                 id_digits: list[dict], code_digits: list[dict]) -> dict:
    """Ghép file cấu hình (định dạng version 2) từ các bản ghi đã sinh khi vẽ."""
    return {
        "version": C.CONFIG_VERSION,
        "exam_name": params["exam_name"],
        "params": {"num_questions": params["num_questions"], "num_choices": params["num_choices"]},
        "page": {"width": C.PAGE_W, "height": C.PAGE_H},
        "markers": {"size": C.MARKER_SIZE, "centers": [list(c) for c in C.MARKER_CENTERS]},
        "bubble_radius": ql.bubble_radius,
        "id_bubble_radius": C.ID_BUBBLE_RADIUS,
        "choice_labels": list(C.CHOICE_LABELS_ALL[: params["num_choices"]]),
        "questions": questions,
        "id_block": {"digits": id_digits},
        "code_block": {"digits": code_digits},
    }


def build_sheet(params: dict) -> tuple[Image.Image, dict, SheetLayout]:
    """Sinh phiếu: trả về (ảnh, cấu hình, vùng hình học đã vẽ). Dùng cho kiểm thử bố cục."""
    p = validate_params(params)
    ql = compute_question_layout(p["num_questions"], p["num_choices"])
    canvas = SheetCanvas(FontProvider())
    layout = SheetLayout()

    draw_corner_markers(canvas, layout)
    draw_title(canvas)
    draw_exam_line(canvas)
    draw_subject_date_line(canvas)
    draw_block_labels(canvas)
    draw_info_frame(canvas)
    draw_cbct_cells(canvas)
    draw_info_lines(canvas)
    id_digits = draw_digit_block(canvas, layout, ID_BLOCK_SPEC)
    code_digits = draw_digit_block(canvas, layout, CODE_BLOCK_SPEC)
    layout.id_rect = (ID_BLOCK_SPEC.left, C.INFO_TOP, ID_BLOCK_SPEC.right, C.INFO_BOTTOM)
    layout.code_rect = (CODE_BLOCK_SPEC.left, C.INFO_TOP, CODE_BLOCK_SPEC.right, C.INFO_BOTTOM)
    draw_instruction(canvas)
    questions = draw_question_blocks(canvas, layout, p, ql)

    config = build_config(p, ql, questions, id_digits, code_digits)
    return canvas.image, config, layout


def generate_sheet(params: dict) -> tuple[Image.Image, dict]:
    """Sinh phiếu từ params (exam_name, num_questions, num_choices); trả về (ảnh PIL, config)."""
    image, config, _ = build_sheet(params)
    return image, config


# ===========================================================================
# 8. Lưu file
# ===========================================================================
def make_preview(image: Image.Image) -> Image.Image:
    """Thu ảnh phiếu về kích thước chuẩn PAGE_W x PAGE_H để xem trước."""
    return image.resize((C.PAGE_W, C.PAGE_H), Image.Resampling.LANCZOS)


def make_a4_page(image: Image.Image) -> tuple[Image.Image, float]:
    """Đặt phiếu lên trang A4 trắng; trả về (ảnh trang, dpi) sao cho chiều rộng khớp đúng 210 mm."""
    dpi = image.width / (C.A4_W_MM / C.MM_PER_INCH)
    page_h = max(image.height, round(C.A4_H_MM / C.MM_PER_INCH * dpi))
    gray = image.convert("L")
    page = Image.new("L", (image.width, page_h), 255)
    page.paste(gray, (0, (page_h - gray.height) // 2))
    # Ảnh 1-bit (ngưỡng 128, không dither): Pillow nén G4 nên PDF nhỏ và nét sắc khi in.
    # (Chế độ "P" bị mã hóa ASCIIHex rất nặng; "L"/"RGB" bị nén JPEG làm mờ nét.)
    return page.convert("1", dither=Image.Dither.NONE), dpi


def save_sheet(params: dict, out_dir, slug: str) -> None:
    """Ghi <slug>.png (xem trước), <slug>.pdf (A4 để in) và <slug>.json (cấu hình) vào out_dir."""
    if not slug or any(sep in slug for sep in "/\\"):
        raise ValueError("slug không được rỗng và không chứa dấu '/' hoặc '\\'.")
    image, config = generate_sheet(params)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    make_preview(image).save(out_dir / f"{slug}.png")
    page, dpi = make_a4_page(image)
    page.save(out_dir / f"{slug}.pdf", "PDF", resolution=dpi)
    with open(out_dir / f"{slug}.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
