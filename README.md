# HealthTech Production Pipeline

A production-ready, event-driven healthcare data pipeline that transforms unstructured medical data into structured FHIR resources.

## Architecture Overview

This pipeline handles multi-modal ingestion (Email, Web Upload), massive scale (1GB+ files), and AI-driven compliance using AWS Guardrails.

### Key Components

- **Ingest Channels**: SES (Email) and Direct S3 Upload (Web)
- **Processing**: Amazon Textract (OCR), Amazon Bedrock (Claude 3.5 Sonnet), AWS Step Functions (Orchestration)
- **Storage**: Amazon HealthLake (FHIR Store)

## Repository Structure

```
/healthtech-production-pipeline
│
├── infra/                          # Terraform Infrastructure
│   ├── main.tf                     # S3, SFN, EventBridge, SES Receipt Rule
│   ├── healthlake.tf               # AWS HealthLake Datastore (R4)
│   ├── iam.tf                      # Least-Privilege Roles
│   ├── outputs.tf                  # Bucket Names, API GW URL
│   └── variables.tf                # Region, Model IDs
│
├── src/
│   ├── frontend/
│   │   └── index.html              # Web UI for large file uploads (Presigned URL)
│   │
│   ├── statemachine/
│   │   └── pipeline.asl.json       # Step Functions Definition (Map State included)
│   │
│   └── functions/
│       ├── mime_extractor/         # Triggered by SES. Extracts attachment -> S3 'incoming/'
│       │   └── handler.py
│       ├── get_presigned_url/      # API GW handler for Web Uploads
│       │   └── handler.py
│       ├── document_router/        # Triggered by EventBridge. Decides: Textract vs Native Parse
│       │   └── handler.py
│       ├── content_splitter/       # Downloads file/OCR result -> Splits into 50-page chunks
│       │   └── handler.py
│       ├── bedrock_guardrail/      # Analyzes Chunk: "Is this Medical or Fiction?"
│       │   └── handler.py
│       └── fhir_ingest/            # Validates & Puts to HealthLake + Adds Provenance Resource
│           └── handler.py
│
└── .github/
    └── workflows/
        └── deploy.yaml             # Terraform Apply Workflow
```

## Critical Design Decisions

### MIME Handling
SES delivers raw MIME blobs. The "Pre-Processor" Lambda strips MIME and extracts the clean PDF to a clean S3 prefix before processing starts.

### Loop Prevention
EventBridge triggers ONLY on the `incoming/` prefix. Does not trigger on `temp/` or `raw_email/` to avoid infinite loops.

### Scale
Uses Map state in Step Functions with `MaxConcurrency: 20` to process large files in parallel chunks.

### Guardrails
The AI Model classifies content (Valid Medical vs. Invalid/Fiction) before extraction.

## Deployment

### Prerequisites

1. AWS Account with appropriate permissions
2. Verified SES Domain for email ingestion
3. GitHub Actions configured with AWS OIDC

### Deploy with Terraform

```bash
cd infra
terraform init
terraform apply -var="domain_name=yourdomain.com"
```

### CI/CD

Push to `main` branch triggers automatic deployment via GitHub Actions.

## Pipeline Flow

1. **Ingestion**: Files arrive via email (SES) or web upload (S3 presigned URL)
2. **Routing**: Document Router determines processing path (Textract OCR vs Native Parse)
3. **Splitting**: Content Splitter breaks large files into manageable chunks
4. **Analysis**: Bedrock Guardrail validates medical content using Claude 3.5 Sonnet
5. **Storage**: FHIR Ingest creates resources in HealthLake with Provenance tracking

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BUCKET_NAME` | S3 bucket for data lake |
| `BEDROCK_MODEL_ID` | Claude model ID for guardrails |
| `HEALTHLAKE_DS_ID` | HealthLake datastore ID |

## License

MIT License
