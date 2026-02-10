"""
Document Ingestion Kubeflow Pipeline
Ingestion Stage: Read document from S3, parse metadata, generate MD5 hash
Conversion Stage: Convert document to DoclingDocument using docling serve API
Storage Stage: Chunk DoclingDocument and store chunks in Milvus database
"""
from typing import Dict
from kfp import dsl
from kfp import compiler
from kfp import kubernetes
from dotenv import load_dotenv
from pathlib import Path
from kfp.dsl import Output, Artifact, Input


@dsl.component(base_image="registry.redhat.io/ubi10/python-312-minimal", packages_to_install=["boto3","dotenv"])
def ingestion_stage(
    ingestion_document_s3_location: str,
    document_metadata: Dict[str, str],
) -> Dict[str, str]:  
       
    """Ingestion Stage: Read document from S3 and process metadata"""
    import sys
    import boto3
    import os
    import hashlib
    from urllib.parse import urlparse
    from dotenv import load_dotenv
    from pathlib import Path

    CONFIG_SECRETS_LOCATION = "/tmp/ingestion-config/"
    TASK_STORAGE="/mnt/storage/"
    S3_BUCKET_NAME="s3_bucket_name"
    DOCUMENT_NAME="document_name"
    FILE_MD5_HASH="file_md5_hash"

    dotenv_path = Path(CONFIG_SECRETS_LOCATION+'.env')
    load_dotenv(dotenv_path=dotenv_path)

    aws_access_key_id = os.environ.get("aws_access_key_id")
    aws_secret_access_key = os.environ.get("aws_secret_access_key")
    region = os.environ.get("aws_region", "us-east-1")

    try:
        # Parse S3 location
        print(f"Parsing S3 location: {ingestion_document_s3_location}")

        # Parse the S3 URI (e.g., s3://bucket-name/path/to/file.pdf)
        parsed_url = urlparse(ingestion_document_s3_location)

        if parsed_url.scheme != "s3":
            raise ValueError(
                f"Invalid S3 URI scheme: {parsed_url.scheme}. Expected 's3://'"
            )

        bucket_name = parsed_url.netloc
        object_key = parsed_url.path.lstrip("/")

        if not bucket_name:
            raise ValueError("S3 bucket name is empty")
        if not object_key:
            raise ValueError("S3 object key is empty")

        # Extract document name from the object key
        document_name = object_key.split("/")[-1]

        print(f"S3 Bucket: {bucket_name}")
        print(f"Object Key: {object_key}")
        print(f"Document Name: {document_name}")

        # Add bucket name and document name to metadata
        if document_metadata is None:
            document_metadata = {}

        document_metadata[S3_BUCKET_NAME]= bucket_name
        document_metadata[DOCUMENT_NAME]=document_name

        # Read file from S3
        print("Connecting to S3 and reading file...")

        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError(
                "Credentials file must contain 'aws_access_key_id' and 'aws_secret_access_key'"
            )

        print(f"AWS Region: {region}")

        # Create S3 client with credentials from file
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )

        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response["Body"].read()

        print(f"Successfully read {len(file_content)} bytes from S3")
        print(f"Content type: {response.get('ContentType', 'unknown')}")

        # Generate MD5 hash of file contents

        md5_hash = hashlib.md5(file_content).hexdigest()
        print(f"MD5 hash: {md5_hash}")

        # Add MD5 hash to metadata
        document_metadata[FILE_MD5_HASH]= md5_hash

        print(f"Final metadata: {document_metadata}")

        destination_file = TASK_STORAGE+md5_hash+".raw"
        # Write file to Kubeflow-managed output path for next stage
        print(f"Writing file to output path: {destination_file}")

        with open(TASK_STORAGE+md5_hash, "wb") as file:
            file.write(file_content)


        print(
            f"File written successfully to {destination_file} ({len(file_content)} bytes)"
        )
        print("Ingestion stage complete")
        return document_metadata

    except ValueError as ve:
        print(f"ERROR: Invalid input - {ve}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"ERROR: Failed to read document from S3 - {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


@dsl.component(
    base_image="registry.redhat.io/ubi10/python-312-minimal", packages_to_install=["httpx", "docling-core"]
)
def conversion_stage(
    input_document_metadata: Dict[str, str]
) -> Dict[str, str]:
    """Conversion Stage: Convert document to DoclingDocument using docling serve API"""
    import os
    import sys
    import asyncio
    import httpx
    import json
    from dotenv import load_dotenv
    from pathlib import Path


    CONFIG_SECRETS_LOCATION = "/tmp/ingestion-config/"
    TASK_STORAGE="/mnt/storage/"
    DOCUMENT_NAME="document_name"
    FILE_MD5_HASH="file_md5_hash"


    async def convert_document():
        print("Starting conversion stage")

        source_file = TASK_STORAGE+input_document_metadata[FILE_MD5_HASH]

        # Verify the file exists and read it
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Document file not found at {source_file}")


        # Read file content
        with open(source_file, "rb") as f:
            ingested_content = f.read()
            print(
                f"Successfully read {len(ingested_content)} bytes from Kubeflow artifact storage"
            )

        document_metadata = input_document_metadata

        # Get docling serve API endpoint from environment variable
        docling_api_url = os.environ.get(
            "DOCLING_API_URL", "http://docling-serve:5000/convert"
        )
        print(f"Calling docling serve API at: {docling_api_url}")

        # Configure conversion options for docling
        conversion_options = {
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

        file_type = document_metadata.get("file_type", 'application/pdf')
        document_name = document_metadata.get(DOCUMENT_NAME)

        print(f"Conversion options: {json.dumps(conversion_options, indent=2)}")

        # Call docling serve API to convert to markdown using async httpx client
        async with httpx.AsyncClient(timeout=300.0) as client:
            files = {"files": (document_name, ingested_content,file_type)}
            
            response = await client.post(docling_api_url, files=files, data=conversion_options)

            if response.status_code != 200:
                raise Exception(
                    f"Docling API returned status code {response.status_code}: {response.text}"
                )

            response_data = response.json()
            docling_document = response_data.document.json_content

        print(
            f"Document has {len(docling_document.pages) if hasattr(docling_document, 'pages') else 0} pages"
        )

        destination_file = source_file+".json"

        # Serialize DoclingDocument to JSON for stage 3
        with open(destination_file, "w", encoding="utf-8") as f:
            # Export document to JSON
            doc_json = docling_document.model_dump_json(indent=2)
            f.write(doc_json)
        print("DoclingDocument written successfully")

        print("Conversion stage complete, moving to stage 3")

        return document_metadata

    try:
        dotenv_path = Path(CONFIG_SECRETS_LOCATION+'.env')
        load_dotenv(dotenv_path=dotenv_path)
        res = asyncio.run(convert_document())
        return res
    except FileNotFoundError as fnf:
        print(f"ERROR: {fnf}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as http_err:
        print(f"ERROR: Failed to call docling API - {http_err}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Conversion failed - {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


@dsl.component(
    base_image="registry.redhat.io/ubi10/python-312-minimal", packages_to_install=["docling-core", "pymilvus"]
)
def storage_stage(
    input_document_metadata: Dict[str, str]
):
    """Storage Stage: Chunk DoclingDocument and write to Milvus"""
    import os
    import sys
    import json
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    from dotenv import load_dotenv
    from pathlib import Path
    from pymilvus import (
        connections,
        Collection,
        FieldSchema,
        CollectionSchema,
        DataType,
        utility,
    )


    CONFIG_SECRETS_LOCATION = "/tmp/ingestion-config/"
    TASK_STORAGE="/mnt/storage/"
    S3_BUCKET_NAME="s3_bucket_name"
    DOCUMENT_NAME="document_name"
    FILE_MD5_HASH="file_md5_hash"

    print("Starting storage stage")        
    dotenv_path = Path(CONFIG_SECRETS_LOCATION+'.env')
    load_dotenv(dotenv_path=dotenv_path)

    milvus_host = os.environ.get("MILVUS_HOST", "localhost")
    milvus_port = os.environ.get("MILVUS_PORT", "19530")

    try:
        # Read metadata from previous stage
        source_file = TASK_STORAGE+input_document_metadata[FILE_MD5_HASH]+'.json'

        # Verify the file exists and read it
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Document file not found at {source_file}")


        # Read file content
        with open(source_file, "rb") as f:
            ingested_content = f.read()
            print(
                f"Successfully read {len(ingested_content)} bytes from Kubeflow artifact storage"
            )

        document_metadata = input_document_metadata

        # Deserialize JSON to DoclingDocument
        docling_document = DoclingDocument.model_validate_json(ingested_content)

        print("Successfully loaded DoclingDocument")
        print(
            f"Document has {len(docling_document.pages) if hasattr(docling_document, 'pages') else 0} pages"
        )
 
        collection_name = document_metadata.get(S3_BUCKET_NAME)
        document_name = document_metadata.get(DOCUMENT_NAME)

        if not collection_name:
            raise ValueError("s3_bucket_name not found in document_metadata")

        print(f"\nUsing Milvus collection name: {collection_name}")

        # Connect to Milvus

        print(f"Connecting to Milvus at {milvus_host}:{milvus_port}")
        connections.connect(alias="default", host=milvus_host, port=milvus_port)

        # Define collection schema if it doesn't exist
        collection_name = collection_name.replace("-", "_").replace(
            ".", "_"
        )  # Sanitize collection name

        if not utility.has_collection(collection_name):
            print(f"Creating new collection: {collection_name}")
            fields = [
                FieldSchema(
                    name="id", dtype=DataType.INT64, is_primary=True, auto_id=True
                ),
                FieldSchema(
                    name="chunk_text", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="document_name", dtype=DataType.VARCHAR, max_length=512
                ),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(
                    name="metadata_json", dtype=DataType.VARCHAR, max_length=2048
                ),
            ]
            schema = CollectionSchema(
                fields=fields, description=f"Document chunks from {collection_name}"
            )
            collection = Collection(name=collection_name, schema=schema)
            print(f"Collection {collection_name} created successfully")
        else:
            print(f"Using existing collection: {collection_name}")
            collection = Collection(name=collection_name)

        print("Chunking document with HybridChunker...")
        chunker = HybridChunker()

        # Chunk the document
        chunk_iter = chunker.chunk(dl_doc=docling_document)

        for i, chunk in enumerate(chunk_iter):
            enriched_text = chunker.contextualize(chunk=chunk)

        chunk_texts = []
        document_names = []
        chunk_indices = []
        metadata_jsons = []

        for idx, chunk in enumerate(chunk_iter):
            enriched_text = chunker.contextualize(chunk=chunk)
            chunk_texts.append(enriched_text)
            document_names.append(document_name or "unknown")
            chunk_indices.append(idx)
            metadata_jsons.append(json.dumps(document_metadata))

        chunk_count = len(chunk_texts)

        # Insert chunks into Milvus
        print(
            f"\nInserting {chunk_count} chunks into Milvus collection '{collection_name}'..."
        )

        entities = [chunk_texts, document_names, chunk_indices, metadata_jsons]

        insert_result = collection.insert(entities)
        collection.flush()

        print(f"Successfully inserted {chunk_count} chunks into Milvus")
        print(f"Insert result: {insert_result}")

        # Disconnect from Milvus
        connections.disconnect("default")
        print("Disconnected from Milvus")

    except FileNotFoundError as fnf:
        print(f"ERROR: {fnf}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"ERROR: Failed to process document - {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 80)
    print("Pipeline complete")


@dsl.pipeline(
    name="document-ingestion-pipeline",
    description="Document ingestion pipeline: S3 ingestion, docling conversion, and Milvus storage",
)
def document_ingestion_pipeline(
    document_metadata: Dict[str, str],
    ingestion_document_s3_location: str = "s3://default-bucket/documents/",

): 
    import os
    CONFIG_SECRETS_LOCATION = "/tmp/ingestion-config/"

    conversion_timeout = os.environ.get("DOCLING_TIMEOUT", 600)
   
    """Define the document ingestion pipeline"""
    # Ingestion Stage: Read from S3 and write to Kubeflow artifact storage
    ingestion_stage_task = ingestion_stage(
        ingestion_document_s3_location=ingestion_document_s3_location,
        document_metadata=document_metadata,
    )

    # Conversion Stage: Convert document to DoclingDocument (receives file and metadata from ingestion stage)
    conversion_stage_task = conversion_stage(
        input_document_metadata=ingestion_stage_task.output,
    ).after(ingestion_stage_task)


    # Storage Stage: Chunk and store DoclingDocument 
    storage_stage_task = storage_stage(
        input_document_metadata=conversion_stage_task.output,
    ).after(conversion_stage_task)

    # pvc1 = kubernetes.CreatePVC(
    #     pvc_name_suffix='-ingest',
    #     access_modes=['ReadWriteOnce'],
    #     size='5Gi',
    #     storage_class_name="gp3-csi"
    # )  

    # kubernetes.mount_pvc(
    #     ingestion_stage_task,
    #     pvc_name=pvc1.outputs['name'],
    #     mount_path='/mnt/storage',
    # )

    kubernetes.use_secret_as_volume(
        ingestion_stage_task,
        secret_name="ingestion-config-secret",
        mount_path=CONFIG_SECRETS_LOCATION,
        optional=False,
    )

    kubernetes.set_timeout(conversion_stage_task,conversion_timeout)

    # kubernetes.mount_pvc(
    #     conversion_stage_task,
    #     pvc_name=pvc1.outputs['name'],
    #     mount_path='/mnt/storage',
    # )

    # kubernetes.mount_pvc(
    #     storage_stage_task,
    #     pvc_name=pvc1.outputs['name'],
    #     mount_path='/mnt/storage',
    # )

    # kubernetes.DeletePVC(
    #     pvc_name=pvc1.outputs['name']
    # ).after(storage_stage_task)
    


if __name__ == "__main__":
    # Compile the pipeline to YAML
    compiler.Compiler().compile(
        pipeline_func=document_ingestion_pipeline,
        package_path="document_ingestion_pipeline.yaml",
    )
    print("Pipeline compiled successfully to 'document_ingestion_pipeline.yaml'")
