# exhibition_participants/tools

Reusable tooling for exhibition participant imports, cleanup, enrichment, and Apollo-ready exports lives here.

## XLSX / CSV -> Apollo CSV

`xlsx_to_apollo_csv.py` converts common company-list spreadsheets into a quoted CSV that is friendly for Apollo imports.

### What it does

- reads `.xlsx` without external Python packages
- also supports `.csv`
- uses the first sheet by default, or `--sheet <name>`
- maps common columns like:
  - Company Name / Company
  - URL / Website / Domain
  - LinkedIn
  - City
  - Country
  - Industry / Branch
  - Employees
- derives `Company Domain` from the website
- deduplicates rows
- writes a fully quoted CSV

### Example

```powershell
python exhibition_participants/tools/xlsx_to_apollo_csv.py "C:\path\to\input.xlsx"
```

Optional:

```powershell
python exhibition_participants/tools/xlsx_to_apollo_csv.py "C:\path\to\input.xlsx" --sheet "Companies" --output "C:\path\to\input_apollo.csv"
```

### Output columns

- Company
- Company Domain
- Website
- LinkedIn
- City
- Country
- Industry
- Employees
- Source File
