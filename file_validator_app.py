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
        st.markdown(
            """
            <a href="https://www.assistiq.ai" target="_blank">
                <img src="https://www.assistiq.ai/hubfs/website/brand/logos/primary-nav-logo.svg" width="160">
            </a>
            """, 
            unsafe_allow_html=True
        )

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

with st.sidebar:
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <a href="https://www.assistiq.ai" target="_blank">
                <img src="https://www.assistiq.ai/hubfs/website/brand/logos/primary-nav-logo.svg" width="160">
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )
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
FILE: Case Picklists Data Extract (Section 3.1)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All cases scheduled for <daterun> and <daterun> + 3 days
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (9 columns exactly):
| Column               | Required | Description                                      | Format                    |
|----------------------|----------|--------------------------------------------------|---------------------------|
| case_id              | Y        | Unique identifier for the case                   | String                    |
| case_timestamp       | Y        | Case scheduled time in UTC                       | yyyy-MM-dd'T'HH:mm:ss     |
| picklist_id          | Y        | Case pick list identifier                        | String                    |
| procedure_id         | Y        | Identifier for the service/procedure of the case | String                    |
| primary_provider_id  | Y        | Id of the primary provider associated to case    | String                    |
| supply_id            | Y        | Identifier for the supply in the picklist        | String                    |
| is_implant           | Y        | Is the supply of type implant                    | Boolean (true/false, 1/0) |
| open_qty             | Y        | Open quantity                                    | Integer >= 0              |
| hold_qty             | Y        | Hold/PRN quantity                                | Integer >= 0              |

IMPORTANT: created_ts and updated_ts are NOT part of this spec. Do NOT flag their absence as errors.
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "charge_capture": """You are a data validation expert for AssistIQ integration files. Validate the Charge Capture file against exact specifications.

<file_specification>
FILE: Charge Capture Cases Data Extract (Section 3.2)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All cases scheduled between <daterun - 14 days> and <daterun>
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (20 columns):
| Column                           | Required | Description                                                       | Format                    |
|----------------------------------|----------|-------------------------------------------------------------------|---------------------------|
| case_id                          | Y        | Unique identifier for the case                                    | String                    |
| case_timestamp                   | Y        | Case scheduled time in UTC                                        | yyyy-MM-dd'T'HH:mm:ss     |
| picklist_id                      | Y        | Case pick list identifier                                         | String                    |
| primary_procedure_id             | Y        | Identifier for the primary service/procedure of the case          | String                    |
| primary_provider_id              | Y        | Identifier for the primary provider/doctor                        | String                    |
| supply_id                        | Y        | Identifier for the supply in the picklist                         | String                    |
| is_implant                       | Y        | Is the supply of type implant                                     | Boolean (true/false, 1/0) |
| used_qty                         | Y        | Quantity used, inclusive of wasted qty                            | Integer > 0               |
| wasted_qty                       | Y        | Wasted quantity                                                   | Integer >= 0              |
| wasted_reason                    | Y        | Reason for wasted qty                                             | String                    |
| is_onetime_supply                | Y        | Flag if entered as a one time product (implant/supply)            | Boolean (true/false, 1/0) |
| item_description                 | Y        | Item description                                                  | String                    |
| item_manufacturer                | Y        | Item manufacturer name                                            | String                    |
| item_manufacturer_id             | Y        | Item manufacturer's unique id in system                           | String                    |
| item_manufacturer_catalog_number | Y        | Item manufacturer catalog number                                  | String                    |
| item_price                       | Y        | Item unit price                                                   | Float >= 0                |
| lot_number                       | Y        | Lot number for the supply                                         | String                    |
| expiration_date                  | Y        | Expiration date for the supply                                    | yyyy-MM-dd                |
| serial_number                    | Y        | Serial number                                                     | String                    |
| picklist_type                    | Y        | Usage source: "Intra-op Pick List" or "Implant usage"             | String                    |

IMPORTANT NOTES:
- "quantity_used" is WRONG — correct name is "used_qty"
- "quantity_wasted" is WRONG — correct name is "wasted_qty"
- "unit_price" is WRONG — correct name is "item_price"
- "total_price" is NOT in spec — do not flag its absence as an error
- "created_ts" and "updated_ts" are NOT in spec — do not flag their absence
- "reason_wasted" is WRONG — correct name is "wasted_reason"
- Null/empty values in lot_number, serial_number, expiration_date are acceptable for non-implant rows
- "NULL" string values should be flagged — fields should be empty/blank not the string "NULL"
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "preference_cards": """You are a data validation expert for AssistIQ integration files. Validate the Preference Cards file against exact specifications.

