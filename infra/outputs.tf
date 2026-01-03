output "s3_bucket_name" {
  value = aws_s3_bucket.data_lake.id
}

output "healthlake_endpoint" {
  # Updated to use awscc output
  value = awscc_healthlake_fhir_datastore.store.datastore_endpoint
}

output "api_gateway_url" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "step_function_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "api_base_url" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "dashboard_url" {
  value = "${aws_apigatewayv2_api.http_api.api_endpoint}/dashboard"
}
