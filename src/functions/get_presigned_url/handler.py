import boto3
import os
import json

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = os.environ['BUCKET_NAME']
    filename = event['queryStringParameters']['filename']
    
    # FORCE PREFIX 'incoming/' to trigger EventBridge
    key = f"incoming/web_upload/{filename}"
    
    url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=3600
    )
    
    return {
        "statusCode": 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"upload_url": url, "key": key})
    }
