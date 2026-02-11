```
helm repo add zilliztech https://zilliztech.github.io/milvus-helm/
helm repo update

oc new-project milvus

oc adm policy add-scc-to-user anyuid -z default 
helm upgrade --install my-release --set cluster.enabled=false --set etcd.replicaCount=1 --set pulsarv3.enabled=false --set minio.mode=standalone    zilliztech/milvus

kubectl port-forward service/my-release-milvus 27017:19530

oc expose svc my-release-milvus --port 19530 --name milvus-api
```

route is listening on /webui/
