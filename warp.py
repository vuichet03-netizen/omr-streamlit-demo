"""Nắn phiếu từ ảnh chụp điện thoại: tìm 4 marker góc và biến đổi phối cảnh.

Ảnh sau khi nắn có kích thước page.width x page.height (pixel chuẩn), tâm 4 marker
trùng config["markers"]["centers"]. Chỉ dùng xử lý ảnh cơ bản của OpenCV.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Tham số (không hard-code tọa độ phiếu; kích thước trang đọc từ JSON)
# ---------------------------------------------------------------------------
MAX_SIDE = 2000                 # cạnh dài tối đa khi đọc / khi tìm marker
GAUSSIAN_KSIZE = (5, 5)
ADAPTIVE_BLOCK_RATIO = 0.04     # blockSize = tỉ lệ cạnh ngắn, luôn lẻ
ADAPTIVE_BLOCK_MIN = 15
ADAPTIVE_C = 8
MORPH_KSIZE = 3
AREA_MIN_RATIO = 0.0003         # diện tích contour / diện tích ảnh
AREA_MAX_RATIO = 0.02
APPROX_EPS_RATIO = 0.04         # epsilon approxPolyDP = tỉ lệ chu vi
ASPECT_LO = 0.75                # rộng/cao của minAreaRect
ASPECT_HI = 1.33
SOLIDITY_MIN = 0.85             # diện tích contour / diện tích minAreaRect
AREA_SPREAD_MAX = 2.5           # max/min diện tích 4 marker được chọn

MSG_NOT_ENOUGH = (
    "Không tìm thấy đủ 4 ô đen ở góc, hãy chụp lại sao cho thấy rõ cả 4 góc và không bị che"
)
MSG_AREA_SPREAD = "Có thể marker góc bị che hoặc quá mờ"


class MarkerNotFound(Exception):
    """Không chọn được đúng 4 marker góc trên ảnh."""


# ===========================================================================
# 1. Đọc ảnh
# ===========================================================================
def load_image(src) -> np.ndarray:
    """Đọc ảnh từ đường dẫn hoặc bytes, sửa xoay EXIF, trả về BGR; cạnh dài tối đa MAX_SIDE."""
    try:
        if isinstance(src, (bytes, bytearray, memoryview)):
            image = Image.open(io.BytesIO(bytes(src)))
        else:
            image = Image.open(src)
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Không đọc được ảnh: {exc}") from exc

    width, height = image.size
    long_edge = max(width, height)
    if long_edge > MAX_SIDE:
        scale = MAX_SIDE / long_edge
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    rgb = np.asarray(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ===========================================================================
# 2. Tiện ích debug và hình học
# ===========================================================================
def _save_debug(debug_dir: Path | str | None, name: str, image: np.ndarray) -> None:
    """Ghi ảnh PNG vào debug_dir; imencode để tránh lỗi đường dẫn Unicode trên Windows."""
    if debug_dir is None:
        return
    folder = Path(debug_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise OSError(f"Không ghi được ảnh debug: {path}")
    path.write_bytes(buf.tobytes())


def _prepare_working_image(img_bgr: np.ndarray) -> tuple[np.ndarray, float]:
    """Thu nhỏ nếu cạnh dài > MAX_SIDE. Trả về (ảnh làm việc, tỉ lệ so với ảnh đầu vào)."""
    height, width = img_bgr.shape[:2]
    long_edge = max(height, width)
    if long_edge <= MAX_SIDE:
        return img_bgr, 1.0
    scale = MAX_SIDE / long_edge
    work = cv2.resize(
        img_bgr,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return work, scale


def _adaptive_block_size(height: int, width: int) -> int:
    """blockSize lẻ, tỉ lệ theo cạnh ngắn của ảnh."""
    block = int(min(height, width) * ADAPTIVE_BLOCK_RATIO)
    if block % 2 == 0:
        block += 1
    return max(block, ADAPTIVE_BLOCK_MIN)


def _contour_centroid(contour: np.ndarray) -> tuple[float, float] | None:
    """Trọng tâm contour bằng moments; None nếu diện tích ~ 0."""
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        return None
    return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]


def _binarize_markers(gray: np.ndarray) -> np.ndarray:
    """Ngưỡng thích nghi nghịch đảo rồi mở/đóng hình thái học nhẹ."""
    height, width = gray.shape[:2]
    block = _adaptive_block_size(height, width)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, ADAPTIVE_C,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MORPH_KSIZE, MORPH_KSIZE))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    return binary


# ===========================================================================
# 3. Lọc ứng viên marker
# ===========================================================================
def _is_marker_candidate(contour: np.ndarray, image_area: float) -> bool:
    """True nếu contour giống ô vuông đen đặc (diện tích, 4 đỉnh lồi, tỉ lệ, độ đặc)."""
    area = cv2.contourArea(contour)
    if area < AREA_MIN_RATIO * image_area or area > AREA_MAX_RATIO * image_area:
        return False
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, APPROX_EPS_RATIO * peri, True)
    if len(approx) != 4 or not cv2.isContourConvex(approx):
        return False
    # minAreaRect chịu được phiếu nghiêng; boundingRect theo trục sẽ loại marker khi ảnh nghiêng.
    _center, (rect_w, rect_h), _angle = cv2.minAreaRect(contour)
    if rect_w < 1 or rect_h < 1:
        return False
    short, long_side = min(rect_w, rect_h), max(rect_w, rect_h)
    ratio = short / long_side
    if ratio < ASPECT_LO or long_side / short > ASPECT_HI:
        return False
    if area / (rect_w * rect_h) < SOLIDITY_MIN:
        return False
    return True


def _collect_candidates(binary: np.ndarray) -> list[dict]:
    """Tìm contour và giữ những contour vượt bộ lọc marker."""
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(binary.shape[0] * binary.shape[1])
    candidates: list[dict] = []
    for contour in contours:
        if not _is_marker_candidate(contour, image_area):
            continue
        centroid = _contour_centroid(contour)
        if centroid is None:
            continue
        candidates.append({
            "contour": contour,
            "area": float(cv2.contourArea(contour)),
            "cx": centroid[0],
            "cy": centroid[1],
        })
    return candidates


def _similar_area_cluster(candidates: list[dict]) -> list[dict]:
    """Chọn cụm >= 4 ứng viên có diện tích lệch nhau không quá AREA_SPREAD_MAX, ưu tiên cụm to.

    Ô vuông nhỏ trang trí nhỏ hơn marker góc ~ 9 lần diện tích nên không cùng cụm.
    Ô CBCT / vật đen lớn hơn nhiều cũng bị loại vì không đủ 4 phần tử cùng cỡ.
    """
    ordered = sorted(candidates, key=lambda item: -item["area"])
    for seed in ordered:
        high = seed["area"]
        group = [
            item for item in ordered
            if item["area"] <= high and high / item["area"] <= AREA_SPREAD_MAX
        ]
        if len(group) >= 4:
            return group
    return []


def _pick_one_per_quadrant(candidates: list[dict]) -> dict[str, dict]:
    """Chia 4 góc phần tư quanh tâm các ứng viên; mỗi góc lấy ứng viên diện tích lớn nhất."""
    mean_x = float(np.mean([item["cx"] for item in candidates]))
    mean_y = float(np.mean([item["cy"] for item in candidates]))
    quadrants: dict[str, dict] = {}
    for item in candidates:
        if item["cx"] < mean_x and item["cy"] < mean_y:
            name = "tl"
        elif item["cx"] >= mean_x and item["cy"] < mean_y:
            name = "tr"
        elif item["cx"] >= mean_x and item["cy"] >= mean_y:
            name = "br"
        else:
            name = "bl"
        current = quadrants.get(name)
        if current is None or item["area"] > current["area"]:
            quadrants[name] = item
    return quadrants


def _order_corners(points: np.ndarray) -> np.ndarray:
    """Sắp 4 điểm theo thứ tự trên-trái, trên-phải, dưới-phải, dưới-trái (tổng x+y và hiệu y-x)."""
    pts = np.asarray(points, dtype=np.float32)
    total = pts[:, 0] + pts[:, 1]
    diff = pts[:, 1] - pts[:, 0]
    ordered = np.stack([
        pts[int(np.argmin(total))],
        pts[int(np.argmin(diff))],
        pts[int(np.argmax(total))],
        pts[int(np.argmax(diff))],
    ])
    return ordered.astype(np.float32)


def _draw_candidates(bgr: np.ndarray, candidates: list[dict]) -> np.ndarray:
    """Vẽ mọi ứng viên (xanh) lên bản sao ảnh."""
    canvas = bgr.copy()
    for item in candidates:
        cv2.drawContours(canvas, [item["contour"]], -1, (0, 180, 0), 2)
        cv2.circle(canvas, (int(item["cx"]), int(item["cy"])), 6, (0, 180, 0), -1)
    return canvas


def _draw_markers(bgr: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Vẽ 4 marker đã chọn (đỏ) kèm nhãn TL/TR/BR/BL."""
    canvas = bgr.copy()
    labels = ("TL", "TR", "BR", "BL")
    for (x, y), label in zip(points, labels):
        cv2.circle(canvas, (int(x), int(y)), 10, (0, 0, 255), 3)
        cv2.putText(
            canvas, label, (int(x) + 12, int(y) - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA,
        )
    return canvas


# ===========================================================================
# 4. Tìm 4 marker
# ===========================================================================
def find_markers(img_bgr: np.ndarray, debug_dir=None) -> np.ndarray:
    """Tìm 4 ô đen góc; trả về float32 shape (4, 2) thứ tự tl, tr, br, bl theo tọa độ ảnh đầu vào."""
    work, scale = _prepare_working_image(img_bgr)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, GAUSSIAN_KSIZE, 0)
    _save_debug(debug_dir, "01_gray.png", gray)
    _save_debug(debug_dir, "02_blur.png", blur)

    binary = _binarize_markers(blur)
    _save_debug(debug_dir, "03_threshold.png", binary)

    candidates = _collect_candidates(binary)
    _save_debug(debug_dir, "04_candidates.png", _draw_candidates(work, candidates))

    cluster = _similar_area_cluster(candidates)
    if len(cluster) < 4:
        raise MarkerNotFound(MSG_NOT_ENOUGH)
    quadrants = _pick_one_per_quadrant(cluster)
    if len(quadrants) < 4:
        raise MarkerNotFound(MSG_NOT_ENOUGH)

    chosen = [quadrants[name] for name in ("tl", "tr", "br", "bl")]
    areas = [item["area"] for item in chosen]
    if max(areas) / min(areas) > AREA_SPREAD_MAX:
        raise MarkerNotFound(MSG_AREA_SPREAD)

    work_points = np.array([[item["cx"], item["cy"]] for item in chosen], dtype=np.float32)
    work_points = _order_corners(work_points)
    _save_debug(debug_dir, "05_markers.png", _draw_markers(work, work_points))
    # Quy đổi về tọa độ ảnh đầu vào nếu đã thu nhỏ để xử lý.
    return (work_points / scale).astype(np.float32)


