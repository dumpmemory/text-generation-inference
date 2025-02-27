import pytest
import torch

from copy import copy
from transformers import AutoTokenizer

from text_generation.pb import generate_pb2
from text_generation.models.causal_lm import CausalLM, CausalLMBatch


@pytest.fixture(scope="session")
def default_causal_lm():
    return CausalLM("gpt2")


@pytest.fixture(scope="session")
def gpt2_tokenizer():
    tokenizer = AutoTokenizer.from_pretrained("gpt2", padding_side="left")
    tokenizer.pad_token_id = 50256
    return tokenizer


@pytest.fixture
def default_pb_request(default_pb_parameters, default_pb_stop_parameters):
    return generate_pb2.Request(
        id=0,
        inputs="Test",
        input_length=1,
        parameters=default_pb_parameters,
        stopping_parameters=default_pb_stop_parameters,
    )


@pytest.fixture
def default_pb_batch(default_pb_request):
    return generate_pb2.Batch(id=0, requests=[default_pb_request], size=1)


@pytest.fixture
def default_causal_lm_batch(default_pb_batch, gpt2_tokenizer):
    return CausalLMBatch.from_pb(default_pb_batch, gpt2_tokenizer, torch.device("cpu"))


@pytest.fixture
def default_multi_requests_causal_lm_batch(default_pb_request, gpt2_tokenizer):
    req_0 = copy(default_pb_request)
    req_1 = default_pb_request
    req_1.id = 1
    req_1.stopping_parameters.max_new_tokens = 5

    batch_pb = generate_pb2.Batch(id=0, requests=[req_0, req_1], size=2)
    return CausalLMBatch.from_pb(batch_pb, gpt2_tokenizer, torch.device("cpu"))


def test_batch_from_pb(default_pb_batch, default_causal_lm_batch):
    batch = default_causal_lm_batch

    assert batch.batch_id == default_pb_batch.id
    assert batch.requests == default_pb_batch.requests

    assert len(batch.input_ids) == default_pb_batch.size
    assert batch.input_ids[0][-1] == 14402
    assert torch.all(batch.input_ids[0][:-1] == 50256)

    assert batch.attention_mask[0][-1] == 1
    assert torch.all(batch.attention_mask[0][:-1] == 0)

    assert batch.past_key_values is None

    assert torch.equal(batch.input_ids, batch.all_input_ids[:, :, 0])

    assert batch.input_lengths == [1]

    assert batch.size == default_pb_batch.size
    assert len(batch.next_token_choosers) == len(batch.stopping_criterias) == batch.size

    assert batch.max_sequence_length == batch.input_lengths[0]


def test_batch_concatenate_no_prefill(default_causal_lm_batch):
    with pytest.raises(ValueError):
        CausalLMBatch.concatenate([default_causal_lm_batch, default_causal_lm_batch])


def test_causal_lm_batch_type(default_causal_lm):
    assert default_causal_lm.batch_type == CausalLMBatch


def test_causal_lm_generate_token(default_causal_lm, default_causal_lm_batch):
    sequence_length = len(default_causal_lm_batch.all_input_ids[0])
    generations, next_batch = default_causal_lm.generate_token(default_causal_lm_batch)

    assert len(generations) == len(next_batch)
    assert isinstance(next_batch, CausalLMBatch)

    assert len(next_batch.all_input_ids) == next_batch.size
    assert (
        len(next_batch.all_input_ids[0])
        == len(next_batch.attention_mask[0])
        == sequence_length + 1
    )
    assert next_batch.all_input_ids[0][-1] == 13
    assert next_batch.all_input_ids[0][-2] == 14402
    assert torch.all(next_batch.all_input_ids[0][:-2] == 50256)

    assert torch.all(next_batch.attention_mask[0][-2:] == 1)
    assert torch.all(next_batch.attention_mask[0][:-2] == 0)

    assert next_batch.input_ids.shape == (next_batch.size, 1)
    assert next_batch.input_ids[0, 0] == 13

    assert next_batch.input_lengths == [2]
    assert next_batch.max_sequence_length == next_batch.input_lengths[0]

    assert next_batch.past_key_values is not None
    assert all(
        [p[0].shape == (1, 12, sequence_length, 64) for p in next_batch.past_key_values]
    )
    assert all(
        [p[1].shape == (1, 12, sequence_length, 64) for p in next_batch.past_key_values]
    )
    assert all([generation.generated_text is None for generation in generations])
    assert all([len(generation.prefill_tokens) == 1 for generation in generations])
    assert all([generation.token_id.item() == 13 for generation in generations])
    assert all([generation.token_text == "." for generation in generations])
    assert generations[0].request_id == 0


def test_causal_lm_generate_token_completion(
    default_causal_lm, default_causal_lm_batch
):
    next_batch = default_causal_lm_batch
    for _ in range(default_causal_lm_batch.stopping_criterias[0].max_new_tokens - 1):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is None

    assert len(generations) == 1
    assert generations[0].generated_text.text == "Test.java:784) at net.minecraft."
    assert generations[0].request_id == default_causal_lm_batch.requests[0].id
    assert (
        generations[0].generated_text.generated_tokens
        == default_causal_lm_batch.stopping_criterias[0].max_new_tokens
    )


