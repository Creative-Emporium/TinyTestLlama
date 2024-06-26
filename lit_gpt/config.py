# Copyright Lightning AI. Licensed under the Apache License 2.0, see LICENSE file.

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Type, Union

import torch
import yaml
from typing_extensions import Self

import litgpt.model
from litgpt.utils import find_multiple


@dataclass
class Config:
    org: str = "Lightning-AI"
    name: str = "lit-GPT"
    block_size: int = 4096
    vocab_size: int = 50254
    padding_multiple: int = 512
    padded_vocab_size: Optional[int] = None
    n_layer: int = 16
    n_head: int = 32
    n_embd: int = 4096
    rotary_percentage: float = 0.25
    parallel_residual: bool = True
    bias: bool = True
    # to use multi-head attention (MHA), set this to `n_head` (default)
    # to use multi-query attention (MQA), set this to 1
    # to use grouped-query attention (GQA), set this to a value in between
    # Example with `n_head=4`
    # ┌───┐┌───┐┌───┐┌───┐     ┌───┐    ┌───┐             ┌───┐
    # │ v ││ v ││ v ││ v │     │ v │    │ v │             │ v │
    # └───┘└───┘└───┘└───┘     └───┘    └───┘             └───┘
    #   │    │    │    │         │        │                 │
    # ┌───┐┌───┐┌───┐┌───┐     ┌───┐    ┌───┐             ┌───┐
    # │ k ││ k ││ k ││ k │     │ k │    │ k │             │ k │
    # └───┘└───┘└───┘└───┘     └───┘    └───┘             └───┘
    #   │    │    │    │      ┌──┴──┐  ┌──┴──┐      ┌────┬──┴─┬────┐
    # ┌───┐┌───┐┌───┐┌───┐  ┌───┐┌───┐┌───┐┌───┐  ┌───┐┌───┐┌───┐┌───┐
    # │ q ││ q ││ q ││ q │  │ q ││ q ││ q ││ q │  │ q ││ q ││ q ││ q │
    # └───┘└───┘└───┘└───┘  └───┘└───┘└───┘└───┘  └───┘└───┘└───┘└───┘
    # ◀──────────────────▶  ◀──────────────────▶  ◀──────────────────▶
    #         MHA                    GQA                   MQA
    #   n_query_groups=4       n_query_groups=2      n_query_groups=1
    #
    # credit https://arxiv.org/pdf/2305.13245.pdf
    n_query_groups: Optional[int] = None
    shared_attention_norm: bool = False
    _norm_class: Literal["LayerNorm", "RMSNorm"] = "LayerNorm"
    norm_eps: float = 1e-5
    _mlp_class: Literal["GptNeoxMLP", "LLaMAMLP"] = "GptNeoxMLP"
    intermediate_size: Optional[int] = None
    condense_ratio: int = 1

    def __post_init__(self):
        # error checking
        assert self.n_embd % self.n_head == 0
        # vocab size should be a power of 2 to be optimal on hardware. compute the closest value
        if self.padded_vocab_size is None:
            self.padded_vocab_size = find_multiple(self.vocab_size, self.padding_multiple)
        # compute the number of query groups
        if self.n_query_groups is not None:
            assert self.n_head % self.n_query_groups == 0
        else:
            self.n_query_groups = self.n_head
        # compute the intermediate size for MLP if not set
        if self.intermediate_size is None:
            if self._mlp_class == "LLaMAMLP":
                raise ValueError("The config needs to set the `intermediate_size`")
            self.intermediate_size = 4 * self.n_embd

    @property
    def head_size(self) -> int:
        return self.n_embd // self.n_head

    @classmethod
    def from_name(cls, name: str, **kwargs: Any) -> Self:
        conf_dict = name_to_config[name].copy()
        conf_dict.update(kwargs)
        return cls(**conf_dict)

    @property
    def mlp_class(self) -> Type:
        # `self._mlp_class` cannot be the type to keep the config json serializable
        return getattr(lit_gpt.model, self._mlp_class)

    @property
    def norm_class(self) -> Type:
        # `self._norm_class` cannot be the type to keep the config json serializable
        if self._norm_class == "RMSNorm":
            from lit_gpt.rmsnorm import RMSNorm

            return RMSNorm
        elif self._norm_class == "FusedRMSNorm":
            from lit_gpt.rmsnorm import FusedRMSNorm
            return FusedRMSNorm
        return getattr(torch.nn, self._norm_class)


