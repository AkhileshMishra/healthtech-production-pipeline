import boto3
import json
import uuid
import os
import html
import urllib3
import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Control-plane client (not used for FHIR CRUD)
healthlake = boto3.client("healthlake")

_http = urllib3.PoolManager()


def _is_unknown(v):
    if v is None:
        return True
    if isinstance(v, str) and v.strip().upper() in {"", "<UNKNOWN>", "UNKNOWN", "N/A", "NA", "NONE"}:
        return True
    return False


def _normalize_gender(v):
    g = (v or "unknown").strip().lower()
    return g if g in {"male", "female", "other", "unknown"} else "unknown"


def _is_legal_appendix_chunk(res: dict) -> bool:
    reason = (res.get("reason") or "").lower()

    legal_markers = [
        "mental capacity act",
        "section 3",
        "section 4",
        "section 5",
        "statute",
        "legal document",
        "explanatory notes",
        "declaration",
        "duty is to the court",
        "provisions in sections",
    ]
    if not any(m in reason for m in legal_markers):
        return False

    hard_invalid_markers = ["movie script", "fiction", "screenplay", "source code", "javascript", "python code"]
    if any(m in reason for m in hard_invalid_markers):
        return False

    return True


def _sigv4_post_to_healthlake(url: str, body_json: dict) -> dict:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("AWS_REGION is not set")

    body = json.dumps(body_json).encode("utf-8")

    session = botocore.session.get_session()
    creds = session.get_credentials()
    if creds is None:
        raise ValueError("No AWS credentials available for SigV4 signing")
    frozen = creds.get_frozen_credentials()

    req = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={"Content-Type": "application/fhir+json", "Accept": "application/json"},
    )
    SigV4Auth(frozen, "healthlake", region).add_auth(req)
    prepared = req.prepare()

    resp = _http.request(
        "POST",
        url,
        body=body,
        headers=dict(prepared.headers),
        retries=False,
        timeout=urllib3.Timeout(connect=5.0, read=30.0),
    )

    resp_text = resp.data.decode("utf-8") if resp.data else ""
    if resp.status not in (200, 201):
        raise Exception(f"HealthLake FHIR create failed status={resp.status} body={resp_text}")

    return json.loads(resp_text) if resp_text else {}


def _healthlake_fhir_create(datastore_id: str, resource: dict) -> dict:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    resource_type = resource.get("resourceType")
    if not resource_type:
        raise ValueError("FHIR resource missing resourceType")

    url = f"https://healthlake.{region}.amazonaws.com/datastore/{datastore_id}/r4/{resource_type}"
    return _sigv4_post_to_healthlake(url, resource)


def _aggregate_entities_one_patient(valid_results: list[dict]) -> dict:
    """
    Merge chunk-level entities into one patient-level entity set.
    Preference order: first non-unknown value wins.
    Vitals/Medications: concatenate unique non-unknown strings.
    """
    agg = {
        "PatientName": "<UNKNOWN>",
        "PatientIdentifier": "<UNKNOWN>",
        "Gender": "unknown",
        "Vitals": "<UNKNOWN>",
        "Medications": "<UNKNOWN>",
    }

    vitals = []
    meds = []

    for res in valid_results:
        e = res.get("entities", {}) or {}

        # PatientName
        if _is_unknown(agg["PatientName"]) and not _is_unknown(e.get("PatientName")):
            agg["PatientName"] = e.get("PatientName")

        # PatientIdentifier
        if _is_unknown(agg["PatientIdentifier"]) and not _is_unknown(e.get("PatientIdentifier")):
            agg["PatientIdentifier"] = e.get("PatientIdentifier")

        # Gender
        if agg["Gender"] == "unknown" and not _is_unknown(e.get("Gender")):
            agg["Gender"] = _normalize_gender(e.get("Gender"))

        # Vitals / Medications (collect, then join)
        v = e.get("Vitals")
        if not _is_unknown(v) and v not in vitals:
            vitals.append(v)

        m = e.get("Medications")
        if not _is_unknown(m) and m not in meds:
            meds.append(m)

    if vitals:
        agg["Vitals"] = " | ".join(vitals)
    if meds:
        agg["Medications"] = " | ".join(meds)

    return agg


