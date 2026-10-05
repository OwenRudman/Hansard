# 12th Senate: automated Label/Hierarchy run

All 419 sittings from the "12th Senate" sheet of `mzalendo_links.xlsx` (2017-08-31 to 2022-06-21).

## How the files were produced
1. **Links to raw JSON:** `link_to_json.ipynb` v2.0 (Box/Automation, 1 Oct). All 419 downloaded, none failed.
2. **Cleaning:** `Mzalendo_Speed_Script.ipynb`, cleaner revision 4.41 (Box/Automation, 2 Oct). All 419 completed. Re-running it on the earlier raw files reproduced your cleaned files exactly (80 of 80).
3. **Audit against the PDF:** `hansard_auto_audit` (auditor.py + pdfparse.py). The only change is the Node path for this machine.
4. **Suggest hierarchy and export:** run inside your saved copy of the Hansard Label Editor. Its code is byte-identical to the live tool page you sent.
5. **Post-run checks (`postcheck.py`, new):** these move sittings from "Finished - no issues found" to "Needs human check" when the audit couldn't really check them. See the table below.

## What's in this folder
- **Finished - no issues found**: final JSONs. Every block was checked against the PDF and nothing came up. All blocks are marked reviewed and heading levels come from Suggest hierarchy.
- **Needs human check - each has a flags list**: JSONs where something needs a person to look. Each comes with "<sitting> - Senate - flags.txt", which lists the block number, the PDF page and what to check. Flagged blocks are left unreviewed, so "Go to first unreviewed" in the tool steps through them.
- **summary.csv**: one row per sitting with its status, flag count, block count, the PDF it was checked against, and "done manually" for the 13 sittings you audited by hand.
- **../Audit code used for this run**: the scripts that produced these files.

## Totals
| | Sittings |
|---|---|
| Finished - no issues found | 233 |
| Needs human check - each has a flags list | 186 |
| **Total** | **419** |

Total flags: **1,497**

| Flag type | Count |
|---|---|
| PDF shows a new speaker starting inside a block | 488 |
| Name in the PDF doesn't match the Speaker/Title boxes | 472 |
| Text not found in the PDF | 466 |
| Heading left with no level by Suggest hierarchy | 37 |
| Speech with no speaker | 10 |
| PDF layout not recognised by the parser, so the checks didn't run (whole sitting) | 10 |
| Mzalendo date or duplicate problem (whole sitting) | 5 |
| Empty sitting on Mzalendo (whole sitting) | 3 |
| Quorum/Division cutout placed by Suggest hierarchy | 3 |
| Page markers the cleaner missed, marked deleted (one flag per sitting) | 3 |

"Text not found" is concentrated in a few sittings: 2019-09-17 has 160, 2022-06-08 has 47 and 2021-05-25 has 31. 81 sittings have any.

## Flag rate by year
| Year | Sittings | Flags | Flags per sitting | Flags per 1,000 blocks | Needing a check |
|---|---|---|---|---|---|
| 2017 | 19 | 133 | 7.0 | 35.5 | 13 |
| 2018 | 93 | 415 | 4.5 | 16.2 | 56 |
| 2019 | 93 | 483 | 5.2 | 15.3 | 44 |
| 2020 | 79 | 212 | 2.7 | 9.0 | 38 |
| 2021 | 85 | 147 | 1.7 | 6.8 | 21 |
| 2022 | 50 | 107 | 2.1 | 10.2 | 14 |

No year rises above 2017. Rates fall after 2019, so I checked whether that's because the parser finds less in later PDFs. It isn't: the PDF parser finds about 0.8 speaker turns per JSON speech block in every year, from 2017 to 2022.

There is a problem with individual PDFs instead. 10 PDFs are laid out differently: speaker lines are indented 107–118 or 140 points instead of 120–135, or bold speaker names aren't detected. On those 10 the name and new-speaker checks never ran. They are in "Needs human check" with a whole-sitting note:
2018-02-27, 2019-03-20, 2019-03-21, 2020-01-29 14:00, 2020-05-26 10:00, 2020-11-03, 2020-12-09, 2020-12-21, 2021-09-23, 2022-03-22.

## Failures and data problems
- **No PDF:** none. Four PDFs were misnamed and were matched by checking their text:
  - `24_10_0208…` is 2018-10-24.
  - `2022-01-28…Afternoon` is 2020-01-28 14:00.
  - `2021-05-07…Monday` is 2021-05-17.
  - Mzalendo's "2018-11-25" (a Sunday) is the 25 Oct 2018 sitting.
- **Errors:** none.
- **Scanned PDFs (no real text):** none.
- **Mzalendo pages with the wrong transcript:** found by checking every sitting against every PDF.
  - The Mzalendo **2018-03-28** page holds the **14 March 2018** sitting. It was audited against the 14 March PDF. The real 28 March transcript isn't on Mzalendo.
  - The Mzalendo **2018-03-14** page duplicates **2018-03-15**: 127 of 128 text samples are identical.
  - **2021-05-17 14:00** is entirely contained in the 14:30 version, and there's only one PDF.
  - **2022-03-09 10:00** shares about 60% of its text with the 14:30 sitting.
- **PDFs with no Mzalendo link (not processed):** 2019-03-27, 2020-01-21 (Special Sitting), 2022-01-26 (Special Sitting), 2022-02-09.

## Empty sittings
2020-08-11, 2020-08-17 10:00 and 2020-08-17 14:30 each came from Mzalendo as one empty block. The audit alone put them in "Finished - no issues found" with 0 blocks, so it didn't fail or flag them as it should have. The post-run check moved all three to "Needs human check" with an "empty sitting" flag.

## Sittings already audited by hand
These 13 were still run so they can be compared with your versions. They are marked "done manually" in summary.csv.
| Sitting | Status | Flags |
|---|---|---|
| 2017-08-31 | needs check | 4 |
| 2017-09-13 | needs check | 5 |
| 2017-09-14 | needs check | 4 |
| 2017-09-26 | finished | 0 |
| 2017-09-27 | finished | 0 |
| 2017-09-28 | finished | 0 |
| 2017-10-10 | finished | 0 |
| 2017-10-11 | finished | 0 |
| 2017-10-12 | needs check | 2 |
| 2017-11-07 | needs check | 1 |
| 2017-11-08 | needs check | 8 |
| 2017-11-09 | needs check | 3 |
| 2017-11-29 | needs check | 1 |

## Caveats
- **Calibration:** the auditor was built and tested on an older cleaner's output. Until it's scored against your 13 hand-finished JSONs, treat the "Finished - no issues found"check split as a first pass.
- **Speaker/Title order:** many blocks have Speaker and Title the other way round, e.g. Speaker "(Sen. (Prof.) Kamar)" with Title "The Temporary Speaker". The processing instructions say this doesn't need fixing, so it isn't flagged.
