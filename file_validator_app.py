import streamlit as st
import anthropic
import os
import pandas as pd
from io import StringIO

# Initialize Claude client
@st.cache_resource
def get_claude_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("⚠️ ANTHROPIC_API_KEY environment variable not set!")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

def convert_to_pipe_delimited(file, filename):
    """Convert various file formats to pipe-delimited text"""
    
    file_ext = filename.lower().split('.')[-1]
    
    try:
        if file_ext == 'txt':
            # Read as text - check if it's already pipe-delimited
            content = file.read().decode('utf-8')
            
            # Check if it's pipe-delimited
            if '|' in content.split('\n')[0]:
                return content, "txt (pipe-delimited)"
            
            # Check if it's tab-delimited
            elif '\t' in content.split('\n')[0]:
                df = pd.read_csv(StringIO(content), sep='\t')
                pipe_content = df.to_csv(sep='|', index=False)
                return pipe_content, "txt (tab-delimited, converted to pipe)"
            
            # Check if it's comma-delimited
            elif ',' in content.split('\n')[0]:
                df = pd.read_csv(StringIO(content))
                pipe_content = df.to_csv(sep='|', index=False)
                return pipe_content, "txt (comma-delimited, converted to pipe)"
            
            else:
                return content, "txt (unknown delimiter)"
                
        elif file_ext == 'csv':
            # Read CSV and convert to pipe-delimited
            df = pd.read_csv(file)
            pipe_content = df.to_csv(sep='|', index=False)
            return pipe_content, "csv (converted to pipe)"
            
        elif file_ext == 'tsv':
            # Read TSV and convert to pipe-delimited
            df = pd.read_csv(file, sep='\t')
            pipe_content = df.to_csv(sep='|', index=False)
            return pipe_content, "tsv (converted to pipe)"
            
        elif file_ext in ['xlsx', 'xls']:
            # Read Excel and convert to pipe-delimited
            df = pd.read_excel(file, engine='openpyxl' if file_ext == 'xlsx' else None)
            pipe_content = df.to_csv(sep='|', index=False)
            return pipe_content, f"{file_ext} (converted to pipe)"
            
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
            
    except Exception as e:
        raise Exception(f"Error converting file: {str(e)}")

# Validation prompts for each file type
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

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| service_line_id     | Y        | Unique service line identifier       | String                    | Non-empty, unique                   |
| service_line_name   | Y        | Service line name                    | String                    | Non-empty, max 100 chars            |
| service_line_abbrev | Y        | Service line abbreviation            | String                    | Non-empty, max 20 chars             |
| procedure_id        | Y        | Procedure identifier                 | String                    | Non-empty                           |
| procedure_name      | Y        | Procedure name                       | String                    | Non-empty, max 255 chars            |
| created_ts          | Y        | Record created timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| updated_ts          | Y        | Record updated timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
</file_specification>

Validate the file thoroughly and provide detailed feedback.""",

    "service_line_providers": """You are a data validation expert for AssistIQ integration files. Validate the Service Line Providers file against exact specifications.

<file_specification>
FILE: Service Line Providers

FILENAME: <daterun>.txt where <daterun> is "YYYY-MM-DD"
DELIMITER: Pipe (|)

REQUIRED FIELDS:
| Column              | Required | Description                          | Format                    | Validation Rules                    |
|---------------------|----------|--------------------------------------|---------------------------|-------------------------------------|
| service_line_id     | Y        | Service line identifier              | String                    | Non-empty                           |
| service_line_name   | Y        | Service line name                    | String                    | Non-empty                           |
| provider_id         | Y        | Provider identifier                  | String                    | Non-empty                           |
| provider_first_name | Y        | Provider first name                  | String                    | Non-empty, max 100 chars            |
| provider_middle_name| N        | Provider middle name                 | String                    | Max 100 chars if present            |
| provider_last_name  | Y        | Provider last name                   | String                    | Non-empty, max 100 chars            |
| is_active           | Y        | Active status                        | Boolean                   | true/false, 1/0, Y/N                |
| created_ts          | Y        | Record created timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
| updated_ts          | Y        | Record updated timestamp             | yyyy-MM-dd'T'HH:mm:ss    | Valid UTC datetime                  |
</file_specification>

