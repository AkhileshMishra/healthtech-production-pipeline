# --- IAM Role for Step Functions ---
resource "aws_iam_role" "sfn_role" {
  name = "sfn-execution-role-${var.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "states.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "sfn_policy" {
  role = aws_iam_role.sfn_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["lambda:InvokeFunction"],
        Resource = [
          aws_lambda_function.document_router.arn,
          aws_lambda_function.content_splitter.arn,
          aws_lambda_function.bedrock_guardrail.arn,
          aws_lambda_function.fhir_ingest.arn
        ]
      }
    ]
  })
}

# --- IAM Role for EventBridge ---
resource "aws_iam_role" "eventbridge_role" {
  name = "eventbridge-sfn-role-${var.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "events.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "eventbridge_policy" {
  role = aws_iam_role.eventbridge_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["states:StartExecution"],
        Resource = [aws_sfn_state_machine.pipeline.arn]
      }
    ]
  })
}

# --- IAM Role for Lambdas (Shared for brevity, separate in prod) ---
resource "aws_iam_role" "lambda_role" {
  name = "lambda-execution-role-${var.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:HeadObject"],
        Resource = ["${aws_s3_bucket.data_lake.arn}", "${aws_s3_bucket.data_lake.arn}/*"]
      },
      {
        Effect = "Allow",
        Action = ["textract:*", "bedrock:InvokeModel", "healthlake:CreateResource", "healthlake:SearchWithGet", "healthlake:ReadResource", "healthlake:UpdateResource"],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "*"
      }
    ]
  })
}