def test_causal_lm_generate_token_completion_multi(
    default_causal_lm, default_multi_requests_causal_lm_batch
):
    next_batch = default_multi_requests_causal_lm_batch

    for i in range(
        default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens - 1
    ):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is not None

    assert len(generations) == 2
    assert generations[1].generated_text.text == "Test.java:784)"
    assert (
        generations[1].request_id
        == default_multi_requests_causal_lm_batch.requests[1].id
    )
    assert (
        generations[1].generated_text.generated_tokens
        == default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens
    )

    for _ in range(
        default_multi_requests_causal_lm_batch.stopping_criterias[0].max_new_tokens
        - default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens
        - 1
    ):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is None

    assert len(generations) == 1
    assert generations[0].generated_text.text == "Test.java:784) at net.minecraft."
    assert (
        generations[0].request_id
        == default_multi_requests_causal_lm_batch.requests[0].id
    )
    assert (
        generations[0].generated_text.generated_tokens
        == default_multi_requests_causal_lm_batch.stopping_criterias[0].max_new_tokens
    )


def test_batch_concatenate(
    default_causal_lm, default_causal_lm_batch, default_multi_requests_causal_lm_batch
):
    next_batch_0 = default_causal_lm_batch
    _, next_batch_0 = default_causal_lm.generate_token(next_batch_0)
    _, next_batch_0 = default_causal_lm.generate_token(next_batch_0)

    next_batch_1 = default_multi_requests_causal_lm_batch
    _, next_batch_1 = default_causal_lm.generate_token(next_batch_1)

    next_batch = CausalLMBatch.concatenate([next_batch_0, next_batch_1])

    assert torch.equal(next_batch.all_input_ids[0], next_batch_0.all_input_ids[0])
    assert torch.equal(next_batch.all_input_ids[1], next_batch_1.all_input_ids[0])
    assert torch.equal(next_batch.all_input_ids[2], next_batch_1.all_input_ids[1])

    assert torch.all(next_batch.attention_mask[0] == 1)
    assert torch.all(next_batch.attention_mask[1:, -2:] == 1)
    assert torch.all(next_batch.attention_mask[1:, :-2] == 0)

    assert next_batch.batch_id == 0
    assert next_batch.input_ids[0, 0] == 12355
    assert torch.all(next_batch.input_ids[1:] == 13)

    assert next_batch.input_lengths == [3, 2, 2]
    assert next_batch.max_sequence_length == 3

    assert next_batch.requests[0] == next_batch_0.requests[0]
    assert next_batch.requests[1:] == next_batch_1.requests

    assert next_batch.next_token_choosers[0] == next_batch_0.next_token_choosers[0]
    assert next_batch.next_token_choosers[1:] == next_batch_1.next_token_choosers

    assert next_batch.stopping_criterias[0] == next_batch_0.stopping_criterias[0]
    assert next_batch.stopping_criterias[1:] == next_batch_1.stopping_criterias

    assert next_batch.past_key_values is not None
    assert all([p[0].shape == (3, 12, 2, 64) for p in next_batch.past_key_values])
    assert all([p[1].shape == (3, 12, 2, 64) for p in next_batch.past_key_values])

    for i, past in enumerate(next_batch.past_key_values):
        assert torch.equal(next_batch_0.past_key_values[i][0][0, :, -2:], past[0][0])
        assert torch.equal(
            next_batch_1.past_key_values[i][0][:, :, -1:], past[0][1:, :, -1:, :]
        )

        assert torch.equal(next_batch_0.past_key_values[i][1][0, :, -2:], past[1][0])
        assert torch.equal(
            next_batch_1.past_key_values[i][1][:, :, -1:], past[1][1:, :, -1:, :]
        )

    for _ in range(
        default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens - 2
    ):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is not None

    assert len(generations) == 3
    assert generations[2].generated_text.text == "Test.java:784)"
    assert (
        generations[2].request_id
        == default_multi_requests_causal_lm_batch.requests[1].id
    )
    assert (
        generations[2].generated_text.generated_tokens
        == default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens
    )

    for _ in range(
        default_causal_lm_batch.stopping_criterias[0].max_new_tokens
        - default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens
        - 2
    ):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is not None

    assert len(generations) == 2
    assert generations[0].generated_text.text == "Test.java:784) at net.minecraft."
    assert generations[0].request_id == default_causal_lm_batch.requests[0].id
    assert (
        generations[0].generated_text.generated_tokens
        == default_causal_lm_batch.stopping_criterias[0].max_new_tokens
    )

    for _ in range(
        default_multi_requests_causal_lm_batch.stopping_criterias[0].max_new_tokens
        - default_causal_lm_batch.stopping_criterias[0].max_new_tokens
        - default_multi_requests_causal_lm_batch.stopping_criterias[1].max_new_tokens
        - 4
    ):
        generations, next_batch = default_causal_lm.generate_token(next_batch)
        assert len(generations) == len(next_batch)

    generations, next_batch = default_causal_lm.generate_token(next_batch)
    assert next_batch is None

    assert len(generations) == 1
    assert generations[0].generated_text.text == "Test.java:784) at net.minecraft."
    assert (
        generations[0].request_id
        == default_multi_requests_causal_lm_batch.requests[0].id
    )
    assert (
        generations[0].generated_text.generated_tokens
        == default_multi_requests_causal_lm_batch.stopping_criterias[0].max_new_tokens
    )
