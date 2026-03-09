import streamlit as st
import anthropic
import json
import time

# ─── Auth ───────────────────────────────────────────────────────────────────
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

# ─── Auto logout 15 mins ────────────────────────────────────────────────────
TIMEOUT = 15 * 60
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()
if time.time() - st.session_state.last_activity > TIMEOUT:
    st.session_state.authenticated = False
    st.rerun()
st.session_state.last_activity = time.time()

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

# ─── Shared Claude client ────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# ════════════════════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLES (all 4 real Northwell pairs from Sean)
# ════════════════════════════════════════════════════════════════════════════
FEW_SHOT = """
You are an HL7-to-JSON parser for AssistIQ surgical supply platform.
Convert SIU HL7 messages into the exact AssistIQ appointment JSON format.

Below are 4 real examples showing the exact input HL7 and expected JSON output.
Study these carefully — your output must match this structure precisely.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT HL7:
MSH|^~\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114142|63263|SIU^S14|334502.25676|D
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
MSH|^~\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114147|63263|SIU^S14|334502.25677|D
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
MSH|^~\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114017|63263|SIU^S14|334502.25675|D
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
MSH|^~\&|EPIC|LIJFH^LIJFH^NHPARLOC|||20260309114012|63263|SIU^S14|334502.25674|D
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
status                        → SCH field 26 component 1: "Sch"/"Scheduled" = "booked", "Cancelled" = "cancelled", "Pending" = "pending". Unrecognized codes: use raw value + flag as low confidence.
duration (top-level)          → AIS field 9 in seconds ÷ 60 = minutes (10800 → 180)
startDateTime                 → AIS field 4 (YYYYMMDDHHMMSS) → ISO 8601 format YYYY-MM-DDTHH:MM:SS-0400
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
metadata.createdAt            → MSH field 7 as ISO 8601 (add milliseconds .000 if not present)
metadata.HL7Message.sourceId  → MSH field 10
metadata.HL7Message.createdAt → MSH field 7 as ISO 8601 with .000 milliseconds
metadata.HL7Message.rawData   → always "*"
metadata.HL7Message.id        → always null (system-assigned on ingestion)
metadata.connectorRevision    → always null (system-assigned on ingestion)
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

# ════════════════════════════════════════════════════════════════════════════
# APP
# ════════════════════════════════════════════════════════════════════════════
st.title("AssistIQ — Self Serve Integration Tool")
tab1, tab2 = st.tabs(["📁 Flat File Validator", "🔄 HL7 → JSON Parser"])

# ── Tab 1: Flat File Validator ───────────────────────────────────────────────
with tab1:
    st.header("Flat File Validator")
    st.info("Upload your Epic integration flat files to validate against Epic V2 specs.")

    FILE_TYPES = ["Case Picklists", "Charge Capture", "Preference Cards",
                  "Product Master", "Service Lines", "Service Line Providers"]
    file_type = st.selectbox("Select File Type", FILE_TYPES)
    uploaded_file = st.file_uploader("Upload File", type=["csv", "xlsx", "txt"])

    if uploaded_file and st.button("🔍 Validate File"):
        with st.spinner("Validating..."):
            content = uploaded_file.read().decode("utf-8", errors="ignore")
            prompt = f"""You are an Epic V2 integration file validator for AssistIQ.
File type: {file_type}
File content:
{content[:3000]}

Return ONLY a JSON object with:
- "valid": true/false
- "errors": list of objects with "row", "field", "issue"
- "warnings": list of warning objects
- "summary": brief summary string
- "confidence": "high", "medium", or "low"
No markdown, no explanation."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip().replace("```json","").replace("```","")
            try:
                result = json.loads(raw)
                st.success("✅ File is valid") if result.get("valid") else st.error("❌ Validation failed")
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("Errors")
                    if result.get("errors"):
                        for e in result["errors"]:
                            st.error(f"Row {e.get('row','?')}: {e.get('field','?')} — {e.get('issue','?')}")
                    else:
                        st.success("No errors found")
                with c2:
                    st.subheader("Warnings")
                    if result.get("warnings"):
                        for w in result["warnings"]:
                            st.warning(str(w))
                    else:
                        st.info("No warnings")
                st.info(f"Summary: {result.get('summary','')}")
            except:
                st.code(raw)

