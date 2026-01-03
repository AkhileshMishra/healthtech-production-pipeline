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
# 3) Lambda: dashboard-ui
# -----------------------------
data "archive_file" "dashboard_ui_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/functions/dashboard_ui"
  output_path = "${path.module}/lambda_zips/dashboard_ui.zip"
}

resource "aws_lambda_function" "dashboard_ui" {
  filename         = data.archive_file.dashboard_ui_zip.output_path
  function_name    = "dashboard-ui-${var.env}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  source_code_hash = data.archive_file.dashboard_ui_zip.output_base64sha256
  runtime          = "python3.11"
  timeout          = 10
}

resource "aws_apigatewayv2_integration" "dashboard_ui_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.dashboard_ui.invoke_arn
}

resource "aws_apigatewayv2_route" "dashboard_ui_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /dashboard"
  target    = "integrations/${aws_apigatewayv2_integration.dashboard_ui_integration.id}"
}

resource "aws_lambda_permission" "api_gw_dashboard_ui" {
  statement_id  = "AllowExecutionFromAPIGatewayDashboardUI"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dashboard_ui.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
