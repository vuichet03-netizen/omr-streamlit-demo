# He thong cham trac nghiem OMR tu anh chup dien thoai

Do an mon Xu ly anh: sinh phieu, nan phieu bang 4 marker goc, cham diem
bang nguong hoa + fill ratio, giao dien Streamlit, cong cu thuc nghiem.

## 1. Cai dat (Python 3.10+)

```bash
cd omr_project
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Cau truc thu muc

```text
omr_project/
  constants.py        hang so dung chung (he toa do chuan, bo cuc phieu)
  sheet_generator.py  sinh phieu PDF/PNG + cau hinh JSON
  warp.py             doc anh, tim 4 marker, nan phieu
  grader.py           nguong hoa, fill ratio, cham diem, ve ket qua, xuat Excel
  app.py              giao dien Streamlit
  grade_cli.py        cham nhanh 1 anh tu dong lenh
  make_ground_truth.py sinh bai lam gia + ground truth
  build_manifest.py   quet data/images -> data/manifest.csv
  evaluate.py         danh gia toan bo he thong
  test_warp.py        kiem tra warp hang loat
  check_layout.py     kiem tra bo cuc phieu
  templates/          moi mau phieu: <slug>.json / .pdf / .png (+ .keys.json)
  data/images/        anh chup phieu
  data/ground_truth.csv  dap an tung cau (template, sheet_id, q, expected)
  data/ground_truth_id.csv  MSSV + ma de (template, sheet_id, student_id, exam_code)
  data/manifest.csv   danh sach anh danh gia (image, template, sheet_id, condition)
  results/            dau ra cua evaluate.py
  debug/              anh trung gian (khong commit)
```

## 3. Chay nhanh (da co san du lieu mau)

```bash
# Kiem tra warp hang loat (60/60 anh OK)
python test_warp.py

# Cham 1 anh bat ky (key = chuoi dap an dung, dai bang so cau)
python grade_cli.py --image data/images/t1_s01_binhthuong_01.jpg \
  --template templates/t1.json --key <chuoi_dap_an> --method adaptive

# Danh gia toan bo: warp + cham otsu/adaptive, so voi ground truth
python evaluate.py
# -> results/eval_detail.csv, results/eval_summary.csv,
#    results/accuracy_by_condition.png, results/fill_ratio_hist.png,
#    results/failures/ (10 ca sai nang nhat)

# Giao dien web
streamlit run app.py
```

## 4. Quy trinh lam them du lieu moi (neu muon mo rong)

```bash
# B1. Sinh cau hinh + phieu moi (qua giao dien Streamlit, tab Tao phieu),
#     hoac sua truc tiep file templates/<slug>.json
# B2. In phieu, to theo bang huong dan
python make_ground_truth.py --template templates/t1.json --sheets 8 --seed 42 --out data
#     -> sinh data/fill_guide_<template>_<sheet_id>.txt de nhin va to theo
# B3. Chup anh, dat ten dung quy tac {template}_{sheet_id}_{condition}_{n}.jpg
#     vi du: t1_s03_nghieng_01.jpg ; condition: binhthuong, nghieng,
#     thieusang, bongdo, nenlonxon (them tonhat neu can)
# B4. Quet lai manifest va chay danh gia
python build_manifest.py
python evaluate.py
```

## 5. Ket qua hien tai (60 anh, 2 template t1/t2 x 5 dieu kien x 2 phuong phap)

- Warp thanh cong: 100% (60/60).
- Adaptive vuot otsu ro o dieu kien kho (thieusang, bongdo, nenlonxon).
- Chi tiet xem `results/eval_summary.csv`; diem MSSV/ma de kem hon o vung
  bi loa sang (bong den gan goc ma de) — loi do dieu kien chup, khong phai thuat toan.

## 6. Luu y khi viet bao cao

- Moi toa do doc tu file JSON cau hinh, khong hard-code so cau/dap an/toa do.
- Chu ve len anh bang `cv2.putText` phai KHONG DAU.
- Moi buoc xu ly anh quan trong co tuy chon luu anh trung gian (`debug_dir`).
- Chi dung phep xu ly anh co ban cua OpenCV, khong dung thu vien OMR
  hay mo hinh hoc may co san.
