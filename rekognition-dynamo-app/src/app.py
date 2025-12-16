import json
import os
import time
import uuid
from urllib.parse import unquote_plus
import boto3
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
rek = boto3.client("rekognition")
TABLE_NAME = os.environ["TABLE_NAME"]
UPLOAD_BUCKET = os.environ["UPLOAD_BUCKET"]
table = dynamodb.Table(TABLE_NAME)

def _response(status, body):
   return {
       "statusCode": status,
       "headers": {
           "Content-Type": "application/json",
           "Access-Control-Allow-Origin": "*",
       },
       "body": json.dumps(body),
   }

def _get_json(event):
   if "body" not in event or event["body"] is None:
       return {}
   if event.get("isBase64Encoded"):
       # Not expected for API Gateway proxy JSON in this flow
       return {}
   try:
       return json.loads(event["body"])
   except Exception:
       return {}

def lambda_handler(event, context):
   path = event.get("rawPath") or event.get("path", "")
   method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "")
   # Fallback for REST API proxy style
   if not method:
       method = event.get("httpMethod", "")
   if path.endswith("/upload-url") and method == "POST":
       return handle_upload_url(event)
   if path.endswith("/analyze") and method == "POST":
       return handle_analyze(event)
   if path.endswith("/result") and method == "GET":
       return handle_get_result(event)
   return _response(404, {"error": "Not found", "path": path, "method": method})

def handle_upload_url(event):
   body = _get_json(event)
   filename = body.get("filename", "image.jpg")
   content_type = body.get("contentType", "image/jpeg")
   key = f"uploads/{uuid.uuid4()}_{filename}"
   upload_url = s3.generate_presigned_url(
       ClientMethod="put_object",
       Params={
           "Bucket": UPLOAD_BUCKET,
           "Key": key,
           "ContentType": content_type,
       },
       ExpiresIn=300,  # 5 minutes
   )
   return _response(200, {
       "uploadUrl": upload_url,
       "bucket": UPLOAD_BUCKET,
       "key": key,
   })

def handle_analyze(event):
   body = _get_json(event)
   key = body.get("key")
   if not key:
       return _response(400, {"error": "Missing required field: key"})
   # Rekognition needs S3 object reference
   try:
       rek_resp = rek.detect_labels(
           Image={"S3Object": {"Bucket": UPLOAD_BUCKET, "Name": key}},
           MaxLabels=10,
           MinConfidence=70,
       )
   except Exception as e:
       return _response(500, {"error": "Rekognition failed", "details": str(e)})
   labels = [
       {"name": l["Name"], "confidence": float(l["Confidence"])}
       for l in rek_resp.get("Labels", [])
   ]
   analysis_id = str(uuid.uuid4())
   now = int(time.time())
   item = {
       "pk": f"ANALYSIS#{analysis_id}",
       "sk": f"TS#{now}",
       "analysisId": analysis_id,
       "bucket": UPLOAD_BUCKET,
       "key": key,
       "createdAt": now,
       "labels": labels,
   }
   try:
       table.put_item(Item=item)
   except Exception as e:
       return _response(500, {"error": "DynamoDB put_item failed", "details": str(e)})
   return _response(200, {
       "analysisId": analysis_id,
       "createdAt": now,
       "labels": labels,
   })

def handle_get_result(event):
   qs = event.get("queryStringParameters") or {}
   analysis_id = qs.get("analysisId")
   if not analysis_id:
       return _response(400, {"error": "Missing query param: analysisId"})
   pk = f"ANALYSIS#{analysis_id}"
   # Query by pk; pick newest by sk
   try:
       resp = table.query(
           KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(pk),
           ScanIndexForward=False,
           Limit=1,
       )
   except Exception as e:
       return _response(500, {"error": "DynamoDB query failed", "details": str(e)})
   items = resp.get("Items", [])
   if not items:
       return _response(404, {"error": "Not found", "analysisId": analysis_id})
   return _response(200, items[0])
