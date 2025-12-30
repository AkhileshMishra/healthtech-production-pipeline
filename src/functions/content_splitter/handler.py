import boto3
import json
import time

s3 = boto3.client('s3')
textract = boto3.client('textract')

def get_textract_results(job_id):
    # Simple Poller inside Splitter for demo simplicity 
    # (In high scale production, use a dedicated Wait State/Lambda)
    pages = []
    next_token = None
    
    while True:
        if next_token:
            response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
        else:
            response = textract.get_document_text_detection(JobId=job_id)
            
        status = response['JobStatus']
        if status == 'IN_PROGRESS':
            time.sleep(2)
            continue
        elif status == 'FAILED':
            raise Exception("Textract Failed")
            
        # Parse Blocks
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                pages.append(block['Text']) # Simplified for demo
        
        next_token = response.get('NextToken')
        if not next_token:
            break
            
    return "\n".join(pages)

def lambda_handler(event, context):
    bucket = event['bucket']
    key = event['key']
    mode = event['mode']
    metadata = event.get('metadata', {})
    
    full_text = ""
    
    if mode == "ASYNC_OCR":
        # Retrieve Textract Results
        full_text = get_textract_results(event['job_id'])
    else:
        # Native Parse (Simulated for brevity)
        obj = s3.get_object(Bucket=bucket, Key=key)
        full_text = obj['Body'].read().decode('utf-8', errors='ignore')

    # SPLIT LOGIC (e.g., 5000 chars per chunk ~ 2 pages)
    chunk_size = 5000
    text_chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
    
    output_chunks = []
    for idx, chunk in enumerate(text_chunks):
        # Write chunk to 'temp/' (EventBridge IGNORES this prefix)
        chunk_key = f"temp/chunks/{context.aws_request_id}/{idx}.txt"
        s3.put_object(Bucket=bucket, Key=chunk_key, Body=chunk)
        
        output_chunks.append({
            "chunk_id": idx,
            "s3_bucket": bucket,
            "s3_key": chunk_key,
            "metadata": metadata,
            "total_chunks": len(text_chunks)
        })
        
    return {"chunks": output_chunks}
