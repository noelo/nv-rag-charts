# ENV setup

AWS with OpenShift Open Environment
3 node OCP4 cluster

## RHAIE Setup
https://github.com/redhat-ai-services/ai-accelerator/tree/main 

## GPU Worker Nodes
https://github.com/rh-aiservices-bu/rhoaibu-cluster
./rhoaibu-cluster/bootstrap/machinesets/gpu-machineset.sh

```
### Select the GPU instance type:
1) Tesla T4 Single GPU	  3) A10G Single GPU	   5) A10G Multi GPU x8	    7) H100		     9) L40 Single GPU	     11) L40 Multi GPU x8     13) L40S Multi GPU x4
2) Tesla T4 Multi GPU	  4) A10G Multi GPU x4	   6) A100		    8) DL1		    10) L40 Multi GPU x4     12) L40S Single GPU      14) L40S Multi GPU x8
Please enter your choice: 13
### Is this GPU internal (PRIVATE) or external (SHARED)? [default: SHARED] (Enter p for PRIVATE, anything else for SHARED): 
### Enter the AWS region (default: us-west-2): us-east-2
### Select the availability zone (az1, az2, az3):
1) az1
2) az2
3) az3
Please enter your choice: 1
### Do you want to enable spot instances? (y/n): n
### Creating new machineset worker-gpu-g6e.12xlarge-us-east-2a.
machineset.machine.openshift.io/worker-gpu-g6e.12xlarge-us-east-2a created
--- New machineset worker-gpu-g6e.12xlarge-us-east-2a created.
```

[NOTE] Edit the new machine set and ensure that you have enought storage provisioned.

## Hardware Profile

Create a hardware profile with the correct CPU/GPU & Memory settings.

Use the following node selector _nvidia.com/gpu.present=true_


### Retieve ToolCall parser (optional)
```
curl https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5/resolve/main/llama_nemotron_toolcall_parser_no_streaming.py
```

```
oc create cm tool-call-parser --from-file=llama_nemotron_toolcall_parser_no_streaming.py
```


# Model Serving

## InferenceService

```
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  annotations:
    serving.kserve.io/deploymentMode: RawDeployment
  labels:
    opendatahub.io/dashboard: "true"
  name: nemotron
spec:
  predictor:
    annotations:
      serving.knative.dev/progress-deadline: 30m
    automountServiceAccountToken: false
    maxReplicas: 1
    minReplicas: 1
    model:
      args:
      - --tensor-parallel-size=2
      env:
      - name: HF_TOKEN
        value: hf_************
      modelFormat:
        name: vLLM
      name: ""
      resources:
        limits:
          cpu: "8"
          memory: 8Gi
          nvidia.com/gpu: "2"
        requests:
          cpu: "4"
          memory: 4Gi
          nvidia.com/gpu: "2"
      runtime: nemotron
      storageUri: hf://nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
    tolerations:
    - effect: NoSchedule
      key: nvidia-gpu-only
      operator: Exists
    - effect: NoSchedule
      key: nvidia.com/gpu
      operator: Exists
```

## ServingRuntime

```
apiVersion: serving.kserve.io/v1alpha1
kind: ServingRuntime
metadata:
  labels:
    opendatahub.io/dashboard: "true"
  name: nemotron
spec:
  annotations:
    opendatahub.io/kserve-runtime: vllm
    prometheus.io/path: /metrics
    prometheus.io/port: "8080"
  containers:
  - args:
    - --port=8080
    - --model=/mnt/models
    - --served-model-name={{.Name}}
    command:
    - python
    - -m
    - vllm.entrypoints.openai.api_server
    env:
    - name: HF_HOME
      value: /tmp/hf_home
    image: registry.redhat.io/rhoai/odh-vllm-cuda-rhel9@sha256:5b86924790aeb996a7e3b7f9f4c8a3a676a83cd1d7484ae584101722d362c69b
    name: kserve-container
    ports:
    - containerPort: 8080
      protocol: TCP
    volumeMounts:
    - mountPath: /dev/shm
      name: shm
    - name: config-volume
      mountPath: /etc/llm-parser
  multiModel: false
  supportedModelFormats:
  - autoSelect: true
    name: vLLM
  volumes:
  - emptyDir:
      medium: Memory
      sizeLimit: 2Gi
    name: shm
  - configMap:
      name: tool-call-parser
    name: config-volume
```


[NOTE] Wait for model download

```
nemotron-predictor... storage-initializer 2026-02-12 15:21:04.745 1 kserve INFO [storage.py:download():110] Successfully copied hf://nvidia/Llama-3_3-Nemotron-Super-49B-v1_5 to /mnt/models
nemotron-predictor... storage-initializer 2026-02-12 15:21:04.745 1 kserve INFO [storage.py:download():111] Model downloaded in 738.964122658 seconds.
```

[NOTE] If pod times out set the following annotation on the InferenceService

```
    annotations:
      serving.knative.dev/progress-deadline: 30m
```



apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  annotations:
    serving.kserve.io/deploymentMode: RawDeployment
  labels:
    opendatahub.io/dashboard: "true"
spec:
  predictor:
    annotations:
      serving.knative.dev/progress-deadline: 30m
    automountServiceAccountToken: false
    maxReplicas: 1
    minReplicas: 1
    model:
      args:
      - --tensor-parallel-size=4
      - --trust-remote-code
      - --max-model-len=100000
      - --enable-auto-tool-choice
      - --tool-call-parser
      - llama3_json
      - --async-scheduling
      env:
      - name: HF_TOKEN
        value: hf_************
      modelFormat:
        name: vLLM
      name: ""
      resources:
        limits:
          cpu: "8"
          memory: 16Gi
          nvidia.com/gpu: "4"
        requests:
          cpu: "4"
          memory: 4Gi
          nvidia.com/gpu: "4"
      runtime: nemotron
      storageUri: hf://nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
    tolerations:
    - effect: NoSchedule
      key: nvidia-gpu-only
      operator: Exists
    - effect: NoSchedule
      key: nvidia.com/gpu
      operator: Exists