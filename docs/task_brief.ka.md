# ტექნიკური დავალება — CASCO ზარალის ღირებულების მოდელი და ანდერაითინგის რეკომენდაციები

> 🇬🇧 English version: [task_brief.md](task_brief.md)
> 
> ეს არის TBC დაზღვევის მიერ მოწოდებული ორიგინალი დავალების ტექსტი. მონაცემთა ფაილები კონფიდენციალურია და რეპოზიტორიაში არ შედის.


## 1. ბიზნეს პრობლემა და მიზნები

თიბისის ერთ-ერთი მთავარი პროდუქტი ავტომობილის დაზღვევა (CASCO)ა. ამჟამინდელი ტარიფიკაცია ზოგადია და არა დეტალური. პოლისის ტარიფი შემდეგ პარამეტრებს ეყრდნობა *(დეტალები — მესამე სექციაში):*

კლიენტის ასაკი, მანქანის ტიპი, ფრანშიზა, დაზღვევის ლიმიტი (საბაზრო ღირებულება)

**მიზანი** — მონაცემებზე დაფუძნებული ანალიზი რისკის სეგმენტებზე, სადაც ამჟამინდელი ფასი არ შეესაბამება რეალურ ზარალიანობას. შესაძლოა ფასის კორექტირება ნებისმიერ მხარეს (+-). რეკომენდაციების ფორმატი თავისუფალია.

**ზარალიანობა**, ასევე ცნობილი როგორც **loss ratio** გამოითვლება შემდეგი ფორმულით: `incurred claim amount / earned premium`

**ანდერაითინგის გუნდი** პასუხისმგებელია რისკების შეფასებასა და პოლისების ფასების სტრუქტურიზებაზე.

**აქტუარი/მონაცემთა მეცნიერი** პასუხისმგებელია სტატისტიკურად მართებული მეთოდოლოგიების შემუშავებასა და მონაცემებზე დაყრდნობით რეკომენდაციული სტრუქტურის შექმნაზე.

დავალების შესასრულებად საჭირო ტექნოლოგიებში ხართ თავისუფალი. მთავარი არის შედეგი, რომელიც მიზნად ისახავს ზარალიანობის შეფასებას სხვადასხვა სეგმენტში და ტარიფიკაციის რეკომენდაციებს, რომლებიც უნდა იყოს დაფუძნებული მოსალოდნელ ზარალიანობაზე. შესაბამისად, ისტორიული ზარალიანობით, უნდა შეფასდეს არსებული ტარიფიკაცია და სასურველია გვაჩვენოთ სად შეიძლება ფასების კორექტირება და როგორ. პოლისის ტარიფი გამოითვლება შემდეგი ფორმულით: `gross written premium / sum insured`

გთხოვთ გარკვევით გაეცნოთ მონაცემებთა სპეციფიკაციებს და კითხვების შემთხვევაში დაგვიკავშირდეთ.


## 2. მონაცემები

მონაცემთა ფაილები არის  `data/` ფოლდერში.  
ბაზის ამოღების თარიღია `2026-05-15`. 

### 2.1 `Policies_1805_v2.csv` — policy master
One row per CASCO policy. Key fields:

| ველი | მნიშვნელობა |
|---|---|
| `policyid`, `clientid` | იდენტიფიკატორები |
| `efdate`, `todate`, `cancellationdate` | პოლისის დაწყების, დასრულების და გაუქმენის თარიღები |
| `policystatusid`, `policystatus` | პოლისის სტატუსი: (active/expired/cancelled etc.). შესაძლოა საჭიროებდეს დაკორექტირებას |
| `suminsured`, `suminsuredcurrency`, `code`, `suminsuredgel` | დაზღვეული ავტომობილის საბაზრო ღირებულება და დაზღვევის ლიმიტი. ვალუტების ნორმალიზებისთვის (დოლარში) შეგიძლია `fx_rates.csv` გამოიყენო. ცხრილში ასევე მოცემულია `maxrate` ველი, მაგრამ `fx_rates` არის უფრო ზუსტი და გვაძლევს საშუალებას ნებისმიერი ვალუტა გადავიყვანოთ დოლარში. |
| `grosswrittenpremiumgel`, `earned_premium` | პრემიის ანუ გადასახდელი თანხის ველები |
| `licenseid`/`licensename`, `sectorid`/`sectorname`, `directionid`/`directionname` | სტრუქტურული ველები |
| `vehicletypeid`/`vehicletypename`, `vehiclemarkid`/`vehiclemarkname`, `vehiclemodelid`/`vehiclemodelname`, `enginecapacity`, `carage`, `istaxi` | ავტომობილის მონაცემები |
| `eligible_driver_count` | დასახელებული მძღოლების რაოდენობა (enrcols-ში უფრო სწორი რიცხვია ვიდრე ამ ბაზაში.) ველის სახელი: `დასახ. მძღოლების რაოდ` |

### 2.2 `Claims_1805.csv` — claims
One row per reported claim, linked via `policyid`.

| Field | Meaning |
|---|---|
| `reportedclaimid` | ზარალის იდენტიფიკატორი |
| `accidenttypeid`, `accidenttypename` | შემთხვევის ტიპი |
| `accidentdate` | შემთხვევის თარიღი |
| `calcclaimstatus` | `VALID_CLAIM_STATUSES = ["Easy Settlement", "Hard Settlement"]` |
| `reportedclaimamount` | ზარალის ოდენობა |

### 2.3 `Clients_1805.csv` — client master
One row per client (`clientid`).  
Fields: `age`, `gender`,  
`subsegmentkey`/`subsegmentname` (კლიენტის სეგმენტი. NA შეგიძლია Mass სეგმენტში ჩააგდო),  
`clientstatus` (ფიზიკური/იურიდიული პირი — გვჭირდება მხოლოდ ფიზიკური პირი),  

