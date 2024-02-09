import inspect
import os
import os.path as osp
import random
import re
from collections import OrderedDict
from inspect import Parameter
from itertools import chain
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Union,
    get_type_hints,
)

import torch
from torch import Tensor
from torch.utils.hooks import RemovableHandle

from torch_geometric.nn.aggr import Aggregation
from torch_geometric.nn.conv.utils.inspector import (
    Inspector,
    func_body_repr,
    func_header_repr,
)
from torch_geometric.nn.conv.utils.jit import class_from_module_repr
from torch_geometric.nn.conv.utils.typing import (
    parse_types,
    resolve_types,
    sanitize,
    split_types_repr,
)
from torch_geometric.nn.resolver import aggregation_resolver as aggr_resolver
from torch_geometric.typing import Adj, Size, SparseTensor
from torch_geometric.utils import (
    is_sparse,
    is_torch_sparse_tensor,
    to_edge_index,
)
from torch_geometric.utils.sparse import ptr2index

FUSE_AGGRS = {'add', 'sum', 'mean', 'min', 'max'}


def ptr2ind(ptr: Tensor) -> Tensor:
    ind = torch.arange(ptr.numel() - 1, device=ptr.device)
    return ind.repeat_interleave(ptr[1:] - ptr[:-1])


class MessagePassing(torch.nn.Module):
    r"""Base class for creating message passing layers of the form

    .. math::
        \mathbf{x}_i^{\prime} = \gamma_{\mathbf{\Theta}} \left( \mathbf{x}_i,
        \bigoplus_{j \in \mathcal{N}(i)} \, \phi_{\mathbf{\Theta}}
        \left(\mathbf{x}_i, \mathbf{x}_j,\mathbf{e}_{j,i}\right) \right),

    where :math:`\bigoplus` denotes a differentiable, permutation invariant
    function, *e.g.*, sum, mean, min, max or mul, and
    :math:`\gamma_{\mathbf{\Theta}}` and :math:`\phi_{\mathbf{\Theta}}` denote
    differentiable functions such as MLPs.
    See `here <https://pytorch-geometric.readthedocs.io/en/latest/tutorial/
    create_gnn.html>`__ for the accompanying tutorial.

    Args:
        aggr (str or [str] or Aggregation, optional): The aggregation scheme
            to use, *e.g.*, :obj:`"add"`, :obj:`"sum"` :obj:`"mean"`,
            :obj:`"min"`, :obj:`"max"` or :obj:`"mul"`.
            In addition, can be any
            :class:`~torch_geometric.nn.aggr.Aggregation` module (or any string
            that automatically resolves to it).
            If given as a list, will make use of multiple aggregations in which
            different outputs will get concatenated in the last dimension.
            If set to :obj:`None`, the :class:`MessagePassing` instantiation is
            expected to implement its own aggregation logic via
            :meth:`aggregate`. (default: :obj:`"add"`)
        aggr_kwargs (Dict[str, Any], optional): Arguments passed to the
            respective aggregation function in case it gets automatically
            resolved. (default: :obj:`None`)
        flow (str, optional): The flow direction of message passing
            (:obj:`"source_to_target"` or :obj:`"target_to_source"`).
            (default: :obj:`"source_to_target"`)
        node_dim (int, optional): The axis along which to propagate.
            (default: :obj:`-2`)
        decomposed_layers (int, optional): The number of feature decomposition
            layers, as introduced in the `"Optimizing Memory Efficiency of
            Graph Neural Networks on Edge Computing Platforms"
            <https://arxiv.org/abs/2104.03058>`_ paper.
            Feature decomposition reduces the peak memory usage by slicing
            the feature dimensions into separated feature decomposition layers
            during GNN aggregation.
            This method can accelerate GNN execution on CPU-based platforms
            (*e.g.*, 2-3x speedup on the
            :class:`~torch_geometric.datasets.Reddit` dataset) for common GNN
            models such as :class:`~torch_geometric.nn.models.GCN`,
            :class:`~torch_geometric.nn.models.GraphSAGE`,
            :class:`~torch_geometric.nn.models.GIN`, etc.
            However, this method is not applicable to all GNN operators
            available, in particular for operators in which message computation
            can not easily be decomposed, *e.g.* in attention-based GNNs.
            The selection of the optimal value of :obj:`decomposed_layers`
            depends both on the specific graph dataset and available hardware
            resources.
            A value of :obj:`2` is suitable in most cases.
            Although the peak memory usage is directly associated with the
            granularity of feature decomposition, the same is not necessarily
            true for execution speedups. (default: :obj:`1`)
    """

    special_args: Set[str] = {
        'edge_index', 'adj_t', 'edge_index_i', 'edge_index_j', 'size',
        'size_i', 'size_j', 'ptr', 'index', 'dim_size'
    }

    def __init__(
        self,
        aggr: Optional[Union[str, List[str], Aggregation]] = "add",
        *,
        aggr_kwargs: Optional[Dict[str, Any]] = None,
        flow: str = "source_to_target",
        node_dim: int = -2,
        decomposed_layers: int = 1,
        **kwargs,
    ):
        super().__init__()

        if aggr is None:
            self.aggr = None
        elif isinstance(aggr, (str, Aggregation)):
            self.aggr = str(aggr)
        elif isinstance(aggr, (tuple, list)):
            self.aggr = [str(x) for x in aggr]

        self.aggr_module = aggr_resolver(aggr, **(aggr_kwargs or {}))

        self.flow = flow

        if flow not in ['source_to_target', 'target_to_source']:
            raise ValueError(f"Expected 'flow' to be either 'source_to_target'"
                             f" or 'target_to_source' (got '{flow}')")

        self.node_dim = node_dim
        self.decomposed_layers = decomposed_layers

        self.inspector = Inspector(self)
        self.inspector.inspect(self.message)
        self.inspector.inspect(self.aggregate, pop_first=True)
        self.inspector.params['aggregate'].pop('aggr', None)
        self.inspector.inspect(self.message_and_aggregate, pop_first=True)
        self.inspector.inspect(self.update, pop_first=True)
        self.inspector.inspect(self.edge_update)

        self._user_args = self.inspector.keys(
            ['message', 'aggregate', 'update']).difference(self.special_args)
        self._fused_user_args = self.inspector.keys(
            ['message_and_aggregate', 'update']).difference(self.special_args)
        self._edge_user_args = self.inspector.keys(['edge_update']).difference(
            self.special_args)

        # Support for "fused" message passing.
        self.fuse = self.inspector.implements('message_and_aggregate')
        if self.aggr is not None:
            self.fuse &= isinstance(self.aggr, str) and self.aggr in FUSE_AGGRS

        # Support for explainability.
        self._explain = False
        self._edge_mask = None
        self._loop_mask = None
        self._apply_sigmoid = True

        # Hooks:
        self._propagate_forward_pre_hooks = OrderedDict()
        self._propagate_forward_hooks = OrderedDict()
        self._message_forward_pre_hooks = OrderedDict()
        self._message_forward_hooks = OrderedDict()
        self._aggregate_forward_pre_hooks = OrderedDict()
        self._aggregate_forward_hooks = OrderedDict()
        self._message_and_aggregate_forward_pre_hooks = OrderedDict()
        self._message_and_aggregate_forward_hooks = OrderedDict()
        self._edge_update_forward_pre_hooks = OrderedDict()
        self._edge_update_forward_hooks = OrderedDict()

    def reset_parameters(self):
        r"""Resets all learnable parameters of the module."""
        if self.aggr_module is not None:
            self.aggr_module.reset_parameters()

    def forward(self, *args, **kwargs) -> Any:
        r"""Runs the forward pass of the module."""
        pass

    def _check_input(self, edge_index, size):
        the_size: List[Optional[int]] = [None, None]

        if is_sparse(edge_index):
            if self.flow == 'target_to_source':
                raise ValueError(
                    ('Flow direction "target_to_source" is invalid for '
                     'message propagation via `torch_sparse.SparseTensor` '
                     'or `torch.sparse.Tensor`. If you really want to make '
                     'use of a reverse message passing flow, pass in the '
                     'transposed sparse tensor to the message passing module, '
                     'e.g., `adj_t.t()`.'))
            the_size[0] = edge_index.size(1)
            the_size[1] = edge_index.size(0)
            return the_size
        elif isinstance(edge_index, Tensor):
            int_dtypes = (torch.uint8, torch.int8, torch.int32, torch.int64)

            if edge_index.dtype not in int_dtypes:
                raise ValueError(f"Expected 'edge_index' to be of integer "
                                 f"type (got '{edge_index.dtype}')")
            if edge_index.dim() != 2:
                raise ValueError(f"Expected 'edge_index' to be two-dimensional"
                                 f" (got {edge_index.dim()} dimensions)")
            if not torch.jit.is_tracing() and edge_index.size(0) != 2:
                raise ValueError(f"Expected 'edge_index' to have size '2' in "
                                 f"the first dimension (got "
                                 f"'{edge_index.size(0)}')")
            if size is not None:
                the_size[0] = size[0]
                the_size[1] = size[1]
            return the_size

        raise ValueError(
            ('`MessagePassing.propagate` only supports integer tensors of '
             'shape `[2, num_messages]`, `torch_sparse.SparseTensor` or '
             '`torch.sparse.Tensor` for argument `edge_index`.'))

    def _set_size(self, size: List[Optional[int]], dim: int, src: Tensor):
        the_size = size[dim]
        if the_size is None:
            size[dim] = src.size(self.node_dim)
        elif the_size != src.size(self.node_dim):
            raise ValueError(
                (f'Encountered tensor with size {src.size(self.node_dim)} in '
                 f'dimension {self.node_dim}, but expected size {the_size}.'))

    def _lift(self, src, edge_index, dim):
        if is_torch_sparse_tensor(edge_index):
            assert dim == 0 or dim == 1
            if edge_index.layout == torch.sparse_coo:
                index = edge_index._indices()[1 - dim]
            elif edge_index.layout == torch.sparse_csr:
                if dim == 0:
                    index = edge_index.col_indices()
                else:
                    index = ptr2index(edge_index.crow_indices())
            elif edge_index.layout == torch.sparse_csc:
                if dim == 0:
                    index = ptr2index(edge_index.ccol_indices())
                else:
                    index = edge_index.row_indices()
            else:
                raise ValueError(f"Unsupported sparse tensor layout "
                                 f"(got '{edge_index.layout}')")
            return src.index_select(self.node_dim, index)

        elif isinstance(edge_index, Tensor):
            try:
                index = edge_index[dim]
                return src.index_select(self.node_dim, index)
            except (IndexError, RuntimeError) as e:
                if index.min() < 0 or index.max() >= src.size(self.node_dim):
                    raise IndexError(
                        f"Encountered an index error. Please ensure that all "
                        f"indices in 'edge_index' point to valid indices in "
                        f"the interval [0, {src.size(self.node_dim) - 1}] "
                        f"(got interval "
                        f"[{int(index.min())}, {int(index.max())}])")
                else:
                    raise e

                if index.numel() > 0 and index.min() < 0:
                    raise ValueError(
                        f"Found negative indices in 'edge_index' (got "
                        f"{index.min().item()}). Please ensure that all "
                        f"indices in 'edge_index' point to valid indices "
                        f"in the interval [0, {src.size(self.node_dim)}) in "
                        f"your node feature matrix and try again.")

                if (index.numel() > 0
                        and index.max() >= src.size(self.node_dim)):
                    raise ValueError(
                        f"Found indices in 'edge_index' that are larger "
                        f"than {src.size(self.node_dim) - 1} (got "
                        f"{index.max().item()}). Please ensure that all "
                        f"indices in 'edge_index' point to valid indices "
                        f"in the interval [0, {src.size(self.node_dim)}) in "
                        f"your node feature matrix and try again.")

                raise e

        elif isinstance(edge_index, SparseTensor):
            row, col, _ = edge_index.coo()
            if dim == 0:
                return src.index_select(self.node_dim, col)
            elif dim == 1:
                return src.index_select(self.node_dim, row)

        raise ValueError(
            ('`MessagePassing.propagate` only supports integer tensors of '
             'shape `[2, num_messages]`, `torch_sparse.SparseTensor` '
             'or `torch.sparse.Tensor` for argument `edge_index`.'))

    def _collect(self, args, edge_index, size, kwargs):
        i, j = (1, 0) if self.flow == 'source_to_target' else (0, 1)

        out = {}
        for arg in args:
            if arg[-2:] not in ['_i', '_j']:
                out[arg] = kwargs.get(arg, Parameter.empty)
            else:
                dim = j if arg[-2:] == '_j' else i
                data = kwargs.get(arg[:-2], Parameter.empty)

                if isinstance(data, (tuple, list)):
                    assert len(data) == 2
                    if isinstance(data[1 - dim], Tensor):
                        self._set_size(size, 1 - dim, data[1 - dim])
                    data = data[dim]

                if isinstance(data, Tensor):
                    self._set_size(size, dim, data)
                    data = self._lift(data, edge_index, dim)

                out[arg] = data

        if is_torch_sparse_tensor(edge_index):
            indices, values = to_edge_index(edge_index)
            out['adj_t'] = edge_index
            out['edge_index'] = None
            out['edge_index_i'] = indices[0]
            out['edge_index_j'] = indices[1]
            out['ptr'] = None  # TODO Get `rowptr` from CSR representation.
            if out.get('edge_weight', None) is None:
                out['edge_weight'] = values
            if out.get('edge_attr', None) is None:
                out['edge_attr'] = None if values.dim() == 1 else values
            if out.get('edge_type', None) is None:
                out['edge_type'] = values

        elif isinstance(edge_index, Tensor):
            out['adj_t'] = None
            out['edge_index'] = edge_index
            out['edge_index_i'] = edge_index[i]
            out['edge_index_j'] = edge_index[j]
            out['ptr'] = None

        elif isinstance(edge_index, SparseTensor):
            row, col, value = edge_index.coo()
            rowptr, _, _ = edge_index.csr()

            out['adj_t'] = edge_index
            out['edge_index'] = None
            out['edge_index_i'] = row
            out['edge_index_j'] = col
            out['ptr'] = rowptr
            if out.get('edge_weight', None) is None:
                out['edge_weight'] = value
            if out.get('edge_attr', None) is None:
                out['edge_attr'] = value
            if out.get('edge_type', None) is None:
                out['edge_type'] = value

        out['index'] = out['edge_index_i']
        out['size'] = size
        out['size_i'] = size[i] if size[i] is not None else size[j]
        out['size_j'] = size[j] if size[j] is not None else size[i]
        out['dim_size'] = out['size_i']

        return out

    def propagate(self, edge_index: Adj, size: Size = None, **kwargs):
        r"""The initial call to start propagating messages.

        Args:
            edge_index (torch.Tensor or SparseTensor): A :class:`torch.Tensor`,
                a :class:`torch_sparse.SparseTensor` or a
                :class:`torch.sparse.Tensor` that defines the underlying
                graph connectivity/message passing flow.
                :obj:`edge_index` holds the indices of a general (sparse)
                assignment matrix of shape :obj:`[N, M]`.
                If :obj:`edge_index` is a :obj:`torch.Tensor`, its :obj:`dtype`
                should be :obj:`torch.long` and its shape needs to be defined
                as :obj:`[2, num_messages]` where messages from nodes in
                :obj:`edge_index[0]` are sent to nodes in :obj:`edge_index[1]`
                (in case :obj:`flow="source_to_target"`).
                If :obj:`edge_index` is a :class:`torch_sparse.SparseTensor` or
                a :class:`torch.sparse.Tensor`, its sparse indices
                :obj:`(row, col)` should relate to :obj:`row = edge_index[1]`
                and :obj:`col = edge_index[0]`.
                The major difference between both formats is that we need to
                input the *transposed* sparse adjacency matrix into
                :meth:`propagate`.
            size ((int, int), optional): The size :obj:`(N, M)` of the
                assignment matrix in case :obj:`edge_index` is a
                :class:`torch.Tensor`.
                If set to :obj:`None`, the size will be automatically inferred
                and assumed to be quadratic.
                This argument is ignored in case :obj:`edge_index` is a
                :class:`torch_sparse.SparseTensor` or
                a :class:`torch.sparse.Tensor`. (default: :obj:`None`)
            **kwargs: Any additional data which is needed to construct and
                aggregate messages, and to update node embeddings.
        """
        decomposed_layers = 1 if self.explain else self.decomposed_layers

        for hook in self._propagate_forward_pre_hooks.values():
            res = hook(self, (edge_index, size, kwargs))
            if res is not None:
                edge_index, size, kwargs = res

        size = self._check_input(edge_index, size)

        # Run "fused" message and aggregation (if applicable).
        if is_sparse(edge_index) and self.fuse and not self.explain:
            coll_dict = self._collect(self._fused_user_args, edge_index, size,
                                      kwargs)

            msg_aggr_kwargs = self.inspector.distribute(
                'message_and_aggregate', coll_dict)
            for hook in self._message_and_aggregate_forward_pre_hooks.values():
                res = hook(self, (edge_index, msg_aggr_kwargs))
                if res is not None:
                    edge_index, msg_aggr_kwargs = res
            out = self.message_and_aggregate(edge_index, **msg_aggr_kwargs)
            for hook in self._message_and_aggregate_forward_hooks.values():
                res = hook(self, (edge_index, msg_aggr_kwargs), out)
                if res is not None:
                    out = res

            update_kwargs = self.inspector.distribute('update', coll_dict)
            out = self.update(out, **update_kwargs)

        else:  # Otherwise, run both functions in separation.
            if decomposed_layers > 1:
                user_args = self._user_args
                decomp_args = {a[:-2] for a in user_args if a[-2:] == '_j'}
                decomp_kwargs = {
                    a: kwargs[a].chunk(decomposed_layers, -1)
                    for a in decomp_args
                }
                decomp_out = []

            for i in range(decomposed_layers):
                if decomposed_layers > 1:
                    for arg in decomp_args:
                        kwargs[arg] = decomp_kwargs[arg][i]

                coll_dict = self._collect(self._user_args, edge_index, size,
                                          kwargs)

                msg_kwargs = self.inspector.distribute('message', coll_dict)
                for hook in self._message_forward_pre_hooks.values():
                    res = hook(self, (msg_kwargs, ))
                    if res is not None:
                        msg_kwargs = res[0] if isinstance(res, tuple) else res
                out = self.message(**msg_kwargs)
                for hook in self._message_forward_hooks.values():
                    res = hook(self, (msg_kwargs, ), out)
                    if res is not None:
                        out = res

                if self.explain:
                    explain_msg_kwargs = self.inspector.distribute(
                        'explain_message', coll_dict)
                    out = self.explain_message(out, **explain_msg_kwargs)

                aggr_kwargs = self.inspector.distribute('aggregate', coll_dict)
                for hook in self._aggregate_forward_pre_hooks.values():
                    res = hook(self, (aggr_kwargs, ))
                    if res is not None:
                        aggr_kwargs = res[0] if isinstance(res, tuple) else res

                out = self.aggregate(out, **aggr_kwargs)

                for hook in self._aggregate_forward_hooks.values():
                    res = hook(self, (aggr_kwargs, ), out)
                    if res is not None:
                        out = res

                update_kwargs = self.inspector.distribute('update', coll_dict)
                out = self.update(out, **update_kwargs)

                if decomposed_layers > 1:
                    decomp_out.append(out)

            if decomposed_layers > 1:
                out = torch.cat(decomp_out, dim=-1)

        for hook in self._propagate_forward_hooks.values():
            res = hook(self, (edge_index, size, kwargs), out)
            if res is not None:
                out = res

        return out

    def edge_updater(self, edge_index: Adj, **kwargs):
        r"""The initial call to compute or update features for each edge in the
        graph.

        Args:
            edge_index (torch.Tensor or SparseTensor): A :obj:`torch.Tensor`, a
                :class:`torch_sparse.SparseTensor` or a
                :class:`torch.sparse.Tensor` that defines the underlying graph
                connectivity/message passing flow.
                See :meth:`propagate` for more information.
            **kwargs: Any additional data which is needed to compute or update
                features for each edge in the graph.
        """
        for hook in self._edge_update_forward_pre_hooks.values():
            res = hook(self, (edge_index, kwargs))
            if res is not None:
                edge_index, kwargs = res

        size = self._check_input(edge_index, size=None)

        coll_dict = self._collect(self._edge_user_args, edge_index, size,
                                  kwargs)

        edge_kwargs = self.inspector.distribute('edge_update', coll_dict)
        out = self.edge_update(**edge_kwargs)

        for hook in self._edge_update_forward_hooks.values():
            res = hook(self, (edge_index, kwargs), out)
            if res is not None:
                out = res

        return out

    def message(self, x_j: Tensor) -> Tensor:
        r"""Constructs messages from node :math:`j` to node :math:`i`
        in analogy to :math:`\phi_{\mathbf{\Theta}}` for each edge in
        :obj:`edge_index`.
        This function can take any argument as input which was initially
        passed to :meth:`propagate`.
        Furthermore, tensors passed to :meth:`propagate` can be mapped to the
        respective nodes :math:`i` and :math:`j` by appending :obj:`_i` or
        :obj:`_j` to the variable name, *.e.g.* :obj:`x_i` and :obj:`x_j`.
        """
        return x_j

    @property
    def explain(self) -> bool:
        return self._explain

    @explain.setter
    def explain(self, explain: bool):
        if explain:
            methods = ['message', 'explain_message', 'aggregate', 'update']
        else:
            methods = ['message', 'aggregate', 'update']

        self._explain = explain
        self.inspector.inspect(self.explain_message, pop_first=True)
        self._user_args = self.inspector.keys(methods).difference(
            self.special_args)

    def explain_message(self, inputs: Tensor, size_i: int) -> Tensor:
        # NOTE Replace this method in custom explainers per message-passing
        # layer to customize how messages shall be explained, e.g., via:
        # conv.explain_message = explain_message.__get__(conv, MessagePassing)
        # see stackoverflow.com: 394770/override-a-method-at-instance-level

        edge_mask = self._edge_mask

        if edge_mask is None:
            raise ValueError(f"Could not find a pre-defined 'edge_mask' as "
                             f"part of {self.__class__.__name__}.")

        if self._apply_sigmoid:
            edge_mask = edge_mask.sigmoid()

        # Some ops add self-loops to `edge_index`. We need to do the same for
        # `edge_mask` (but do not train these entries).
        if inputs.size(self.node_dim) != edge_mask.size(0):
            edge_mask = edge_mask[self._loop_mask]
            loop = edge_mask.new_ones(size_i)
            edge_mask = torch.cat([edge_mask, loop], dim=0)
        assert inputs.size(self.node_dim) == edge_mask.size(0)

        size = [1] * inputs.dim()
        size[self.node_dim] = -1
        return inputs * edge_mask.view(size)

    def aggregate(self, inputs: Tensor, index: Tensor,
                  ptr: Optional[Tensor] = None,
                  dim_size: Optional[int] = None) -> Tensor:
        r"""Aggregates messages from neighbors as
        :math:`\bigoplus_{j \in \mathcal{N}(i)}`.

        Takes in the output of message computation as first argument and any
        argument which was initially passed to :meth:`propagate`.

        By default, this function will delegate its call to the underlying
        :class:`~torch_geometric.nn.aggr.Aggregation` module to reduce messages
        as specified in :meth:`__init__` by the :obj:`aggr` argument.
        """
        return self.aggr_module(inputs, index, ptr=ptr, dim_size=dim_size,
                                dim=self.node_dim)

    def message_and_aggregate(
        self,
        adj_t: Union[SparseTensor, Tensor],
    ) -> Tensor:
        r"""Fuses computations of :func:`message` and :func:`aggregate` into a
        single function.
        If applicable, this saves both time and memory since messages do not
        explicitly need to be materialized.
        This function will only gets called in case it is implemented and
        propagation takes place based on a :obj:`torch_sparse.SparseTensor`
        or a :obj:`torch.sparse.Tensor`.
        """
        raise NotImplementedError

    def update(self, inputs: Tensor) -> Tensor:
        r"""Updates node embeddings in analogy to
        :math:`\gamma_{\mathbf{\Theta}}` for each node
        :math:`i \in \mathcal{V}`.
        Takes in the output of aggregation as first argument and any argument
        which was initially passed to :meth:`propagate`.
        """
        return inputs

    def edge_update(self) -> Tensor:
        r"""Computes or updates features for each edge in the graph.
        This function can take any argument as input which was initially passed
        to :meth:`edge_updater`.
        Furthermore, tensors passed to :meth:`edge_updater` can be mapped to
        the respective nodes :math:`i` and :math:`j` by appending :obj:`_i` or
        :obj:`_j` to the variable name, *.e.g.* :obj:`x_i` and :obj:`x_j`.
        """
        raise NotImplementedError

    def register_propagate_forward_pre_hook(self,
                                            hook: Callable) -> RemovableHandle:
        r"""Registers a forward pre-hook on the module.
        The hook will be called every time before :meth:`propagate` is invoked.
        It should have the following signature:

        .. code-block:: python

            hook(module, inputs) -> None or modified input

        The hook can modify the input.
        Input keyword arguments are passed to the hook as a dictionary in
        :obj:`inputs[-1]`.

        Returns a :class:`torch.utils.hooks.RemovableHandle` that can be used
        to remove the added hook by calling :obj:`handle.remove()`.
        """
        handle = RemovableHandle(self._propagate_forward_pre_hooks)
        self._propagate_forward_pre_hooks[handle.id] = hook
        return handle

    def register_propagate_forward_hook(self,
                                        hook: Callable) -> RemovableHandle:
        r"""Registers a forward hook on the module.
        The hook will be called every time after :meth:`propagate` has computed
        an output.
        It should have the following signature:

        .. code-block:: python

            hook(module, inputs, output) -> None or modified output

        The hook can modify the output.
        Input keyword arguments are passed to the hook as a dictionary in
        :obj:`inputs[-1]`.

        Returns a :class:`torch.utils.hooks.RemovableHandle` that can be used
        to remove the added hook by calling :obj:`handle.remove()`.
        """
        handle = RemovableHandle(self._propagate_forward_hooks)
        self._propagate_forward_hooks[handle.id] = hook
        return handle

    def register_message_forward_pre_hook(self,
                                          hook: Callable) -> RemovableHandle:
        r"""Registers a forward pre-hook on the module.
        The hook will be called every time before :meth:`message` is invoked.
        See :meth:`register_propagate_forward_pre_hook` for more information.
        """
        handle = RemovableHandle(self._message_forward_pre_hooks)
        self._message_forward_pre_hooks[handle.id] = hook
        return handle

    def register_message_forward_hook(self, hook: Callable) -> RemovableHandle:
        r"""Registers a forward hook on the module.
        The hook will be called every time after :meth:`message` has computed
        an output.
        See :meth:`register_propagate_forward_hook` for more information.
        """
        handle = RemovableHandle(self._message_forward_hooks)
        self._message_forward_hooks[handle.id] = hook
        return handle

    def register_aggregate_forward_pre_hook(self,
                                            hook: Callable) -> RemovableHandle:
        r"""Registers a forward pre-hook on the module.
        The hook will be called every time before :meth:`aggregate` is invoked.
        See :meth:`register_propagate_forward_pre_hook` for more information.
        """
        handle = RemovableHandle(self._aggregate_forward_pre_hooks)
        self._aggregate_forward_pre_hooks[handle.id] = hook
        return handle

    def register_aggregate_forward_hook(self,
                                        hook: Callable) -> RemovableHandle:
        r"""Registers a forward hook on the module.
        The hook will be called every time after :meth:`aggregate` has computed
        an output.
        See :meth:`register_propagate_forward_hook` for more information.
        """
        handle = RemovableHandle(self._aggregate_forward_hooks)
        self._aggregate_forward_hooks[handle.id] = hook
        return handle

    def register_message_and_aggregate_forward_pre_hook(
            self, hook: Callable) -> RemovableHandle:
        r"""Registers a forward pre-hook on the module.
        The hook will be called every time before :meth:`message_and_aggregate`
        is invoked.
        See :meth:`register_propagate_forward_pre_hook` for more information.
        """
        handle = RemovableHandle(self._message_and_aggregate_forward_pre_hooks)
        self._message_and_aggregate_forward_pre_hooks[handle.id] = hook
        return handle

    def register_message_and_aggregate_forward_hook(
            self, hook: Callable) -> RemovableHandle:
        r"""Registers a forward hook on the module.
        The hook will be called every time after :meth:`message_and_aggregate`
        has computed an output.
        See :meth:`register_propagate_forward_hook` for more information.
        """
        handle = RemovableHandle(self._message_and_aggregate_forward_hooks)
        self._message_and_aggregate_forward_hooks[handle.id] = hook
        return handle

    def register_edge_update_forward_pre_hook(
            self, hook: Callable) -> RemovableHandle:
        r"""Registers a forward pre-hook on the module.
        The hook will be called every time before :meth:`edge_update` is
        invoked. See :meth:`register_propagate_forward_pre_hook` for more
        information.
        """
        handle = RemovableHandle(self._edge_update_forward_pre_hooks)
        self._edge_update_forward_pre_hooks[handle.id] = hook
        return handle

    def register_edge_update_forward_hook(self,
                                          hook: Callable) -> RemovableHandle:
        r"""Registers a forward hook on the module.
        The hook will be called every time after :meth:`edge_update` has
        computed an output.
        See :meth:`register_propagate_forward_hook` for more information.
        """
        handle = RemovableHandle(self._edge_update_forward_hooks)
        self._edge_update_forward_hooks[handle.id] = hook
        return handle

    @torch.jit.unused
    def jittable(self, typing: Optional[str] = None) -> 'MessagePassing':
        r"""Analyzes the :class:`MessagePassing` instance and produces a new
        jittable module that can be used in combination with
        :meth:`torch.jit.script`.

        Args:
            typing (str, optional): If given, will generate a concrete instance
                with :meth:`forward` types based on :obj:`typing`, *e.g.*,
                :obj:`"(Tensor, Optional[Tensor]) -> Tensor"`.
        """
        try:
            from jinja2 import Template
        except ImportError:
            raise ModuleNotFoundError(
                "No module named 'jinja2' found on this machine. "
                "Run 'pip install jinja2' to install the library.")

        source = inspect.getsource(self.__class__)

        # Find and parse `propagate()` types to format `{arg1: type1, ...}`.
        if hasattr(self, 'propagate_type'):
            prop_types = {
                k: sanitize(str(v))
                for k, v in self.propagate_type.items()
            }
        else:
            match = re.search(r'#\s*propagate_type:\s*\((.*)\)', source)
            if match is None:
                raise TypeError(
                    'TorchScript support requires the definition of the types '
                    'passed to `propagate()`. Please specify them via\n\n'
                    'propagate_type = {"arg1": type1, "arg2": type2, ... }\n\n'
                    'or via\n\n'
                    '# propagate_type: (arg1: type1, arg2: type2, ...)\n\n'
                    'inside the `MessagePassing` module.')
            prop_types = split_types_repr(match.group(1))
            prop_types = dict([re.split(r'\s*:\s*', t) for t in prop_types])

        # Find and parse `edge_updater` types to format `{arg1: type1, ...}`.
        if 'edge_update' in self.__class__.__dict__.keys():
            if hasattr(self, 'edge_updater_type'):
                edge_updater_types = {
                    k: sanitize(str(v))
                    for k, v in self.edge_updater.items()
                }
            else:
                match = re.search(r'#\s*edge_updater_type:\s*\((.*)\)', source)
                if match is None:
                    raise TypeError(
                        'TorchScript support requires the definition of the '
                        'types passed to `edge_updater()`. Please specify '
                        'them via\n\n edge_updater_type = {"arg1": type1, '
                        '"arg2": type2, ... }\n\n or via\n\n'
                        '# edge_updater_type: (arg1: type1, arg2: type2, ...)'
                        '\n\ninside the `MessagePassing` module.')
                edge_updater_types = split_types_repr(match.group(1))
                edge_updater_types = dict(
                    [re.split(r'\s*:\s*', t) for t in edge_updater_types])
        else:
            edge_updater_types = {}

        type_hints = get_type_hints(self.__class__.update)
        prop_return_type = type_hints.get('return', 'Tensor')
        if str(prop_return_type)[:6] == '<class':
            prop_return_type = prop_return_type.__name__

        type_hints = get_type_hints(self.__class__.edge_update)
        edge_updater_return_type = type_hints.get('return', 'Tensor')
        if str(edge_updater_return_type)[:6] == '<class':
            edge_updater_return_type = edge_updater_return_type.__name__

        # Parse `_collect()` types to format `{arg:1, type1, ...}`.
        collect_types = self.inspector.types(
            ['message', 'aggregate', 'update'])

        # Parse `_collect()` types to format `{arg:1, type1, ...}`,
        # specific to the argument used for edge updates.
        edge_collect_types = self.inspector.types(['edge_update'])

        # Collect `forward()` header, body and @overload types.
        forward_types = parse_types(self.forward)
        forward_types = [resolve_types(*types) for types in forward_types]
        forward_types = list(chain.from_iterable(forward_types))

        keep_annotation = len(forward_types) < 2
        forward_header = func_header_repr(self.forward, keep_annotation)
        forward_body = func_body_repr(self.forward, keep_annotation)

        if keep_annotation:
            forward_types = []
        elif typing is not None:
            forward_types = []
            forward_body = 8 * ' ' + f'# type: {typing}\n{forward_body}'

        root = os.path.dirname(osp.realpath(__file__))
        with open(osp.join(root, 'message_passing.jinja'), 'r') as f:
            template = Template(f.read())

        uid = '%06x' % random.randrange(16**6)
        cls_name = f'{self.__class__.__name__}Jittable_{uid}'
        jit_module_repr = template.render(
            uid=uid,
            module=str(self.__class__.__module__),
            cls_name=cls_name,
            parent_cls_name=self.__class__.__name__,
            prop_types=prop_types,
            prop_return_type=prop_return_type,
            fuse=self.fuse,
            collect_types=collect_types,
            user_args=self._user_args,
            edge_user_args=self._edge_user_args,
            forward_header=forward_header,
            forward_types=forward_types,
            forward_body=forward_body,
            msg_args=self.inspector.keys(['message']),
            aggr_args=self.inspector.keys(['aggregate']),
            msg_and_aggr_args=self.inspector.keys(['message_and_aggregate']),
            update_args=self.inspector.keys(['update']),
            edge_collect_types=edge_collect_types,
            edge_update_args=self.inspector.keys(['edge_update']),
            edge_updater_types=edge_updater_types,
            edge_updater_return_type=edge_updater_return_type,
            check_input=inspect.getsource(self._check_input)[:-1],
        )
        # Instantiate a class from the rendered JIT module representation.
        cls = class_from_module_repr(cls_name, jit_module_repr)
        module = cls.__new__(cls)
        module.__dict__ = self.__dict__.copy()
        module.jittable = None
        return module

    def __repr__(self) -> str:
        if hasattr(self, 'in_channels') and hasattr(self, 'out_channels'):
            return (f'{self.__class__.__name__}({self.in_channels}, '
                    f'{self.out_channels})')
        return f'{self.__class__.__name__}()'
