from typing import Optional, Tuple

import torch

import torch_geometric.typing
from torch_geometric.typing import pyg_lib


def index_sort(
    inputs: torch.Tensor,
    max_value: Optional[int] = None,
) -> Tuple[torch.Tensor, torch.Tensor]:
    r"""Sorts the elements of the :obj:`inputs` tensor in ascending order.
    It is expected that :obj:`inputs` is one-dimensional and that it only
    contains positive integer values. If :obj:`max_value` is given, it can
    be used by the underlying algorithm for better performance.

    Args:
        inputs (torch.Tensor): A vector with positive integer values.
        max_value (int, optional): The maximum value stored inside
            :obj:`inputs`. This value can be an estimation, but needs to be
            greater than or equal to the real maximum.
            (default: :obj:`None`)
    """
    if not torch_geometric.typing.WITH_INDEX_SORT:  # pragma: no cover
        return inputs.sort()
    return pyg_lib.ops.index_sort(inputs, max_value=max_value)
