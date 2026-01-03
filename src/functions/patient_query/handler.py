import os
import json
import urllib.parse
import urllib3
import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

_http = urllib3.PoolManager()

ALLOWED_PATIENT_SEARCH_PARAMS = {
    "identifier",
    "name",
    "family",
    "given",
    "_count",
    "_total",
}

def _sigv4_get(url: str) -> dict:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("AWS_REGION is not set")

    session = botocore.session.get_session()
    creds = session.get_credentials()
    if creds is None:
        raise ValueError("No AWS credentials available for SigV4 signing")
    frozen = creds.get_frozen_credentials()

    req = AWSRequest(
        method="GET",
        url=url,
        headers={"Accept": "application/json"},
    )
    SigV4Auth(frozen, "healthlake", region).add_auth(req)
    prepared = req.prepare()

    resp = _http.request(
        "GET",
        url,
        headers=dict(prepared.headers),
        retries=False,
        timeout=urllib3.Timeout(connect=5.0, read=30.0),
    )

    body = resp.data.decode("utf-8") if resp.data else ""
    if resp.status not in (200, 201):
        raise Exception(f"HealthLake GET failed status={resp.status} body={body}")

    return json.loads(body) if body else {}

def _healthlake_base() -> str:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    datastore_id = os.environ["HEALTHLAKE_ID"]
    return f"https://healthlake.{region}.amazonaws.com/datastore/{datastore_id}/r4"

def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            # Keep consistent with your existing API CORS (currently allow all).
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps(body),
    }

def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    path = event.get("rawPath", "") or ""
    qs = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}

    base = _healthlake_base()

    # Route 1: GET /patients -> Patient search
    if path.endswith("/patients"):
        # Allowlist query params to avoid turning this into an open proxy
        safe_qs = {k: v for k, v in qs.items() if k in ALLOWED_PATIENT_SEARCH_PARAMS and v is not None}

        # Defaults helpful for console-like validation
        safe_qs.setdefault("_count", "20")
        safe_qs.setdefault("_total", "accurate")

        query = urllib.parse.urlencode(safe_qs, doseq=True)
        url = f"{base}/Patient" + (f"?{query}" if query else "")
        data = _sigv4_get(url)
        return _resp(200, data)

    # Route 2: GET /patients/{id} -> Patient read
    if "/patients/" in path:
        patient_id = path_params.get("id") or path.split("/patients/")[-1].split("/")[0]
        if not patient_id:
            return _resp(400, {"message": "Missing patient id"})
        url = f"{base}/Patient/{urllib.parse.quote(patient_id)}"
        data = _sigv4_get(url)
        return _resp(200, data)

    return _resp(404, {"message": "Not found"})
