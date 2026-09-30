# `data/` — not included / არ შედის რეპოზიტორიაში

**🇬🇧** The source data belongs to TBC Insurance and is **confidential**, so it is not part of this repository (`.gitignore` blocks every file here except this README). To run the pipeline, place the original files in this folder with exactly these names:

**🇬🇪** საწყისი მონაცემები ეკუთვნის TBC დაზღვევას და **კონფიდენციალურია**, ამიტომ რეპოზიტორიაში არ შედის (`.gitignore` ბლოკავს ამ საქაღალდის ყველა ფაილს, ამ README-ს გარდა). პაიპლაინის გასაშვებად ორიგინალი ფაილები ჩადეთ ამ საქაღალდეში ზუსტად ამ სახელებით:

| File / ფაილი | Grain / დონე | Join key | Used columns / გამოყენებული სვეტები |
|---|---|---|---|
| `Policies_1805_v4.csv` | 1 row per policy | `policyid`, `clientid` | `licensename`, `efdate`, `suminsuredgel`, `grosswrittenpremiumgel`, `earned_premium`, `vehicletypename`, `enginecapacity`, `carage`, `eligible_driver_count` |
| `Claims_1805_v2.csv` | 1 row per claim | `policyid` | `calcclaimstatus`, `reportedclaimamount` |
| `Clients_1805_v3.csv` | 1 row per client | `clientid` | `clientstatus`, `age`, `gender`, `subsegmentkey`, `subsegmentname` |
| `enrcols.csv` (~1 GB) | policy enrichment (Casco / MTPL / MPA) | `id` = `policyid` | `გამოყენება`, `ფრანშიზის ველი`, `ფრანშიზა`, `არასტანდარტული ფრანში`, `მძღოლის მინიმალური ასა`, `დასახ. მძღოლების რაოდ`, … |
| `franchise_field_categories.csv` | lookup | `resolved_value` | `resolved_value`, `category` |
| `fx_rates.csv` | 1 row per day | `date` (as-of `efdate`) | `date`, `gel_per_usd` |

Full field descriptions / ველების სრული აღწერა: [docs/task_brief.md](../docs/task_brief.md) · [docs/task_brief.ka.md](../docs/task_brief.ka.md)
