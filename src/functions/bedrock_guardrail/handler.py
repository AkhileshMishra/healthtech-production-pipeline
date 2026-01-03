import boto3
import json
import os
import re
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Reuse clients across invocations
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")


def _build_prompt(text_content: str) -> str:
    return f"""
You are a Medical Data Compliance Auditor.

TASK 1: CLASSIFY
Analyze the text. Is it a Valid Medical Record (Notes, Labs, Referral, Medical Reports for Legal Assessment)
or INVALID (Movie Script, Fiction, Code)?

CRITICAL INSTRUCTION:
Ignore standard legal boilerplate, disclaimer text, or acts/statutes definitions (like Mental Capacity Act)
if valid clinical patient data is present in the document. Focus on the presence of patient history,
diagnosis, or medical observations.

TASK 2: EXTRACT
If VALID, extract:
- PatientName
- PatientIdentifier (NRIC/FIN/Passport; if multiple appear, pick the patient's)
- Gender (male|female|other|unknown)
- Vitals (free-text summary)
- Medications (free-text list)

OUTPUT RULES (VERY IMPORTANT):
- Output ONLY a single JSON object.
- No markdown, no ``` fences, no commentary, no extra keys.

Required JSON schema:
{{
  "classification": "VALID" | "INVALID",
  "reason": "explanation",
  "entities": {{
    "PatientName": "string|<UNKNOWN>",
    "PatientIdentifier": "string|<UNKNOWN>",
    "Gender": "male|female|other|unknown",
    "Vitals": "string|<UNKNOWN>",
    "Medications": "string|<UNKNOWN>"
  }}
}}

INPUT:
{text_content}
""".strip()


def _extract_all_text_blocks(bedrock_result: dict) -> str:
    parts = []
    for block in bedrock_result.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def _parse_json_from_text(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty model output (no text to parse).")

    t = raw_text.strip()

    # Remove ```json fences if present
    t = re.sub(r"^\s*```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)

    # Extract first JSON object if model adds prose
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if m:
        t = m.group(0)

    return json.loads(t)


def _normalize_entities(payload: dict) -> dict:
    """
    Ensure entities always contains all keys with safe defaults so downstream mapping is stable.
    """
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        entities = {}

    entities.setdefault("PatientName", "<UNKNOWN>")
    entities.setdefault("PatientIdentifier", "<UNKNOWN>")
    entities.setdefault("Gender", "unknown")
    entities.setdefault("Vitals", "<UNKNOWN>")
    entities.setdefault("Medications", "<UNKNOWN>")

    # Normalize gender values
    g = (entities.get("Gender") or "unknown").strip().lower()
    if g not in {"male", "female", "other", "unknown"}:
        g = "unknown"
    entities["Gender"] = g

    payload["entities"] = entities
    return payload


def _try_converse_tool_output(model_id: str, prompt: str) -> dict | None:
    """
    Prefer structured output via Converse tool use (no JSON string parsing).
    """
    if not hasattr(bedrock, "converse"):
        return None

    tool_config = {
        "tools": [
            {
                "toolSpec": {
                    "name": "audit_output",
                    "description": "Return the audit result as structured JSON.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "classification": {"type": "string", "enum": ["VALID", "INVALID"]},
                                "reason": {"type": "string"},
                                "entities": {
                                    "type": "object",
                                    "properties": {
                                        "PatientName": {"type": "string"},
                                        "PatientIdentifier": {"type": "string"},
                                        "Gender": {"type": "string"},
                                        "Vitals": {"type": "string"},
                                        "Medications": {"type": "string"},
                                    },
                                    "required": ["PatientName", "PatientIdentifier", "Gender", "Vitals", "Medications"],
                                },
                            },
                            "required": ["classification", "reason", "entities"],
                        }
                    },
                }
            }
        ],
        "toolChoice": {"tool": {"name": "audit_output"}},
    }

    try:
        resp = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 1000, "temperature": 0},
        )

        if resp.get("stopReason") != "tool_use":
            return None

        content_blocks = resp.get("output", {}).get("message", {}).get("content", [])
        for block in content_blocks:
            if "toolUse" in block and isinstance(block["toolUse"], dict):
                tool_input = block["toolUse"].get("input")
                if isinstance(tool_input, dict):
                    return tool_input
        return None

    except ClientError as e:
        logger.warning("Converse tool-output call failed, falling back to invoke_model: %s", str(e))
        return None


def _invoke_model_text_output(model_id: str, prompt: str) -> dict:
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
    )

    resp = bedrock.invoke_model(modelId=model_id, body=body)
    result = json.loads(resp["body"].read())
    raw_text = _extract_all_text_blocks(result)
    return _parse_json_from_text(raw_text)


def lambda_handler(event, context):
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

    obj = s3.get_object(Bucket=event["s3_bucket"], Key=event["s3_key"])
    text_content = obj["Body"].read().decode("utf-8")

    # (Optional debug preview—remove in prod if PHI risk)
    preview_head = text_content[:2000]
    preview_tail = text_content[-2000:] if len(text_content) > 2000 else ""
    logger.info("S3 input bucket=%s key=%s bytes=%d", event["s3_bucket"], event["s3_key"], len(text_content))
    logger.info("S3 input HEAD(2000): %s", preview_head)
    logger.info("S3 input TAIL(2000): %s", preview_tail)

    prompt = _build_prompt(text_content)

    parsed_content = _try_converse_tool_output(model_id, prompt)
    if parsed_content is None:
        try:
            parsed_content = _invoke_model_text_output(model_id, prompt)
        except Exception as e:
            parsed_content = {
                "classification": "INVALID",
                "reason": f"Failed to parse model output as JSON: {str(e)}",
                "entities": {},
            }

    parsed_content = _normalize_entities(parsed_content)
    parsed_content["metadata"] = event.get("metadata", {})

    return parsed_content