########################
# Stability AI StableLM
########################
configs = [
    # https://huggingface.co/stabilityai/stablelm-base-alpha-3b/blob/main/config.json
    dict(org="stabilityai", name="stablelm-base-alpha-3b", padding_multiple=512),
    # https://huggingface.co/stabilityai/stablelm-base-alpha-7b/blob/main/config.json
    dict(org="stabilityai", name="stablelm-base-alpha-7b", n_head=48, n_embd=6144, padding_multiple=256),
    # https://huggingface.co/stabilityai/stablelm-tuned-alpha-3b/blob/main/config.json
    dict(org="stabilityai", name="stablelm-tuned-alpha-3b", n_head=32, padding_multiple=512),
    # https://huggingface.co/stabilityai/stablelm-tuned-alpha-7b/blob/main/config.json
    dict(org="stabilityai", name="stablelm-tuned-alpha-7b", n_head=48, n_embd=6144, padding_multiple=256),
]

##########################
# Stability AI StableCode
##########################
stablecode = [
    # https://huggingface.co/stabilityai/stablecode-completion-alpha-3b/blob/main/config.json
    dict(
        name="stablecode-completion-alpha-3b",
        hf_config=dict(org="stabilityai", name="stablecode-completion-alpha-3b"),
        block_size=16384,
        vocab_size=49152,
        n_layer=32,
        n_embd=2560,
    ),
    # https://huggingface.co/stabilityai/stablecode-completion-alpha-3b-4k/blob/main/config.json
    dict(
        name="stablecode-completion-alpha-3b-4k",
        hf_config=dict(org="stabilityai", name="stablecode-completion-alpha-3b-4k"),
        vocab_size=49152,
        n_layer=32,
        n_embd=2560,
    ),
    # https://huggingface.co/stabilityai/stablecode-instruct-alpha-3b/blob/main/config.json
    dict(
        name="stablecode-instruct-alpha-3b",
        hf_config=dict(org="stabilityai", name="stablecode-instruct-alpha-3b"),
        vocab_size=49152,
        n_layer=32,
        n_embd=2560,
    ),
]
configs.extend(stablecode)

####################
# EleutherAI Pythia
####################
pythia = [
    
    #https://huggingface.co/EleutherAI/pythia-14m/blob/main/config.json
    dict(org="EleutherAI", name="pythia-14m", block_size=512, n_layer=6, n_embd=128, n_head=4, padding_multiple=128),
    #https://huggingface.co/EleutherAI/pythia-31m/blob/main/config.json
    dict(org="EleutherAI", name="pythia-31m", block_size=1024, n_layer=6, n_embd=256, n_head=8, padding_multiple=128),
    # https://huggingface.co/EleutherAI/pythia-70m/blob/main/config.json
    dict(org="EleutherAI", name="pythia-70m", block_size=2048, n_layer=6, n_embd=512, n_head=8, padding_multiple=128),
    # https://huggingface.co/EleutherAI/pythia-160m/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-160m", block_size=2048, n_layer=12, n_embd=768, n_head=12, padding_multiple=128
    ),
    # https://huggingface.co/EleutherAI/pythia-410m/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-410m", block_size=2048, n_layer=24, n_embd=1024, n_head=16, padding_multiple=128
    ),
    # https://huggingface.co/EleutherAI/pythia-1b/blob/main/config.json
    dict(org="EleutherAI", name="pythia-1b", block_size=2048, n_layer=16, n_embd=2048, n_head=8, padding_multiple=128),
    # https://huggingface.co/EleutherAI/pythia-1.4b/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-1.4b", block_size=2048, n_layer=24, n_embd=2048, n_head=16, padding_multiple=128
    ),
    # https://huggingface.co/EleutherAI/pythia-2.8b/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-2.8b", block_size=2048, n_layer=32, n_embd=2560, n_head=32, padding_multiple=128
    ),
    # https://huggingface.co/EleutherAI/pythia-6.9b/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-6.9b", block_size=2048, n_layer=32, n_embd=4096, n_head=32, padding_multiple=256
    ),
    # https://huggingface.co/EleutherAI/pythia-12b/blob/main/config.json
    dict(
        org="EleutherAI", name="pythia-12b", block_size=2048, n_layer=36, n_embd=5120, n_head=40, padding_multiple=512
    ),
]
configs.extend(pythia)
for c in pythia:
    copy = c.copy()
    copy["name"] = f"{c['name']}-deduped"
    configs.append(copy)

