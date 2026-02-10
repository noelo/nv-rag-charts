from kfp import dsl
from kfp import compiler
from kfp import kubernetes


@dsl.component(base_image="registry.redhat.io/ubi10/python-312-minimal")
def make_data():
    with open('/data/file.txt', 'w') as f:
        f.write('my data')

@dsl.component(base_image="registry.redhat.io/ubi10/python-312-minimal")
def read_data():
    with open('/data/file.txt') as f:
        print(f.read())

@dsl.pipeline
def my_pipeline():
    pvc1 = kubernetes.CreatePVC(
        # can also use pvc_name instead of pvc_name_suffix to use a pre-existing PVC
        pvc_name_suffix='-my-pvc',
        access_modes=['ReadWriteOnce'],
        size='5Gi',
        storage_class_name='gp3-csi',
    )

    task1 = make_data()
    # normally task sequencing is handled by data exchange via component inputs/outputs
    # but since data is exchanged via volume, we need to call .after explicitly to sequence tasks
    task2 = read_data().after(task1)

    kubernetes.mount_pvc(
        task1,
        pvc_name=pvc1.outputs['name'],
        mount_path='/data',
    )
    kubernetes.mount_pvc(
        task2,
        pvc_name=pvc1.outputs['name'],
        mount_path='/data',
    )

    # wait to delete the PVC until after task2 completes
    delete_pvc1 = kubernetes.DeletePVC(
        pvc_name=pvc1.outputs['name']).after(task2)

if __name__ == "__main__":
    # Compile the pipeline to YAML
    compiler.Compiler().compile(
        pipeline_func=my_pipeline,
        package_path="my_pipeline.yaml",
    )
    print("Pipeline compiled successfully to 'my_pipeline.yaml'")