Validate the file thoroughly and provide detailed feedback."""
}

FILE_TYPE_INFO = {
    "case_picklist": {
        "name": "Case Pick Lists",
        "description": "Daily case schedules with supply lists for next 72 hours",
        "example_filename": "2026-02-10.txt"
    },
    "charge_capture": {
        "name": "Charge Capture",
        "description": "Product usage and charges from previous 14 days",
        "example_filename": "2026-02-10.txt"
    },
    "preference_cards": {
        "name": "Preference Cards",
        "description": "Surgeon-specific supply preferences for procedures",
        "example_filename": "2026-02-10.txt"
    },
    "product_master": {
        "name": "Product Master",
        "description": "Complete product catalog from ERP system",
        "example_filename": "2026-02-10.txt"
    },
    "service_lines": {
        "name": "Service Lines",
        "description": "Service lines with associated procedures",
        "example_filename": "2026-02-10.txt"
    },
    "service_line_providers": {
        "name": "Service Line Providers",
        "description": "Providers/doctors for each service line",
        "example_filename": "2026-02-10.txt"
    }
}

def validate_file(file_content, filename, file_type):
    """Send file to Claude for validation"""
    
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
| used_qty         | quantity_used | Rename column |

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
- Error rate: [percentage]%
"""
    
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return message.content[0].text

FIXED_SCHEMA = {
    "case_id": "Unique case/scheduling identifier",
    "patient_id": "Patient medical record number",
    "patient_name": "Full patient name",
    "surgeon": "Primary surgeon name",
    "procedure": "Procedure or surgery name",
    "room": "OR or procedure room",
    "scheduled_time": "Scheduled date and time (ISO format)",
    "department": "Hospital department or service",
    "status": "Case status (scheduled, cancelled, modified)",
    "attending_physician": "Attending physician if different from surgeon",
}

SAMPLE_HL7 = """MSH|^~\\&|EPIC|BAPTIST|BRIDGES|BRIDGES|20260306090000||SIU^S12|123456|P|2.3
SCH|123456||20260306090000|60|MIN||^^^20260306090000^20260306100000
PID|1||MRN98765^^^Baptist^MR||Smith^John^A||19700101|M
PV1|1|I|OR-3^OR-3^OR-3|||||||Smith^Dr. Jane^^^MD
AIG|1||12345^Dr. Jane Smith^EPIC
AIL|1||OR-3^Operating Room 3^EPIC
TQ1|1|||20260306090000|20260306100000
ZPR|CABG^Coronary Artery Bypass Graft|CARD|SCHEDULED"""

