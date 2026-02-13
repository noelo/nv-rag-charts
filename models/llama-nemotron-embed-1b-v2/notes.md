# vLLM Usage (from Nvidias notes)

[NOTE] the config.json isn't replaced but it's contents are overwritten using the overrides below 

```
--hf-overrides
      - '{"architectures":"LlamaModel","is_causal": "false","model_type":"llama"}'

```

* Ensure you are using vllm==0.11.0.
* Clone this model's repository.
* Overwrite config.json with config_vllm.json.
* Start the vLLM server with the following command (replace the <path_to_the_cloned_repository> and <num_gpus_to_use> with your values):

```
vllm serve \
    <path_to_the_cloned_repository> \
    --trust-remote-code \
    --runner pooling \
    --model-impl vllm \
    --override-pooler-config '{\"pooling_type\": \"MEAN\"}' \
    --data-parallel-size <num_gpus_to_use> \
    --dtype float32

```