####################################
# togethercomputer RedPajama INCITE
####################################
redpajama_incite = [
    # https://huggingface.co/togethercomputer/RedPajama-INCITE-Base-3B-v1/blob/main/config.json
    dict(
        org="togethercomputer",
        name="RedPajama-INCITE-{}-3B-v1",
        block_size=2048,
        n_layer=32,
        n_embd=2560,
        n_head=32,
        padding_multiple=256,
        rotary_percentage=1.0,
        parallel_residual=False,
    ),
    # https://huggingface.co/togethercomputer/RedPajama-INCITE-7B-Base/blob/main/config.json
    dict(
        org="togethercomputer",
        name="RedPajama-INCITE-7B-{}",
        block_size=2048,
        n_layer=32,
        n_embd=4096,
        n_head=32,
        padding_multiple=256,
        rotary_percentage=1.0,
        parallel_residual=False,
    ),
    # this redirects to the checkpoint above. kept for those who had the old weights already downloaded
    dict(
        org="togethercomputer",
        name="RedPajama-INCITE-{}-7B-v0.1",
        block_size=2048,
        n_layer=32,
        n_embd=4096,
        n_head=32,
        padding_multiple=256,
        rotary_percentage=1.0,
        parallel_residual=False,
    ),
]
for c in redpajama_incite:
    for kind in ("Base", "Chat", "Instruct"):
        copy = c.copy()
        copy["name"] = c["name"].format(kind)
        configs.append(copy)

##################################
# togethercomputer LLaMA-2-7B-32K
##################################
together_llama2_32k = [
    # https://huggingface.co/togethercomputer/LLaMA-2-7B-32K/blob/main/config.json
    dict(
        name="LLaMA-2-7B-32K",
        hf_config=dict(org="togethercomputer", name="LLaMA-2-7B-32K"),
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
        rope_condense_ratio=8,
    )
]
configs.extend(together_llama2_32k)

#################
# TII UAE Falcon
#################
falcon = [
    # https://huggingface.co/tiiuae/falcon-7b/blob/main/config.json
    dict(
        org="tiiuae",
        name="falcon-7b{}",
        block_size=2048,
        padded_vocab_size=65024,
        n_layer=32,
        n_head=71,
        n_embd=4544,
        rotary_percentage=1.0,
        parallel_residual=True,
        n_query_groups=1,
        bias=False,
        # this is not in the config, but in the original model implementation, only for this config
        shared_attention_norm=True,
    ),
    # https://huggingface.co/tiiuae/falcon-40b/blob/main/config.json
    dict(
        org="tiiuae",
        name="falcon-40b{}",
        block_size=2048,
        padded_vocab_size=65024,
        n_layer=60,
        n_head=128,
        n_embd=8192,
        rotary_percentage=1.0,
        parallel_residual=True,
        n_query_groups=8,
        bias=False,
    ),
]
for c in falcon:
    for kind in ("", "-instruct"):
        copy = c.copy()
        copy["name"] = c["name"].format(kind)
        configs.append(copy)


#############################
# StatNLP Research
#############################
tiny_LLaMA = [
     
    # https://twitter.com/cwolferesearch/status/1691929174175264858
    dict(
        org="StatNLP-research",
        name="tiny_LLaMA_1b",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    ),
    dict(
        org="StatNLP-research",
        name="tiny_LLaMA_120M",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=12,
        n_head=12,
        n_embd=768,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    ),
    dict(
        org="StatNLP-research",
        name="code_tiny_LLaMA_1b",
        block_size=8192,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
        condense_ratio= 4
    ),
]
configs.extend(tiny_LLaMA)