def parse_hl7_message(hl7_text):
    """Send HL7 message to Claude for parsing and mapping"""
    client = get_claude_client()

    prompt = f"""You are an HL7 message parser for a surgical supply tracking system. Parse the following HL7 SIU message and map it to the fixed JSON schema below.

TARGET SCHEMA:
{str(FIXED_SCHEMA)}

HL7 MESSAGE:
{hl7_text}

Respond ONLY with a valid JSON object in this exact structure (no markdown, no backticks):
{{
  "mapped": {{
    "case_id": "...",
    "patient_id": "...",
    "patient_name": "...",
    "surgeon": "...",
    "procedure": "...",
    "room": "...",
    "scheduled_time": "...",
    "department": "...",
    "status": "...",
    "attending_physician": "..."
  }},
  "field_explanations": {{
    "case_id": "Found in SCH segment field 1"
  }},
  "unmapped_fields": ["field_name"],
  "unmapped_reasons": {{
    "field_name": "Segment not present in message"
  }},
  "confidence": "high",
  "notes": "Any important observations"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    import json
    text = message.content[0].text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# Configure page
st.set_page_config(
    page_title="AIQ File Validator",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #0066cc;
        color: white;
        height: 3em;
        font-size: 18px;
        font-weight: bold;
    }
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.25rem;
        color: #155724;
    }
    .error-box {
        padding: 1rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.25rem;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.title("🏥 AssistIQ Integration Tools")
st.markdown("**Flat file validation and HL7 message parsing in one place**")
st.markdown("---")

tab1, tab2 = st.tabs(["📄 Flat File Validator", "🔬 HL7 Parser"])

with tab2:
    st.markdown("### HL7 → JSON Parser")
    st.markdown("Paste a raw SIU message to map it to the AssistIQ case schema.")

    col_in, col_out = st.columns(2)

    with col_in:
        st.markdown("**Raw HL7 Input**")
        if st.button("Load Sample Message"):
            st.session_state.hl7_input = SAMPLE_HL7
        hl7_input = st.text_area(
            "Paste HL7 message here",
            value=st.session_state.get("hl7_input", ""),
            height=300,
            placeholder="MSH|^~\\&|EPIC|BAPTIST...",
            label_visibility="collapsed"
        )

        st.markdown("**Fixed Target Schema**")
        st.caption(" · ".join(FIXED_SCHEMA.keys()))

        if st.button("🔍 Parse & Map", type="primary"):
            if hl7_input.strip():
                with st.spinner("Parsing message..."):
                    try:
                        result = parse_hl7_message(hl7_input)
                        st.session_state.hl7_result = result
                    except Exception as e:
                        st.error(f"Parse failed: {str(e)}")
            else:
                st.warning("Please paste an HL7 message first.")

    with col_out:
        if "hl7_result" in st.session_state:
            result = st.session_state.hl7_result
            confidence = result.get("confidence", "unknown")
            conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")

            st.markdown(f"**Confidence: {conf_color} {confidence.upper()}**")

            out_tab1, out_tab2, out_tab3 = st.tabs(["Mapped JSON", "Field Map", "Unmapped"])

            with out_tab1:
                import json
                st.code(json.dumps(result.get("mapped", {}), indent=2), language="json")
                st.download_button(
                    "📥 Download JSON",
                    data=json.dumps(result.get("mapped", {}), indent=2),
                    file_name="mapped_case.json",
                    mime="application/json"
                )

            with out_tab2:
                explanations = result.get("field_explanations", {})
                mapped = result.get("mapped", {})
                if explanations:
                    for field, explanation in explanations.items():
                        with st.container():
                            st.markdown(f"**{field}**: `{mapped.get(field, '—')}`")
                            st.caption(explanation)
                            st.divider()
                else:
                    st.info("No field explanations available.")
                if result.get("notes"):
                    st.info(f"📝 {result['notes']}")

            with out_tab3:
                unmapped = result.get("unmapped_fields", [])
                reasons = result.get("unmapped_reasons", {})
                if not unmapped:
                    st.success("✅ All fields mapped successfully")
                else:
                    for field in unmapped:
                        st.error(f"**{field}**: {reasons.get(field, 'Could not be determined')}")
        else:
            st.info("Output will appear here after parsing.")

with tab1:
    # Sidebar
    with st.sidebar:
        st.markdown("### 📖 How to Use")
        st.markdown("""
        1. **Select file type** from the dropdown
        2. **Upload your .txt file** (pipe-delimited)
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
        # File type selector
        file_type = st.selectbox(
            "**Select File Type** 📁",
            list(FILE_TYPE_INFO.keys()),
            format_func=lambda x: FILE_TYPE_INFO[x]["name"]
        )
        
        # Show file info
        info = FILE_TYPE_INFO[file_type]
        st.info(f"**{info['name']}**: {info['description']}")
        st.caption(f"📄 Example filename: `{info['example_filename']}`")

    with col2:
        st.markdown("### 📊 Quick Stats")
        if 'validation_count' not in st.session_state:
            st.session_state.validation_count = 0
        if 'pass_count' not in st.session_state:
            st.session_state.pass_count = 0
        
        st.metric("Files Validated", st.session_state.validation_count)
        st.metric("Files Passed", st.session_state.pass_count)

    st.markdown("---")

    # File uploader
    uploaded_file = st.file_uploader(
        "**Upload File** 📤",
        type=["txt", "csv", "tsv", "xlsx", "xls"],
        help="Upload your data file in any format: TXT (pipe-delimited), CSV, TSV, Excel (.xlsx/.xls)"
    )

    if uploaded_file is not None:
        # Convert file to pipe-delimited format
        try:
            file_content, conversion_info = convert_to_pipe_delimited(uploaded_file, uploaded_file.name)
            lines = file_content.split('\n')
            
            # File stats
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Filename", uploaded_file.name)
            with col2:
                st.metric("Format", conversion_info)
            with col3:
                st.metric("File Size", f"{len(file_content)} bytes")
            with col4:
                st.metric("Total Lines", len(lines))
            
            # Show format info if converted
            if "converted" in conversion_info:
                st.info(f"ℹ️ File automatically converted from {uploaded_file.name.split('.')[-1].upper()} to pipe-delimited format for validation")
            
            # File preview
            with st.expander("📄 **File Preview** (first 20 lines, pipe-delimited)", expanded=False):
                preview_lines = '\n'.join(lines[:20])
                st.code(preview_lines, language='text')
            
            st.markdown("---")
            
            # Validate button
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔍 **VALIDATE FILE**", type="primary"):
                    with st.spinner("🔄 Validating file with Claude AI... This may take 10-30 seconds..."):
                        try:
                            result = validate_file(file_content, uploaded_file.name, file_type)
                            
                            # Update stats
                            st.session_state.validation_count += 1
                            
                            # Show results
                            st.markdown("---")
                            st.markdown("## 📋 Validation Results")
                            
                            # Determine if passed
                            first_line = result.split('\n')[0]
                            is_pass = "PASS" in first_line
                            
                            if is_pass:
                                st.session_state.pass_count += 1
                                st.success("### ✅ Validation Passed!")
                                st.balloons()
                            else:
                                st.error("### ❌ Validation Failed - Errors Found")
                            
                            # Show detailed results
                            st.markdown(result)
                            
                            # Action buttons
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
            st.error("❌ **Error:** Unable to read file. Please ensure it's a valid text or Excel file with UTF-8 encoding.")
        except Exception as e:
            st.error(f"❌ **Error reading/converting file:** {str(e)}")

    else:
        # Instructions when no file uploaded
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

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <small>AssistIQ Integration Tools v2.0 | Powered by Claude AI | 
    <a href='https://www.assistiq.com' target='_blank'>www.assistiq.com</a></small>
</div>
""", unsafe_allow_html=True)