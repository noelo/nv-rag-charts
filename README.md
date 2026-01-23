oc new-project nvidia-rag

helm --create-namespace nvidia-rag install rag-minio ./minio/

helm install llamastack ./llama-stack-operator-instance --skip-schema-validation

helm template nim-llamastack ./llama-stack-operator-instance/ --dry-run=true

helm install nim-llamastack ./llama-stack-operator-instance/ --skip-schema-validation --set MODEL_API_TOKEN_0="nvapi-"

pip install llama-stack-client==v0.3.5

llama-stack-client inference chat-completion --message "hello, what model are you"

oc adm policy add-scc-to-user anyuid -z nim-rag-nv-ingest

helm install nim-rag ./nvidia-blueprint-rag/ --set ngcApiSecret.password="nvapi-" --set imagePullSecret.password="nvapi-"

Operators

Cluser Observability
Grafana-operator
Open Telemetry

Install collector.yaml

https://github.com/rhoai-genaiops/genaiops-helmcharts/tree/main/charts/grafana/templates


  ##===LLM Model specific configurations===
  APP_LLM_MODELNAME: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
  # URL on which LLM model is hosted. If "", Nvidia hosted API is used
  APP_LLM_SERVERURL: "nim-llm:8000"


    ##===Query Rewriter Model specific configurations===
  APP_QUERYREWRITER_MODELNAME: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
  # URL on which query rewriter model is hosted. If "", Nvidia hosted API is used
  APP_QUERYREWRITER_SERVERURL: "nim-llm:8000"

    ##===Filter Expression Generator Model specific configurations===
  APP_FILTEREXPRESSIONGENERATOR_MODELNAME: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
  # URL on which filter expression generator model is hosted. If "", Nvidia hosted API is used
  APP_FILTEREXPRESSIONGENERATOR_SERVERURL: "nim-llm:8000"

    ##===Embedding Model specific configurations===
  # URL on which embedding model is hosted. If "", Nvidia hosted API is used
  APP_EMBEDDINGS_SERVERURL: "nemoretriever-embedding-ms:8000"
  APP_EMBEDDINGS_MODELNAME: "nvidia/llama-3.2-nv-embedqa-1b-v2"

    ##===Reranking Model specific configurations===
  # URL on which ranking model is hosted. If "", Nvidia hosted API is used
  APP_RANKING_SERVERURL: "nemoretriever-ranking-ms:8000"
  APP_RANKING_MODELNAME: "nvidia/llama-3.2-nv-rerankqa-1b-v2"

  ##===VLM Model specific configurations===
  APP_VLM_SERVERURL: "http://nim-vlm:8000/v1"
  APP_VLM_MODELNAME: "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"

  curl http://rag-server:8081/health?check_dependencies=true



  helm repo nvidia add https://helm.ngc.nvidia.com/nim/nvidia --username='$oauthtoken' --password=nvapi-
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add zipkin https://zipkin.io/zipkin-helm
helm repo add opentelemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo add prometheus https://prometheus-community.github.io/helm-charts
helm repo add nmp https://helm.ngc.nvidia.com/nvidia/nemo-microservices --username='$oauthtoken' --password=nvapi-

