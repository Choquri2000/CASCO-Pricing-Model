# დოკუმენტაცია — `src/segments.py`

> 🇬🇧 English version: [segments.md](segments.md)

**როლი:** გამოიყვანოს ოთხი რისკის-სეგმენტის განზომილება ანალიზის ჩარჩოდან.
**დამოკიდებულება:** `load_data` (ჩარჩოსთვის). **გამოიყენება:** `metrics`, `recommend`, `run`.

---

## 1. სეგმენტის განზომილებები

| განზომილება | წარმოქმნილი სვეტი | წყარო |
|---|---|---|
| კლიენტის ასაკი | `client_age_bin` | `age` |
| ავტომობილის ტიპი | `vehicle_type` | `vehicletypename` (შევიდებული) |
| ფრანშიზა | `franchise` (= `deductible_type`) | `load_data`-დან |
| დაზღვეული თანხა (USD) | `suminsured_usd_bin` | `suminsured_usd` |

---

## 2. კონსტანტები და ფორმულები

### 2.1 ავტომობილის ტიპის შევიდება (სიტყვასიტყვით README-დან)
```python
VEHICLE_TYPE_MAP = {
    "ჯიპი": "მაღალი გამავლობის", "პიკაპი": "მაღალი გამავლობის",
    "ვენი": "სედანი", "უნივერსალი": "სედანი", "ჰეტჩბეკი": "სედანი",
    "კუპე": "კუპე/კაბრიოლეტი", "კაბრიოლეტი": "კუპე/კაბრიოლეტი",
}
```
გამოყენებულია `df["vehicle_type"] = df[col].replace(VEHICLE_TYPE_MAP)`-ით.

### 2.2 კლიენტის ასაკობრივი ზოლები
```python
AGE_BINS  = [18, 20, 25, 29, 40, float("inf")]
AGE_LABELS = ["18-20", "21-25", "26-29", "30-40", ">40"]
```
ფორმულა: `pd.cut(age, bins=AGE_BINS, labels=AGE_LABELS, right=True, include_lowest=True)`.
*შენიშვნა:* `>40` მკაცრად 40-ზე მეტია, ამიტომ დაემატა `30-40` ზოლი, რათა 30–40 არ მორჩენილიყო.

### 2.3 დაზღვეული თანხის USD ზოლები (სიტყვასიტყვით README-დან)
```python
SI_BINS  = [0, 5_000] + list(range(6_000, 51_000, 1_000)) + [float("inf")]
SI_LABELS = ["SI<=5k"] + [f"{i}k<SI<={(i+1)}k" for i in range(5, 50)] + [">50k"]
```
ფორმულა: `pd.cut(suminsured_usd, bins=SI_BINS, labels=SI_LABELS, right=True, include_lowest=True)`.

---

## 3. ფუნქციები

### `add_vehicle_type(df, col="vehicletypename")`
აბრუნებს ასლს `vehicle_type`-ით დამატებულით (შევიდებული კატეგორიები).

### `add_client_age_bin(df, col="age")`
აძალებს `age`-ს რიცხვითად, შემდეგ `pd.cut` `client_age_bin`-ში.

### `add_suminsured_bin(df, col="suminsured_usd")`
`pd.cut` FX-ნორმალიზებული დაზღვეული თანხის `suminsured_usd_bin`-ში.

### `add_segments(df)`
იძახებს ზემოთა სამ ფუნქციას და აყენებს `df["franchise"] = df["deductible_type"]` (ფრანშიზის განზომილების ფსევდონიმი).

### `build_segment_key(df)`
ქმნის ერთ კომპოზიტურ ლეიბლს:
```
segment = "age:" + client_age_bin
        + " | veh:" + vehicle_type
        + " | fr:" + franchise
        + " | si:" + suminsured_usd_bin
```
გამოიყენება ყველაზე წვრილხალი აგრეგაციისთვის (1,056 განსხვავებული სეგმენტი).

---

## 4. სინტაქსის შენიშვნები
- `pd.cut(..., right=True)` → ზოლებია (a, b]; `include_lowest=True` პირველ ზოლს აძლევს მის მარცხენა კიდეს.
- ყველა `add_*` ფუნქცია აბრუნებს **ასლს** (`df.copy()`) — ისინი არ ცვლიან შეყვანას.
- `float("inf")` როგორც ბოლო ზოლის კიდე იჭერს ყველა მნიშვნელობას ზედა გამოკვეთილ ზღვარზე ზემოთ.

## 5. ვერიფიკაცია
- [x] `client_age_bin` ფარავს ყველა ასაკს ხარვეზების გარეშე (18-20, 21-25, 26-29, 30-40, >40)
- [x] `vehicle_type` შეავიდებს 7 მაპირებულ ნედლ ტიპს; ნაშთიანი იშვიათი ტიპები შენარჩუნებულია
- [x] `suminsured_usd_bin` ქმნის README-ის ლეიბლების ნაკრებს
- [x] `segment` უნიკალურია თითოეული კომბინაციისთვის; 1,056 განსხვავებული მნიშვნელობა პორტფელის დონეზე
