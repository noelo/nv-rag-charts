# Document Ingestion Kubeflow Pipeline

This pipeline implements a document ingestion workflow for processing documents from S3, converting them with Docling, and storing chunks in Milvus.

## Pipeline Stages

1. **Ingestion Stage**: Reads document from S3, parses metadata, generates MD5 hash
2. **Conversion Stage**: Converts document to DoclingDocument using docling serve API
3. **Storage Stage**: Chunks the DoclingDocument using HybridChunker and stores chunks in Milvus database

## Setup

Install the required dependencies:

```bash
pip install kfp>=2.0.0
```

Or use uv/pip with the project:

```bash
uv pip install -e .
```

## Usage

### Option 1: Compile Only

To compile the pipeline to a YAML file without submitting:

```bash
python run_pipeline.py --compile-only
```

This generates `document_ingestion_pipeline.yaml` which you can upload to the Kubeflow UI.

### Option 2: Compile and Submit

To compile and submit the pipeline directly to your Kubeflow instance:

```bash
python run_pipeline.py --host http://your-kubeflow-host:8080
```

### Option 3: Use the Pipeline Programmatically

You can also import and use the pipeline in your own code:

```python
from kubeflow_pipeline import document_ingestion_pipeline
from kfp import compiler

# Compile to YAML
compiler.Compiler().compile(
    pipeline_func=document_ingestion_pipeline,
    package_path="my_pipeline.yaml"
)
```

## Pipeline Files

- `kubeflow_pipeline.py` - Main pipeline definition with ingestion, conversion, and storage stages
- `run_pipeline.py` - Helper script to compile and submit the pipeline
- `document_ingestion_pipeline.yaml` - Compiled pipeline (generated after running)

## Uploading to Kubeflow UI

1. Run `python run_pipeline.py --compile-only`
2. Open your Kubeflow Pipelines UI
3. Click "Upload pipeline"
4. Select the generated `document_ingestion_pipeline.yaml` file
5. Create a run from the uploaded pipeline

## Environment Variables

The pipeline requires the following environment variables:

- `AWS_CREDENTIALS_FILE`: Path to AWS credentials JSON file
- `DOCLING_API_URL`: URL for the docling serve API (default: http://docling-serve:5000/convert)
- `MILVUS_HOST`: Milvus server host (default: localhost)
- `MILVUS_PORT`: Milvus server port (default: 19530)

## Pipeline Parameters

- `ingestion_document_s3_location`: S3 URI of the document to ingest (e.g., s3://bucket/path/to/file.pdf)
- `document_metadata`: List of key-value metadata pairs to attach to the document
