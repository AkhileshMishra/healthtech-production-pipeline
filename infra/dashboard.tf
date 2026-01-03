# -----------------------------
# 1) Lambda: patient-query
# -----------------------------
data "archive_file" "patient_query_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/functions/patient_query"
  output_path = "${path.module}/lambda_zips/patient_query.zip"
}

resource "aws_lambda_function" "patient_query" {
  filename         = data.archive_file.patient_query_zip.output_path
  function_name    = "patient-query-${var.env}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  source_code_hash = data.archive_file.patient_query_zip.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30

  environment {
    variables = {
      HEALTHLAKE_ID = awscc_healthlake_fhir_datastore.store.datastore_id
    }
  }
}

# -----------------------------
# 2) API routes (reuse existing HTTP API)
# -----------------------------
resource "aws_apigatewayv2_integration" "patient_query_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.patient_query.invoke_arn
}

resource "aws_apigatewayv2_route" "patients_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /patients"
  target    = "integrations/${aws_apigatewayv2_integration.patient_query_integration.id}"
}

resource "aws_apigatewayv2_route" "patient_by_id_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /patients/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.patient_query_integration.id}"
}

resource "aws_lambda_permission" "api_gw_patient_query" {
  statement_id  = "AllowExecutionFromAPIGatewayPatientQuery"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.patient_query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# -----------------------------
# 3) Static dashboard site (S3 Website Hosting)
#    NOTE: For production with PHI, add auth (Cognito/CloudFront signed) rather than public hosting.
# -----------------------------
resource "aws_s3_bucket" "dashboard_site" {
  bucket        = "healthtech-dashboard-${var.env}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_website_configuration" "dashboard_site" {
  bucket = aws_s3_bucket.dashboard_site.id

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "dashboard_site" {
  bucket                  = aws_s3_bucket.dashboard_site.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "dashboard_site_public" {
  bucket = aws_s3_bucket.dashboard_site.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = ["s3:GetObject"]
        Resource  = "${aws_s3_bucket.dashboard_site.arn}/*"
      }
    ]
  })
}

# Upload dashboard HTML
resource "aws_s3_object" "dashboard_index" {
  bucket       = aws_s3_bucket.dashboard_site.id
  key          = "index.html"
  source       = "${path.module}/../dashboard/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../dashboard/index.html")
}