<file_specification>
FILE: Preference Card Data Extract (Section 3.3)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All active preference cards at the time of extraction
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (9 columns):
| Column             | Required | Description                                        | Format                    |
|--------------------|----------|----------------------------------------------------|---------------------------|
| preference_card_id | Y        | Unique identifier for the preference card          | String                    |
| card_name          | N        | Preference card name                               | String                    |
| procedure_id       | Y        | Identifier for the primary service/procedure       | String                    |
| provider_id        | Y        | Identifier for the primary provider/doctor         | String (NOT primary_provider_id) |
| supply_id          | Y        | Identifier for the supply in the picklist          | String                    |
| is_implant         | Y        | Is the supply of type implant                      | Boolean (true/false, 1/0) |
| open_qty           | Y        | Open quantity                                      | Integer >= 0              |
| hold_qty           | Y        | Hold/PRN quantity                                  | Integer >= 0              |
| location           | Y        | Location identifier                                | String                    |

IMPORTANT NOTES:
- "provider_id" is CORRECT per spec — do NOT flag it as wrong or suggest renaming to "primary_provider_id"
- "card_name" is optional (N) — do not flag its absence as an error
- "is_implant" and "location" are valid columns per spec — do NOT flag them as extra/unexpected
- "procedure_name", "created_ts", "updated_ts" are NOT in this spec — do not flag their absence
- The file should represent ALL preference cards in the EHR for all active procedures and providers
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "chargeable_supplies": """You are a data validation expert for AssistIQ integration files. Validate the Chargeable Supplies file against exact specifications.

<file_specification>
FILE: Chargeable Supplies Data Extract (Section 3.4)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All chargeable products
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (4 columns):
| Column      | Required | Description                   | Format  |
|-------------|----------|-------------------------------|---------|
| supply_id   | Y        | Unique identifier for supply  | String  |
| is_implant  | Y        | Is the supply an implant      | String  |
| is_tissue   | Y        | Is the supply a tissue        | String  |
| supply_name | Y        | Supply name                   | String  |

IMPORTANT NOTES:
- "product_id" is WRONG — correct name is "supply_id"
- This file has only 4 columns — do not expect or require Product Master fields like gtin, price, manufacturer etc.
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "service_lines": """You are a data validation expert for AssistIQ integration files. Validate the Service Lines file against exact specifications.

<file_specification>
FILE: Service Lines Data Extract (Section 3.5)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All service lines for active procedures
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (5 columns):
| Column              | Required | Description                                        | Format  |
|---------------------|----------|----------------------------------------------------|---------|
| service_line_id     | Y        | Unique identifier for the service line             | String  |
| service_line_name   | Y        | Service line name                                  | String  |
| service_line_abbrev | Y        | Service line abbreviation                          | String  |
| procedure_id        | Y        | Identifier for the primary service/procedure       | String  |
| procedure_name      | Y        | Procedure name                                     | String  |

IMPORTANT NOTES:
- "created_ts" and "updated_ts" are NOT in spec — do not flag their absence
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "service_line_providers": """You are a data validation expert for AssistIQ integration files. Validate the Service Line Providers file against exact specifications.

<file_specification>
FILE: Service Line Providers Data Extract (Section 3.6)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All providers for all service lines for active procedures
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (8 columns):
| Column               | Required | Description                              | Format                    |
|----------------------|----------|------------------------------------------|---------------------------|
| service_line_id      | Y        | Unique identifier for the service line   | String                    |
| service_line_name    | Y        | Service line name                        | String                    |
| service_line_abbrev  | Y        | Service line abbreviation                | String                    |
| provider_id          | Y        | Identifier for the provider on the case  | String                    |
| provider_first_name  | Y        | Provider/doctor first name               | String                    |
| provider_middle_name | Y        | Provider/doctor middle name              | String                    |
| provider_last_name   | Y        | Provider/doctor last name                | String                    |
| is_active            | Y        | Is the doctor active and practicing      | Boolean (true/false, 1/0) |

IMPORTANT NOTES:
- "created_ts" and "updated_ts" are NOT in spec — do not flag their absence
- "provider_middle_name" may be empty/null — this is acceptable
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",

    "product_master": """You are a data validation expert for AssistIQ integration files. Validate the Product Master file against exact specifications.

<file_specification>
FILE: Products Master Data Extract (Section 3.7)
FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"  e.g. 2026-03-24.txt
DELIMITER: Pipe (|)
LINE ENDING: Newline
EXTRACTION: All active products
FREQUENCY: Daily (prior to 6am local timezone)