#############################
# OpenCSG Algo Team
#############################
csg = [
    # https://huggingface.co/opencsg
    dict(
        org="OpenCSG",
        name="csg-wukong-1B",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    ),
    
    dict(
        org="OpenCSG",
        name="csg-wukong-1B-deepseek",
        block_size=2048,
        vocab_size=102400,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    ),
    
    dict(
        org="OpenCSG",
        name="csg-wukong-1B-qwew",
        block_size=2048,
        vocab_size=151936,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    ),
    
    dict(
        org="OpenCSG",
        name="csg-wukong-1B-yi",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5, #Llama 2 use 1e-5. Llama 1 use 1e-6
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    ),

    dict(
        org="OpenCSG",
        name="csg_tiny_120M",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=12,
        n_head=12,
        n_embd=768,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    ),
    
    dict(
        org="OpenCSG",
        name="csg_tiny_120M-v2",
        block_size=2048,
        vocab_size=102400,
        padding_multiple=64,
        n_layer=12,
        n_head=12,
        n_embd=768,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    ),
    
    dict(
        org="OpenCSG",
        name="csg_tiny_120M-v3",
        block_size=2048,
        vocab_size=151936,
        padding_multiple=64,
        n_layer=12,
        n_head=12,
        n_embd=768,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    ),
    dict(
        org="OpenCSG",
        name="csg_tiny_120M-v4",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=12,
        n_head=12,
        n_embd=768,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    ),

    dict(
        org="OpenCSG",
        name="csg_tiny_10M_llama",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=6,
        n_head=4,
        n_embd=128,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=768,
        n_query_groups=1,
    ),
    
    
    dict(
        org="OpenCSG",
        name="csg_tiny_10M_yi",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=6,
        n_head=4,
        n_embd=72,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=576,
        n_query_groups=1,
    ),

    dict(
        org="OpenCSG",
        name="csg_tiny_30M_yi",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=6,
        n_head=4,
        n_embd=200,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=1048,
        n_query_groups=1,
    ),
    
    dict(
        org="OpenCSG",
        name="csg_tiny_70M_yi",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=8,
        n_head=6,
        n_embd=512,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=1536,
        n_query_groups=1,
    ),
        
    dict(
        org="OpenCSG",
        name="csg_tiny_88M_yi",
        block_size=2048,
        vocab_size=64000,
        padding_multiple=64,
        n_layer=6,
        n_head=4,
        n_embd=512,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=2048,
        n_query_groups=1,
    )
    
]
configs.extend(csg)

