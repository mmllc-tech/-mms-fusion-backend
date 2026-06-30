"""
HDL Generator Service
Converts validated client Excel data into Oracle HCM Data Loader (.dat) files
in the correct dependency sequence.
"""
import io, json
from datetime import datetime
from typing import List, Dict, Any

HDL_OBJECTS = {

    "ReferenceDataSet": {
        "seq": 1,
        "method": "HDL",
        "business_object": "SetDefinition",
        "metadata": ["SetCode", "SetName", "SetDescription"],
        "mapping": {
            "Set Code": "SetCode",
            "Set Name": "SetName",
            "Description": "SetDescription",
        },
        "defaults": {},
        "required": ["SetCode", "SetName"],
    },

    "LegislativeDataGroup": {
        "seq": 2,
        "method": "HDL",
        "business_object": "LegislativeDataGroup",
        "metadata": ["LegislativeDataGroupName", "CountryCode", "CurrencyCode", "Description"],
        "mapping": {
            "LDG Name": "LegislativeDataGroupName",
            "Country": "CountryCode",
            "Currency": "CurrencyCode",
            "Description": "Description",
        },
        "defaults": {"CountryCode": "US", "CurrencyCode": "USD"},
        "required": ["LegislativeDataGroupName", "CountryCode", "CurrencyCode"],
    },

    "LegalEntity": {
        "seq": 3,
        "method": "HDL",
        "business_object": "LegalEntity",
        "metadata": ["LegalEntityName", "LegalEntityIdentifier", "EffectiveFrom",
                     "Country", "AddressLine1", "TownOrCity", "Region2", "PostalCode",
                     "LegalEmployer", "PayrollStatutoryUnit", "EIN"],
        "mapping": {
            "Legal Entity Name": "LegalEntityName",
            "Legal Entity Identifier": "LegalEntityIdentifier",
            "Start Date": "EffectiveFrom",
            "Country": "Country",
            "Registered Address Line 1": "AddressLine1",
            "Registered City": "TownOrCity",
            "Registered State": "Region2",
            "Registered Zip": "PostalCode",
            "Legal Employer?": "LegalEmployer",
            "Payroll Statutory Unit?": "PayrollStatutoryUnit",
            "EIN": "EIN",
        },
        "defaults": {"Country": "US", "EffectiveFrom": "1900/01/01",
                     "LegalEmployer": "Y", "PayrollStatutoryUnit": "Y"},
        "required": ["LegalEntityName", "LegalEntityIdentifier", "EIN"],
    },

    "BusinessUnit": {
        "seq": 4,
        "method": "HDL",
        "business_object": "BusinessUnit",
        "metadata": ["BusinessUnitName", "ShortCode", "EffectiveStartDate",
                     "PrimaryLedgerName", "DefaultSetCode"],
        "mapping": {
            "Business Unit Name": "BusinessUnitName",
            "Business Unit Short Code": "ShortCode",
            "Start Date": "EffectiveStartDate",
            "Primary LDG": "PrimaryLedgerName",
            "Default Set Code": "DefaultSetCode",
        },
        "defaults": {"EffectiveStartDate": "1900/01/01", "DefaultSetCode": "COMMON"},
        "required": ["BusinessUnitName", "ShortCode"],
    },

    "Location": {
        "seq": 5,
        "method": "HDL",
        "business_object": "Location",
        "metadata": ["SetCode", "EffectiveStartDate", "LocationCode", "LocationName",
                     "ActiveStatus", "AddressLine1", "AddressLine2",
                     "TownOrCity", "Region2", "Region1", "PostalCode", "Country"],
        "mapping": {
            "Set Code": "SetCode",
            "Location Code": "LocationCode",
            "Location Name": "LocationName",
            "Address Line 1": "AddressLine1",
            "Address Line 2": "AddressLine2",
            "City": "TownOrCity",
            "State": "Region2",
            "County": "Region1",
            "Zip Code": "PostalCode",
            "Country": "Country",
        },
        "defaults": {"SetCode": "COMMON", "EffectiveStartDate": "1900/01/01",
                     "ActiveStatus": "ACTIVE", "Country": "US"},
        "required": ["LocationCode", "LocationName", "TownOrCity", "Region2"],
    },

    "Department": {
        "seq": 6,
        "method": "HDL",
        "business_object": "Organization",
        "metadata": ["EffectiveStartDate", "EffectiveEndDate", "ClassificationCode",
                     "Name", "BusinessUnitName", "LocationCode", "SetCode"],
        "mapping": {
            "Department Name": "Name",
            "Business Unit": "BusinessUnitName",
            "Location Code": "LocationCode",
            "Set Code": "SetCode",
        },
        "defaults": {"EffectiveStartDate": "1900/01/01", "EffectiveEndDate": "4712/12/31",
                     "ClassificationCode": "DEPARTMENT", "SetCode": "COMMON"},
        "required": ["Name"],
        "child_components": [{
            "business_object": "OrgUnitClassification",
            "metadata": ["ClassificationCode", "OrganizationName",
                        "EffectiveStartDate", "EffectiveEndDate", "Status"],
            "row_builder": lambda row: {
                "ClassificationCode": "DEPARTMENT",
                "OrganizationName": row.get("Name", ""),
                "EffectiveStartDate": "1900/01/01",
                "EffectiveEndDate": "4712/12/31",
                "Status": "A"
            }
        }]
    },

    "JobFamily": {
        "seq": 7,
        "method": "HDL",
        "business_object": "JobFamily",
        "metadata": ["SetCode", "EffectiveStartDate", "EffectiveEndDate",
                     "Code", "Name", "ActiveStatus"],
        "mapping": {
            "Job Family Code": "Code",
            "Job Family Name": "Name",
            "Set Code": "SetCode",
        },
        "defaults": {"SetCode": "COMMON", "EffectiveStartDate": "1900/01/01",
                     "EffectiveEndDate": "4712/12/31", "ActiveStatus": "A"},
        "required": ["Code", "Name"],
    },

    "Job": {
        "seq": 8,
        "method": "HDL",
        "business_object": "Job",
        "metadata": ["SetCode", "EffectiveStartDate", "EffectiveEndDate",
                     "JobCode", "Name", "ActiveStatus", "OvertimeStatus", "ManagementLevel"],
        "mapping": {
            "Job Code": "JobCode",
            "Job Name": "Name",
            "Set Code": "SetCode",
            "Exempt Status": "OvertimeStatus",
            "Management Level": "ManagementLevel",
        },
        "defaults": {"SetCode": "COMMON", "EffectiveStartDate": "1900/01/01",
                     "EffectiveEndDate": "4712/12/31", "ActiveStatus": "A"},
        "required": ["JobCode", "Name"],
        "value_transforms": {
            "OvertimeStatus": {"Exempt": "EXEMPT", "Nonexempt": "NONEXEMPT"},
            "ManagementLevel": {"Individual Contributor": "IC", "People Manager": "MANAGER"}
        }
    },

    "Grade": {
        "seq": 9,
        "method": "HDL",
        "business_object": "Grade",
        "metadata": ["SetCode", "EffectiveStartDate", "EffectiveEndDate",
                     "GradeCode", "GradeName", "ActiveStatus"],
        "mapping": {
            "Grade Code": "GradeCode",
            "Grade Name": "GradeName",
            "Set Code": "SetCode",
        },
        "defaults": {"SetCode": "COMMON", "EffectiveStartDate": "1900/01/01",
                     "EffectiveEndDate": "4712/12/31", "ActiveStatus": "A"},
        "required": ["GradeCode", "GradeName"],
    },

    "Action": {
        "seq": 10,
        "method": "HDL",
        "business_object": "Action",
        "metadata": ["ActionCode", "ActionName", "ActionType",
                     "EffectiveStartDate", "EffectiveEndDate"],
        "mapping": {
            "Action Code": "ActionCode",
            "Action Name": "ActionName",
            "Action Type": "ActionType",
        },
        "defaults": {"EffectiveStartDate": "1900/01/01", "EffectiveEndDate": "4712/12/31"},
        "required": ["ActionCode", "ActionName", "ActionType"],
    },

    "ActionReason": {
        "seq": 11,
        "method": "HDL",
        "business_object": "ActionReason",
        "metadata": ["ActionTypeCode", "ReasonCode", "ReasonName",
                     "EffectiveStartDate", "EffectiveEndDate"],
        "mapping": {
            "Action Type": "ActionTypeCode",
            "Reason Code": "ReasonCode",
            "Reason Name": "ReasonName",
        },
        "defaults": {"EffectiveStartDate": "1900/01/01", "EffectiveEndDate": "4712/12/31"},
        "required": ["ActionTypeCode", "ReasonCode", "ReasonName"],
    },
}

