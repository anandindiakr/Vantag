# Vantag Retail Intelligence Platform — Documentation Package

Complete 22-document production documentation set for the Vantag / Retail Nazar / JagaJaga platform.

## Contents

### 01_Product/
| # | Doc |
|---|---|
| 00 | Master Index |
| 01 | PRD — Product Requirements Document |
| 02 | BRD — Business Requirements Document |
| 03 | SRS — Software Requirements Specification |
| 04 | User Personas & Journey Maps |

### 02_Architecture/
| # | Doc |
|---|---|
| 05 | SAD — System Architecture Document |
| 06 | HLD — High-Level Design |
| 07 | LLD — Low-Level Design |
| 08 | Database Design & ERD |
| 09 | API Specification |
| 10 | Security Architecture |

### 03_Development/
| # | Doc |
|---|---|
| 11 | Coding Standards & Developer Guide |
| 12 | AI/ML Model Documentation |

### 04_Operations/
| # | Doc |
|---|---|
| 13 | Deployment & Operations Runbook |

### 05_Quality/
| # | Doc |
|---|---|
| 14 | Test Plan & Test Cases |
| 15 | QA Report & Defect Log |

### 06_Compliance/
| # | Doc |
|---|---|
| 16 | Compliance & Privacy Policy |
| 17 | Terms of Service |

### 07_UserGuides/
| # | Doc |
|---|---|
| 18 | User Guide & Onboarding Handbook |
| 19 | Edge Agent Installation Guide |
| 20 | Super-Admin Guide |
| 21 | Brand & Style Guide |

## Regenerate

```powershell
pip install python-docx
python build_part1.py
python build_part2.py
python build_part3.py
```

All `.docx` files will be re-written in their category folders.

## Reading order

- **New engineer**: 05 → 06 → 07 → 08 → 09 → 10 → 11
- **Product / business**: 01 → 02 → 03 → 04
- **QA / SRE**: 13 → 14 → 15 → 10
- **Legal / compliance**: 16 → 17 → 10
- **Customer-facing**: 18 → 19 → 21
- **System owner**: 20 → 13 → 15
