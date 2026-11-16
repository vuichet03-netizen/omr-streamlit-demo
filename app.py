"""Giao diện Streamlit chuyên nghiệp cho hệ thống chấm trắc nghiệm OMR.

Chạy:  streamlit run app.py
Dùng lại sheet_generator, warp, grader - không viết lại thuật toán.
Chỉ thay đổi lớp trình bày, giữ nguyên mọi logic nghiệp vụ.
"""

from __future__ import annotations

import io
import json
import logging
import re
import tempfile
import unicodedata
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st

import constants as C
from grader import GradeParams, GradeResult, draw_result, export_excel, grade_image
from sheet_generator import generate_sheet, make_preview, save_sheet
from warp import MarkerNotFound, load_image, warp_sheet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omr_app")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"

st.set_page_config(
    page_title="OMR Studio - Chấm trắc nghiệm",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ===========================================================================
# CSS an toàn: chỉ trang điểm nhẹ, không đụng tới header/sidebar của Streamlit
# ===========================================================================
def inject_style() -> None:
    """Nạp CSS trang trí: màu sắc + chuyển động nhẹ. Không ẩn header/toolbar."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Be Vietnam Pro', system-ui, sans-serif; }
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }

        :root { --ink: #0f172a; --brand1: #1d4ed8; --brand2: #7c3aed; --brand3: #db2777; }

        /* Topbar: kinh mo trang hien dai, lien mach voi nen trang */
        header[data-testid="stHeader"] {
            background: rgba(248, 250, 255, .75);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(15, 23, 42, .06);
        }
        div[data-testid="stToolbar"] { right: 1rem; }
        div[data-testid="stDecoration"] { display: none; }

        /* Nen mesh gradient sang, có chieu sau */
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(1000px 340px at 6% -60px, rgba(29,78,216,.16), transparent 60%),
                radial-gradient(820px 300px at 96% -20px, rgba(219,39,119,.12), transparent 60%),
                radial-gradient(760px 460px at 50% 118%, rgba(14,165,233,.12), transparent 60%),
                linear-gradient(180deg, #f8faff 0%, #f1f4fa 100%);
        }

        /* Sidebar ánh sáng thương hiệu: nền chàm than, chữ trắng dễ đọc */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b1533 0%, #1a2370 55%, #4c1d95 100%);
            border-right: 1px solid rgba(255,255,255,.08);
        }
        section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] div {
            color: #e8edf7 !important;
        }
        section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {
            color: #a9b4d0 !important;
        }
        section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] {
            background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
            border-radius: 12px; }
        .side-brand { display: flex; align-items: center; gap: 10px;
            margin: -38px 40px 2px 0; padding-top: 2px; }
        .side-badge { width: 38px; height: 38px; border-radius: 12px; display: flex;
            align-items: center; justify-content: center; font-size: 1.25rem; color: #fff;
            background: linear-gradient(135deg, #38bdf8, #818cf8 55%, #e879f9);
            box-shadow: 0 6px 16px rgba(56,189,248,.4); }
        .side-nav-gap { height: 22px; }
        section[data-testid="stSidebar"] div.stButton { margin-bottom: 4px; }
        section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
            background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.16);
            border-radius: 14px; padding: .55rem .8rem; font-weight: 600; text-align: left; }
        section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] p {
            color: #fff !important; }
        section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {
            background: rgba(255,255,255,.16); border-color: rgba(255,255,255,.30);
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(56,189,248,.25); }
        section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
            background: linear-gradient(120deg, #38bdf8, #818cf8 55%, #e879f9);
            border: none; border-radius: 14px; padding: .55rem .8rem; font-weight: 700;
            text-align: left; box-shadow: 0 8px 22px rgba(129,140,248,.45); opacity: 1; }
        section[data-testid="stSidebar"] div.stButton > button[kind="primary"] p {
            color: #fff !important; }
        section[data-testid="stSidebar"] div.stButton > button:disabled {
            opacity: 1; cursor: default; }

        /* Banner hero đầu trang: điểm nhấn màu sắc mạnh, nằm trong luồng trang */
        .hero-banner { position: relative; overflow: hidden; color: #fff;
            border-radius: 20px; padding: 26px 30px; margin-bottom: 16px;
            box-shadow: 0 18px 44px rgba(29,78,216,.30);
            animation: fade-up .5s ease both; }
        .hero-banner::before { content: ""; position: absolute; right: -60px; top: -80px;
            width: 260px; height: 260px; border-radius: 50%;
            background: radial-gradient(circle, rgba(255,255,255,.30), transparent 65%); }
        .hero-banner::after { content: ""; position: absolute; left: 30%; bottom: -90px;
            width: 340px; height: 180px; border-radius: 50%;
            background: radial-gradient(ellipse, rgba(255,255,255,.16), transparent 70%); }
        .hero-blue { background: linear-gradient(115deg, #0f2a6b, #1d4ed8 45%, #6d28d9 80%, #a21caf); }
        .hero-emerald { background: linear-gradient(115deg, #064e3b, #059669 45%, #0ea5e9 85%); }
        .hero-amber { background: linear-gradient(115deg, #7c2d12, #ea580c 50%, #d97706 80%, #a21caf); }
        .hero-rose { background: linear-gradient(115deg, #881337, #e11d48 48%, #7c3aed 88%); }
        .hero-banner .eyebrow { color: #fde68a; }
        .hero-banner h1 { margin: .1rem 0 .4rem 0; font-size: 1.8rem; font-weight: 800;
            letter-spacing: -.01em; color: #fff; }
        .hero-banner p { margin: 0; opacity: .94; font-size: .95rem; max-width: 780px; color: #f1f5f9; }
        .eyebrow { font-size: .72rem; letter-spacing: .14em; font-weight: 800;
            color: #4f46e5; margin-bottom: .1rem; }
        .chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: .7rem 0 .1rem 0; }
        .hero-banner .chip { color: #fff; background: rgba(255,255,255,.16);
            border: 1px solid rgba(255,255,255,.42); }
        .hero-banner .chip.hot { color: #052e22; background: #a7f3d0; border-color: #6ee7b7; }
        /* Banner cam: chip nen trang + chu cam dam de dat tuong phan WCAG AA chu nho */
        .hero-amber .chip { background: #fff; color: #9a3412; border-color: #fff; }
        .hero-amber .chip.hot { background: #ecfdf5; color: #065f46; border-color: #a7f3d0; }
        .hero-amber p { font-weight: 500; }
        .chip { font-size: .78rem; font-weight: 600; color: #1e40af;
            background: linear-gradient(180deg, #eef4ff, #e0eaff); border: 1px solid #c7d8fe;
            padding: 4px 13px; border-radius: 999px; white-space: nowrap;
            transition: transform .18s ease, box-shadow .18s ease; }
        .chip:hover { transform: translateY(-2px); box-shadow: 0 6px 14px rgba(29,78,216,.22); }
        .chip.hot { color: #065f46; background: linear-gradient(180deg, #ecfdf5, #d1fae5);
            border-color: #6ee7b7; }
        .muted { color: #64748b; font-size: .86rem; }

        /* Thẻ kết quả điểm: vào trang mượt */
        .score-strip { border-left: 5px solid #ccc; padding: 10px 14px; border-radius: 10px;
            background: linear-gradient(180deg, #ffffff, #f4f7ff); margin-bottom: 12px;
            box-shadow: 0 4px 14px rgba(15,23,42,.06);
            animation: fade-up .45s ease both; }
        .empty-box { border: 1.5px dashed #a5b4fc; background: linear-gradient(180deg, #f5f7ff, #eef2ff);
            border-radius: 14px; padding: 26px 18px; text-align: center; color: #475569;
            animation: fade-up .45s ease both; }

        /* Hieu ung xuat hien: chi ap dung cho hero, the diem, hop rong de tranh nhap nhay khi rerun */
        .hero-banner, .score-strip, .empty-box {
            animation: fade-up .5s ease both;
        }

        /* The container có vien: nang nhe khi di chuot */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #e6d3a3;
            transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            transform: translateY(-3px);
            box-shadow: 0 14px 30px rgba(30,64,175,.14);
            border-color: #d9bd7a !important;
        }

        /* Thẻ số liệu: viền màu gradient theo thứ tự */
        div[data-testid="stMetric"] {
            background: #ffffff; border: 1px solid #e3e9f5; border-top: 4px solid #6366f1;
            border-radius: 14px; padding: 10px 12px;
            transition: transform .2s ease, box-shadow .2s ease;
        }
        div[data-testid="stMetric"]:hover { transform: translateY(-3px);
            box-shadow: 0 12px 26px rgba(30,64,175,.16); }
        div[data-testid="column"]:nth-child(1) div[data-testid="stMetric"] { border-top-color: #6366f1; }
        div[data-testid="column"]:nth-child(2) div[data-testid="stMetric"] { border-top-color: #0ea5e9; }
        div[data-testid="column"]:nth-child(3) div[data-testid="stMetric"] { border-top-color: #10b981; }
        div[data-testid="column"]:nth-child(4) div[data-testid="stMetric"] { border-top-color: #f59e0b; }
        div[data-testid="stMetric"] label { color: #6366f1 !important; font-weight: 700 !important; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] div { color: #0f172a !important; }
        div[data-testid="stImage"] img { border-radius: 12px; transition: transform .25s ease; }
        div[data-testid="stImage"]:hover img { transform: scale(1.015); }

        @keyframes fade-up { from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); } }

        /* Nut bam: gradient + sang dan khi hover */
        div.stButton > button { border-radius: 10px; font-weight: 600;
            transition: transform .15s ease, box-shadow .15s ease, filter .15s ease; }
        div.stButton > button:hover { transform: translateY(-1px); filter: brightness(1.06); }
        div.stButton > button:active { transform: translateY(0); }
        div.stButton > button[kind="primary"] {
            background: linear-gradient(120deg, #1d4ed8, #7c3aed); border: none;
            box-shadow: 0 6px 16px rgba(79,70,229,.30); color: #fff; }
        div.stButton > button[kind="primary"]:hover {
            box-shadow: 0 10px 24px rgba(79,70,229,.45); }
        div.stDownloadButton > button { border-radius: 10px; font-weight: 600;
            transition: transform .15s ease, box-shadow .15s ease; }
        div.stDownloadButton > button:hover { transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(29,78,216,.25); }

        /* Ton trong nguoi dung muon giam chuyen dong */
        @media (prefers-reduced-motion: reduce) {
            .score-strip, .empty-box,
            .block-container div[data-testid="stVerticalBlockBorderWrapper"] { animation: none; }
            .chip, div.stButton > button, div.stDownloadButton > button,
            div[data-testid="stMetric"], div[data-testid="stImage"] img { transition: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str,
                 chips: list[str] | None = None, theme: str = "hero-blue") -> None:
    """Tiêu đề trang: banner gradient theo từng trang (không huy hiệu trạng thái)."""
    tags = ""
    if chips:
        tags = "".join(
            f"<span class='chip{' hot' if i == 0 else ''}'>{c}</span>" for i, c in enumerate(chips)
        )
        tags = f"<div class='chip-row'>{tags}</div>"
    st.markdown(
        f"<div class='hero-banner {theme}'><div class='eyebrow'>◉ OMR STUDIO · {eyebrow}</div>"
        f"<h1>{title}</h1><p>{subtitle}</p>{tags}</div>",
        unsafe_allow_html=True,
    )


def empty_state(title: str, hint: str) -> None:
    """Hộp trạng thái rỗng."""
    st.markdown(f"<div class='empty-box'><b>{title}</b><br><span>{hint}</span></div>",
                unsafe_allow_html=True)


def footer() -> None:
    """Chân trang gọn nhẹ."""
    st.divider()
    st.caption("OMR Studio · Hệ thống chấm trắc nghiệm tiện lợi - miễn phí - chuyên nghiệp")
    st.caption("Phương pháp: xám hóa, làm mờ Gaussian, ngưỡng Otsu / ngưỡng thích nghi, morphology, "
               "tìm contour 4 marker và biến đổi phối cảnh để nắn phiếu.")


# ===========================================================================
# Tien ich (giu nguyen logic)
# ===========================================================================
def slugify(text: str) -> str:
    """Bo dau, khoang trang -> slug [a-z0-9-]."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()


def list_template_slugs() -> list[str]:
    """Danh sách mẫu phiếu (stem cua *.json, bo *.keys.json)."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        path.stem
        for path in TEMPLATE_DIR.glob("*.json")
        if not path.name.endswith(".keys.json")
    )


def config_path(slug: str) -> Path:
    """Đường dẫn file cấu hình mẫu."""
    return TEMPLATE_DIR / f"{slug}.json"


def keys_path(slug: str) -> Path:
    """Đường dẫn file đáp án của mẫu."""
    return TEMPLATE_DIR / f"{slug}.keys.json"


@st.cache_data(show_spinner=False)
def load_config(slug: str) -> dict:
    """Đọc JSON cấu hình mẫu phiếu."""
    with open(config_path(slug), encoding="utf-8") as f:
        return json.load(f)


def load_keys(slug: str) -> dict[str, str]:
    """Doc dict {ten ma de: chuoi đáp án}."""
    path = keys_path(slug)
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Không đọc được %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_keys(slug: str, keys: dict[str, str]) -> None:
    """Ghi file đáp án JSON."""
    with open(keys_path(slug), "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)


def choice_labels_of(config: dict) -> list[str]:
    """Nhãn đáp án của mẫu (A, B, C, ...)."""
    return list(config.get("choice_labels") or C.CHOICE_LABELS_ALL[: config["params"]["num_choices"]])


def validate_key_string(text: str, labels: list[str], num_questions: int) -> str:
    """Chuan hoa chuoi đáp án; raise ValueError tieng Viet neu sai."""
    raw = "".join(text.split()).upper()
    allowed = "".join(labels)
    if len(raw) != num_questions:
        raise ValueError(
            f"Chuỗi đáp án có {len(raw)} ký tự, phiếu có {num_questions} câu. "
            "Hãy dán đúng số ký tự (không khoảng trắng)."
        )
    bad = [ch for ch in raw if ch not in allowed]
    if bad:
        raise ValueError(
            f"Ký tự không hợp lệ: {''.join(sorted(set(bad)))}. "
            f"Chỉ dùng các nhãn {', '.join(labels)}."
        )
    return raw


def match_saved_key(exam_code: str, keys: dict[str, str]) -> str | None:
    """Tìm tên đáp án đã lưu trùng mã đề đọc từ phiếu."""
    code = (exam_code or "").strip()
    if not code or "?" in code:
        return None
    if code in keys:
        return code
    compact = code.replace(" ", "")
    for name in keys:
        if compact == name.replace(" ", ""):
            return name
        digits = "".join(ch for ch in name if ch.isdigit())
        if digits and digits == compact:
            return name
    return None


def bgr_to_rgb(image):
    """BGR OpenCV -> RGB de st.image hien thi dung mau."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def excel_bytes(rows: list[dict]) -> bytes:
    """Goi export_excel vao file tam, tra ve noi dung xlsx."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        export_excel(rows, tmp_path)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


@st.cache_data(show_spinner="Đang vẽ phiếu...")
def cached_preview_png(exam_name: str, num_questions: int, num_choices: int) -> bytes:
    """Sinh phiếu và trả về PNG xem trước (PAGE_W x PAGE_H)."""
    image, _config = generate_sheet(
        {"exam_name": exam_name, "num_questions": num_questions, "num_choices": num_choices}
    )
    preview = make_preview(image)
    buf = io.BytesIO()
    preview.save(buf, format="PNG")
    return buf.getvalue()


def score_color(score: float, total: float = 10.0) -> str:
    """Màu thẻ điểm: xanh / cam / đỏ theo mức điểm."""
    ratio = score / total if total else 0
    if ratio >= 0.8:
        return "#059669"
    if ratio >= 0.5:
        return "#d97706"
    return "#dc2626"


def score_label(score: float, total: float = 10.0) -> str:
    """Nhãn xếp loại gọn cho thẻ điểm."""
    ratio = score / total if total else 0
    if ratio >= 0.8:
        return "Xuất sắc"
    if ratio >= 0.65:
        return "Khá"
    if ratio >= 0.5:
        return "Đạt"
    return "Cần xem lại"


def template_summary(slug: str) -> str:
    """Dòng mô tả ngắn cho một mẫu phiếu, dùng trong sidebar/selectbox."""
    try:
        cfg = load_config(slug)
        n_q = cfg["params"]["num_questions"]
        n_c = cfg["params"]["num_choices"]
        n_k = len(load_keys(slug))
        return f"{slug} — {n_q} câu × {n_c} đáp án · {n_k} mã đề"
    except (OSError, json.JSONDecodeError, KeyError):
        return slug


# ===========================================================================
# Dieu huong: nut bam truc tiep trong sidebar
# ===========================================================================
def render_sidebar() -> str:
    """Sidebar sáng: logo, điều hướng nút bấm, kho mẫu. Trả về trang được chọn."""
    with st.sidebar:
        st.markdown("<div class='side-brand'><div class='side-badge'>◉</div>"
                    "<div><b style='font-size:1.05rem'>OMR Studio</b><br>"
                    "<span style='font-size:.78rem'>Chấm trắc nghiệm từ ảnh chụp</span></div></div>",
                    unsafe_allow_html=True)
        st.markdown("<div class='side-nav-gap'></div>", unsafe_allow_html=True)
        if "nav_page" not in st.session_state:
            st.session_state["nav_page"] = "home"
        nav_items = [("home", "🏠 Tổng quan"), ("create", "📄 Tạo phiếu"),
                     ("keys", "🔑 Đáp án"), ("grade", "✅ Chấm bài")]
        for nav_key, nav_label in nav_items:
            is_active = st.session_state["nav_page"] == nav_key
            if is_active:
                st.button(nav_label, key=f"nav-{nav_key}",
                          use_container_width=True, type="primary", disabled=True)
            else:
                if st.button(nav_label, key=f"nav-{nav_key}", use_container_width=True):
                    st.session_state["nav_page"] = nav_key
                    st.rerun()
        page = st.session_state["nav_page"]
        st.divider()
        slugs = list_template_slugs()
        st.markdown(f"**Kho mẫu phiếu ({len(slugs)})**")
        if slugs:
            for slug in slugs[:8]:
                st.caption(f"• {template_summary(slug)}")
            if len(slugs) > 8:
                st.caption(f"… và {len(slugs) - 8} mẫu khác")
        else:
            st.info("Chưa có mẫu. Vào trang Tạo phiếu để bắt đầu.")
    return page


# ===========================================================================
# Trang chủ
# ===========================================================================
def render_home() -> None:
    """Trang tổng quan: 3 bước, trạng thái dữ liệu, mẹo chụp ảnh."""
    page_header(
        "TỔNG QUAN", "Hệ thống chấm trắc nghiệm OMR",
        "Tạo phiếu in ra giấy, chụp bằng điện thoại, hệ thống tự động nắn phiếu theo 4 marker, "
        "đọc ô tô bằng fill ratio và chấm điểm theo đáp án từng mã đề.",
        ["OpenCV thuần túy", "Miễn phí 100%", "Chạy ngay trên web"],
        "hero-blue",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("**BƯỚC 1 · 📄 Tạo phiếu in**")
            st.caption("Chọn số câu 10–80, số đáp án 2–5. Tải PDF A4 để in, cấu hình lưu JSON.")
    with c2:
        with st.container(border=True):
            st.markdown("**BƯỚC 2 · 🔑 Nhập đáp án**")
            st.caption("Lưu đáp án theo từng mã đề. Mã đề 3 chữ số trên phiếu sẽ tự khớp khi chấm.")
    with c3:
        with st.container(border=True):
            st.markdown("**BƯỚC 3 · ✅ Chấm hàng loạt**")
            st.caption("Tải nhiều ảnh cùng lúc, xem từng bài có khoanh lỗi, tải Excel tổng hợp.")

    with st.container(border=True):
        st.markdown("**Trạng thái dữ liệu**")
        st.caption("Tổng quan nhanh thư mục templates/ và data/")
        slugs = list_template_slugs()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Mẫu phiếu", len(slugs))
        m2.metric("Mã đề đã lưu", sum(len(load_keys(s)) for s in slugs))
        image_dir = BASE_DIR / "data" / "images"
        m3.metric("Ảnh trong data/images",
                  len(list(image_dir.glob("*"))) if image_dir.is_dir() else 0)
        results_dir = BASE_DIR / "results"
        m4.metric("File trong results/",
                  len(list(results_dir.glob("*"))) if results_dir.is_dir() else 0)
        if slugs:
            st.divider()
            rows = []
            for slug in slugs:
                try:
                    cfg = load_config(slug)
                    rows.append({
                        "Mẫu": slug,
                        "Số câu": cfg["params"]["num_questions"],
                        "Số đáp án": cfg["params"]["num_choices"],
                        "Mã đề": len(load_keys(slug)),
                    })
                except (OSError, json.JSONDecodeError, KeyError):
                    rows.append({"Mẫu": slug, "Số câu": "?", "Số đáp án": "?",
                                 "Mã đề": len(load_keys(slug))})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            empty_state("Chưa có mẫu phiếu nào", "Bắt đầu ở trang Tạo phiếu để sinh mẫu đầu tiên.")

    with st.container(border=True):
        st.markdown("**Mẹo chụp ảnh đạt điểm cao**")
        t1, t2, t3 = st.columns(3)
        t1.markdown("**💡 Ánh sáng**")
        t1.caption("Đủ sáng, tránh bóng đổ mạnh. Đặt phiếu trên nền phẳng tương phản.")
        t2.markdown("**📐 Góc chụp**")
        t2.caption("Chụp thẳng từ trên xuống, lấy trọn tờ giấy, thấy rõ 4 ô đen góc.")
        t3.markdown("**✏️ Cách tô**")
        t3.caption("Tô kín ô bằng bút chì, không lem ra ngoài, không dùng bút mực.")
    footer()


# ===========================================================================
# Trang 1 - Tạo phiếu (giu logic)
# ===========================================================================
def render_create() -> None:
    """Sinh phiếu in và lưu mẫu vào templates/."""
    page_header(
        "TẠO PHIẾU", "Tạo phiếu trả lời",
        "Phiếu luôn có mã số sinh viên (11 số) và mã đề (3 số). Mỗi cấu hình được lưu thành "
        "bộ 3 file PDF / PNG / JSON để tải sử dụng.",
        ["PDF khổ A4", "10–80 câu", "2–5 đáp án / câu"],
        "hero-emerald",
    )
    left, right = st.columns([5, 7])
    with left:
        with st.container(border=True):
            st.markdown("**Thông số phiếu**")
            st.caption("Tối đa 80 câu (mỗi khối 10 câu, 4 khối mỗi hàng, 2 hàng).")
            with st.form("form_create"):
                exam_name = st.text_input("Tên kỳ thi (lưu trong file cấu hình, không in lên phiếu)", value="")
                col_a, col_b = st.columns(2)
                with col_a:
                    num_questions = st.number_input(
                        "Số câu", min_value=C.MIN_QUESTIONS, max_value=C.MAX_QUESTIONS, value=40, step=1,
                    )
                with col_b:
                    choice_options = {
                        n: f"{n} đáp án ({''.join(C.CHOICE_LABELS_ALL[:n])})"
                        for n in range(C.MIN_CHOICES, C.MAX_CHOICES + 1)
                    }
                    num_choices = st.selectbox(
                        "Số đáp án mỗi câu",
                        options=list(choice_options),
                        index=2,
                        format_func=lambda n: choice_options[n],
                    )
                slug_in = st.text_input("Tên mẫu (slug)", value="mau-phieu",
                                        help="Chữ, số, dấu gạch ngang. Không dùng dấu '_'.")
                overwrite = st.checkbox("Ghi đè nếu mẫu đã tồn tại")
                col_p, col_s = st.columns(2)
                with col_p:
                    do_preview = st.form_submit_button("👁 Xem trước", use_container_width=True)
                with col_s:
                    do_save = st.form_submit_button("💾 Lưu mẫu", type="primary", use_container_width=True)
        with st.container(border=True):
            st.markdown("**Mỗi mẫu gồm 3 file (+1 file đáp án)**")
            st.caption("Lưu trong thư mục templates/ để các trang khác dùng lại.")
            st.markdown("`slug.pdf` — bản in khổ A4 · `slug.png` — ảnh xem trước · "
                        "`slug.json` — tọa độ ô tròn · `slug.keys.json` — đáp án theo mã đề")

    params = {"exam_name": exam_name, "num_questions": int(num_questions), "num_choices": int(num_choices)}
    if do_preview:
        try:
            png = cached_preview_png(params["exam_name"], params["num_questions"], params["num_choices"])
            st.session_state["preview_png"] = png
        except ValueError as exc:
            st.error(str(exc))
            logger.info("Xem trước that bai: %s", exc)

    with right:
        with st.container(border=True):
            st.markdown(f"**Bản vẽ trực tiếp** — {params['num_questions']} câu × "
                        f"{params['num_choices']} đáp án "
                        f"({''.join(C.CHOICE_LABELS_ALL[:int(params['num_choices'])])})")
            if "preview_png" in st.session_state:
                st.image(st.session_state["preview_png"], caption="Xem trước phiếu",
                         use_container_width=True)
            else:
                empty_state("Chưa có bản xem trước", "Bấm Xem trước để vẽ phiếu ngay tại đây.")

    if do_save:
        slug = slugify(slug_in) or "mau-phieu"
        if not re.fullmatch(C.TEMPLATE_SLUG_PATTERN, slug):
            st.error(f"Tên mẫu '{slug}' không hợp lệ. Chỉ dùng chữ, số và dấu '-' (không dấu '_').")
            return
        dest = config_path(slug)
        if dest.exists() and not overwrite:
            st.warning(f"Mẫu '{slug}' đã có trong templates/. Đánh dấu Ghi đè rồi bấm Lưu lần nữa.")
            return
        try:
            save_sheet(params, TEMPLATE_DIR, slug)
            st.session_state["saved_slug"] = slug
            st.session_state["saved_pdf"] = (TEMPLATE_DIR / f"{slug}.pdf").read_bytes()
            load_config.clear()
            st.success(f"Đã lưu templates/{slug}.pdf, {slug}.png, {slug}.json")
        except ValueError as exc:
            st.error(str(exc))
        except OSError:
            logger.exception("Lỗi ghi file mẫu")
            st.error("Không ghi được file mẫu. Hãy kiểm tra quyền thư mục templates/.")

    if st.session_state.get("saved_pdf") and st.session_state.get("saved_slug"):
        slug = st.session_state["saved_slug"]
        st.download_button("⬇ Tải PDF để in", data=st.session_state["saved_pdf"],
                           file_name=f"{slug}.pdf", mime="application/pdf")
    footer()


# ===========================================================================
# Trang 2 - Đáp án (giu logic)
# ===========================================================================
def render_keys() -> None:
    """Nhập và lưu đáp án đúng theo từng mã đề."""
    page_header(
        "ĐÁP ÁN", "Đáp án đúng theo mã đề",
        "Mỗi mã đề lưu một chuỗi đáp án. Khi chấm, mã đề 3 chữ số đọc từ phiếu sẽ tự khớp "
        "với đáp án đã lưu — không cần chọn tay từng bài.",
        ["Tự khớp mã đề", "Chuỗi dài = số câu", "Lưu file JSON"],
        "hero-amber",
    )
    slugs = list_template_slugs()
    if not slugs:
        empty_state("Chưa có mẫu phiếu", "Hãy tạo mẫu ở trang Tạo phiếu trước.")
        return
    slug = st.selectbox("Mẫu phiếu", slugs, format_func=template_summary)
    try:
        config = load_config(slug)
    except (OSError, json.JSONDecodeError):
        st.error(f"Không đọc được templates/{slug}.json")
        return
    num_questions = int(config["params"]["num_questions"])
    labels = choice_labels_of(config)
    st.info(f"Mẫu {slug} có {num_questions} câu, nhãn {', '.join(labels)}. "
            f"Chuỗi đáp án phải dài đúng {num_questions} ký tự.", icon="📋")

    c_form, c_list = st.columns([6, 6])
    with c_form:
        with st.container(border=True):
            st.markdown("**Thêm / cập nhật đáp án**")
            key_name = st.text_input("Tên mã đề", value="101",
                                     help="Ví dụ: 101. Trùng mã đề tô trên phiếu thì trang Chấm bài tự chọn.")
            mode = st.radio("Cách nhập", ("Dán chuỗi", "Bảng từng câu"), horizontal=True)
            key_string = ""
            if mode == "Dán chuỗi":
                pasted = st.text_area("Chuỗi đáp án",
                                      placeholder=f"ABCDABCD... ({num_questions} ký tự)", height=110)
                key_string = pasted
                typed = len("".join(key_string.split()))
                if key_string.strip():
                    st.progress(min(1.0, typed / max(1, num_questions)),
                                text=f"Đã nhập {typed}/{num_questions} ký tự")
                    if typed != num_questions:
                        st.caption("Chưa đủ độ dài — bổ sung hoặc xóa bớt trước khi lưu.")
            else:
                default_rows = [{"Câu": i, "Đáp án": labels[0]} for i in range(1, num_questions + 1)]
                table = st.data_editor(
                    pd.DataFrame(default_rows),
                    column_config={
                        "Câu": st.column_config.NumberColumn(disabled=True),
                        "Đáp án": st.column_config.SelectboxColumn(options=labels),
                    },
                    hide_index=True,
                    num_rows="fixed",
                    use_container_width=True,
                    height=320,
                )
                key_string = "".join(str(v) for v in table["Đáp án"].tolist())
            if st.button("💾 Lưu đáp án", type="primary", use_container_width=True):
                name = " ".join(key_name.split())
                if not name:
                    st.error("Hãy nhập tên mã đề.")
                else:
                    try:
                        keys = load_keys(slug)
                        keys[name] = validate_key_string(key_string, labels, num_questions)
                        save_keys(slug, keys)
                        st.success(f"Đã lưu đáp án «{name}» vào {slug}.keys.json")
                    except ValueError as exc:
                        st.error(str(exc))

    with c_list:
        with st.container(border=True):
            st.markdown("**Đáp án đã lưu**")
            st.caption("Mỗi thẻ là một mã đề, kèm nút xóa.")
            keys = load_keys(slug)
            if not keys:
                empty_state("Chưa có đáp án nào", "Nhập chuỗi đáp án bên trái rồi bấm Lưu.")
            for name, value in list(keys.items()):
                with st.container(border=True):
                    col_n, col_d = st.columns([4, 1])
                    with col_n:
                        st.markdown(f"**{name}** · `{len(value)} câu`")
                        st.code(value if len(value) <= 60 else value[:57] + "...", language=None)
                    with col_d:
                        confirm_key = f"confirm-del-{slug}-{name}"
                        if st.session_state.get(confirm_key):
                            if st.button("Chắc chắn?", key=f"yes-{slug}-{name}"):
                                keys.pop(name, None)
                                save_keys(slug, keys)
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        else:
                            if st.button("Xóa", key=f"del-{slug}-{name}"):
                                st.session_state[confirm_key] = True
                                st.rerun()
    footer()


def _grade_uploads(uploads, config: dict, keys: dict[str, str], key_name: str,
                   default_key: str, method: str, params: GradeParams) -> tuple[list, list, list]:
    """Nắn và chấm từng ảnh; lỗi một ảnh không dừng các ảnh còn lại."""
    results: list[dict] = []
    notes: list[str] = []
    warnings: list[str] = []
    progress = st.progress(0, text="Đang chấm...")
    for idx, uploaded in enumerate(uploads):
        name = uploaded.name
        try:
            img_bgr = load_image(uploaded.getvalue())
            warped = warp_sheet(img_bgr, config)
            probe = grade_image(warped, config, default_key, method, params)
            matched = match_saved_key(probe.exam_code, keys)
            if matched and matched != key_name:
                used_key_name, used_key = matched, keys[matched]
                result = grade_image(warped, config, used_key, method, params)
                notes.append(f"Anh «{name}»: mã đề trên phiếu là {probe.exam_code}, đã dùng đáp án «{matched}».")
            else:
                used_key_name, used_key, result = key_name, default_key, probe
            annotated = draw_result(warped, config, result, used_key)
            results.append({"file": name, "result": result, "image_rgb": bgr_to_rgb(annotated),
                            "key_name": used_key_name})
        except MarkerNotFound as exc:
            logger.info("MarkerNotFound %s: %s", name, exc)
            warnings.append(f"Anh «{name}»: {exc}")
        except Exception:
            logger.exception("Lỗi khi chấm %s", name)
            warnings.append(f"Anh «{name}»: không chấm được. Hãy chụp lại sao cho thấy đủ 4 ô đen góc.")
        progress.progress((idx + 1) / max(1, len(uploads)), text=f"Đã chấm {idx + 1}/{len(uploads)} ảnh")
    progress.empty()
    return results, notes, warnings


# ===========================================================================
# Trang 3 - Chấm bài (giu logic)
# ===========================================================================
def render_grade() -> None:
    """Nắn phiếu, chấm điểm, xem kết quả và tải Excel."""
    page_header(
        "CHẤM BÀI", "Chấm bài từ ảnh chụp",
        "Tải nhiều ảnh cùng lúc. Nên chụp thẳng, đủ sáng, thấy rõ 4 ô đen góc để nhận marker ổn định.",
        ["Chấm nhiều ảnh", "Tự khớp mã đề", "Xuất Excel 2 sheet"],
        "hero-rose",
    )
    slugs = list_template_slugs()
    if not slugs:
        empty_state("Chưa có mẫu phiếu", "Hãy tạo mẫu ở trang Tạo phiếu trước.")
        return
    slug = st.selectbox("Mẫu phiếu", slugs, key="grade_slug", format_func=template_summary)
    try:
        config = load_config(slug)
    except (OSError, json.JSONDecodeError):
        st.error(f"Không đọc được templates/{slug}.json")
        return
    keys = load_keys(slug)
    if not keys:
        st.warning("Mẫu này chưa có đáp án. Hãy lưu đáp án ở trang Đáp án trước khi chấm.")
        return

    with st.container(border=True):
        st.markdown("**Cấu hình chấm**")
        st.caption("Ngưỡng nâng cao chỉ nên đổi khi kết quả bất thường. Vòng xanh: đúng · "
                   "Vòng đỏ: sai · Vòng xanh dương: đáp án đúng.")
        top1, top2 = st.columns([5, 4])
        with top1:
            key_name = st.selectbox("Mã đề mặc định (đáp án đúng)", list(keys.keys()))
            st.caption(f"Chuỗi {len(keys[key_name])} ký tự · tự khớp nếu phiếu tô mã đề khác.")
        with top2:
            method_label = st.radio("Phương pháp ngưỡng", ("Thích nghi", "Otsu"), horizontal=True)
            st.caption("Thích nghi tốt khi ánh sáng không đều; Otsu nhanh khi ánh sáng đều.")
        with st.expander("⚙ Ngưỡng nâng cao (t_abs, t_rel, adaptive)"):
            c1, c2 = st.columns(2)
            with c1:
                t_abs = st.slider("t_abs (fill tối thiểu để nhận ô tô)", 0.10, 0.80, 0.40, 0.05)
                adaptive_block = st.slider("Cửa sổ thích nghi (số lẻ)", 11, 81, 41, 2,
                    help="Kích thước vùng xung quanh mỗi ô dùng để tính ngưỡng riêng. Số lẻ, càng lớn càng ít bị ảnh hưởng bởi bóng đổ cục bộ.")
            with c2:
                t_rel = st.slider("t_rel (tỉ lệ so với ô đậm nhất trong câu)", 0.30, 0.90, 0.60, 0.05)
                adaptive_c = st.slider("Hằng số trừ (C)", 2, 20, 10, 1,
                    help="Giá trị trừ bớt khỏi ngưỡng trung bình của vùng. Số càng lớn, ô tô nhạt càng khó bị nhận nhầm thành đã tô.")
    default_key = keys[key_name]
    method = "adaptive" if method_label == "Thích nghi" else "otsu"
    params = GradeParams(t_abs=float(t_abs), t_rel=float(t_rel),
                         adaptive_block=int(adaptive_block), adaptive_c=int(adaptive_c))

    uploads = st.file_uploader("Ảnh phiếu (có thể chọn nhiều file)",
                               type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if not uploads:
        empty_state("Kéo-thả ảnh vào đây để bắt đầu", "Hỗ trợ JPG / PNG, chấm nhiều bài trong một lần.")
        return

    signature = (slug, key_name, method, float(t_abs), float(t_rel),
                 int(adaptive_block), int(adaptive_c),
                 tuple((u.name, u.size) for u in uploads))
    if st.session_state.get("grade_signature") != signature:
        results, notes, warnings = _grade_uploads(uploads, config, keys, key_name, default_key, method, params)
        st.session_state.update(grade_signature=signature, grade_results=results,
                                grade_notes=notes, grade_warnings=warnings)
    results = st.session_state.get("grade_results") or []
    notes = st.session_state.get("grade_notes") or []
    warnings = st.session_state.get("grade_warnings") or []

    for message in warnings:
        st.warning(message)
    for note in notes:
        st.info(note)
    if not results:
        return

    scores = [item["result"].score for item in results]
    avg = sum(scores) / len(scores)
    good = sum(1 for s in scores if s >= 8.0)
    low = sum(1 for s in scores if s < 5.0)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Số bài", len(results))
    k2.metric("Điểm trung bình", f"{avg:.2f}")
    k3.metric("Từ 8.0 trở lên", good)
    k4.metric("Dưới 5.0", low)
    if len(results) > 1:
        with st.container(border=True):
            st.markdown("**Biểu đồ điểm**")
            st.bar_chart(pd.DataFrame({"Điểm": scores}, index=[i["file"] for i in results]))

    for item in results:
        result: GradeResult = item["result"]
        color = score_color(result.score)
        label = score_label(result.score)
        with st.expander(f"{item['file']} — {result.score:.2f} điểm · {label}",
                         expanded=len(results) == 1):
            st.markdown(
                f"<div class='score-strip' style='border-color:{color}'>"
                f"<b style='font-size:1.4rem;color:{color}'>{result.score:.2f} điểm</b>"
                f" · {label} · {item['key_name']}<br>"
                f"<span class='muted'>Đúng <b>{result.correct_count}/{len(result.answers)}</b> · "
                f"Sai {result.wrong_count} · Trống {result.blank_count} · Multi {result.multi_count} · "
                f"MSSV: <b>{result.student_id}</b> · Mã đề: <b>{result.exam_code}</b></span></div>",
                unsafe_allow_html=True,
            )
            c_img, c_detail = st.columns([7, 5])
            with c_img:
                st.image(item["image_rgb"],
                         caption=f"{item['file']} — xanh: đúng · đỏ: sai · xanh dương: đáp án đúng",
                         use_container_width=True)
            with c_detail:
                st.markdown("**Chi tiết từng câu**")
                detail = pd.DataFrame([{
                    "Câu": i + 1, "Chọn": a or "—", "Đúng": result.key[i],
                    "TT": s, "KQ": "✓" if f else "✗",
                } for i, (a, s, f) in enumerate(zip(result.answers, result.statuses, result.correct_flags))])
                st.dataframe(detail, hide_index=True, use_container_width=True, height=380)

    with st.container(border=True):
        st.markdown("**Bảng điểm tất cả các bài**")
        st.caption("Sheet Tổng hợp và Chi tiết nằm trong file Excel.")
        table = pd.DataFrame([{
            "file": item["file"], "mã số": item["result"].student_id, "mã đề": item["result"].exam_code,
            "đáp án đúng": item["key_name"], "số câu đúng": item["result"].correct_count,
            "bỏ trống": item["result"].blank_count, "tô nhiều ô": item["result"].multi_count,
            "điểm": item["result"].score,
        } for item in results])
        st.dataframe(table, hide_index=True, use_container_width=True)
        st.download_button(
            "⬇ Tải Excel tổng hợp",
            data=excel_bytes([{"file": i["file"], "result": i["result"]} for i in results]),
            file_name="ket_qua_cham.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    footer()


# ===========================================================================
# Diem vao
# ===========================================================================
def main() -> None:
    """Điều hướng sidebar: tổng quan, tạo phiếu, đáp án, chấm bài."""
    inject_style()
    page = render_sidebar()
    if page == "home":
        render_home()
    elif page == "create":
        render_create()
    elif page == "keys":
        render_keys()
    else:
        render_grade()


if __name__ == "__main__":
    main()
