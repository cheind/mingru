"""PyTorch (convolutional) MinGRU reference implementation

Christoph Heind, 2024
https://github.com/cheind/mingru
"""

import torch
import torch.nn.functional as F

from .scan import parallel_scan_log


def g(x: torch.Tensor) -> torch.Tensor:
    """Activation function for hidden state
    Ensures that g(h) is non-negative and hence avoids
    complex numbers in log-space.
    """
    out = torch.empty_like(x)
    mask = x >= 0
    out[mask] = x[mask] + 0.5
    out[~mask] = torch.sigmoid(x[~mask])
    return out


def log_g(x: torch.Tensor) -> torch.Tensor:
    """Log-activation function for hidden state
    Ensures that g(h) is non-negative and hence avoids
    complex numbers in log-space.
    """
    out = torch.empty_like(x)
    mask = x >= 0
    out[mask] = (x[mask] + 0.5).log()
    out[~mask] = -F.softplus(-x[~mask])
    return out


def _mingru_parallel(
    h: torch.Tensor,
    gate: torch.Tensor,
    hidden: torch.Tensor,
):
    """Parallel MinGRU forward

    This function takes gate and hidden outputs directly,
    as MinGRU forward is equal for convolutional/standard
    MinGRU from this point on.

    This function works for any number of spatial dimensions,
    which is indicated by `*` below.

    Params:
        h: (B,1,hidden_dims,*) previous hidden state
        gate: (B,S,hidden_dims,*) gate outputs
        hidden: (B,S,hidden_dims,*) hidden outputs

    Returns:
        h: (B,S,hidden_dims,*) hidden states
    """

    log_z = -F.softplus(-gate)  # log(z)
    log_coeffs = -F.softplus(gate)  # log(1-z)
    log_h_0 = h.log()
    log_tilde_h = log_g(hidden)

    h = parallel_scan_log(
        log_coeffs,
        torch.cat((log_h_0, log_z + log_tilde_h), dim=1),
    )
    return h[:, 1:]  # tail


def _mingru_sequential(
    h: torch.Tensor,
    gate: torch.Tensor,
    hidden: torch.Tensor,
):
    """Sequential MinGRU forward.

    This function takes gate and hidden outputs directly,
    as MinGRU forward is equal for convolutional/standard
    MinGRU from this point on.

    This function works for any number of spatial dimensions,
    which is indicated by `*` below.

    Params:
        h: (B,1,hidden_dims,*) previous hidden state
        gate: (B,1,hidden_dims,*) gate outputs
        hidden: (B,1,hidden_dims,*) hidden outputs

    Returns:
        h: (B,1,hidden_dims,*) next hidden dims
    """

    z = torch.sigmoid(gate)
    h_tilde = g(hidden)
    h_t = (1 - z) * h + z * h_tilde
    return h_t


def mingru_gate_hidden(
    gate: torch.Tensor,
    hidden: torch.Tensor,
    h: torch.Tensor,
):
    """Evaluate the (convolutional) MinGRU

    This method is the main entry point to evaluate the MinGRU. It
    works for both convolutional and non-convolutional MinGRUS.

    The code chooses sequential and parallel forward
    depending on the size of the sequence dimension S.

    Params:
        gate: (B,1,hidden_dims,*) gate outputs
        hidden: (B,1,hidden_dims,*) hidden outputs
        h: (B,1,hidden_dims,*) previous hidden state

    Returns:
        h: (B,S,hidden_dims,*) next hidden states
    """

    if gate.shape[1] == 1:
        return _mingru_sequential(h, gate, hidden)
    else:
        return _mingru_parallel(h, gate, hidden)


__all__ = ["mingru_gate_hidden", "g", "log_g"]
