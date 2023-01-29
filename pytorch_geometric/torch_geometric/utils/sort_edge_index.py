from typing import List, Optional, Tuple, Union

import torch
from torch import Tensor

from .num_nodes import maybe_num_nodes


@torch.jit._overload
def sort_edge_index(edge_index, edge_attr=None, num_nodes=None,
                    sort_by_row=True):
    # type: (Tensor, Optional[bool], Optional[int], bool) -> Tensor  # noqa
    pass


@torch.jit._overload
def sort_edge_index(edge_index, edge_attr=None, num_nodes=None,
                    sort_by_row=True):
    # type: (Tensor, Tensor, Optional[int], bool) -> Tuple[Tensor, Tensor]  # noqa
    pass


@torch.jit._overload
def sort_edge_index(edge_index, edge_attr=None, num_nodes=None,
                    sort_by_row=True):
    # type: (Tensor, List[Tensor], Optional[int], bool) -> Tuple[Tensor, List[Tensor]]  # noqa
    pass


def sort_edge_index(
    edge_index: Tensor,
    edge_attr: Union[Optional[Tensor], List[Tensor]] = None,
    num_nodes: Optional[int] = None,
    sort_by_row: bool = True,
) -> Union[Tensor, Tuple[Tensor, Tensor], Tuple[Tensor, List[Tensor]]]:
    """Row-wise sorts :obj:`edge_index`.

    Args:
        edge_index (LongTensor): The edge indices.
        edge_attr (Tensor or List[Tensor], optional): Edge weights or multi-
            dimensional edge features.
            If given as a list, will re-shuffle and remove duplicates for all
            its entries. (default: :obj:`None`)
        num_nodes (int, optional): The number of nodes, *i.e.*
            :obj:`max_val + 1` of :attr:`edge_index`. (default: :obj:`None`)
        sort_by_row (bool, optional): If set to :obj:`False`, will sort
            :obj:`edge_index` column-wise.

    :rtype: :class:`LongTensor` if :attr:`edge_attr` is :obj:`None`, else
        (:class:`LongTensor`, :obj:`Tensor` or :obj:`List[Tensor]]`)

    Examples:

        >>> edge_index = torch.tensor([[2, 1, 1, 0],
                                [1, 2, 0, 1]])
        >>> edge_attr = torch.tensor([[1], [2], [3], [4]])
        >>> sort_edge_index(edge_index)
        tensor([[0, 1, 1, 2],
                [1, 0, 2, 1]])

        >>> sort_edge_index(edge_index, edge_attr)
        (tensor([[0, 1, 1, 2],
                [1, 0, 2, 1]]),
        tensor([[4],
                [3],
                [2],
                [1]]))
    """
    num_nodes = maybe_num_nodes(edge_index, num_nodes)

    idx = edge_index[1 - int(sort_by_row)] * num_nodes
    idx += edge_index[int(sort_by_row)]

    perm = idx.argsort()

    edge_index = edge_index[:, perm]

    if isinstance(edge_attr, Tensor):
        return edge_index, edge_attr[perm]
    elif isinstance(edge_attr, (list, tuple)):
        return edge_index, [e[perm] for e in edge_attr]
    else:
        return edge_index