# ── Tab 2: HL7 → JSON Parser ─────────────────────────────────────────────────
with tab2:
    st.header("HL7 → JSON Parser")
    st.caption("Converts SIU HL7 scheduling messages into AssistIQ appointment JSON format.")

    hospital = st.text_input("Hospital / Facility (optional)", placeholder="e.g. Baptist, Northwell")

    if st.button("Load Sample Message"):
        st.session_state["hl7_input"] = SAMPLE_HL7

    hl7_input = st.text_area(
        "Paste HL7 Message",
        value=st.session_state.get("hl7_input", ""),
        height=280,
        placeholder="Paste your SIU HL7 message here..."
    )

    if st.button("🔄 Parse to JSON", type="primary"):
        if not hl7_input.strip():
            st.warning("Please paste an HL7 message first.")
        else:
            with st.spinner("Parsing..."):
                prompt = f"""{FEW_SHOT}

Now parse the new HL7 message below using the EXACT same JSON structure and field mapping rules.
Hospital context: {hospital if hospital else "not specified"}

HL7 MESSAGE TO PARSE:
{hl7_input}

STRICT RULES:
1. Output ONLY valid JSON — no markdown, no explanation, no code blocks
2. Follow all mapping rules exactly as shown in the 4 examples
3. Duration must be in MINUTES (divide AIS field 9 seconds by 60)
4. metadata.HL7Message.id → always null
5. metadata.connectorRevision → always null
6. Never omit required fields — use null only if truly not found
7. Preserve patient PID values exactly (keep * if masked)
8. For any field you cannot confidently map, include it with your best guess AND add a sibling "_confidence" field: "low - <reason>"
9. metadata.source should be "{hospital or MSH facility}-EPIC-OR"
"""
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )

                raw = response.content[0].text.strip()
                for tag in ["```json", "```"]:
                    raw = raw.replace(tag, "")
                raw = raw.strip()

                try:
                    parsed = json.loads(raw)
                    low_conf = [k for k in parsed if "_confidence" in k]

                    if low_conf:
                        st.warning(f"⚠️ {len(low_conf)} field(s) flagged for manual review")
                    else:
                        st.success("✅ Parsed successfully")

                    out1, out2 = st.tabs(["📋 JSON Output", "ℹ️ Field Summary"])

                    with out1:
                        st.json(parsed)
                        st.download_button(
                            "⬇️ Download JSON",
                            data=json.dumps(parsed, indent=2),
                            file_name=f"appointment_{parsed.get('id','unknown')}.json",
                            mime="application/json"
                        )

                    with out2:
                        reason = parsed.get("reason", [{}])[0]
                        practitioner = reason.get("practitioner", {})
                        surgeon_name = f"{practitioner.get('name',{}).get('family','')} {practitioner.get('name',{}).get('given','')}".strip()
                        fields = {
                            "Appointment ID": parsed.get("id"),
                            "Status": parsed.get("status"),
                            "Duration (mins)": parsed.get("duration"),
                            "Start": parsed.get("startDateTime"),
                            "End": parsed.get("endDateTime"),
                            "Procedure": reason.get("serviceCode", {}).get("display"),
                            "Service Line": reason.get("serviceLine"),
                            "Surgeon": surgeon_name or "—",
                            "OR Room": parsed.get("location", {}).get("room"),
                            "Facility": parsed.get("location", {}).get("facility"),
                            "Source": parsed.get("metadata", {}).get("source"),
                            "HL7 Source ID": parsed.get("metadata", {}).get("HL7Message", {}).get("sourceId"),
                        }
                        for label, value in fields.items():
                            c1, c2 = st.columns([1, 2])
                            with c1:
                                st.markdown(f"**{label}**")
                            with c2:
                                st.markdown(str(value) if value else "—")

                        if low_conf:
                            st.markdown("---")
                            st.markdown("**⚠️ Needs manual review:**")
                            for f in low_conf:
                                st.warning(f"{f}: {parsed[f]}")

                except json.JSONDecodeError:
                    st.error("Could not parse response as JSON. Raw output:")
                    st.code(raw)
