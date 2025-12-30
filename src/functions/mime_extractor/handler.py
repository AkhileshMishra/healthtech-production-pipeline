import boto3
import email
from email.policy import default
import json
import urllib.parse
import os

s3 = boto3.client('s3')

def lambda_handler(event, context):
    # Triggered by SNS from SES Receipt Rule
    sns_msg = json.loads(event['Records'][0]['Sns']['Message'])
    
    # SES Notification Object
    msg_id = sns_msg['mail']['messageId']
    bucket_name = os.environ['BUCKET_NAME'] # Passed via Terraform
    
    # Key where SES dumped the raw file
    raw_key = f"raw_email/{msg_id}"
    
    print(f"Processing raw email: {raw_key}")
    
    # 1. Get MIME Blob
    try:
        raw_obj = s3.get_object(Bucket=bucket_name, Key=raw_key)
        raw_bytes = raw_obj['Body'].read()
    except Exception as e:
        print(f"Error reading S3: {e}")
        return
        
    # 2. Parse MIME
    msg = email.message_from_bytes(raw_bytes, policy=default)
    sender = msg['from']
    
    # 3. Extract Attachments
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart': continue
        if part.get_content_disposition() is None: continue
        
        filename = part.get_filename()
        if filename:
            # Clean the filename
            clean_name = os.path.basename(filename)
            
            # 4. WRITE TO 'incoming/' (Triggers EventBridge)
            target_key = f"incoming/{msg_id}/{clean_name}"
            
            s3.put_object(
                Bucket=bucket_name,
                Key=target_key,
                Body=part.get_payload(decode=True),
                Metadata={
                    'source_channel': 'email',
                    'sender': str(sender),
                    'original_name': clean_name
                }
            )
            print(f"Extracted attachment to: {target_key}")

    return {"status": "success"}
