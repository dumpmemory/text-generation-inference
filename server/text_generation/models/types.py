import torch

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from transformers import PreTrainedTokenizerBase

from text_generation.pb import generate_pb2


class Batch(ABC):
    @abstractmethod
    def to_pb(self) -> generate_pb2.Batch:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_pb(
        cls,
        pb: generate_pb2.Batch,
        tokenizer: PreTrainedTokenizerBase,
        device: torch.device,
    ) -> "Batch":
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def concatenate(cls, batches: List["Batch"]) -> "Batch":
        raise NotImplementedError

    @abstractmethod
    def __len__(self):
        raise NotImplementedError


@dataclass
class GeneratedText:
    text: str
    generated_tokens: int
    finish_reason: str
    seed: Optional[int]

    def to_pb(self) -> generate_pb2.GeneratedText:
        return generate_pb2.GeneratedText(
            text=self.text,
            generated_tokens=self.generated_tokens,
            finish_reason=self.finish_reason,
            seed=self.seed,
        )


@dataclass
class PrefillTokens:
    token_ids: List[int]
    logprobs: List[float]
    texts: List[str]

    def to_pb(self) -> generate_pb2.PrefillTokens:
        return generate_pb2.PrefillTokens(
            ids=self.token_ids, logprobs=self.logprobs, texts=self.texts
        )

    def __len__(self):
        return len(self.token_ids)


@dataclass
class Generation:
    request_id: int
    prefill_tokens: Optional[PrefillTokens]
    token_id: int
    token_logprob: float
    token_text: str
    generated_text: Optional[GeneratedText]

    def to_pb(self) -> generate_pb2.Generation:
        return generate_pb2.Generation(
            request_id=self.request_id,
            prefill_tokens=self.prefill_tokens.to_pb()
            if self.prefill_tokens is not None
            else None,
            token_id=self.token_id,
            token_logprob=self.token_logprob,
            token_text=self.token_text,
            generated_text=self.generated_text.to_pb()
            if self.generated_text is not None
            else None,
        )
