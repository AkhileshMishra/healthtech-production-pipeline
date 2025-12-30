variable "aws_region" {
  description = "AWS Region"
  default     = "us-east-1"
}

variable "env" {
  description = "Environment name (dev, prod)"
  default     = "dev"
}

variable "domain_name" {
  description = "Verified SES Domain for email ingestion"
  type        = string
}

variable "bedrock_model_id" {
  description = "Model ID for Guardrails (Claude 3.5 Sonnet)"
  default     = "anthropic.claude-3-5-sonnet-20240620-v1:0"
}