VALIDATION_RULES = {
    "Location": {
        "required": ["Location Code", "Location Name", "City", "State", "Zip Code"],
        "patterns": {
            "State": {"regex": r"^[A-Z]{2}$", "msg": "State must be 2-letter code e.g. TX"},
            "Zip Code": {"regex": r"^\d{5}(-\d{4})?$", "msg": "Zip must be 5 digits e.g. 77001"},
        }
    },
    "Department": {
        "required": ["Department Name", "Business Unit"],
    },
    "Job": {
        "required": ["Job Code", "Job Name", "Exempt Status", "EEO-1 Category"],
    },
    "Grade": {
        "required": ["Grade Code", "Grade Name"],
    },
    "Legal Entity": {
        "required": ["Legal Entity Name", "Legal Entity Identifier", "EIN",
                     "Registered Address Line 1", "Registered City",
                     "Registered State", "Registered Zip", "Legislative Data Group"],
        "patterns": {
            "EIN": {"regex": r"^\d{2}-\d{7}$", "msg": "EIN format must be XX-XXXXXXX"},
        }
    },
}

def format_date(val: str) -> str:
    if not val:
        return ""
    val = str(val).strip()
    import re
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val)
    if m:
        return f"{m.group(3)}/{m.group(2):0>2}/{m.group(1):0>2}"
    return val