# ===========================================================================
# 5. Nắn phiếu
# ===========================================================================
def _page_size(config: dict) -> tuple[int, int]:
    """Đọc (width, height) pixel chuẩn từ config; thiếu thì raise ValueError."""
    page = config.get("page") or {}
    width, height = page.get("width"), page.get("height")
    if not width or not height:
        raise ValueError("File cấu hình thiếu page.width hoặc page.height.")
    return int(width), int(height)


def _marker_destinations(config: dict) -> np.ndarray:
    """4 tâm marker đích trong hệ tọa độ chuẩn, thứ tự tl, tr, br, bl."""
    centers = (config.get("markers") or {}).get("centers")
    if centers is None or len(centers) != 4:
        raise ValueError("File cấu hình phải có markers.centers gồm đúng 4 điểm.")
    return np.asarray(centers, dtype=np.float32)


def warp_sheet(img_bgr: np.ndarray, config: dict, debug_dir=None) -> np.ndarray:
    """Nắn ảnh về trang chuẩn bằng homography 4 điểm marker -> config['markers']['centers'].

    Homography 3x3 có 8 bậc tự do (sai khác một hệ số tỉ lệ). Mỗi cặp điểm tương ứng
    cho 2 phương trình, nên cần đúng 4 cặp (tl, tr, br, bl) — 3 điểm chỉ đủ affine,
    không nắn được phối cảnh (ảnh chụp lệch góc).
    """
    src = find_markers(img_bgr, debug_dir=debug_dir)
    dst = _marker_destinations(config)
    width, height = _page_size(config)
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        img_bgr, matrix, (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    _save_debug(debug_dir, "06_warped.png", warped)
    return warped
