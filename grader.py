"""Chấm phiếu đã nắn: ngưỡng hóa, fill ratio, quyết định đáp án, vẽ kết quả, xuất Excel.

Mọi tọa độ ô đọc từ file cấu hình JSON. Không hard-code số câu, số đáp án hay tâm ô.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Tham số và kết quả
# ---------------------------------------------------------------------------
@dataclass
class GradeParams:
    """Mọi tham số chấm điểm, có giá trị mặc định."""

    blur_ksize: int = 5                 # cạnh kernel Gaussian (lẻ) trước khi ngưỡng
    adaptive_block: int = 41            # cửa sổ adaptiveThreshold trên ảnh 800x1131 (lẻ)
    adaptive_c: int = 10                # hằng số trừ trong adaptiveThreshold
    inner_radius_ratio: float = 0.75    # chỉ lấy vùng trong 75% bán kính, loại viền in sẵn
    t_abs: float = 0.40                 # fill ratio tối thiểu để coi ô câu hỏi đã tô
    t_rel: float = 0.60                 # ô phải đạt >= t_rel * max fill trong cùng câu
    id_t_abs: float = 0.40              # fill ratio tối thiểu cho ô mã số / mã đề
    id_peak_ratio: float = 1.5          # ô thắng phải >= 1.5 lần ô lớn thứ hai cùng cột
    total_score: float = 10.0           # thang điểm toàn bài


@dataclass
class GradeResult:
    """Kết quả chấm một phiếu."""

    answers: list[str]
    statuses: list[str]
    student_id: str
    exam_code: str
    key: str
    correct_flags: list[bool]
    correct_count: int
    blank_count: int
    multi_count: int
    wrong_count: int
    score: float
    method: str
    fill: dict = field(repr=False)


# ---------------------------------------------------------------------------
# 2. Tiện ích
# ---------------------------------------------------------------------------
def _odd(value: int, minimum: int = 3) -> int:
    """Làm số lẻ, không nhỏ hơn minimum (OpenCV yêu cầu kernel/blockSize lẻ)."""
    value = max(int(value), minimum)
    if value % 2 == 0:
        value += 1
    return value


def _save_debug(debug_dir: Path | str | None, name: str, image: np.ndarray) -> None:
    """Ghi PNG vào debug_dir; imencode để tránh lỗi đường dẫn Unicode trên Windows."""
    if debug_dir is None:
        return
    folder = Path(debug_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise OSError(f"Không ghi được ảnh debug: {path}")
    path.write_bytes(buf.tobytes())


def _sorted_questions(config: dict) -> list[dict]:
    """Danh sách câu hỏi theo số thứ tự tăng dần."""
    return sorted(config["questions"], key=lambda item: item["q"])


def _sorted_digits(block: dict) -> list[dict]:
    """Các cột chữ số của một khối, theo pos tăng dần."""
    return sorted(block["digits"], key=lambda item: item["pos"])


# ---------------------------------------------------------------------------
# 3. Ngưỡng hóa
# ---------------------------------------------------------------------------
def binarize(gray: np.ndarray, method: str, params: GradeParams) -> np.ndarray:
    """Làm mờ Gaussian rồi ngưỡng nghịch đảo (nét tô = 255). method: 'otsu' hoặc 'adaptive'."""
    ksize = _odd(params.blur_ksize)
    blur = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    if method == "otsu":
        _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        return binary
    if method == "adaptive":
        block = _odd(params.adaptive_block)
        return cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            block, params.adaptive_c,
        )
    raise ValueError(
        f"Phương pháp ngưỡng '{method}' không hợp lệ. Hãy dùng 'otsu' hoặc 'adaptive'."
    )


# ---------------------------------------------------------------------------
# 4. Fill ratio
# ---------------------------------------------------------------------------
def _circle_fill_ratio(binary: np.ndarray, cx: float, cy: float, radius: float) -> float:
    """Tỉ lệ điểm trắng trong hình tròn tâm (cx, cy); cắt patch nhỏ quanh ô."""
    if radius <= 0:
        return 0.0
    height, width = binary.shape[:2]
    r_px = max(1, int(np.ceil(radius)))
    x_c, y_c = int(round(cx)), int(round(cy))
    x0, y0 = max(0, x_c - r_px), max(0, y_c - r_px)
    x1, y1 = min(width, x_c + r_px + 1), min(height, y_c + r_px + 1)
    if x0 >= x1 or y0 >= y1:
        return 0.0
    patch = binary[y0:y1, x0:x1]
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    total = int(mask.sum())
    if total == 0:
        return 0.0
    return float(np.count_nonzero(patch[mask])) / total


def compute_fill_ratios(binary: np.ndarray, config: dict, params: GradeParams) -> dict:
    """Fill ratio từng ô. Trả về questions (n_q, n_c), id (n_id, 10), code (n_code, 10)."""
    labels = list(config["choice_labels"])
    label_index = {label: i for i, label in enumerate(labels)}
    questions = _sorted_questions(config)
    q_radius = float(config["bubble_radius"]) * params.inner_radius_ratio
    q_fill = np.zeros((len(questions), len(labels)), dtype=np.float32)
    for i, question in enumerate(questions):
        for bubble in question["bubbles"]:
            j = label_index[bubble["label"]]
            q_fill[i, j] = _circle_fill_ratio(
                binary, float(bubble["cx"]), float(bubble["cy"]), q_radius,
            )

    id_radius = float(config["id_bubble_radius"]) * params.inner_radius_ratio
    id_fill = _digit_fill_array(binary, config["id_block"], id_radius)
    code_fill = _digit_fill_array(binary, config["code_block"], id_radius)
    return {"questions": q_fill, "id": id_fill, "code": code_fill}


def _digit_fill_array(binary: np.ndarray, block: dict, radius: float) -> np.ndarray:
    """Mảng fill ratio shape (số cột, 10) cho một khối chữ số; hàng = pos, cột = giá trị 0-9."""
    columns = _sorted_digits(block)
    table = np.zeros((len(columns), 10), dtype=np.float32)
    for column in columns:
        pos = int(column["pos"])
        for bubble in column["bubbles"]:
            value = int(bubble["value"])
            table[pos, value] = _circle_fill_ratio(
                binary, float(bubble["cx"]), float(bubble["cy"]), radius,
            )
    return table


# ---------------------------------------------------------------------------
# 5. Quyết định đáp án
# ---------------------------------------------------------------------------
def _decide_question(ratios: np.ndarray, labels: list[str], params: GradeParams) -> tuple[str, str]:
    """Trả về (chuỗi nhãn đã tô, status blank/single/multi) cho một câu."""
    max_ratio = float(ratios.max()) if ratios.size else 0.0
    selected = [
        label for ratio, label in zip(ratios, labels)
        if ratio >= params.t_abs and ratio >= params.t_rel * max_ratio
    ]
    answer = "".join(selected)
    if not selected:
        return "", "blank"
    if len(selected) == 1:
        return answer, "single"
    return answer, "multi"


def _decide_digit_column(ratios: np.ndarray, params: GradeParams) -> str:
    """Chọn một chữ số 0-9 cho một cột, hoặc '?' nếu không đủ nổi bật.

    Độ nổi bật đo trên phần vượt median cột: viền in sẵn làm mọi ô có nền ~0.2–0.3,
    so sánh thô 1.5 lần sẽ không bao giờ đạt. Trừ median rồi mới nhân id_peak_ratio.
    """
    if ratios.size == 0:
        return "?"
    best = int(np.argmax(ratios))
    best_ratio = float(ratios[best])
    if best_ratio < params.id_t_abs:
        return "?"
    if ratios.size == 1:
        return str(best)
    floor = float(np.median(ratios))
    excess = np.clip(ratios.astype(np.float64) - floor, 0.0, None)
    order = np.argsort(excess)
    best_ex = float(excess[int(order[-1])])
    second_ex = float(excess[int(order[-2])])
    if best_ex <= 0:
        return "?"
    if second_ex <= 1e-6 or best_ex >= params.id_peak_ratio * second_ex:
        return str(best)
    return "?"


def decide(fill: dict, config: dict, params: GradeParams) -> dict:
    """Quyết định đáp án từng câu, mã số sinh viên và mã đề từ mảng fill ratio."""
    labels = list(config["choice_labels"])
    answers: list[str] = []
    statuses: list[str] = []
    for row in fill["questions"]:
        answer, status = _decide_question(row, labels, params)
        answers.append(answer)
        statuses.append(status)
    student_id = "".join(_decide_digit_column(row, params) for row in fill["id"])
    exam_code = "".join(_decide_digit_column(row, params) for row in fill["code"])
    return {
        "answers": answers,
        "statuses": statuses,
        "student_id": student_id,
        "exam_code": exam_code,
    }


# ---------------------------------------------------------------------------
# 6. Chấm điểm
# ---------------------------------------------------------------------------
def grade_image(
    warped_bgr: np.ndarray,
    config: dict,
    key: str,
    method: str,
    params: GradeParams | None = None,
    debug_dir=None,
) -> GradeResult:
    """Xám hóa, ngưỡng, fill ratio, quyết định và chấm theo key. Câu đúng khi đúng một ô khớp key."""
    if params is None:
        params = GradeParams()
    key = str(key)
    num_questions = len(config["questions"])
    if len(key) != num_questions:
        raise ValueError(
            f"Đáp án đúng có {len(key)} ký tự trong khi phiếu có {num_questions} câu. "
            "Hãy truyền key dài đúng số câu."
        )

    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)
    binary = binarize(gray, method, params)
    _save_debug(debug_dir, "01_gray.png", gray)
    _save_debug(debug_dir, "02_binary.png", binary)

    fill = compute_fill_ratios(binary, config, params)
    decided = decide(fill, config, params)

    flags = [
        status == "single" and answer == key[i]
        for i, (answer, status) in enumerate(zip(decided["answers"], decided["statuses"]))
    ]
    correct_count = int(sum(flags))
    blank_count = decided["statuses"].count("blank")
    multi_count = decided["statuses"].count("multi")
    wrong_count = sum(
        1 for status, flag in zip(decided["statuses"], flags)
        if status == "single" and not flag
    )
    score = round(correct_count / num_questions * params.total_score, 2)
    return GradeResult(
        answers=decided["answers"],
        statuses=decided["statuses"],
        student_id=decided["student_id"],
        exam_code=decided["exam_code"],
        key=key,
        correct_flags=flags,
        correct_count=correct_count,
        blank_count=blank_count,
        multi_count=multi_count,
        wrong_count=wrong_count,
        score=score,
        method=method,
        fill=fill,
    )


# ---------------------------------------------------------------------------
# 7. Vẽ kết quả
# ---------------------------------------------------------------------------
def _put_banner(canvas: np.ndarray, lines: list[str]) -> None:
    """Ghi vài dòng chữ không dấu ở góc trên, nền trắng cho dễ đọc."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thickness = 0.45, 1
    x0, y0, line_h = 78, 6, 16
    widths = [cv2.getTextSize(line, font, scale, thickness)[0][0] for line in lines]
    box_w = max(widths) + 10
    box_h = line_h * len(lines) + 6
    cv2.rectangle(canvas, (x0 - 4, y0), (x0 + box_w, y0 + box_h), (255, 255, 255), -1)
    for i, line in enumerate(lines):
        cv2.putText(
            canvas, line, (x0, y0 + (i + 1) * line_h - 3),
            font, scale, (0, 0, 0), thickness, cv2.LINE_AA,
        )


