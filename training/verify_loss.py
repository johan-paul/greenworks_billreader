"""Check optimized response loss against Transformers' standard masked loss."""

import torch
from transformers import Qwen2Config, Qwen2ForCausalLM
from training.train_lora import response_loss

torch.manual_seed(42)
model = Qwen2ForCausalLM(
    Qwen2Config(
        vocab_size=32,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=2,
        num_key_value_heads=2,
    )
).eval()
example = {"input_ids": [1, 2, 3, 4, 5, 6], "labels": [-100, -100, -100, 4, 5, 6]}
expected = model(
    input_ids=torch.tensor([example["input_ids"]]),
    labels=torch.tensor([example["labels"]]),
).loss
actual = response_loss(model, example)
assert torch.allclose(expected, actual, atol=1e-6), (expected.item(), actual.item())
actual.backward()
assert any(
    p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()
)
print("Response-only loss matches standard masked causal loss; gradients are finite.")