def _map_entities_to_patient_fhir(entities: dict) -> dict:
    """
    Create a Patient resource that passes:
    - Narrative XHTML constraints [web:152]
    - US Core Patient constraints (identifier must exist) [web:178]
    """
    patient_name = entities.get("PatientName") or "Unknown Patient"

    name_parts = patient_name.split()
    family = name_parts[-1] if len(name_parts) > 1 else patient_name
    given = name_parts[:-1] if len(name_parts) > 1 else [patient_name]

    # Always provide identifier (real if extracted, else UUID placeholder)
    identifier_system = os.environ.get("PATIENT_ID_SYSTEM", "urn:healthtech:patient-identifier")
    identifier_value = entities.get("PatientIdentifier")
    if _is_unknown(identifier_value):
        identifier_value = str(uuid.uuid4())

    gender = _normalize_gender(entities.get("Gender"))

    # Valid XHTML narrative (must start with <div ...> and include xmlns) [web:152]
    safe_line = html.escape(f"AI-ingested Patient: {patient_name}")
    narrative_div = f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{safe_line}</p></div>'

    return {
        "resourceType": "Patient",
        "id": str(uuid.uuid4()),
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
        "text": {"status": "generated", "div": narrative_div},
        "identifier": [{"system": identifier_system, "value": identifier_value}],
        "gender": gender,
        "name": [{"use": "official", "family": family, "given": given, "text": patient_name}],
        "extension": [
            {
                "url": "https://example.com/fhir/StructureDefinition/ai-extracted-entities",
                "valueString": json.dumps(entities, ensure_ascii=False),
            }
        ],
    }


def lambda_handler(event, context):
    results = event if isinstance(event, list) else []

    valid_results = [r for r in results if r.get("classification") == "VALID"]
    invalid_results = [r for r in results if r.get("classification") == "INVALID"]

    # Reject only if NO valid chunks exist
    if not valid_results:
        reason = invalid_results[0].get("reason", "No valid medical content found.") if invalid_results else "Empty input"
        return {"status": "REJECTED", "reason": reason}

    # Ignore legal appendix invalid chunks when doc has medical content
    legal_appendix = [r for r in invalid_results if _is_legal_appendix_chunk(r)]
    hard_invalid = [r for r in invalid_results if r not in legal_appendix]

    # Optional safety: reject if hard-invalid mixed in
    if hard_invalid:
        reason = hard_invalid[0].get("reason", "Contains invalid content.")
        return {"status": "REJECTED", "reason": reason}

    metadata = valid_results[0].get("metadata", {}) if valid_results else {}
    source_agent = metadata.get("sender", "Web Upload")

    # Merge entities across chunks into ONE patient
    merged_entities = _aggregate_entities_one_patient(valid_results)

    # If merge produced nothing useful, skip
    if _is_unknown(merged_entities.get("PatientName")) and _is_unknown(merged_entities.get("PatientIdentifier")):
        return {"status": "SKIPPED", "reason": "No usable patient entities extracted"}

    patient_resource = _map_entities_to_patient_fhir(merged_entities)

    datastore_id = os.environ["HEALTHLAKE_ID"]
    _healthlake_fhir_create(datastore_id, patient_resource)

    return {
        "status": "SUCCESS",
        "items_processed": 1,
        "source_agent": source_agent,
        "ignored_legal_chunks": len(legal_appendix),
        "used_placeholder_identifier": _is_unknown(merged_entities.get("PatientIdentifier")),
        "gender": merged_entities.get("Gender", "unknown"),
    }