REQUIRED FIELDS (14 columns):
| Column                       | Required | Description                                          | Format        |
|------------------------------|----------|------------------------------------------------------|---------------|
| product_id                   | Y        | Identifier for the supply/product in the picklist    | String        |
| gtin                         | N        | Item's GTIN                                          | String        |
| description                  | Y        | Item's description                                   | String        |
| category                     | Y        | Product categorization in the system                 | String        |
| type                         | Y        | supply vs implant vs tissue                          | String        |
| active                       | Y        | Whether product is active (in use)                   | Boolean       |
| price                        | Y        | Unit price of product used                           | Float >= 0    |
| supplier_id                  | N        | Item's supplier ID                                   | String        |
| supplier_name                | N        | Item's supplier name                                 | String        |
| supplier_product_id          | Y        | Item's supplier product catalog number               | String        |
| manufacturer_id              | N        | Item's manufacturer ID in system                     | String        |
| manufacturer_name            | N        | Item's manufacturer name                             | String        |
| manufacturer_catalog_number  | N        | Item's manufacturer product catalog number (SKU)     | String        |
| billing_code                 | Y        | Billing code that goes into Epic for this product    | String        |

IMPORTANT NOTES:
- All column names use snake_case — camelCase versions like "productId", "productDesc", "isImplant" are WRONG
- "billing_code" is required and must be present
- "isImplant" is NOT in this spec — do not require it
- "typeCode" and "typeDesc" are NOT in spec — the correct columns are "category" and "type"
- "supplierDesc" is WRONG — correct name is "supplier_name"
- "supplierCatalogNumber" is WRONG — correct name is "supplier_product_id"
- "manufacturerCatalogNumber" is WRONG — correct name is "manufacturer_catalog_number"
</file_specification>

Validate the file and provide results in this ACTIONABLE format:

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

## 📋 COLUMN ERRORS
[Show ONLY columns with errors. If all correct, say "All columns correct"]

| Your Column Name | Expected Name | Fix Action |
|------------------|---------------|------------|

---

## 🔍 MISSING COLUMNS
[List ONLY missing required columns. If none, say "No missing columns"]

---

## 🚨 DATA ERRORS BY ROW
[Show first 10 rows with errors. If none, say "No data errors"]

| Row | Column | Current Value | Error | Fix |
|-----|--------|---------------|-------|-----|

---

## ✅ STEP-BY-STEP FIX PLAN
**Step 1: [Action]**
[Instructions]

---