def draw_result(warped_bgr: np.ndarray, config: dict, result: GradeResult, key: str) -> np.ndarray:
    """Vòng xanh lá = chọn đúng; đỏ = chọn sai (kể cả multi); xanh dương mảnh = đáp án đúng khi sai/trống."""
    canvas = warped_bgr.copy()
    questions = _sorted_questions(config)
    radius = int(round(float(config["bubble_radius"]))) + 3
    key = str(key)
    green, red, blue = (0, 220, 0), (0, 0, 255), (255, 80, 0)

    for i, question in enumerate(questions):
        selected = set(result.answers[i])
        correct_label = key[i]
        is_correct = result.correct_flags[i]
        for bubble in question["bubbles"]:
            center = (int(round(bubble["cx"])), int(round(bubble["cy"])))
            label = bubble["label"]
            if label in selected:
                color = green if is_correct else red
                cv2.circle(canvas, center, radius, color, 2, cv2.LINE_AA)
            elif not is_correct and label == correct_label:
                cv2.circle(canvas, center, radius, blue, 1, cv2.LINE_AA)

    n = len(result.answers)
    _put_banner(canvas, [
        f"Diem: {result.score:.2f}  Dung: {result.correct_count}/{n}  "
        f"Sai: {result.wrong_count}  Trong: {result.blank_count}  Multi: {result.multi_count}",
        f"MSSV: {result.student_id}  Ma de: {result.exam_code}",
    ])
    return canvas


# ---------------------------------------------------------------------------
# 8. Xuất Excel
# ---------------------------------------------------------------------------
def export_excel(results: list[dict], path) -> None:
    """Ghi workbook 2 sheet Tong hop và Chi tiet. results: list dict {file, result}."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    detail_rows = []
    for item in results:
        name = item["file"]
        result: GradeResult = item["result"]
        summary_rows.append({
            "file": name,
            "ma so": result.student_id,
            "ma de": result.exam_code,
            "so cau dung": result.correct_count,
            "so cau sai": result.wrong_count,
            "bo trong": result.blank_count,
            "to nhieu o": result.multi_count,
            "diem": result.score,
            "phuong phap": result.method,
        })
        for i, (answer, status, flag) in enumerate(
            zip(result.answers, result.statuses, result.correct_flags)
        ):
            detail_rows.append({
                "file": name,
                "cau": i + 1,
                "dap an dung": result.key[i],
                "dap an chon": answer,
                "trang thai": status,
                "dung/sai": "dung" if flag else "sai",
            })
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Tong hop", index=False)
        pd.DataFrame(detail_rows).to_excel(writer, sheet_name="Chi tiet", index=False)
