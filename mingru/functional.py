"""Torch MinGRU implementation

Christoph Heind, 2024

Based on:
    Were RNNs All We Needed?
    Leo Feng, 2024, https://arxiv.org/pdf/2410.01201v1
"""

import torch
import torch.nn.functional as F

from .scan import parallel_scan_log


def g(x: torch.Tensor):
    """Proposed activation function for h"""
    out = torch.empty_like(x)
    mask = x >= 0
    out[mask] = x[mask] + 0.5
    out[~mask] = torch.sigmoid(x[~mask])
    return out


def log_g(x: torch.Tensor):
    """Proposed activation function for h in log-space"""
    out = torch.empty_like(x)
    mask = x >= 0
    out[mask] = (x[mask] + 0.5).log()
    out[~mask] = -F.softplus(-x[~mask])
    return out


def mingru_sequential(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Sequential forward.

    Params:
        x: (B,1,input_dims) input
        h: (B,1,hidden_dims) previous hidden dims

    Returns:
        h: (B,1,hidden_dims) next hidden dims
    """
    gate, hidden = F.linear(x, weight, bias).chunk(2, dim=-1)

    z = torch.sigmoid(gate)
    h_tilde = g(hidden)
    h_t = (1 - z) * h + z * h_tilde
    return h_t


def mingru_parallel(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Parallel forward

    Params:
        x: (B,S,input_dims) input
        h: (B,1,hidden_dims) initial hidden-state

    Returns:
        h: (B,S,hidden_dims) hidden states
    """

    gate, hidden = F.linear(x, weight, bias).chunk(2, dim=-1)

    log_z = -F.softplus(-gate)  # log(z)
    log_coeffs = -F.softplus(gate)  # log(1-z)
    log_h_0 = h.log()
    log_tilde_h = log_g(hidden)
    h = parallel_scan_log(
        log_coeffs,
        torch.cat((log_h_0, log_z + log_tilde_h), dim=1),
    )
    return h[:, 1:]  # tail


def mingru(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Evaluate the MinGRU.

    Params:
        x: (B,S,input_dims) input
        h: (B,1,hidden_dims) initial hidden-state
        weight: weights of linear z-gate and hidden transform combined
        bias: optional bias term of z-gate and hidden transform combined

    Returns:
        h: (B,S,hidden_dims) hidden states
    """
    S = x.shape[1]
    if S == 1:
        return mingru_sequential(x, h, weight, bias)
    else:
        return mingru_parallel(x, h, weight, bias)


def conv_mingru_sequential(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Sequential forward.

    Params:
        x: (B,1,input_dims,H,W) input
        h: (B,1,hidden_dims,H,W) previous hidden dims
        weight: (hidden_dims*2, input_dims, k1, k2)
        bias: (hidden_dims*2,)

    Returns:
        h: (B,1,hidden_dims,H,W) next hidden dims
    """
    gate, hidden = F.conv2d(
        x.squeeze(1),
        weight,
        bias,
        stride=1,
        padding="same",
    ).chunk(2, dim=1)

    z = torch.sigmoid(gate)
    h_tilde = g(hidden)
    h_t = (1 - z) * h.squeeze(1) + z * h_tilde
    return h_t.unsqueeze(1)


def conv_mingru_parallel(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Parallel forward

    Params:
        x: (B,S,input_dims,H,W) input
        h: (B,1,hidden_dims,H,W) initial hidden-state
        weight: (hidden_dims*2, input_dims, k1, k2)
        bias: (hidden_dims*2,)

    Returns:
        h: (B,S,hidden_dims,H,W) hidden states
    """
    B, S, input_dims, H, W = x.shape
    hidden_dims = h.shape[2]

    gate, hidden = (
        F.conv2d(
            x.view(B * S, input_dims, H, W),
            weight,
            bias,
            stride=1,
            padding="same",
        )
        .view(B, S, hidden_dims * 2, H, W)
        .chunk(2, dim=2)
    )

    log_z = -F.softplus(-gate)  # log(z)
    log_coeffs = -F.softplus(gate)  # log(1-z)
    log_h_0 = h.log()
    log_tilde_h = log_g(hidden)

    h = parallel_scan_log(
        log_coeffs,
        torch.cat((log_h_0, log_z + log_tilde_h), dim=1),
    )
    return h[:, 1:]  # tail


def conv_mingru(
    x: torch.Tensor,
    h: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None = None,
):
    """Evaluate the MinGRU.

    Params:
        x: (B,S,input_dims,H,W) input
        h: (B,1,hidden_dims,H,W) initial hidden-state
        weight: weights of convolution z-gate and hidden transform combined
        bias: optional bias term of z-gate and hidden transform combined

    Returns:
        h: (B,S,hidden_dims,H,W) hidden states
    """
    S = x.shape[1]
    if S == 1:
        return conv_mingru_sequential(x, h, weight, bias)
    else:
        return conv_mingru_parallel(x, h, weight, bias)


__all__ = ["mingru", "conv_mingru", "g", "log_g"]