#############################
# OpenLM Research Open LLaMA
#############################
open_LLaMA = [
    # https://huggingface.co/openlm-research/open_llama_3b/blob/main/config.json
    dict(
        org="openlm-research",
        name="open_llama_3b",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=26,
        n_head=32,
        n_embd=3200,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=8640,
    ),
    # https://huggingface.co/openlm-research/open_llama_7b/blob/main/config.json
    dict(
        org="openlm-research",
        name="open_llama_7b",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    # https://huggingface.co/openlm-research/open_llama_13b/blob/main/config.json
    dict(
        org="openlm-research",
        name="open_llama_13b",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
]
configs.extend(open_LLaMA)


###############
# LMSYS Vicuna
###############
vicuna = [
    # https://huggingface.co/lmsys/vicuna-7b-v1.3/blob/main/config.json
    dict(
        org="lmsys",
        name="vicuna-7b-v1.3",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    # https://huggingface.co/lmsys/vicuna-13b-v1.3/blob/main/config.json
    dict(
        org="lmsys",
        name="vicuna-13b-v1.3",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    # https://huggingface.co/lmsys/vicuna-33b-v1.3/blob/main/config.json
    dict(
        org="lmsys",
        name="vicuna-33b-v1.3",
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=60,
        n_head=52,
        n_embd=6656,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=17920,
    ),
    dict(
        org="lmsys",
        name="vicuna-7b-v1.5",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    dict(
        org="lmsys",
        name="vicuna-7b-v1.5-16k",
        block_size=16384,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
        condense_ratio=4,
    ),
    dict(
        org="lmsys",
        name="vicuna-13b-v1.5",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    dict(
        org="lmsys",
        name="vicuna-13b-v1.5-16k",
        block_size=16384,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
        condense_ratio=4,
    ),
]
configs.extend(vicuna)


#################
# LMSYS LongChat
#################
long_chat = [
    # https://huggingface.co/lmsys/longchat-7b-16k/blob/main/config.json
    dict(
        org="lmsys",
        name="longchat-7b-16k",
        block_size=16384,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
        condense_ratio=8,
    ),
    # https://huggingface.co/lmsys/longchat-13b-16k/blob/main/config.json
    dict(
        org="lmsys",
        name="longchat-13b-16k",
        block_size=16384,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
        condense_ratio=8,
    ),
]
configs.extend(long_chat)


######################
# NousResearch Hermes
######################
nous_research = [
    # https://huggingface.co/NousResearch/Nous-Hermes-13B/blob/main/config.json
    dict(
        org="NousResearch",
        name="Nous-Hermes-13b",
        block_size=2048,
        padded_vocab_size=32001,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-6,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    )
]
configs.extend(nous_research)


###############
# Meta LLaMA 2
###############
llama_2 = [
    # https://huggingface.co/meta-llama/Llama-2-7b-hf/blob/main/config.json
    dict(
        org="meta-llama",
        name="Llama-2-7b{}-hf",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    dict(
        org="meta-llama",
        name="CodeLlama-2-7b-hf",
        block_size=4096,
        vocab_size=32016,
        padded_vocab_size=32016,
        padding_multiple=64,
        n_layer=32,
        n_head=32,
        n_embd=4096,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    # https://huggingface.co/meta-llama/Llama-2-13b-hf/blob/main/config.json
    dict(
        org="meta-llama",
        name="Llama-2-13b{}-hf",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    # https://huggingface.co/meta-llama/Llama-2-70b-hf/blob/main/config.json
    dict(
        org="meta-llama",
        name="Llama-2-70b{}-hf",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=28672,
    ),
]
for c in llama_2:
    for kind in ("", "-chat"):
        copy = c.copy()
        copy["name"] = c["name"].format(kind)
        configs.append(copy)

###############
# Meta LLaMA 3
###############
llama_3 = [
    # https://huggingface.co/meta-llama/Meta-Llama-3-8B/blob/main/config.json
    dict(
        name="Llama-3-8B{}",
        hf_config=dict(org="meta-llama", name="Meta-Llama-3-8B{}"),
        block_size=8192,
        vocab_size=128000,
        padded_vocab_size=128256,
        n_layer=32,
        n_head=32,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        norm_class_name="RMSNorm",
        mlp_class_name="LLaMAMLP",
        intermediate_size=14336,
        rope_base=500000,
    ),
    # https://huggingface.co/meta-llama/Meta-Llama-3-70B/blob/main/config.json
    dict(
        name="Llama-3-70B{}",
        hf_config=dict(org="meta-llama", name="Meta-Llama-3-70B{}"),
        block_size=8192,
        vocab_size=128000,
        padded_vocab_size=128256,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        norm_class_name="RMSNorm",
        mlp_class_name="LLaMAMLP",
        intermediate_size=28672,
        rope_base=500000,
    ),
]
for c in llama_3:
    for kind in ("", "-Instruct"):
        copy = deepcopy(c)
        copy["name"] = c["name"].format(kind)
        copy["hf_config"]["name"] = c["hf_config"]["name"].format(kind)
        configs.append(copy)


###############
# Google Gemma
###############
gemma = [
    # https://huggingface.co/google/gemma-2b/blob/main/config.json
    dict(
        name="Gemma-2b",
        hf_config=dict(org="google", name="gemma-2b"),
        scale_embeddings=True,
        vocab_size=256000,
        padding_multiple=64,
        n_embd=2048,
        n_layer=18,
        n_head=8,
        n_query_groups=1,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        norm_class_name="RMSNorm",
        mlp_class_name="GemmaMLP",
        gelu_approximate="tanh",
        intermediate_size=16384,
    ),
    # https://huggingface.co/google/gemma-7b/blob/main/config.json
    dict(
        name="Gemma-7b",
        hf_config=dict(org="google", name="gemma-7b"),
        scale_embeddings=True,
        vocab_size=256000,
        padding_multiple=64,
        n_embd=3072,
        n_layer=28,
        n_head=16,
        head_size=256,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        norm_class_name="RMSNorm",
        mlp_class_name="GemmaMLP",
        gelu_approximate="tanh",
        intermediate_size=24576,
    ),
]
configs.extend(gemma)
for c in gemma:
    copy = deepcopy(c)
    copy["name"] = f"{c['name']}-it"
    copy["hf_config"]["name"] = f"{c['hf_config']['name']}-it"
    configs.append(copy)

##################
# Google CodeGemma
##################
codegemma = [
    # https://huggingface.co/google/codegemma-7b-it/blob/main/config.json
    dict(
        name="CodeGemma-7b-it",
        hf_config=dict(org="google", name="codegemma-7b-it"),
        scale_embeddings=True,
        vocab_size=256000,
        padding_multiple=64,
        n_embd=3072,
        n_layer=28,
        n_head=16,
        head_size=256,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        norm_class_name="RMSNorm",
        mlp_class_name="GemmaMLP",
        gelu_approximate="tanh",
        intermediate_size=24576,
    ),
]
configs.extend(codegemma)
        
##########################
# Stability AI FreeWilly2
##########################
freewilly_2 = [
    # https://huggingface.co/stabilityai/FreeWilly2/blob/main/config.json
    dict(
        org="stabilityai",
        name="FreeWilly2",
        block_size=4096,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=28672,
    )
]
configs.extend(freewilly_2)

################
# Microsoft Phi
################
phi = [
    # https://huggingface.co/microsoft/phi-1_5/blob/main/config.json
    dict(
        name="phi-1_5",
        hf_config=dict(org="microsoft", name="phi-1_5"),
        vocab_size=50257,
        padded_vocab_size=51200,
        block_size=2048,
        n_embd=2048,
        n_layer=24,
        rotary_percentage=0.5,  # 32 / (n_embd / n_head) = 32 / 64
        shared_attention_norm=True,
        lm_head_bias=True,
        gelu_approximate="tanh",
    ),
    # https://huggingface.co/microsoft/phi-2/blob/main/config.json
    dict(
        name="phi-2",
        hf_config=dict(org="microsoft", name="phi-2"),
        vocab_size=50257,
        padded_vocab_size=51200,
        block_size=2048,
        n_embd=2560,
        n_layer=32,
        rotary_percentage=0.4,  # 32 / (n_embd / n_head) = 32 / 80
        shared_attention_norm=True,
        lm_head_bias=True,
        gelu_approximate="tanh",
    ),
]
configs.extend(phi)

#############
# Mistral AI
#############
mistral = [
    # https://huggingface.co/mistralai/Mistral-7B-v0.1/blob/main/config.json
    dict(
        name="Mistral-7B-{}v0.1",
        hf_config=dict(org="mistralai", name="Mistral-7B-{}v0.1"),
        padded_vocab_size=32000,
        block_size=4096,  # should be 32768 but sliding window attention is not implemented
        n_layer=32,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-05,
        _mlp_class="LLaMAMLP",
        intermediate_size=14336,
    ),
    # https://huggingface.co/mistralai/Mixtral-8x7B-v0.1/blob/main/config.json
    dict(
        name="Mixtral-8x7B-{}v0.1",
        hf_config=dict(org="mistralai", name="Mixtral-8x7B-{}v0.1"),
        padded_vocab_size=32000,
        block_size=4096,  # should be 32768 but sliding window attention is not implemented
        n_layer=32,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-05,
        _mlp_class="LLaMAMoE",
        intermediate_size=14336,
        rope_base=1000000,
        n_expert=8,
        n_expert_per_token=2,
    ),
]
for c in mistral:
    for kind in ("", "Instruct-"):
        copy = deepcopy(c)
        copy["name"] = c["name"].format(kind)
        copy["hf_config"]["name"] = c["hf_config"]["name"].format(kind)
        configs.append(copy)

########################
# garage-bAInd Platypus
########################
platypus = [
    # https://huggingface.co/garage-bAInd/Platypus-30B/blob/main/config.json
    dict(
        name="Platypus-30B",
        hf_config=dict(org="garage-bAInd", name="Platypus-30B"),
        block_size=2048,
        padded_vocab_size=32000,
        n_layer=60,
        n_head=52,
        n_embd=6656,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-06,
        _mlp_class="LLaMAMLP",
        intermediate_size=17920,
    ),
    # https://huggingface.co/garage-bAInd/Platypus2-7B/blob/main/config.json
    dict(
        name="Platypus2-7B",
        hf_config=dict(org="garage-bAInd", name="Platypus2-7B"),
        padded_vocab_size=32000,
        n_layer=32,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-05,
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
    ),
    # https://huggingface.co/garage-bAInd/Platypus2-13B/blob/main/config.json
    dict(
        name="Platypus2-13B",
        hf_config=dict(org="garage-bAInd", name="Platypus2-13B"),
        padded_vocab_size=32000,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        norm_eps=1e-05,
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    # https://huggingface.co/garage-bAInd/Platypus2-70B/blob/main/config.json
    dict(
        name="Platypus2-70B",
        hf_config=dict(org="garage-bAInd", name="Platypus2-70B"),
        padded_vocab_size=32000,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=28672,
    ),
    # https://huggingface.co/garage-bAInd/Camel-Platypus2-13B/blob/main/config.json
    dict(
        name="Camel-Platypus2-13B",
        hf_config=dict(org="garage-bAInd", name="Camel-Platypus2-13B"),
        padded_vocab_size=32000,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    # https://huggingface.co/garage-bAInd/Camel-Platypus2-70B/blob/main/config.json
    dict(
        name="Camel-Platypus2-70B",
        hf_config=dict(org="garage-bAInd", name="Camel-Platypus2-70B"),
        padded_vocab_size=32000,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=28672,
    ),
    # https://huggingface.co/garage-bAInd/Stable-Platypus2-13B/blob/main/config.json
    dict(
        name="Stable-Platypus2-13B",
        hf_config=dict(org="garage-bAInd", name="Stable-Platypus2-13B"),
        padded_vocab_size=32000,
        n_layer=40,
        n_head=40,
        n_embd=5120,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=13824,
    ),
    # https://huggingface.co/garage-bAInd/Platypus2-70B-instruct/blob/main/config.json
    dict(
        name="Platypus2-70B-instruct",
        hf_config=dict(org="garage-bAInd", name="Platypus2-70B-instruct"),
        padded_vocab_size=32000,
        n_layer=80,
        n_head=64,
        n_embd=8192,
        n_query_groups=8,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=28672,
    ),
]
configs.extend(platypus)

############
# TinyLlama
############
tiny_llama = [
    dict(
        name="tiny-llama-1.1b{}",
        hf_config=dict(org="TinyLlama", name="TinyLlama-1.1B{}"),
        block_size=2048,
        vocab_size=32000,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",  # original TinyLlama uses FusedRMSNorm
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
    )
]
for c in tiny_llama:
    for kind, hf_postfix in (("", "-intermediate-step-955k-token-2T"), ("chat", "-Chat-v0.6")):
        copy = deepcopy(c)
        copy["name"] = c["name"].format(kind)
        copy["hf_config"]["name"] = c["hf_config"]["name"].format(hf_postfix)
        configs.append(copy)

##########################
# Trelis Function Calling
##########################
llama_2_function_calling = [
    # https://huggingface.co/Trelis/Llama-2-7b-chat-hf-function-calling-v2/blob/main/config.json
    dict(
        name="Llama-2-7b-chat-hf-function-calling-v2",
        hf_config=dict(org="Trelis", name="Llama-2-7b-chat-hf-function-calling-v2"),
        padding_multiple=64,
        n_layer=32,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        _norm_class="RMSNorm",
        _mlp_class="LLaMAMLP",
        intermediate_size=11008,
        norm_eps=1e-6,
        block_size=4096,
        vocab_size=32000,
        n_head=32,
        n_embd=4096,
        rope_base=10000,
    )
]

configs.extend(llama_2_function_calling)

#############################
# TinyLlama3--Test
#############################
TinyLLama_3 = [
     
    # Test Case for new Tinyllama_3 implementation not yet correct but a placeholder
    dict(
        org="creative_EE",
        name="TinyLlama3",
        block_size=2048,
        vocab_size=128000,
        padded_vocab_size=128256,
        padding_multiple=64,
        n_layer=22,
        n_head=32,
        n_embd=2048,
        rotary_percentage=1.0,
        parallel_residual=False,
        bias=False,
        ffn_dim_multiplier=1.3,
        _norm_class="FusedRMSNorm",
        norm_eps=1e-5,
        _mlp_class="LLaMAMLP",
        intermediate_size=5632,
        n_query_groups=4,
        condense_ratio=4,
        rope_base=50000,        
        rope_condense_ratio=4,        
    ),
]
configs.extend(TinyLLama_3)

name_to_config = {config["name"]: config for config in configs}
