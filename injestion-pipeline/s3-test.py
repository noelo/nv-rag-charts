import sys
import boto3
import os
import hashlib
from urllib.parse import urlparse
from docling_core.types.doc.document import DoclingDocument
from dotenv import load_dotenv
from pathlib import Path
import json
import httpx
import asyncio

# Create S3 client with credentials from file
s3_client = boto3.client(
    "s3",
    endpoint_url="https://minio-api-minio.apps.ocp.2mjjj.sandbox286.opentlc.com",
    aws_access_key_id="minio",
    aws_secret_access_key="minio123",
    region_name="us-east-1",
    use_ssl=True
)


bucket_list = s3_client.list_objects(Bucket="doc-ingestion")
print(bucket_list)
for obj in bucket_list["Contents"]:
    print(obj["Key"])

response = s3_client.get_object(Bucket="doc-ingestion", Key="MyPure_Bill-2.pdf")
file_content = response["Body"].read()

print(f"Successfully read {len(file_content)} bytes from S3")
print(f"Content type: {response.get('ContentType', 'unknown')}")

# s3_client.download_file(bucket_name, 'hello.txt', '/tmp/hello.txt')

# Generate MD5 hash of file contents

md5_hash = hashlib.md5(file_content).hexdigest()
print(f"MD5 hash: {md5_hash}")


async def convert_document(file_content):
    # Get docling serve API endpoint from environment variable
    docling_api_url="http://docling-serve-docling.apps.ocp.2mjjj.sandbox286.opentlc.com/v1/convert/file"
    
    print(f"Calling docling serve API at: {docling_api_url}")

    # Configure conversion options for docling

    options={
        "from_formats": [
        "docx",
        "pptx",
        "html",
        "image",
        "pdf",
        "asciidoc",
        "md",
        "csv",
        "xlsx",
        "xml_uspto",
        "xml_jats",
        "mets_gbs",
        "json_docling",
        "audio",
        "vtt"
        ],
        "to_formats": [
        "json"
        ],
        "image_export_mode": "placeholder",
        "do_ocr": True,
        "force_ocr": False,
        "ocr_engine": "auto",
        "ocr_lang": [
        "fr",
        "de",
        "es",
        "en"
        ],
        "pdf_backend": "pypdfium2",
        "table_mode": "fast",
    }


    # print(f"Conversion options: {json.dumps(options, indent=2)}")

    # Call docling serve API to convert to markdown using async httpx client
    async with httpx.AsyncClient(timeout=300.0) as client:
        files = {"files": ("test.pdf", file_content,"application/json")}
        
        response = await client.post(docling_api_url, files=files, data=options)

        if response.status_code != 200:
            raise Exception(f"Docling API returned status code {response.status_code}: {response.text}")      

        doc_status=response.json()["status"]
        processing_time=response.json()["processing_time"]
        if doc_status!="success":
            raise Exception(f"Docling failed to process document {doc_status}")

        response_obj = response.json()["document"]["json_content"]
        try:
            doclingdoc_json = DoclingDocument.model_validate_json(json.dumps(response_obj))
        except Exception as e:
            raise Exception(f"Invalid DoclingDocument, returned JSON payload failed validation. {e}")

        print(f"Successfully processed document in {processing_time}")

        return doclingdoc_json



output_json = asyncio.run(convert_document(file_content))

doc = DoclingDocument.model_validate(output_json)

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
    utility,)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer
import numpy as np


connections.connect(alias="default", host="localhost", port=27017)
collection_name="test-collection5"

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
        FieldSchema(
            name="chunk_vector", dtype=DataType.FLOAT_VECTOR, dim=512
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


EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(EMBED_MODEL_ID),
)
chunker = HybridChunker(tokenizer=tokenizer)

print(f"{tokenizer.get_max_tokens()=}")

chunk_iter = chunker.chunk(dl_doc=doc)

chunk_texts = []
document_names = []
chunk_indices = []
metadata_jsons = []
chunk_vectors=[]

for idx, chunk in enumerate(chunk_iter):
    enriched_text = chunker.contextualize(chunk=chunk)
    chunk_texts.append(enriched_text)
    document_names.append(doc.origin.filename)
    chunk_indices.append(idx)
    metadata_jsons.append(json.dumps("{}"))
    chunk_vectors.append(np.random.rand(512).astype(np.float32))

chunk_count = len(chunk_texts)

# Insert chunks into Milvus
print(
    f"\nInserting {chunk_count} chunks into Milvus collection '{collection_name}'..."
)

entities = [chunk_texts, document_names, chunk_indices, metadata_jsons, chunk_vectors]
# entities = [chunk_texts, document_names, chunk_indices, metadata_jsons]

insert_result = collection.insert(entities)
collection.flush()
print(f"Num entities {collection.num_entities}")

print(f"Successfully inserted {chunk_count} chunks into Milvus")
print(f"Insert result: {insert_result}")

# Disconnect from Milvus
connections.disconnect("default")
print("Disconnected from Milvus")
