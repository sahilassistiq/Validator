import streamlit as st
import anthropic
import os
import json
import time
import pandas as pd
from io import StringIO

# ════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG  (must be first st call)
# ════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AIQ Integration Tools",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ════════════════════════════════════════════════════════════════════════════
# AUTH — Login / Auto-logout / Logout button
# ════════════════════════════════════════════════════════════════════════════
TIMEOUT = 15 * 60  # 15 minutes

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔒 Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if username == st.secrets["USERNAME"] and password == st.secrets["PASSWORD"]:
                st.session_state.authenticated = True
                st.session_state.last_activity = time.time()
                st.rerun()
            else:
                st.error("Invalid username or password")
        st.stop()

check_password()

if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()
if time.time() - st.session_state.last_activity > TIMEOUT:
    st.session_state.authenticated = False
    st.rerun()
st.session_state.last_activity = time.time()

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# CLAUDE CLIENT
# ════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_claude_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("⚠️ ANTHROPIC_API_KEY not set!")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


def get_anthropic_model():
    # Keep the model configurable so future Anthropic model changes do not break uploads.
    # Default is a current Anthropic API model ID. Override in Streamlit secrets if needed:
    # ANTHROPIC_MODEL = "claude-opus-4-8"
    return st.secrets.get("ANTHROPIC_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-opus-4-8"

# ════════════════════════════════════════════════════════════════════════════
# FLAT FILE VALIDATOR — helpers
# ════════════════════════════════════════════════════════════════════════════
def convert_to_pipe_delimited(file, filename):
    """Convert various file formats to pipe-delimited text"""
    file_ext = filename.lower().split('.')[-1]
    try:
        if file_ext == 'txt':
            content = file.read().decode('utf-8')
            if '|' in content.split('\n')[0]:
                return content, "txt (pipe-delimited)"
            elif '\t' in content.split('\n')[0]:
                df = pd.read_csv(StringIO(content), sep='\t')
                return df.to_csv(sep='|', index=False), "txt (tab-delimited, converted to pipe)"
            elif ',' in content.split('\n')[0]:
                df = pd.read_csv(StringIO(content))
                return df.to_csv(sep='|', index=False), "txt (comma-delimited, converted to pipe)"
            else:
                return content, "txt (unknown delimiter)"
        elif file_ext == 'csv':
            df = pd.read_csv(file)
            return df.to_csv(sep='|', index=False), "csv (converted to pipe)"
        elif file_ext == 'tsv':
            df = pd.read_csv(file, sep='\t')
            return df.to_csv(sep='|', index=False), "tsv (converted to pipe)"
        elif file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(file, engine='openpyxl' if file_ext == 'xlsx' else None)
            return df.to_csv(sep='|', index=False), f"{file_ext} (converted to pipe)"
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
    except Exception as e:
        raise Exception(f"Error converting file: {str(e)}")


VALIDATION_PROMPTS = {
    "case_picklist": """You are a data validation expert for AssistIQ integration files. Validate the Case Pick Lists file against exact specifications.

<file_specification>
FILE: Case Picklists Data Extract

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All cases scheduled for <daterun> and <daterun> + 3 days
FREQUENCY: Daily (5-6am local time)

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| case_id             | Y        | Unique case identifier               | String                    | Non-empty, unique per case          |
| case_timestamp      | Y        | Scheduled case time in UTC           | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| picklist_id         | Y        | Case pick list identifier            | String                    | Non-empty                           |
| procedure_id        | Y        | Procedure identifier                 | String                    | Non-empty                           |
| primary_provider_id | Y        | Primary provider ID                  | String                    | Non-empty                           |
| supply_id           | Y        | Supply/product identifier            | String                    | Non-empty                           |
| is_implant          | Y        | Implant flag                         | Boolean                   | true/false, TRUE/FALSE, 1/0, Y/N    |
| open_qty            | Y        | Open quantity                        | Integer                   | >= 0, whole number                  |
| hold_qty            | Y        | Hold/PRN quantity                    | Integer                   | >= 0, whole number                  |
| created_ts          | Y        | Record created timestamp UTC         | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| updated_ts          | Y        | Record updated timestamp UTC         | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime, >= created_ts   |
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "charge_capture": """You are a data validation expert for AssistIQ integration files. Validate the Charge Capture file against exact specifications.

<file_specification>
FILE: Charge Capture Data

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)
EXTRACTION: All charges from previous 14 days

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| case_id             | Y        | Unique case identifier               | String                    | Non-empty                           |
| supply_id           | Y        | Supply/product identifier            | String                    | Non-empty                           |
| quantity_used       | Y        | Quantity used                        | Integer                   | > 0, whole number                   |
| quantity_wasted     | N        | Quantity wasted                      | Integer                   | >= 0 if present                     |
| unit_price          | Y        | Price per unit                       | Decimal                   | >= 0, max 2 decimals                |
| total_price         | Y        | Total price                          | Decimal                   | >= 0, max 2 decimals                |
| is_implant          | Y        | Implant flag                         | Boolean                   | true/false, 1/0, Y/N                |
| lot_number          | N        | Lot number (implants)                | String                    | Max 50 chars if present             |
| serial_number       | N        | Serial number (implants)             | String                    | Max 50 chars if present             |
| expiry_date         | N        | Expiration date                      | yyyy-MM-dd                | Valid future date if present        |
| created_ts          | Y        | Record created timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| updated_ts          | Y        | Record updated timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "preference_cards": """You are a data validation expert for AssistIQ integration files. Validate the Preference Cards file against exact specifications.

<file_specification>
FILE: Preference Cards

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| preference_card_id  | Y        | Unique preference card ID            | String                    | Non-empty                           |
| procedure_id        | Y        | Procedure identifier                 | String                    | Non-empty                           |
| procedure_name      | Y        | Procedure name                       | String                    | Non-empty, max 255 chars            |
| primary_provider_id | Y        | Provider/surgeon ID                  | String                    | Non-empty                           |
| supply_id           | Y        | Supply/product ID                    | String                    | Non-empty                           |
| open_qty            | Y        | Preferred open quantity              | Integer                   | >= 0                                |
| hold_qty            | Y        | Preferred hold quantity              | Integer                   | >= 0                                |
| created_ts          | Y        | Record created timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| updated_ts          | Y        | Record updated timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "product_master": """You are a data validation expert for AssistIQ integration files. Validate the Product Master file against exact specifications.

<file_specification>
FILE: Product Master

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column                      | Required | Description                          | Format                    | Validation Rules                    |
|-----------------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| productId                   | Y        | Unique product identifier            | String                    | Non-empty, unique                   |
| productDesc                 | Y        | Product description                  | String                    | Non-empty, max 255 chars            |
| typeCode                    | Y        | Item type code                       | String                    | Non-empty                           |
| typeDesc                    | Y        | Item type description                | String                    | Non-empty                           |
| price                       | Y        | Unit price                           | Decimal                   | >= 0, max 2 decimals                |
| supplierCatalogNumber       | N        | Supplier SKU                         | String                    | Max 50 chars if present             |
| supplierId                  | N        | Supplier ID                          | String                    | Max 50 chars if present             |
| supplierDesc                | N        | Supplier name                        | String                    | Max 100 chars if present            |
| manufacturerCatalogNumber   | N        | Manufacturer SKU                     | String                    | Max 50 chars if present             |
| manufacturerId              | N        | Manufacturer ID                      | String                    | Max 50 chars if present             |
| manufacturer                | N        | Manufacturer name                    | String                    | Max 100 chars if present            |
| gtin                        | N        | GTIN barcode                         | String                    | 12-14 numeric digits if present     |
| isImplant                   | Y        | Implant flag                         | Boolean                   | true/false, 1/0, Y/N                |
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "service_lines": """You are a data validation expert for AssistIQ integration files. Validate the Service Lines file against exact specifications.

<file_specification>
FILE: Service Lines

FILENAME: Any .txt filename is acceptable. The file may be named anything (e.g. "3.5 sample.txt") — do NOT flag the filename as an error.
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| service_line_id     | Y        | Unique service line identifier       | String                    | Non-empty, unique                   |
| service_line_name   | Y        | Service line name                    | String                    | Non-empty, max 100 chars            |
| service_line_abbrev | Y        | Service line abbreviation            | String                    | Non-empty, max 20 chars             |
| procedure_id        | Y        | Procedure identifier                 | String                    | Non-empty                           |
| procedure_name      | Y        | Procedure name                       | String                    | Non-empty, max 255 chars            |

NOTE: created_ts and updated_ts are NOT required for this file type. Do NOT flag their absence as an error.
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "service_line_providers": """You are a data validation expert for AssistIQ integration files. Validate the Service Line Providers file against exact specifications.

<file_specification>
FILE: Service Line Providers

FILENAME: Any .txt filename is acceptable. The file may be named anything (e.g. "3.6 sample.txt") — do NOT flag the filename as an error.
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column               | Required | Description                          | Format                    | Validation Rules                    |
|----------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| service_line_id      | Y        | Service line identifier              | String                    | Non-empty                           |
| service_line_name    | Y        | Service line name                    | String                    | Non-empty                           |
| service_line_abbrev  | Y        | Service line abbreviation            | String                    | Non-empty, max 20 chars             |
| provider_id          | Y        | Provider identifier                  | String                    | Non-empty                           |
| provider_first_name  | Y        | Provider first name                  | String                    | Non-empty, max 100 chars            |
| provider_middle_name | N        | Provider middle name                 | String                    | Max 100 chars if present            |
| provider_last_name   | Y        | Provider last name                   | String                    | Non-empty, max 100 chars            |
| is_active            | Y        | Active status                        | Boolean                   | true/false, 1/0, Y/N                |

NOTE: created_ts and updated_ts are NOT required for this file type. Do NOT flag their absence as an error.
NOTE: service_line_abbrev IS a required field — do NOT flag it as an extra or unexpected column.

ROW COUNTING INSTRUCTIONS: Row 1 is the header. Data rows start at row 2. When reporting errors, count carefully — row 2 is the first data row, row 3 is the second, etc. If there are blank lines at the end of the file, do not count them. Double-check your row numbers before reporting.
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",
}