## 📊 QUICK STATS
- Rows validated: [number]
- Rows with errors: [number]
- Error rate: [percentage]%""",
}

FILE_TYPE_INFO = {
    "case_picklist":         {"name": "Case Pick Lists (3.1)",         "description": "Daily case schedules with supply lists for today + next 72 hours",          "example_filename": "2026-03-24.txt"},
    "charge_capture":        {"name": "Charge Capture (3.2)",          "description": "Product usage and charges from previous 14 days",                          "example_filename": "2026-03-24.txt"},
    "preference_cards":      {"name": "Preference Cards (3.3)",        "description": "All active preference cards for all active procedures and providers",       "example_filename": "2026-03-24.txt"},
    "chargeable_supplies":   {"name": "Chargeable Supplies (3.4)",     "description": "All chargeable products from the EHR system",                              "example_filename": "2026-03-24.txt"},
    "service_lines":         {"name": "Service Lines (3.5)",           "description": "Service lines with associated procedures",                                 "example_filename": "2026-03-24.txt"},
    "service_line_providers":{"name": "Service Line Providers (3.6)",  "description": "Providers/doctors for each service line",                                  "example_filename": "2026-03-24.txt"},
    "product_master":        {"name": "Product Master (3.7)",          "description": "Complete product master from EHR or ERP system",                           "example_filename": "2026-03-24.txt"},
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
        model="claude-sonnet-4-20250514",
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
FIELD MAPPING RULES (enhanced — handles real-world variance across Epic, GE, MEDITECH)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── APPOINTMENT ID ──
id → SCH field 2. If empty, try SCH field 1.

── STATUS (normalize all variants) ──
status → Check SCH-25 first, then SCH-26.
  Normalize:
    "Sch", "SCH", "Scheduled", "BOOKED", "Booked", "booked" → "booked"
    "Cancel", "Cancelled", "CANCELLED", "Canceled"          → "cancelled"
    "Arrived", "ARRIVED"                                     → "arrived"
    "Complete", "Completed", "COMPLETED", "Done"             → "fulfilled"
    "Pending", "PENDING"                                     → "pending"
  If unrecognized: use raw value and add "status" to flags array.

── DURATION (handle seconds / minutes / hours) ──
duration → Check AIS-7 with AIS-8 as the unit. If AIS is absent, check SCH-9 with SCH-10 as unit.
  Unit conversion:
    "S" or "s" (seconds) → divide by 60 to get minutes
    "MIN", "min", "m", "M" (minutes) → use as-is
    "h", "H", "hr", "HR" (hours) → multiply by 60
  Always output duration as an integer number of minutes.
  Example: AIS field 7 = 10800, field 8 = S → 10800 ÷ 60 = 180 minutes.

── START DATETIME ──
startDateTime → Check AIS-4 first (format YYYYMMDDHHMMSS).
  If AIS-4 is empty or AIS is absent, check SCH-11 — this field uses format ^^^YYYYMMDDHHMMSS,
  take the 4th component after splitting by ^.
  Convert to ISO 8601: YYYY-MM-DDTHH:MM:SS
  Timezone: if the original message contains a timezone offset (e.g. -0400), preserve it.
  If no timezone is present, append -0400 (Eastern) and add "timezone_assumed" to flags.

── END DATETIME ──
endDateTime → startDateTime + duration minutes. Always calculate, never leave null.

── SERVICE CODE ──
reason[0].serviceCode.code    → AIS-3 component 1
reason[0].serviceCode.display → AIS-3 component 2

── SERVICE LINE ──
reason[0].serviceLine → Check PV1-10 first.
  If PV1-10 is empty, check AIP-5 (the service line / specialty field).
  If still empty, check RGS-3 component 2.
  If none found, set to null and add "serviceLine" to flags.

── PROVIDER (priority fallback logic) ──
  Step 1: If multiple AIP segments exist, select the one where AIP-5 component 2 contains
          "Primary" or AIP-4 component 1 is "1.1". If no primary marked, use first AIP.
  Step 2: If AIP segment is absent or AIP-3 is empty, fall back to PV1-7 (attending physician).
  Step 3: If PV1-7 is also empty, try PV1-8 (referring physician).
  Always add "practitioner_source" to flags indicating which segment was used (AIP/PV1-7/PV1-8).

practitioner.id           → AIP-3 component 1 (or PV1-7/8 component 1 if fallback)
practitioner.name.family  → AIP-3 component 2 (or PV1-7/8 component 2 if fallback)
practitioner.name.given   → AIP-3 component 3 (or PV1-7/8 component 3 if fallback)
practitioner.role.code    → AIP-4 component 1 (if from AIP). If from PV1 fallback, use "attending"
practitioner.role.display → AIP-4 component 2 (if from AIP). If from PV1 fallback, use "Attending"
practitioner.resourceType → always "Practitioner"

  If multiple AIP segments exist beyond the primary, include them in an
  "additionalProviders" array at the top level, each with id/name/role fields.

── LOCATION (fallback logic) ──
location.room     → AIL-3 component 2 first. If empty, try AIL-3 component 1.
                    If AIL segment is absent, use PV1-3 component 2.
location.display  → same as location.room
location.facility → AIL-3 component 4 first. If empty, use PV1-3 component 4.
                    If still empty, use MSH-4 component 1.
  Add "location_source" to flags if falling back to PV1 or MSH.

── PATIENT ──
patient.* → from PID fields. Preserve * exactly if already masked.
  identifier[0]: type = "MRN", value = PID-3 component 1
  identifier[1]: type = "AccountID", value = PID-18 (if present)
  name.family = PID-5 component 1
  name.given  = PID-5 component 2

── METADATA ──
metadata.source               → "{MSH-4 component 1}-EPIC-OR"
metadata.createdAt            → MSH-7 as ISO 8601 with milliseconds (add .000 if absent)
metadata.HL7Message.sourceId  → MSH-10
metadata.HL7Message.createdAt → MSH-7 as ISO 8601 with .000 milliseconds
metadata.HL7Message.rawData   → always "*"
metadata.HL7Message.id        → always null
metadata.connectorRevision    → always null
resourceType                  → always "Appointment"

── FIXED FIELDS ──
reason[0].id           → AIS-1
reason[0].note         → always []
reason[0].resourceType → always "Procedure"
reason[0].duration     → same as top-level duration
reason[0].startDateTime → same as top-level startDateTime
reason[0].endDateTime  → same as top-level endDateTime
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
        st.markdown("---")
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
- Apply ALL fallback logic from the FIELD MAPPING RULES — provider, location, duration units, status normalization, and start datetime fallbacks
- If multiple AIP segments exist, include additional providers in "additionalProviders" array
- Include a "confidence" field at the top level: "high", "medium", or "low"
- Include a "flags" array listing: any fields you fell back on, any assumed values (e.g. timezone_assumed), and any fields you were uncertain about
- duration must always be an integer number of minutes — never seconds or hours
- endDateTime must always be calculated, never null"""

                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
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
                key_fields = ["id", "status", "duration", "startDateTime", "endDateTime", "resourceType", "confidence"]
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
                    st.markdown(f"**practitioner.role**: `{p.get('role', {}).get('display', '—')}`")
                if result.get("additionalProviders"):
                    st.markdown(f"**additionalProviders**: `{len(result['additionalProviders'])} additional provider(s)`")
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
