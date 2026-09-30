# დოკუმენტაცია — `src/recommend.py`

> 🇬🇧 English version: [recommend.md](recommend.md)

**როლი:** აქციოს სეგმენტის ზარალიანობის კოეფიციენტი კრედიბილურობით-შეწონილ, შეზღუდულ ფასის კორექციებად.
**დამოკიდებულება:** `metrics.aggregate_by` გამოსავალი. **გამოიყენება:** `run`.

---

## 1. ძირითადი იდეა
შეადარე თითოეული სეგმენტის დაკვირვებული ზარალიანობის კოეფიციენტი **სამიზნე** ზარალიანობის კოეფიციენტს. სეგმენტი, რომელიც უფრო ცხელია ვიდრე სამიზნე, ნაკლებად ტარიფიკებულია → დატვირთე; უფრო ცივი → დასთავე.

---

## 2. ფორმულები

### 2.1 ნედლი კორექცია
```
raw_correction = (loss_ratio / target_loss_ratio) - 1
```
- თუ `loss_ratio == target` → 0.
- თუ `loss_ratio > target` → დადებითი (ფასის ზრდა).
- თუ `loss_ratio < target` → უარყოფითი (ფასის შემცირება).
- `NaN` ზარალიანობის კოეფიციენტი (მონაცემების გარეშე) → `raw_correction = NaN` (სიგნალი არაა).

### 2.2 კრედიბილურობა (წრფივი შეკუმშვა)
```
credibility = min(1, earned_premium / full_credibility_premium)
```
თხელი სეგმენტები (დაბალი მოგებული პრემია) იღებენ პატარა კრედიბილურობას → მათი კორექცია შეკუმშულია 0-სკენ.

### 2.3 რეკომენდებული კორექცია (შეზღუდული)
```
recommended_correction = clip(raw_correction * credibility, -max_correction, +max_correction)
```

### 2.4 რეკომენდებული რეიტი და % ცვლილება
```
recommended_premium_rate = premium_rate * (1 + recommended_correction)
recommended_rate_change_pct = recommended_correction * 100
```

### 2.5 მოქმედების ლეიბლი
```
action = "Increase"  if recommended_correction >= 0.05
       = "Decrease"  if recommended_correction <= -0.05
       = "Hold"      otherwise
```

---

## 3. ნაგულისხმევი პარამეტრები
| პარამეტრი | ნაგულისხმევი | მნიშვნელობა |
|---|---|---|
| `target_loss_ratio` | `0.60` | მისაღები ზარალიანობის კოეფიციენტი (მენეჯმენტის ვარაუდი) |
| `full_credibility_premium` | `5_000_000` GEL | მოგებული პრემია სრული კრედიბილურობისთვის |
| `max_correction` | `0.50` | კაპი ±50%-ზე |

ყველა ფუნქციის არგუმენტია — შეცვალე ისინი ლოგიკის შეხების გარეშე.

---

## 4. ფუნქცია: `recommend(seg_metrics, ...) -> DataFrame`
ამატებს სვეტებს: `credibility, raw_correction, recommended_correction,
recommended_premium_rate, recommended_rate_change_pct, action`.
- `raw` გამოითვლება მხოლოდ სადაც `loss_ratio` სწორია (`lr.notna() & lr >= 0`).
- `shrunk = raw * credibility`, შემდეგ კლიპული.

### `summarize_recommendations(rec) -> DataFrame`
აბრუნებს კომპაქტურ ხედს (სეგმენტის განზომილებები + ძირითადი მეტრიკები + კორექციები + მოქმედება), დალაგებული `earned_premium`-ით კლებადობით. სვეტები შეირჩევა მხოლოდ თუ არსებობს.

---

## 5. სინტაქსის შენიშვნები
- `np.minimum(1.0, earned / full)` ვექტორული კრედიბილურობა.
- `shrunk.clip(-max_correction, max_correction)` აძლევს კაპს ძალას.
- `raw.where(lr.notna() & (lr >= 0))` ინარჩუნებს NaN-ს სადაც ზარალიანობის კოეფიციენტის სიგნალი არაა.

## 6. ვერიფიკაცია
- [x] სეგმენტი `loss_ratio=0.526`-ით (სამიზნე 0.60) → კორექცია ≈ −0.12 (−12%)
- [x] სრულკრედიბილური სეგმენტი (earned ≥ 5M) → `credibility = 1.0`
- [x] კორექციები არასდროს აჭარბებს ±0.50-ს
- [x] `action` ემთხვევა ±5% ზღვარს