def build_hdl_file(object_name: str, rows: List[Dict]) -> str:
    if object_name not in HDL_OBJECTS:
        raise ValueError(f"Unknown HDL object: {object_name}")

    obj = HDL_OBJECTS[object_name]
    bo = obj["business_object"]
    metadata_fields = obj["metadata"]
    mapping = obj["mapping"]
    defaults = obj.get("defaults", {})
    transforms = obj.get("value_transforms", {})
    children = obj.get("child_components", [])

    lines = []
    meta_line = f"METADATA|{bo}|" + "|".join(metadata_fields)
    lines.append(meta_line)

    for row in rows:
        hdl_row = {}
        for k, v in defaults.items():
            hdl_row[k] = v

        for client_field, hdl_attr in mapping.items():
            val = row.get(client_field, "")
            if val is None:
                val = ""
            val = str(val).strip()

            if "Date" in hdl_attr and "/" in val:
                val = format_date(val)

            if hdl_attr in transforms and val in transforms[hdl_attr]:
                val = transforms[hdl_attr][val]

            if val:
                hdl_row[hdl_attr] = val

        data_vals = [hdl_row.get(f, "") for f in metadata_fields]
        data_line = f"MERGE|{bo}|" + "|".join(data_vals)
        lines.append(data_line)

        for child in children:
            child_bo = child["business_object"]
            child_meta = child["metadata"]
            child_row = child["row_builder"](hdl_row)
            lines.append(f"METADATA|{child_bo}|" + "|".join(child_meta))
            child_vals = [child_row.get(f, "") for f in child_meta]
            lines.append(f"MERGE|{child_bo}|" + "|".join(child_vals))

    return "\n".join(lines)

def validate_sheet(sheet_name: str, rows: List[Dict]) -> Dict:
    import re
    rules = VALIDATION_RULES.get(sheet_name, {})
    required = rules.get("required", [])
    patterns = rules.get("patterns", {})

    errors = []
    warnings = []
    passed = 0

    for i, row in enumerate(rows, 1):
        row_errors = []
        row_warns = []

        for field in required:
            if not row.get(field, "").strip():
                row_errors.append(f"Row {i}: '{field}' is required")

        for field, rule in patterns.items():
            val = row.get(field, "").strip()
            if val and not re.match(rule["regex"], val):
                row_warns.append(f"Row {i}: {rule['msg']} (got '{val}')")

        if required:
            key_field = required[0]
            key_val = row.get(key_field, "").strip()
            if key_val:
                dupe_count = sum(1 for r in rows if r.get(key_field, "").strip() == key_val)
                if dupe_count > 1:
                    row_errors.append(f"Row {i}: Duplicate {key_field} '{key_val}'")

        errors.extend(row_errors)
        warnings.extend(row_warns)
        if not row_errors:
            passed += 1

    return {
        "sheet": sheet_name,
        "total_rows": len(rows),
        "passed": passed,
        "errors": errors,
        "warnings": warnings
    }

