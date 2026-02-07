"""
Document Ingestion Kubeflow Pipeline
Ingestion Stage: Read document from S3, parse metadata, generate MD5 hash
Conversion Stage: Convert document to DoclingDocument using docling serve API
Storage Stage: Chunk DoclingDocument and store chunks in Milvus database
"""

from kfp import dsl
from kfp import compiler


@dsl.component(base_image="python:3.11-slim", packages_to_install=["boto3"])
def ingestion_stage(
    ingestion_document_s3_location: str,
    document_metadata: list,
    document_file: dsl.OutputPath(),
    metadata_output: dsl.OutputPath()
):
    """Ingestion Stage: Read document from S3 and process metadata"""
    import sys
    import re
    from urllib.parse import urlparse

    try:
        # Parse S3 location
        print(f"Parsing S3 location: {ingestion_document_s3_location}")

        # Parse the S3 URI (e.g., s3://bucket-name/path/to/file.pdf)
        parsed_url = urlparse(ingestion_document_s3_location)

        if parsed_url.scheme != 's3':
            raise ValueError(f"Invalid S3 URI scheme: {parsed_url.scheme}. Expected 's3://'")

        bucket_name = parsed_url.netloc
        object_key = parsed_url.path.lstrip('/')

        if not bucket_name:
            raise ValueError("S3 bucket name is empty")
        if not object_key:
            raise ValueError("S3 object key is empty")

        # Extract document name from the object key
        document_name = object_key.split('/')[-1]

        print(f"S3 Bucket: {bucket_name}")
        print(f"Object Key: {object_key}")
        print(f"Document Name: {document_name}")

        # Add bucket name and document name to metadata
        if document_metadata is None:
            document_metadata = []

        document_metadata.append({"key": "s3_bucket", "value": bucket_name})
        document_metadata.append({"key": "document_name", "value": document_name})

        print(f"Updated metadata: {document_metadata}")

        # Read file from S3
        import boto3
        import os
        import json

        print(f"Connecting to S3 and reading file...")

        # Read credentials from file specified in environment variable
        credentials_file = os.environ.get('AWS_CREDENTIALS_FILE')
        if not credentials_file:
            raise ValueError("AWS_CREDENTIALS_FILE environment variable is not set")

        print(f"Reading AWS credentials from: {credentials_file}")

        with open(credentials_file, 'r') as f:
            credentials = json.load(f)

        # Extract credentials from file
        aws_access_key_id = credentials.get('aws_access_key_id')
        aws_secret_access_key = credentials.get('aws_secret_access_key')
        aws_session_token = credentials.get('aws_session_token')  # Optional
        region = credentials.get('region', 'us-east-1')

        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("Credentials file must contain 'aws_access_key_id' and 'aws_secret_access_key'")

        print(f"AWS Region: {region}")

        # Create S3 client with credentials from file
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region
        )

        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read()

        print(f"Successfully read {len(file_content)} bytes from S3")
        print(f"Content type: {response.get('ContentType', 'unknown')}")

        # Generate MD5 hash of file contents
        import hashlib
        md5_hash = hashlib.md5(file_content).hexdigest()
        print(f"MD5 hash: {md5_hash}")

        # Add MD5 hash to metadata
        document_metadata.append({"key": "md5_hash", "value": md5_hash})

        print(f"Final metadata: {document_metadata}")

        # Write file to Kubeflow-managed output path for next stage
        print(f"Writing file to output path: {document_file}")

        with open(document_file, 'wb') as f:
            f.write(file_content)

        print(f"File written successfully to {document_file} ({len(file_content)} bytes)")

        # Write metadata to output path for next stage
        import json
        print(f"Writing metadata to output path: {metadata_output}")
        with open(metadata_output, 'w', encoding='utf-8') as f:
            json.dump(document_metadata, f, indent=2)
        print(f"Metadata written successfully: {document_metadata}")

        print("Ingestion stage complete")

    except ValueError as ve:
        print(f"ERROR: Invalid input - {ve}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read document from S3 - {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


@dsl.component(base_image="python:3.11-slim", packages_to_install=["httpx", "docling-core"])
def conversion_stage(
    document_file: dsl.InputPath(),
    metadata_input: dsl.InputPath(),
    docling_document_output: dsl.OutputPath(),
    metadata_output: dsl.OutputPath()
):
    """Conversion Stage: Convert document to DoclingDocument using docling serve API"""
    import os
    import sys
    import asyncio
    import httpx
    import json
    from docling_core.types.doc import PictureItem, TableItem, DoclingDocument
    from docling_core.transforms.response import ConvertDocumentResponse

    async def convert_document():
        print("Starting conversion stage")

        # Read metadata from previous stage
        print(f"Reading metadata from: {metadata_input}")
        with open(metadata_input, 'r', encoding='utf-8') as f:
            document_metadata = json.load(f)
        print(f"Loaded metadata: {document_metadata}")

        # Verify the file exists and read it
        if not os.path.exists(document_file):
            raise FileNotFoundError(f"Document file not found at {document_file}")

        file_size = os.path.getsize(document_file)
        print(f"Received document file: {document_file}")
        print(f"File size: {file_size} bytes")

        # Read file content
        with open(document_file, 'rb') as f:
            content = f.read()
            print(f"Successfully read {len(content)} bytes from Kubeflow artifact storage")

        # Get docling serve API endpoint from environment variable
        docling_api_url = os.environ.get('DOCLING_API_URL', 'http://docling-serve:5000/convert')
        print(f"Calling docling serve API at: {docling_api_url}")

        # Extract filename from path
        filename = os.path.basename(document_file)

        # Configure conversion options for docling
        conversion_options = {
            "pipeline_options": {
                "do_ocr": True,
                "do_table_structure": True,
                "table_structure_options": {
                    "do_cell_matching": True,
                    "mode": "fast"
                }
            },
            "format_options": {
                "markdown": {
                    "image_mode": "placeholder",
                    "strict_text": False
                }
            }
        }

        print(f"Conversion options: {json.dumps(conversion_options, indent=2)}")

        # Call docling serve API to convert to markdown using async httpx client
        async with httpx.AsyncClient(timeout=300.0) as client:
            files = {'file_sources': (filename, content)}
            data = {'options': json.dumps(conversion_options)}
            response = await client.post(docling_api_url, files=files, data=data)

            if response.status_code != 200:
                raise Exception(f"Docling API returned status code {response.status_code}: {response.text}")

            # Parse response using ConvertDocumentResponse
            response_data = response.json()
            convert_response = ConvertDocumentResponse(**response_data)

            # Get DoclingDocument from the response
            if not hasattr(convert_response, 'document') or not convert_response.document:
                raise Exception("Response does not contain a valid DoclingDocument")

            docling_document = convert_response.document

        print(f"Successfully converted document to DoclingDocument")
        print(f"Document has {len(docling_document.pages) if hasattr(docling_document, 'pages') else 0} pages")

        # Serialize DoclingDocument to JSON for stage 3
        print(f"Writing DoclingDocument to output path: {docling_document_output}")
        with open(docling_document_output, 'w', encoding='utf-8') as f:
            # Export document to JSON
            doc_json = docling_document.model_dump_json(indent=2)
            f.write(doc_json)
        print(f"DoclingDocument written successfully")

        # Propagate metadata to next stage
        print(f"Writing metadata to output path: {metadata_output}")
        with open(metadata_output, 'w', encoding='utf-8') as f:
            json.dump(document_metadata, f, indent=2)
        print(f"Metadata written successfully")

        print("Conversion stage complete, moving to stage 3")

    try:
        asyncio.run(convert_document())
    except FileNotFoundError as fnf:
        print(f"ERROR: {fnf}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as http_err:
        print(f"ERROR: Failed to call docling API - {http_err}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Conversion failed - {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


@dsl.component(base_image="python:3.11-slim", packages_to_install=["docling-core", "pymilvus"])
def storage_stage(
    docling_document_input: dsl.InputPath(),
    metadata_input: dsl.InputPath()
):
    """Storage Stage: Chunk DoclingDocument and write to Milvus"""
    import os
    import sys
    import json
    from docling_core.types.doc import DoclingDocument
    from docling_core.transforms.chunker import HybridChunker
    from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility

    print("Starting storage stage")

    try:
        # Read metadata from previous stage
        print(f"Reading metadata from: {metadata_input}")
        with open(metadata_input, 'r', encoding='utf-8') as f:
            document_metadata = json.load(f)
        print(f"Loaded metadata: {document_metadata}")

        # Read DoclingDocument from conversion stage
        if not os.path.exists(docling_document_input):
            raise FileNotFoundError(f"DoclingDocument file not found at {docling_document_input}")

        print(f"Received DoclingDocument file: {docling_document_input}")

        with open(docling_document_input, 'r', encoding='utf-8') as f:
            doc_json = f.read()

        # Deserialize JSON to DoclingDocument
        docling_document = DoclingDocument.model_validate_json(doc_json)

        print(f"Successfully loaded DoclingDocument")
        print(f"Document has {len(docling_document.pages) if hasattr(docling_document, 'pages') else 0} pages")

        # Initialize HybridChunker with configuration
        chunker = HybridChunker(
            max_tokens=512,
            merge_peers=True,
            tokenizer="text"
        )

        print(f"Chunking document with HybridChunker (max_tokens=512)...")

        # Chunk the document
        chunks = list(chunker.chunk(docling_document))

        print(f"Document chunked into {len(chunks)} chunks")
        print("\n" + "="*80)
        print("CHUNKS OUTPUT:")
        print("="*80 + "\n")

        # Output chunks to stdout
        for idx, chunk in enumerate(chunks, 1):
            print(f"\n--- Chunk {idx} ---")
            print(f"Tokens: {chunk.meta.get('num_tokens', 'N/A') if hasattr(chunk, 'meta') else 'N/A'}")
            print(f"Content:\n{chunk.text if hasattr(chunk, 'text') else str(chunk)}")
            print("-" * 80)

        # Extract bucket_name from metadata for Milvus collection name
        bucket_name = None
        for meta in document_metadata:
            if meta.get('key') == 's3_bucket':
                bucket_name = meta.get('value')
                break

        if not bucket_name:
            raise ValueError("s3_bucket not found in document_metadata")

        print(f"\nUsing Milvus collection name: {bucket_name}")

        # Connect to Milvus
        milvus_host = os.environ.get('MILVUS_HOST', 'localhost')
        milvus_port = os.environ.get('MILVUS_PORT', '19530')
        print(f"Connecting to Milvus at {milvus_host}:{milvus_port}")

        connections.connect(
            alias="default",
            host=milvus_host,
            port=milvus_port
        )

        # Define collection schema if it doesn't exist
        collection_name = bucket_name.replace('-', '_').replace('.', '_')  # Sanitize collection name

        if not utility.has_collection(collection_name):
            print(f"Creating new collection: {collection_name}")
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="document_name", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=2048)
            ]
            schema = CollectionSchema(fields=fields, description=f"Document chunks from {bucket_name}")
            collection = Collection(name=collection_name, schema=schema)
            print(f"Collection {collection_name} created successfully")
        else:
            print(f"Using existing collection: {collection_name}")
            collection = Collection(name=collection_name)

        # Prepare data for insertion
        document_name = None
        for meta in document_metadata:
            if meta.get('key') == 'document_name':
                document_name = meta.get('value')
                break

        chunk_texts = []
        document_names = []
        chunk_indices = []
        metadata_jsons = []

        for idx, chunk in enumerate(chunks):
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            chunk_texts.append(chunk_text)
            document_names.append(document_name or "unknown")
            chunk_indices.append(idx)
            metadata_jsons.append(json.dumps(document_metadata))

        # Insert chunks into Milvus
        print(f"\nInserting {len(chunks)} chunks into Milvus collection '{collection_name}'...")

        entities = [
            chunk_texts,
            document_names,
            chunk_indices,
            metadata_jsons
        ]

        insert_result = collection.insert(entities)
        collection.flush()

        print(f"Successfully inserted {len(chunks)} chunks into Milvus")
        print(f"Insert result: {insert_result}")

        # Disconnect from Milvus
        connections.disconnect("default")
        print("Disconnected from Milvus")

    except FileNotFoundError as fnf:
        print(f"ERROR: {fnf}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to process document - {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "="*80)
    print("Pipeline complete")


@dsl.pipeline(
    name="document-ingestion-pipeline",
    description="Document ingestion pipeline: S3 ingestion, docling conversion, and Milvus storage"
)
def document_ingestion_pipeline(
    ingestion_document_s3_location: str = "s3://default-bucket/documents/",
    document_metadata: list = []
):
    """Define the document ingestion pipeline"""
    # Ingestion Stage: Read from S3 and write to Kubeflow artifact storage
    ingestion_stage_task = ingestion_stage(
        ingestion_document_s3_location=ingestion_document_s3_location,
        document_metadata=document_metadata
    )

    # Conversion Stage: Convert document to DoclingDocument (receives file and metadata from ingestion stage)
    conversion_stage_task = conversion_stage(
        document_file=ingestion_stage_task.outputs['document_file'],
        metadata_input=ingestion_stage_task.outputs['metadata_output']
    )

    # Storage Stage: Chunk and store DoclingDocument (receives DoclingDocument and metadata from conversion stage)
    storage_stage_task = storage_stage(
        docling_document_input=conversion_stage_task.outputs['docling_document_output'],
        metadata_input=conversion_stage_task.outputs['metadata_output']
    )


if __name__ == "__main__":
    # Compile the pipeline to YAML
    compiler.Compiler().compile(
        pipeline_func=document_ingestion_pipeline,
        package_path="document_ingestion_pipeline.yaml"
    )
    print("Pipeline compiled successfully to 'document_ingestion_pipeline.yaml'")
