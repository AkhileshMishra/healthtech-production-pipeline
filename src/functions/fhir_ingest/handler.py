import boto3
import json
import uuid
from datetime import datetime

healthlake = boto3.client('healthlake')

def lambda_handler(event, context):
    # Event is LIST of results from Map State
    results = event
    
    # 1. Guardrail Check
    invalid_chunks = [r for r in results if r['classification'] == 'INVALID']
    if invalid_chunks:
        reason = invalid_chunks[0]['reason']
        print(f"SECURITY BLOCK: Data contains invalid content. Reason: {reason}")
        return {"status": "REJECTED", "reason": reason}
    
    # 2. Construct FHIR Bundle
    bundle_id = str(uuid.uuid4())
    metadata = results[0].get('metadata', {})
    source_agent = metadata.get('sender', 'Web Upload')
    
    # PROVENANCE RESOURCE (The "Origin" Tracker)
    provenance = {
        "resourceType": "Provenance",
        "target": [], # Add references to created resources here
        "recorded": datetime.utcnow().isoformat() + "Z",
        "agent": [{
            "who": {"display": "AWS Pipeline"},
            "onBehalfOf": {"display": source_agent}
        }],
        "entity": [{
            "role": "source",
            "what": {"display": metadata.get('original_name', 'Unknown File')}
        }]
    }
    
    print(f"Ingesting clean data verified from source: {source_agent}")
    
    # (Simulated HealthLake Write)
    # healthlake.start_fhir_import_job(...)
    
    return {"status": "SUCCESS", "items_processed": len(results)}
