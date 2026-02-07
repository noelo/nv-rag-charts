#!/usr/bin/env python3
"""
Helper script to compile and optionally submit the Kubeflow pipeline
"""

import argparse
from kfp import compiler
from kubeflow_pipeline import document_ingestion_pipeline


def compile_pipeline(output_path="document_ingestion_pipeline.yaml"):
    """Compile the pipeline to a YAML file"""
    print(f"Compiling pipeline to {output_path}...")
    compiler.Compiler().compile(
        pipeline_func=document_ingestion_pipeline,
        package_path=output_path
    )
    print(f"✓ Pipeline compiled successfully to '{output_path}'")
    return output_path


def submit_pipeline(host, pipeline_path):
    """Submit the pipeline to a Kubeflow instance"""
    try:
        from kfp import client

        print(f"Connecting to Kubeflow at {host}...")
        kfp_client = client.Client(host=host)

        print(f"Submitting pipeline from {pipeline_path}...")
        run = kfp_client.create_run_from_pipeline_package(
            pipeline_file=pipeline_path,
            arguments={},
            run_name="document-ingestion-pipeline-run"
        )

        print(f"✓ Pipeline submitted successfully!")
        print(f"Run ID: {run.run_id}")
        print(f"Run URL: {host}/#/runs/details/{run.run_id}")

    except Exception as e:
        print(f"✗ Failed to submit pipeline: {e}")
        print("\nMake sure you have:")
        print("  1. Kubeflow installed and accessible")
        print("  2. Correct host URL (e.g., http://localhost:8080)")
        print("  3. Proper authentication configured")


def main():
    parser = argparse.ArgumentParser(description="Compile and run Kubeflow pipeline")
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Only compile the pipeline without submitting"
    )
    parser.add_argument(
        "--output",
        default="document_ingestion_pipeline.yaml",
        help="Output path for compiled pipeline (default: document_ingestion_pipeline.yaml)"
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8080",
        help="Kubeflow host URL (default: http://localhost:8080)"
    )

    args = parser.parse_args()

    # Always compile first
    pipeline_path = compile_pipeline(args.output)

    # Submit if not compile-only mode
    if not args.compile_only:
        submit_pipeline(args.host, pipeline_path)
    else:
        print("\nTo submit the pipeline later, run:")
        print(f"  python run_pipeline.py --host <kubeflow-host>")


if __name__ == "__main__":
    main()
