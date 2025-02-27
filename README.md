# Text Generation Inference

<div align="center">

![architecture](assets/architecture.jpg)

</div>

A Rust and gRPC server for text generation inference. Used in production at [HuggingFace](https://huggingface.co) 
to power Bloom, BloomZ and MT0-XXL api-inference widgets.

## Features

- [Dynamic batching of incoming requests](https://github.com/huggingface/text-generation-inference/blob/main/router/src/batcher.rs#L88) for increased total throughput
- Quantization with [bitsandbytes](https://github.com/TimDettmers/bitsandbytes)
- [Safetensors](https://github.com/huggingface/safetensors) weight loading
- 45ms per token generation for BLOOM with 8xA100 80GB
- Logits warpers (temperature scaling, topk ...)
- Stop sequences
- Log probabilities

## Officially supported models

- [BLOOM](https://huggingface.co/bigscience/bloom)
- [BLOOMZ](https://huggingface.co/bigscience/bloomz)
- [MT0-XXL](https://huggingface.co/bigscience/mt0-xxl)
- ~~[Galactica](https://huggingface.co/facebook/galactica-120b)~~ (deactivated)
- [SantaCoder](https://huggingface.co/bigcode/santacoder)
- [GPT-Neox 20B](https://huggingface.co/EleutherAI/gpt-neox-20b): use `--revision refs/pr/13`

Other models are supported on a best effort basis using:

`AutoModelForCausalLM.from_pretrained(<model>, device_map="auto")`

or

`AutoModelForSeq2SeqLM.from_pretrained(<model>, device_map="auto")`

## Load Tests for BLOOM

See `k6/load_test.js`

|                                                              | avg       | min          | med       | max        | p(90)     | p(95)     | RPS      |
|--------------------------------------------------------------|-----------|--------------|-----------|------------|-----------|-----------|----------|
| [Original code](https://github.com/huggingface/transformers_bloom_parallel) | 8.9s      | 1s           | 9.12s     | 16.69s     | 13.7s     | 14.26s    | 5.9      |
| New batching logic                                           | **5.44s** | **959.53ms** | **5.28s** | **13.12s** | **7.78s** | **8.92s** | **9.08** |

## Install

```shell
make install
```

## Run 

### BLOOM 560-m

```shell
make run-bloom-560m
```

### BLOOM

First you need to download the weights:

```shell
make download-bloom
```

```shell
make run-bloom # Requires 8xA100 80GB
```

You can also quantize the weights with bitsandbytes to reduce the VRAM requirement:

```shell
make run-bloom-quantize # Requires 8xA100 40GB
```

## Test

```shell
curl 127.0.0.1:3000/generate \
    -v \
    -X POST \
    -d '{"inputs":"Testing API","parameters":{"max_new_tokens":9}}' \
    -H 'Content-Type: application/json'
```

## Develop

```shell
make server-dev
make router-dev
```