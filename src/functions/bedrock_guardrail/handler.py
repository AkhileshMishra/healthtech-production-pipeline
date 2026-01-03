import boto3
import json
import os

bedrock = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    
    # Read Chunk
    obj = s3.get_object(Bucket=event['s3_bucket'], Key=event['s3_key'])
    text_content = obj['Body'].read().decode('utf-8')
    
    # PROMPT
    prompt = f"""
    You are a Medical Data Compliance Auditor.
    
    TASK 1: CLASSIFY
    Analyze the text. Is it a Valid Medical Record (Notes, Labs, Referral, Medical Reports for Legal Assessment) or INVALID (Movie Script, Fiction, Code)?
    
    CRITICAL INSTRUCTION:
    Ignore standard legal boilerplate, disclaimer text, or acts/statutes definitions (like Mental Capacity Act) if valid clinical patient data is present in the document. Focus on the presence of patient history, diagnosis, or medical observations.
    
    TASK 2: EXTRACT
    If VALID, extract: PatientName, Vitals, Medications.
    
    INPUT:
    {text_content}
    
    OUTPUT JSON:
    {{
        "classification": "VALID" | "INVALID",
        "reason": "explanation",
        "entities": {{ ... }}
    }}
    """
    
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    })
    
    resp = bedrock.invoke_model(
        modelId=os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20240620-v1:0'),
        body=body
    )
    
    result = json.loads(resp['body'].read())
    parsed_content = json.loads(result['content'][0]['text'])
    
    # Pass along metadata
    parsed_content['metadata'] = event.get('metadata', {})
    
    return parsed_content
