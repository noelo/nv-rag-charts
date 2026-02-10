# Document Ingestion Kubeflow Pipeline

This pipeline implements a three-stage document ingestion workflow for processing documents from S3, converting them with Docling, and storing chunks in Milvus vector database.

## Pipeline Stages

### 1. Ingestion Stage
- Reads document from S3 using boto3
- Parses S3 URI (s3://bucket/path/to/file.pdf)
- Generates MD5 hash of file contents for deduplication
- Stores raw file to shared PVC at `/mnt/storage/{md5_hash}`
- Enriches metadata with bucket name, document name, and MD5 hash

**Base Image**: `registry.redhat.io/ubi10/python-312-minimal`
**Dependencies**: `boto3`, `dotenv`

### 2. Conversion Stage
- Reads raw file from shared PVC
- Calls docling serve API to convert document to DoclingDocument format
- Supports multiple output formats: markdown, json, html, text, doctags
- Configurable OCR settings (EasyOCR engine, English language)
- Uses `dlparse_v2` PDF backend with fast table mode
- Stores converted DoclingDocument as JSON at `/mnt/storage/{md5_hash}.json`
- Configurable timeout (default: 600 seconds)

**Base Image**: `registry.redhat.io/ubi10/python-312-minimal`
**Dependencies**: `httpx`, `docling-core`

### 3. Storage Stage
- Reads DoclingDocument JSON from shared PVC
- Chunks document using HybridChunker from docling-core
- Contextualizes each chunk for better retrieval
- Creates or connects to Milvus collection (named after S3 bucket, sanitized)
- Inserts chunks with metadata into Milvus
- Collection schema includes: chunk_text, document_name, chunk_index, metadata_json

**Base Image**: `registry.redhat.io/ubi10/python-312-minimal`
**Dependencies**: `docling-core`, `pymilvus`

## Architecture

### Data Flow
1. S3 → Ingestion Stage → `/mnt/storage/{md5_hash}` (raw file)
2. Raw file → Conversion Stage → `/mnt/storage/{md5_hash}.json` (DoclingDocument)
3. DoclingDocument → Storage Stage → Milvus collection

### Storage
- **PVC**: A temporary 5Gi ReadWriteOnce PVC is created at pipeline start
- **Mount Path**: `/mnt/storage/` on all three stage pods
- **Cleanup**: PVC is automatically deleted after storage stage completes

### Configuration
Configuration is loaded from a Kubernetes secret mounted at `/tmp/ingestion-config/.env`

Required secret: `ingestion-config-secret`

## Setup

### 1. Install Dependencies

```bash
pip install kfp>=2.0.0
```

Or using uv:

```bash
uv pip install -e .
```

### 2. Create Kubernetes Secret

Create a `.env` file with your credentials:

```bash
# AWS Credentials
aws_access_key_id=YOUR_ACCESS_KEY
aws_secret_access_key=YOUR_SECRET_KEY
aws_region=us-east-1

# Docling API
DOCLING_API_URL=http://docling-serve:5000/convert
DOCLING_TIMEOUT=600

# Milvus Configuration
MILVUS_HOST=milvus-standalone
MILVUS_PORT=19530
```

Create the Kubernetes secret:

```bash
kubectl create secret generic ingestion-config-secret \
  --from-file=.env=.env \
  -n kubeflow
```

## Usage

### Compile the Pipeline

To compile the pipeline to YAML:

```bash
python kubeflow_pipeline.py
```

This generates `document_ingestion_pipeline.yaml`.

### Upload to Kubeflow UI

1. Compile the pipeline using the command above
2. Open your Kubeflow Pipelines UI
3. Click "Upload pipeline"
4. Select `document_ingestion_pipeline.yaml`
5. Create a run with the following parameters:
   - `ingestion_document_s3_location`: S3 URI (e.g., `s3://my-bucket/documents/example.pdf`)
   - `document_metadata`: Dictionary of metadata (e.g., `{"source": "manual", "category": "technical"}`)

### Programmatic Usage

```python
from kubeflow_pipeline import document_ingestion_pipeline
from kfp import compiler

# Compile to YAML
compiler.Compiler().compile(
    pipeline_func=document_ingestion_pipeline,
    package_path="document_ingestion_pipeline.yaml"
)
```

## Pipeline Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `ingestion_document_s3_location` | str | S3 URI of document to process | `s3://my-bucket/docs/file.pdf` |
| `document_metadata` | Dict[str, str] | Custom metadata key-value pairs | `{"author": "John", "year": "2024"}` |

## Configuration Options

### Environment Variables (in .env file)

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_access_key_id` | AWS access key | *Required* |
| `aws_secret_access_key` | AWS secret key | *Required* |
| `aws_region` | AWS region | `us-east-1` |
| `DOCLING_API_URL` | Docling serve API endpoint | `http://docling-serve:5000/convert` |
| `DOCLING_TIMEOUT` | Conversion timeout in seconds | `600` |
| `MILVUS_HOST` | Milvus server hostname | `localhost` |
| `MILVUS_PORT` | Milvus server port | `19530` |

### Docling Conversion Options

The conversion stage uses the following options (defined in kubeflow_pipeline.py:176-187):

```python
{
    "from_formats": ["pdf"],
    "to_formats": ["md", "json", "html", "text", "doctags"],
    "image_export_mode": "placeholder",
    "do_ocr": True,
    "force_ocr": False,
    "ocr_engine": "easyocr",
    "ocr_lang": ["en"],
    "pdf_backend": "dlparse_v2",
    "table_mode": "fast",
    "abort_on_error": False,
}
```

## Milvus Collection Schema

Collections are automatically created using the S3 bucket name (sanitized: hyphens and dots replaced with underscores).

| Field | Type | Description |
|-------|------|-------------|
| `id` | INT64 | Primary key (auto-generated) |
| `chunk_text` | VARCHAR(65535) | Contextualized chunk content |
| `document_name` | VARCHAR(512) | Original document filename |
| `chunk_index` | INT64 | Sequential chunk number |
| `metadata_json` | VARCHAR(2048) | JSON-encoded metadata |

## Error Handling

Each stage includes comprehensive error handling:

- **Ingestion Stage**: Validates S3 URI format, checks credentials, handles S3 access errors
- **Conversion Stage**: Validates file existence, handles HTTP errors from docling API, validates response format
- **Storage Stage**: Validates file existence, handles Milvus connection errors, provides detailed stack traces

All errors are logged to stderr and cause the stage to exit with code 1.

## Files

- `kubeflow_pipeline.py` - Complete pipeline definition with all three stages
- `document_ingestion_pipeline.yaml` - Compiled pipeline YAML (generated)
- `.env` - Configuration file (should be in .gitignore)

## Troubleshooting

### Pipeline fails at ingestion stage
- Verify `ingestion-config-secret` exists: `kubectl get secret ingestion-config-secret -n kubeflow`
- Check AWS credentials in the secret
- Verify S3 URI format: must start with `s3://`

### Pipeline fails at conversion stage
- Check docling serve is running and accessible
- Verify DOCLING_API_URL in the secret
- Increase DOCLING_TIMEOUT for large documents

### Pipeline fails at storage stage
- Verify Milvus is running: `kubectl get pods -l app=milvus -n kubeflow`
- Check MILVUS_HOST and MILVUS_PORT in the secret
- Ensure collection name is valid (bucket name with sanitized characters)
