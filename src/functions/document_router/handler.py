import boto3
import os
import urllib.parse

textract = boto3.client('textract')

def lambda_handler(event, context):
    # Triggered by EventBridge (Object Created in 'incoming/')
    bucket = event['detail']['bucket']['name']
    key = urllib.parse.unquote_plus(event['detail']['object']['key'])
    
    # Determine File Type
    ext = os.path.splitext(key)[1].lower()
    
    # Fetch Metadata (to pass Source Info down the line)
    head_obj = boto3.client('s3').head_object(Bucket=bucket, Key=key)
    metadata = head_obj.get('Metadata', {})
    
    print(f"Routing file: {key} (Type: {ext})")
    
    if ext in ['.pdf', '.jpg', '.png', '.jpeg']:
        # Start Async Textract
        response = textract.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': bucket, 'Name': key}}
        )
        return {
            "mode": "ASYNC_OCR",
            "job_id": response['JobId'],
            "bucket": bucket,
            "key": key,
            "metadata": metadata
        }
    
    elif ext in ['.csv', '.xlsx', '.docx']:
        return {
            "mode": "NATIVE_PARSE",
            "bucket": bucket,
            "key": key,
            "metadata": metadata
        }
        
    else:
        raise ValueError(f"Unsupported file type: {ext}")
