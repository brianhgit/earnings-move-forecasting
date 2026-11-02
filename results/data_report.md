# Data report

## 1. Kept vs dropped reports

|   year |   kept |   duplicate_filing |   insufficient_history |   missing_price |   price_gap |
|-------:|-------:|-------------------:|-----------------------:|----------------:|------------:|
|   2017 |      0 |                121 |                      0 |               4 |           3 |
|   2018 |      0 |                117 |                      0 |               4 |           2 |
|   2019 |   1745 |                112 |                     77 |               5 |           8 |
|   2020 |   1794 |                173 |                     63 |               1 |           3 |
|   2021 |   1833 |                 88 |                     59 |               1 |           7 |
|   2022 |   1855 |                103 |                     54 |               0 |           0 |
|   2023 |   1902 |                 94 |                     22 |               0 |           3 |
|   2024 |   1914 |                107 |                     36 |               0 |           3 |
|   2025 |   1924 |                107 |                     42 |               0 |           2 |
|   2026 |   1524 |                 94 |                     21 |              26 |           2 |

Chart: [data_report/kept_vs_dropped.html](data_report/kept_vs_dropped.html)

## 2. Hand-check results

|    | check     | plan   | k/n   |   share |   wilson_lower | target   | passes   |
|---:|:----------|:-------|:------|--------:|---------------:|:---------|:---------|
|  0 | precision | A      | 60/60 |   1     |          0.94  | 57/60    | True     |
|  1 | recall    | A      | 26/29 |   0.897 |          0.736 | 27/30    | False    |
|  2 | precision | B      | 59/60 |   0.983 |          0.911 | 57/60    | True     |
|  3 | recall    | B      | 27/29 |   0.931 |          0.78  | 27/30    | True     |

Chart: [data_report/hand_check.html](data_report/hand_check.html)

## 3. Timing sanity check

|   year |    n |   median_ratio |   share_ours_bigger |
|-------:|-----:|---------------:|--------------------:|
|   2019 | 1740 |          2.882 |               0.779 |
|   2020 | 1788 |          2.287 |               0.739 |
|   2021 | 1826 |          2.381 |               0.75  |
|   2022 | 1851 |          2.554 |               0.757 |
|   2023 | 1897 |          3.109 |               0.813 |
|   2024 | 1904 |          3.412 |               0.817 |

Chart: [data_report/timing_check.html](data_report/timing_check.html)