### 2.4 enrcols policy enrichment file — `პოლისების ბაზა - Casco, MTPL, MPA_18-05-2026_12.37.05.csv`
**გაფრთხილება:** ეს არის ჯვარედუქტური პოლისთა ბაზა, რომელიც მოიცავს Casco, MTPL და MPA ხაზებს — არა მხოლოდ Casco-ს. ის უნდა შეუერთოს Casco პოლისთა სამყაროსთან `id` = `policyid`-ზე და მხოლოდ შესაბამისი Casco რიგები/სვეტები გამოიყენოს; ფაილის დანარჩენი ფარგლის გარეთაა. ამ ამოცანისთვის შესაბამისი სვეტები მოიცავს:

`არხი`, `ქვეარხი`, `სვალდებულო/ნებაყოფლობ`,  
`გამოყენება` - პირადი ან კომერციული გამოყენება (გვჭირდება მხოლოდ პირადი გამოყენების პოლისები)  
`სვალდებულო/ნებაყოფლობ`,  
`ფრანშიზის ველი`, `ფრანშიზა`, `არასტანდარტული ფრანში`, `deductibletext` - რამოდენიმე ველი ფრანშიზის შესახებ. დამუშავების ლოგიკა მითითებულია მესამე სექციაში.  
`მძღოლის მინიმალური ასა`, `დასახ. მძღოლების რაოდ`

შეზღუდული არ ხარ მხოლოდ ამ ველებში. თუ მნიშვნელოვანია, შეგიძლია სხვა ველებიც გამოიყენო.


### 2.5 `fx_rates.csv` — daily FX rates
`date`, `gel_per_usd`, `gel_per_eur`, `usd_per_gel`, `eur_usd`. საჭიროა `suminsured`-ის ერთ საერთულოში ნორმალიზაციისთვის, რადგან ის ჩაწერილია იმ ვალუტაში, რომელშიც პოლისი დაიწერა.

## 3. დამატებითი ინფორმაცია

ტარიფიკაციის განმსაზღვრელი პარამეტრები:  


**კლიენტის ასაკი:** 18-20, 21-25, 26-29, >40  
**მანქანის ტიპი:** სედანი, მაღალი გამავლობის, კუპე  
*მონაცემებში შეგხვდება სხვა ტიპებიც, მაგრამ ისინი ერთიანდებიან შემდეგი ლოგიკით:*
```python
df_policies["vehicletypename"] = df_policies["vehicletypename"].replace({
    "ჯიპი": "მაღალი გამავლობის",
    "პიკაპი": "მაღალი გამავლობის",
    "ვენი": "სედანი",
    "უნივერსალი": "სედანი",
    "ჰეტჩბეკი": "სედანი",
    "კუპე": "კუპე/კაბრიოლეტი",
    "კაბრიოლეტი": "კუპე/კაბრიოლეტი",
})
```

**ფრანშიზა:** Yes, No  (სატესტოდ გამოყვანილია enrcols-ს ფრანშიზის ველებიდან, მაგრამ შეზღუდული არ ხარ, შეგიძლია შენ უკეთესი დაყოფა შემოგვთავაზო)
```python
df_policies_enrcols_v2 = pd.read_csv(
    "./data/enrcols.csv",
    dtype={"id": "int64"},
)

NONSTD_MARKER = "არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"

def is_blank(v):
    return pd.isna(v) or str(v).strip() == ""

def resolve_row(row):
    veli = row["ფრანშიზის ველი"]
    if not is_blank(veli):
        return veli
    franchiza = row["ფრანშიზა"]
    if is_blank(franchiza):
        return None
    if str(franchiza).strip() == NONSTD_MARKER:
        nonstd = row["არასტანდარტული ფრანში"]
        return nonstd if not is_blank(nonstd) else None
    return franchiza

# 1. derive resolved_value on df_policies_enrcols_v2
df_policies_enrcols_v2["resolved_value"] = df_policies_enrcols_v2.apply(resolve_row, axis=1).fillna("")

# 2. bring in deductible_category via the lookup already saved at data/franchise_field_categories.csv
lookup = pd.read_csv("data/franchise_field_categories.csv", encoding="utf-8-sig")[
    ["resolved_value", "category"]
].drop_duplicates("resolved_value").rename(columns={"category": "deductible_category"})
lookup["resolved_value"] = lookup["resolved_value"].fillna("")

df_policies_enrcols_v2 = df_policies_enrcols_v2.merge(lookup, on="resolved_value", how="left")
df_policies_enrcols_v2["deductible_category"] = df_policies_enrcols_v2["deductible_category"].fillna("No Deductible")

# 3.
# "No" only for the unconditional zero-deductible / no-deductible cases;
# any rider means a real deductible amount applies under some claim scenario
NO_DEDUCTIBLE_CATEGORIES = {"Zero Deductible (All Risks)", "No Deductible"}

df_policies_enrcols_v2["deductible_type"] = np.where(
    df_policies_enrcols_v2["deductible_category"].isin(NO_DEDUCTIBLE_CATEGORIES),
    "No", "Yes",
)
```

**დაზღვევის ლიმიტი (საბაზრო ღირებულება) - Sum Insured Bin:** 
```python
bins = [0, 5_000] + list(range(6_000, 51_000, 1_000)) + [float("inf")]

labels = (
    ["SI<=5k"]
    + [f"{i}k<SI<={(i+1)}k" for i in range(5, 50)]
    + [">50k"]
)

df_policies["suminsured_usd_bin"] = pd.cut(
    df_policies["suminsured_usd"],
    bins=bins,
    labels=labels,
    right=True,
    include_lowest=True,
)
```