FILE_TYPE_INFO = {
    "case_picklist":          {"name": "Case Pick Lists",         "description": "Daily case schedules with supply lists for next 72 hours",  "example_filename": "2026-02-10.txt"},
    "charge_capture":         {"name": "Charge Capture",          "description": "Product usage and charges from previous 14 days",            "example_filename": "2026-02-10.txt"},
    "preference_cards":       {"name": "Preference Cards",        "description": "Surgeon-specific supply preferences for procedures",         "example_filename": "2026-02-10.txt"},
    "product_master":         {"name": "Product Master",          "description": "Complete product catalog from ERP system",                   "example_filename": "2026-02-10.txt"},
    "service_lines":          {"name": "Service Lines",           "description": "Service lines with associated procedures",                   "example_filename": "Any .txt filename"},
    "service_line_providers": {"name": "Service Line Providers",  "description": "Providers/doctors for each service line",                    "example_filename": "Any .txt filename"},
}

def validate_file(file_content, filename, file_type):
    client = get_claude_client()
    prompt = f"""{VALIDATION_PROMPTS[file_type]}

<sample_file>
Filename: {filename}

Content:
{file_content[:15000]}
</sample_file>

Provide validation results in this ACTIONABLE format:

## 🎯 VALIDATION SUMMARY
Status: [✅ PASS / ❌ FAIL]
Errors Found: [number]
Total Rows: [number]
Ready for Upload: [YES/NO]

---

## ❌ CRITICAL ISSUES (Fix These First)

[Only list critical blocking errors. Maximum 5. If none, say "None"]

**Issue #1: [Title]**
Problem: [What's wrong]
Fix: [Exact action]

---

## ⚠️ WARNINGS (Non-blocking)

[List warnings that are informational but do not block upload. Filename format mismatches go here as warnings, NOT as errors — the filename may be set by the sending system (e.g. Caristix) and is out of the hospital's control. If none, say "None"]

---

## 📋 COLUMN ERRORS

[Show ONLY columns with errors in table. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|
| SUPPLY_ID        | supply_id     | Change to lowercase |

---

## 🔍 MISSING COLUMNS

[List ONLY missing required columns. If none, say "No missing columns"]

Must Add:
1. **column_name** - Description (format)

---

## 🚨 DATA ERRORS BY ROW

[Show ONLY first 10 rows with errors in table. If none, say "No data errors"]
[IMPORTANT: Row 1 = header row. First data row = Row 2. Count rows carefully including any blank lines. Verify row number by checking the content matches before reporting.]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|
| 2   | date   | 7/2/2025      | Wrong format | Change to 2025-07-02T12:00:00 |

---

## ✅ STEP-BY-STEP FIX PLAN

**Step 1: [Action]**
[Detailed instructions]

**Step 2: [Action]**
[Detailed instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%"""

    message = client.messages.create(
        model=get_anthropic_model(),
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ════════════════════════════════════════════════════════════════════════════
# HL7 PARSER — few-shot examples + sample
# ════════════════════════════════════════════════════════════════════════════
FEW_SHOT = """
You are an HL7-to-JSON parser for AssistIQ surgical supply platform.
Convert HL7 messages into the exact AssistIQ appointment JSON format.

Below are 4 real examples (Northwell LIJFH) showing exact input HL7 and expected JSON output.
Study these carefully — your output must match this structure precisely.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT HL7:
MSH|^~\\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114142|63263|SIU^S14|334502.25676|D
SCH||27756||||||||10800|S|^^^20260309142500|||||||||63263^^^^|||||27731|Sch^Scheduled^SCHEDULING
ZCS|BEFORE|N|ORSCH_S14|||
PID|1|*|*^^^EPIC^MRN||*^*^^^^^L||*|F||||||||||*|||||||||||||N
PV1||OP Surg|LIJFH-OR^^^LIJFH^^^^^LIJFH OR^^DEPID|||||||||Pediatric||||||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI||110000359528
DG1|1||^Generalized abdominal pain [R10.84]|Generalized abdominal pain [R10.84]||^95;ORC
RGS|1||1
AIS|1||1078002605^Transplant - Double Lung|20260309142500|0|S|10800|S||||4
AIL|1||^LIJFH OR 1^^FHOR
AIP|1||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI|1.1^Primary|Pediatric|20260309142500|0|S|10800|S

OUTPUT JSON:
{
  "id": "27756",
  "reason": [
    {
      "id": "1",
      "note": [],
      "duration": 180,
      "endDateTime": "2026-03-09T17:25:00-0400",
      "serviceCode": { "code": "1078002605", "display": "Transplant - Double Lung" },
      "serviceLine": "Pediatric",
      "practitioner": {
        "id": "145251",
        "name": { "given": "PHYSICIAN", "family": "SURGERY" },
        "role": { "code": "1.1", "display": "Primary" },
        "resourceType": "Practitioner"
      },
      "resourceType": "Procedure",
      "startDateTime": "2026-03-09T14:25:00-0400"
    }
  ],
  "status": "booked",
  "patient": {
    "name": { "given": "*", "family": "*" },
    "display": "*",
    "reference": "*",
    "identifier": [{ "type": "MRN", "value": "*" }, { "type": "AccountID", "value": "*" }]
  },
  "duration": 180,
  "location": { "room": "LIJFH OR 1", "display": "LIJFH OR 1", "facility": "FHOR" },
  "metadata": {
    "source": "Northwell-EPIC-OR",
    "createdAt": "2026-03-09T11:41:57.893-0400",
    "HL7Message": {
      "id": null,
      "rawData": "*",
      "sourceId": "334502.25676",
      "createdAt": "2026-03-09T11:41:42.000-0400"
    },
    "connectorRevision": null
  },
  "endDateTime": "2026-03-09T17:25:00-0400",
  "resourceType": "Appointment",
  "startDateTime": "2026-03-09T14:25:00-0400"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT HL7:
MSH|^~\\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114147|63263|SIU^S14|334502.25677|D
SCH||27756||||||||10800|S|^^^20260309142500|||||||||63263^^^|||||27731|Sch^Scheduled^SCHEDULING
ZCS|BEFORE|N|ORSCH_S14|||
PID|1|*|*^^^EPIC^MRN||*^*^^^^^L||*|F||||||||||*|||||||||||||N
PV1||OP Surg|LIJFH-OR^^^LIJFH^^^^^LIJFH OR^^DEPID|||||||||Pediatric||||||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI||110000359528
RGS|1||1
AIS|1||1078002605^Transplant - Double Lung|20260309142500|0|S|10800|S||||4
AIL|1||^LIJFH OR 1^^FHOR
AIP|1||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI|1.1^Primary|Pediatric|20260309142500|0|S|10800|S

OUTPUT JSON:
{
  "id": "27756",
  "reason": [
    {
      "id": "1",
      "note": [],
      "duration": 180,
      "endDateTime": "2026-03-09T17:25:00-0400",
      "serviceCode": { "code": "1078002605", "display": "Transplant - Double Lung" },
      "serviceLine": "Pediatric",
      "practitioner": {
        "id": "145251",
        "name": { "given": "PHYSICIAN", "family": "SURGERY" },
        "role": { "code": "1.1", "display": "Primary" },
        "resourceType": "Practitioner"
      },
      "resourceType": "Procedure",
      "startDateTime": "2026-03-09T14:25:00-0400"
    }
  ],
  "status": "booked",
  "patient": {
    "name": { "given": "*", "family": "*" },
    "display": "*",
    "reference": "*",
    "identifier": [{ "type": "MRN", "value": "*" }, { "type": "AccountID", "value": "*" }]
  },
  "duration": 180,
  "location": { "room": "LIJFH OR 1", "display": "LIJFH OR 1", "facility": "FHOR" },
  "metadata": {
    "source": "Northwell-EPIC-OR",
    "createdAt": "2026-03-09T11:41:58.317-0400",
    "HL7Message": {
      "id": null,
      "rawData": "*",
      "sourceId": "334502.25677",
      "createdAt": "2026-03-09T11:41:47.000-0400"
    },
    "connectorRevision": null
  },
  "endDateTime": "2026-03-09T17:25:00-0400",
  "resourceType": "Appointment",
  "startDateTime": "2026-03-09T14:25:00-0400"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT HL7:
MSH|^~\\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114017|63263|SIU^S14|334502.25675|D
SCH||27756||||||||10800|S|^^^20260309142500|||||||||63263^^^|||||27731|Sch^Scheduled^SCHEDULING
ZCS|BEFORE|N|ORSCH_S14|||
PID|1|*|*^^^EPIC^MRN||*^*^^^^^L||*|F||||||||||*|||||||||||||N
PV1||OP Surg|LIJFH-OR^^^LIJFH^^^^^LIJFH OR^^DEPID|||||||||Pediatric||||||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI||110000359528
RGS|1||1
AIS|1||1078002605^Transplant - Double Lung|20260309142500|0|S|10800|S||||4
AIL|1||^LIJFH OR 1^^FHOR
AIP|1||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI|1.1^Primary|Pediatric|20260309142500|0|S|10800|S

OUTPUT JSON:
{
  "id": "27756",
  "reason": [
    {
      "id": "1",
      "note": [],
      "duration": 180,
      "endDateTime": "2026-03-09T17:25:00-0400",
      "serviceCode": { "code": "1078002605", "display": "Transplant - Double Lung" },
      "serviceLine": "Pediatric",
      "practitioner": {
        "id": "145251",
        "name": { "given": "PHYSICIAN", "family": "SURGERY" },
        "role": { "code": "1.1", "display": "Primary" },
        "resourceType": "Practitioner"
      },
      "resourceType": "Procedure",
      "startDateTime": "2026-03-09T14:25:00-0400"
    }
  ],
  "status": "booked",
  "patient": {
    "name": { "given": "*", "family": "*" },
    "display": "*",
    "reference": "*",
    "identifier": [{ "type": "MRN", "value": "*" }, { "type": "AccountID", "value": "*" }]
  },
  "duration": 180,
  "location": { "room": "LIJFH OR 1", "display": "LIJFH OR 1", "facility": "FHOR" },
  "metadata": {
    "source": "Northwell-EPIC-OR",
    "createdAt": "2026-03-09T11:40:22.824-0400",
    "HL7Message": {
      "id": null,
      "rawData": "*",
      "sourceId": "334502.25675",
      "createdAt": "2026-03-09T11:40:17.000-0400"
    },
    "connectorRevision": null
  },
  "endDateTime": "2026-03-09T17:25:00-0400",
  "resourceType": "Appointment",
  "startDateTime": "2026-03-09T14:25:00-0400"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT HL7:
MSH|^~\\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114012|63263|SIU^S14|334502.25674|D
SCH||27756||||||||10800|S|^^^20260309142500|||||||||63263^^^|||||27731|Sch^Scheduled^SCHEDULING
ZCS|BEFORE|N|ORSCH_S14|||
PID|1|*|*^^^EPIC^MRN||*^*^^^^^L||*|F||||||||||*|||||||||||||N
PV1||OP Surg|LIJFH-OR^^^LIJFH^^^^^LIJFH OR^^DEPID|||||||||Pediatric||||||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI||110000359528
RGS|1||1
AIS|1||1078002605^Transplant - Double Lung|20260309142500|0|S|10800|S||||4
AIL|1||^LIJFH OR 1^^FHOR
AIP|1||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI|1.1^Primary|Pediatric|20260309142500|0|S|10800|S

OUTPUT JSON:
{
  "id": "27756",
  "reason": [
    {
      "id": "1",
      "note": [],
      "duration": 180,
      "endDateTime": "2026-03-09T17:25:00-0400",
      "serviceCode": { "code": "1078002605", "display": "Transplant - Double Lung" },
      "serviceLine": "Pediatric",
      "practitioner": {
        "id": "145251",
        "name": { "given": "PHYSICIAN", "family": "SURGERY" },
        "role": { "code": "1.1", "display": "Primary" },
        "resourceType": "Practitioner"
      },
      "resourceType": "Procedure",
      "startDateTime": "2026-03-09T14:25:00-0400"
    }
  ],
  "status": "booked",
  "patient": {
    "name": { "given": "*", "family": "*" },
    "display": "*",
    "reference": "*",
    "identifier": [{ "type": "MRN", "value": "*" }, { "type": "AccountID", "value": "*" }]
  },
  "duration": 180,
  "location": { "room": "LIJFH OR 1", "display": "LIJFH OR 1", "facility": "FHOR" },
  "metadata": {
    "source": "Northwell-EPIC-OR",
    "createdAt": "2026-03-09T11:40:12.811-0400",
    "HL7Message": {
      "id": null,
      "rawData": "*",
      "sourceId": "334502.25674",
      "createdAt": "2026-03-09T11:40:12.000-0400"
    },
    "connectorRevision": null
  },
  "endDateTime": "2026-03-09T17:25:00-0400",
  "resourceType": "Appointment",
  "startDateTime": "2026-03-09T14:25:00-0400"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIELD MAPPING RULES (derived from examples above)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
id                            → SCH field 2
status                        → SCH field 26 component 1: "Sch"/"Scheduled" = "booked", "Cancelled" = "cancelled", "Pending" = "pending". Unrecognized: use raw + flag low confidence.
duration (top-level)          → AIS field 9 in seconds ÷ 60 = minutes (10800 → 180)
startDateTime                 → AIS field 4 (YYYYMMDDHHMMSS) → ISO 8601 YYYY-MM-DDTHH:MM:SS-0400
endDateTime                   → startDateTime + duration minutes
reason[0].id                  → AIS field 1
reason[0].duration            → same as top-level duration
reason[0].startDateTime       → same as top-level startDateTime
reason[0].endDateTime         → same as top-level endDateTime
reason[0].note                → always []
reason[0].resourceType        → always "Procedure"
reason[0].serviceCode.code    → AIS field 3 component 1
reason[0].serviceCode.display → AIS field 3 component 2
reason[0].serviceLine         → PV1 field 10
practitioner.id               → AIP field 3 component 1
practitioner.name.family      → AIP field 3 component 2
practitioner.name.given       → AIP field 3 component 3
practitioner.role.code        → AIP field 5 component 1
practitioner.role.display     → AIP field 5 component 2
practitioner.resourceType     → always "Practitioner"
location.room                 → AIL field 3 component 2
location.display              → same as location.room
location.facility             → AIL field 3 component 4
patient.*                     → from PID fields, preserve * exactly if already masked
metadata.source               → "{MSH field 4 component 1}-EPIC-OR"
metadata.createdAt            → MSH field 7 as ISO 8601 (add .000 ms if not present)
metadata.HL7Message.sourceId  → MSH field 10
metadata.HL7Message.createdAt → MSH field 7 as ISO 8601 with .000 milliseconds
metadata.HL7Message.rawData   → always "*"
metadata.HL7Message.id        → always null
metadata.connectorRevision    → always null
resourceType                  → always "Appointment"
"""

SAMPLE_HL7 = """MSH|^~\\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114142|63263|SIU^S14|334502.25676|D
SCH||27756||||||||10800|S|^^^20260309142500|||||||||63263^^^^|||||27731|Sch^Scheduled^SCHEDULING
ZCS|BEFORE|N|ORSCH_S14|||
PID|1|*|*^^^EPIC^MRN||*^*^^^^^L||*|F||||||||||*|||||||||||||N
PV1||OP Surg|LIJFH-OR^^^LIJFH^^^^^LIJFH OR^^DEPID|||||||||Pediatric||||||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI||110000359528
DG1|1||^Generalized abdominal pain [R10.84]|Generalized abdominal pain [R10.84]||^95;ORC
RGS|1||1
AIS|1||1078002605^Transplant - Double Lung|20260309142500|0|S|10800|S||||4
AIL|1||^LIJFH OR 1^^FHOR
AIP|1||145251^SURGERY^PHYSICIAN^^^^^^^PROVID^^^^PROVID~1103299990^SURGERY^PHYSICIAN^^^^^^^NPI^^^^NPI|1.1^Primary|Pediatric|20260309142500|0|S|10800|S"""

MSG_TYPE_OPTIONS = [
    "SIU — Scheduling",
    "ADT — Patient Admin",
    "DFT — Charges/Billing",
    "ORM — Orders",
]

# ════════════════════════════════════════════════════════════════════════════
# CUSTOM CSS (original morning style)
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    .main { padding: 2rem; }
    .stButton>button {
        width: 100%;
        background-color: #0066cc;
        color: white;
        height: 3em;
        font-size: 18px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# HEADER + TABS
# ════════════════════════════════════════════════════════════════════════════
st.title("🏥 AssistIQ Integration Tools")
st.markdown("**Flat file validation and HL7 message parsing in one place**")
st.markdown("---")

tab1, tab2 = st.tabs(["📁 Flat File Validator", "🔬 HL7 → JSON Parser"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — FLAT FILE VALIDATOR (original morning design)
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    # Sidebar content (only visible when on this tab due to Streamlit behaviour)
    with st.sidebar:
        st.markdown("### 📖 How to Use")
        st.markdown("""
        1. **Select file type** from the dropdown
        2. **Upload your file** (txt, csv, xlsx…)
        3. **Click Validate File** button
        4. **Review results** and fix any errors
        5. **Re-upload** until validation passes
        """)
        st.markdown("---")
        st.markdown("### ✅ What Gets Validated")
        st.markdown("""
        - ✓ Filename format (YYYY-MM-DD.txt)
        - ✓ File delimiter (pipe |)
        - ✓ Required columns present
        - ✓ Column name spelling
        - ✓ Data types (String, Integer, Boolean, Date)
        - ✓ Data completeness (no empty required fields)
        - ✓ Business rules (dates, relationships)
        - ✓ Timestamp formats (UTC)
        """)
        st.markdown("---")
        st.markdown("### 📞 Support")
        st.markdown("""
        Having issues? Contact:
        - **Email:** support@assistiq.com
        - **Slack:** #integration-help
        """)

    # Main content
    col1, col2 = st.columns([2, 1])

    with col1:
        file_type = st.selectbox(
            "**Select File Type** 📁",
            list(FILE_TYPE_INFO.keys()),
            format_func=lambda x: FILE_TYPE_INFO[x]["name"]
        )
        info = FILE_TYPE_INFO[file_type]
        st.info(f"**{info['name']}**: {info['description']}")
        st.caption(f"📄 Example filename: `{info['example_filename']}`")

    with col2:
        st.markdown("### 📊 Quick Stats")
        if "validation_count" not in st.session_state:
            st.session_state.validation_count = 0
        if "pass_count" not in st.session_state:
            st.session_state.pass_count = 0
        st.metric("Files Validated", st.session_state.validation_count)
        st.metric("Files Passed", st.session_state.pass_count)

    st.markdown("---")

    uploaded_file = st.file_uploader(
        "**Upload File** 📤",
        type=["txt", "csv", "tsv", "xlsx", "xls"],
        help="Upload your data file in any format: TXT (pipe-delimited), CSV, TSV, Excel (.xlsx/.xls)"
    )

    if uploaded_file is not None:
        try:
            file_content, conversion_info = convert_to_pipe_delimited(uploaded_file, uploaded_file.name)
            lines = file_content.split('\n')

            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Filename", uploaded_file.name)
            with col2: st.metric("Format", conversion_info)
            with col3: st.metric("File Size", f"{len(file_content)} bytes")
            with col4: st.metric("Total Lines", len(lines))

            if "converted" in conversion_info:
                st.info(f"ℹ️ File automatically converted from {uploaded_file.name.split('.')[-1].upper()} to pipe-delimited for validation")

            with st.expander("📄 **File Preview** (first 20 lines, pipe-delimited)", expanded=False):
                st.code('\n'.join(lines[:20]), language='text')

            st.markdown("---")

            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔍 **VALIDATE FILE**", type="primary"):
                    with st.spinner("🔄 Validating file with Claude AI... This may take 10-30 seconds..."):
                        try:
                            result = validate_file(file_content, uploaded_file.name, file_type)
                            st.session_state.validation_count += 1

                            st.markdown("---")
                            st.markdown("## 📋 Validation Results")

                            is_pass = "PASS" in result.split('\n')[0]
                            if is_pass:
                                st.session_state.pass_count += 1
                                st.success("### ✅ Validation Passed!")
                                st.balloons()
                            else:
                                st.error("### ❌ Validation Failed - Errors Found")

                            st.markdown(result)

                            st.markdown("---")
                            col1, col2 = st.columns(2)
                            with col1:
                                if is_pass:
                                    st.success("✅ **This file is ready for upload to AssistIQ**")
                                else:
                                    st.warning("⚠️ **Please fix errors and re-validate**")
                            with col2:
                                st.download_button(
                                    label="📥 Download Validation Report",
                                    data=result,
                                    file_name=f"validation_report_{uploaded_file.name}.txt",
                                    mime="text/plain"
                                )
                        except Exception as e:
                            st.error(f"❌ **Error during validation:** {str(e)}")
                            st.exception(e)

        except UnicodeDecodeError:
            st.error("❌ **Error:** Unable to read file. Please ensure it's UTF-8 encoded.")
        except Exception as e:
            st.error(f"❌ **Error reading/converting file:** {str(e)}")
    else:
        st.info("👆 **Please upload a file to begin validation**")
        st.markdown("### 📝 Supported File Formats")
        st.markdown("""
        Upload files in any of these formats:
        - **TXT:** Pipe (|), comma, or tab delimited
        - **CSV:** Comma-separated values
        - **TSV:** Tab-separated values
        - **Excel:** .xlsx or .xls files

        **All formats are automatically converted to pipe-delimited for validation.**

        **Additional Requirements:**
        - **Encoding:** UTF-8 (for text files)
        - **Filename:** YYYY-MM-DD.txt format (e.g., 2026-02-10.txt)
        - **First row:** Must contain column headers
        """)

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — HL7 → JSON PARSER (afternoon version)
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### HL7 → JSON Parser")
    st.markdown("Paste a raw HL7 message to convert it to AssistIQ appointment JSON format.")

    col_in, col_out = st.columns(2)

    with col_in:
        # Message type + hospital on same row
        c1, c2 = st.columns(2)
        with c1:
            msg_type = st.selectbox("**Message Type**", MSG_TYPE_OPTIONS)
        with c2:
            hospital = st.text_input("**Hospital / Facility** (optional)", placeholder="e.g. Baptist, Northwell")

        st.markdown("**Raw HL7 Input**")
        if st.button("Load Sample Message"):
            st.session_state["hl7_input"] = SAMPLE_HL7

        hl7_input = st.text_area(
            "Paste HL7 message here",
            value=st.session_state.get("hl7_input", ""),
            height=300,
            placeholder="MSH|^~\\&|EPIC|BAPTIST...",
            label_visibility="collapsed"
        )

        if st.button("🔄 Parse & Map", type="primary"):
            if hl7_input.strip():
                with st.spinner("Parsing message..."):
                    try:
                        client = get_claude_client()
                        prompt = f"""{FEW_SHOT}

Now parse the new HL7 message below using the EXACT same JSON structure and field mapping rules.
Hospital context: {hospital if hospital else "not specified"}
Message type: {msg_type}

HL7 MESSAGE TO PARSE:
{hl7_input}

STRICT RULES:
- Return ONLY valid JSON, no markdown, no backticks, no explanation
- All fields must follow the exact structure shown in the examples
- metadata.HL7Message.id must always be null
- metadata.connectorRevision must always be null
- metadata.HL7Message.rawData must always be "*"
- Include a "confidence" field at the top level: "high", "medium", or "low"
- Include a "flags" array listing any fields you were uncertain about"""

                        message = client.messages.create(
                            model=get_anthropic_model(),
                            max_tokens=2000,
                            messages=[{"role": "user", "content": prompt}]
                        )
                        raw = message.content[0].text.replace("```json", "").replace("```", "").strip()
                        parsed = json.loads(raw)
                        st.session_state["hl7_result"] = parsed
                        st.session_state["hl7_raw"] = raw
                    except Exception as e:
                        st.error(f"Parse failed: {str(e)}")
            else:
                st.warning("Please paste an HL7 message first.")

    with col_out:
        if "hl7_result" in st.session_state:
            result = st.session_state["hl7_result"]
            confidence = result.get("confidence", "unknown")
            conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")

            st.markdown(f"**Confidence: {conf_icon} {confidence.upper()}**")

            flags = result.get("flags", [])
            if flags:
                st.warning(f"⚠️ Flagged fields: {', '.join(flags)}")

            out_tab1, out_tab2, out_tab3 = st.tabs(["Mapped JSON", "Field Map", "Unmapped"])

            with out_tab1:
                display = {k: v for k, v in result.items() if k not in ("confidence", "flags")}
                st.code(json.dumps(display, indent=2), language="json")
                st.download_button(
                    "📥 Download JSON",
                    data=json.dumps(display, indent=2),
                    file_name="appointment.json",
                    mime="application/json"
                )

            with out_tab2:
                # Show key top-level fields in a readable way
                key_fields = ["id", "status", "duration", "startDateTime", "endDateTime", "resourceType"]
                for f in key_fields:
                    if f in result:
                        st.markdown(f"**{f}**: `{result[f]}`")
                if result.get("location"):
                    loc = result["location"]
                    st.markdown(f"**location.room**: `{loc.get('room', '—')}`")
                    st.markdown(f"**location.facility**: `{loc.get('facility', '—')}`")
                if result.get("reason") and len(result["reason"]) > 0:
                    r = result["reason"][0]
                    sc = r.get("serviceCode", {})
                    st.markdown(f"**serviceCode.code**: `{sc.get('code', '—')}`")
                    st.markdown(f"**serviceCode.display**: `{sc.get('display', '—')}`")
                    st.markdown(f"**serviceLine**: `{r.get('serviceLine', '—')}`")
                    p = r.get("practitioner", {})
                    name = p.get("name", {})
                    st.markdown(f"**practitioner**: `{name.get('given', '')} {name.get('family', '')}`")
                if result.get("metadata"):
                    m = result["metadata"]
                    st.markdown(f"**metadata.source**: `{m.get('source', '—')}`")
                    st.markdown(f"**metadata.HL7Message.sourceId**: `{m.get('HL7Message', {}).get('sourceId', '—')}`")

            with out_tab3:
                flags = result.get("flags", [])
                if not flags:
                    st.success("✅ All fields mapped successfully")
                else:
                    for f in flags:
                        st.warning(f"⚠️ {f}")
        else:
            st.info("Output will appear here after parsing.")

# ════════════════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <small>AssistIQ Integration Tools v3.0 | Powered by Claude AI |
    <a href='https://www.assistiq.com' target='_blank'>www.assistiq.com</a></small>
</div>
""", unsafe_allow_html=True)
