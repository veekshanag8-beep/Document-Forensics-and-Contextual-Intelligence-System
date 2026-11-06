# Evaluation on the demonstration dataset

Generated 2026-11-06 15:48 by `scripts/evaluate.py` (full pipeline, fresh run).

| Case | Planted anomalies | Detected | Missed | False positives | Total findings | Seconds | Rejected files |
|---|---|---|---|---|---|---|---|
| case_01_genuine | 0 | 0 | 0 | 0 | 0 | 8.0 | 0 |
| case_02_visual_tamper | 7 | 7 | 0 | 0 | 14 | 18.7 | 0 |
| case_03_contextual | 10 | 10 | 0 | 0 | 10 | 20.3 | 0 |
| misc_failure_handling | 0 | 0 | 0 | 0 | 0 | 3.5 | 1 |

**Recall (planted anomalies detected): 17/17 = 100%**  
**Precision (non-observation findings that correspond to a planted anomaly): 100%** (0 false positives)

Observations (e.g. PDF revision metadata) and corroborated summaries are excluded from both counts.

## Per-anomaly detail

| Case | Document | Kind | Field | Detected by |
|---|---|---|---|---|
| case_02_visual_tamper | salary_slip.jpg | visual_tamper | net_pay | F-006 noise_inconsistency, F-008 layout_geometry |
| case_02_visual_tamper | salary_slip.jpg | arithmetic | net_pay | F-005 slip_net_arithmetic |
| case_02_visual_tamper | salary_slip.jpg | cross_mismatch | net_pay | F-003 salary_credit_mismatch |
| case_02_visual_tamper | application_form.pdf | overlay_hidden_text | monthly_income | F-001 overwritten_text |
| case_02_visual_tamper | application_form.pdf | font_inconsistency | monthly_income | F-007 font_inconsistency |
| case_02_visual_tamper | application_form.pdf | cross_mismatch | monthly_income | F-004 income_vs_payslip |
| case_02_visual_tamper | application_form.pdf | signature_copy | applicant_signature | F-002 signature_copy |
| case_03_contextual | identity_card.jpg | cross_mismatch | name | F-009 cross_person_name |
| case_03_contextual | application_form.pdf | cross_mismatch | date_of_birth | F-004 cross_date_of_birth |
| case_03_contextual | application_form.pdf | age_dob | age | F-008 age_dob_mismatch |
| case_03_contextual | application_form.pdf | checksum | national_id | F-001 id_checksum |
| case_03_contextual | application_form.pdf | cross_mismatch | national_id | F-005 cross_national_id |
| case_03_contextual | salary_slip.pdf | arithmetic | net_pay | F-002 slip_net_arithmetic |
| case_03_contextual | bank_statement.jpg | cross_mismatch | salary_credit | F-007 salary_credit_mismatch |
| case_03_contextual | bank_statement.jpg | running_balance | balance | F-003 running_balance |
| case_03_contextual | bank_statement.jpg | cross_mismatch | address | F-006 cross_address |
| case_03_contextual | salary_slip.pdf | missing_signature | authorised_signature | F-010 missing_signature |

## Caveat

The dataset is synthetic and small (3 cases, 12 documents, 17 planted anomalies + 2 robustness files). Thresholds were tuned on it, so these numbers demonstrate that each capability works end-to-end; they are not an estimate of real-world accuracy.