def get_load_sequence() -> List[Dict]:
    sequence = [
        {"seq": 1,  "obj": "Configure Offerings",          "method": "RPA",  "est": "3 min",  "depends_on": []},
        {"seq": 2,  "obj": "Admin Profile Options",         "method": "RPA",  "est": "2 min",  "depends_on": [1]},
        {"seq": 3,  "obj": "Features by Country (US)",      "method": "FSM",  "est": "2 min",  "depends_on": [1]},
        {"seq": 4,  "obj": "Geography Load (US)",           "method": "REST", "est": "5 min",  "depends_on": [1]},
        {"seq": 5,  "obj": "Common Lookups",                "method": "HDL",  "est": "2 min",  "depends_on": [1]},
        {"seq": 6,  "obj": "Assignment Status Types",       "method": "FSM",  "est": "2 min",  "depends_on": [1]},
        {"seq": 7,  "obj": "Reference Data Sets",           "method": "HDL",  "est": "1 min",  "depends_on": [1]},
        {"seq": 8,  "obj": "Legislative Data Groups",       "method": "HDL",  "est": "1 min",  "depends_on": [4,7]},
        {"seq": 9,  "obj": "Legal Entities",                "method": "HDL",  "est": "2 min",  "depends_on": [8]},
        {"seq": 10, "obj": "Legal Entity HCM Information",  "method": "HDL",  "est": "1 min",  "depends_on": [9]},
        {"seq": 11, "obj": "Business Units",                "method": "HDL",  "est": "1 min",  "depends_on": [9]},
        {"seq": 12, "obj": "BU Set Assignments",            "method": "HDL",  "est": "1 min",  "depends_on": [11]},
        {"seq": 13, "obj": "Locations",                     "method": "HDL",  "est": "2 min",  "depends_on": [11]},
        {"seq": 14, "obj": "Departments",                   "method": "HDL",  "est": "2 min",  "depends_on": [11,13]},
        {"seq": 15, "obj": "Job Families",                  "method": "HDL",  "est": "1 min",  "depends_on": [7]},
        {"seq": 16, "obj": "Jobs",                          "method": "HDL",  "est": "3 min",  "depends_on": [15]},
        {"seq": 17, "obj": "Grades",                        "method": "HDL",  "est": "2 min",  "depends_on": [7]},
        {"seq": 18, "obj": "Grade Rates",                   "method": "HDL",  "est": "2 min",  "depends_on": [17]},
        {"seq": 19, "obj": "Valid Grades",                  "method": "HDL",  "est": "1 min",  "depends_on": [16,17]},
        {"seq": 20, "obj": "Actions & Reasons",             "method": "HDL",  "est": "2 min",  "depends_on": [1]},
        {"seq": 21, "obj": "Value Sets & DFF Setup",        "method": "RPA",  "est": "8 min",  "depends_on": [1]},
        {"seq": 22, "obj": "HCM Design Studio",             "method": "RPA",  "est": "5 min",  "depends_on": [1]},
        {"seq": 23, "obj": "Salary Basis",                  "method": "FSM",  "est": "2 min",  "depends_on": [8]},
        {"seq": 24, "obj": "Consolidation Groups",          "method": "FSM",  "est": "1 min",  "depends_on": [8]},
        {"seq": 25, "obj": "Payroll Definitions",           "method": "HDL",  "est": "2 min",  "depends_on": [24,8]},
        {"seq": 26, "obj": "Security Roles & Profiles",     "method": "RPA",  "est": "12 min", "depends_on": [9,11]},
    ]
    return sequence
