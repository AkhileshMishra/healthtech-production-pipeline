import boto3
import json
import uuid
import os
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
    
    # 3. ACTUAL WRITE TO HEALTHLAKE
    # We wrap the resources in a FHIR Bundle transaction for atomic write
    # Note: 'entries' should be derived from 'results'
    entries = []
    for res in results:
        if 'fhir_resource' in res:
            entries.append({
                "resource": res['fhir_resource'],
                "request": {
                    "method": "POST",
                    "url": res['fhir_resource']['resourceType']
                }
            })

    fhir_bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries 
        # Ensure your Bedrock/Splitter logic formats 'entries' as 
        # valid FHIR 'request' objects (POST/PUT)
    }
    
    try:
        # Note: 'import_job' is for S3 bulk. For real-time (Module 2), use 'create_resource' 
        # or loop through entries if not using Transaction Bundle.
        # Simple loop for demo stability:
        for entry in entries:
            healthlake.create_resource(
                DatastoreId=os.environ['HEALTHLAKE_ID'],
                Resource=json.dumps(entry['resource'])
            )
        print(f"Successfully ingested {len(entries)} resources into HealthLake.")
        
    except Exception as e:
        print(f"Error writing to HealthLake: {str(e)}")
        raise e
    
    return {"status": "SUCCESS", "items_processed": len(results)}
