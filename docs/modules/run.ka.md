# დოკუმენტაცია — `src/run.py`

> 🇬🇧 English version: [run.md](run.md)

**როლი:** მთელი კონვეიერის ორკესტრაცია და CSV/Excel გამოსავალების ჩაწერა.
**დამოკიდებულება:** `load_data`, `segments`, `metrics`, `recommend`. **გამოიყენება:** შენ (CLI შესასვლელი წერტილი).

---

## 1. რას აკეთებს (რიგით)
1. `load_analysis_frame()` → პოლის-დონის ჩარჩო.
2. `add_segments()` + `build_segment_key()` → ოთხი განზომილება + კომპოზიტური `segment`.
3. `aggregate_overall()` → პორტფელის ერთრიგიანი შეჯამება.
4. `aggregate_by(["segment"])` → 1,264 კომპოზიტური სეგმენტი; `recommend()` → კორექციები.
5. `aggregate_by()` ერთგანზომილებიან გახლეჩებზე (ასაკი, ავტომობილი, ფრანშიზა, SI, ასაკი×ავტომობილი, ავტომობილი×ფრანშიზა).
6. ჩაწერე გამოსავალები; დაბეჭდე პორტფელი + ტოპ-15 სეგმენტი.

---

## 2. ჩაწერილი გამოსავალები
| ფაილი | შემცველობა |
|---|---|
| `output/segment_recommendations.csv` | 1,264 სეგმენტი კორექციებითა და მოქმედებით (UTF-8-BOM) |
| `output/portfolio_overall.csv` | ერთრიგიანი პორტფელის ჯამები |
| `output/casco_segment_analysis.xlsx` | ფურცლები: `Portfolio_Overall`, `Segment_Recommendations`, + 6 გახლეჩის ფურცელი |

Excel ჩაწერილია `pd.ExcelWriter(engine="openpyxl")`-ით; ფურცლის სახელები შემოკლებულია 31 სიმბოლომდე (Excel ლიმიტი).

---

## 3. კონსოლის მდგრადობა
```python
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
```
ქართული სეგმენტის ლეიბლები უსაფრთხოდ იბეჭდება Windows-ზე (cp1252-მა თორემ `UnicodeEncodeError` აიგდებოდა).

---

## 4. როგორ უშვათ
```bash
python -m src.run
```
დამოკიდებულებები: `pandas`, `numpy`, `openpyxl`.

---

## 5. ერთმოდულური კვლევა
თითოეული მოდული ასევე მუშაობს მარტოდ (`python -m src.load_data`, `src.segments`, `src.metrics`, `src.recommend`) და ბეჭდავს სწრაფ შეჯამებას — სასარგებლოა ნაბიჯ-ნაბიჯ დებაგისთვის.

## 6. ვერიფიკაცია
- [x] გამოსვლის კოდი 0; სამივე გამოსავალი ფაილი შექმნილია
- [x] `segment_recommendations.csv` აქვს 1,264 მონაცემთა რიგი
- [x] პორტფელის ჯამი ემთხვევა `load_data` ვერიფიკაციას (ზარალიანობის კოეფიციენტი 0.706)
- [x] ტოპ სეგმენტები დალაგებულია მოგებული პრემიით; კორექციები ±50%-ის ფარგლებში
