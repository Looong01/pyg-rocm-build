import copy
import math
from typing import Any, Dict, Optional, Union

import torch
import torch.nn.functional as F
from torch import Tensor, nn
from torch.nn.parameter import Parameter

import torch_geometric.typing
from torch_geometric.nn import inits
from torch_geometric.typing import pyg_lib
from torch_geometric.utils import index_sort
from torch_geometric.utils.sparse import index2ptr


def is_uninitialized_parameter(x: Any) -> bool:
    if not hasattr(nn.parameter, 'UninitializedParameter'):
        return False
    return isinstance(x, nn.parameter.UninitializedParameter)


def reset_weight_(weight: Tensor, in_channels: int,
                  initializer: Optional[str] = None) -> Tensor:
    if in_channels <= 0:
        pass
    elif initializer == 'glorot':
        inits.glorot(weight)
    elif initializer == 'uniform':
        bound = 1.0 / math.sqrt(in_channels)
        torch.nn.init.uniform_(weight.data, -bound, bound)
    elif initializer == 'kaiming_uniform':
        inits.kaiming_uniform(weight, fan=in_channels, a=math.sqrt(5))
    elif initializer is None:
        inits.kaiming_uniform(weight, fan=in_channels, a=math.sqrt(5))
    else:
        raise RuntimeError(f"Weight initializer '{initializer}' not supported")

    return weight


def reset_bias_(bias: Optional[Tensor], in_channels: int,
                initializer: Optional[str] = None) -> Optional[Tensor]:
    if bias is None or in_channels <= 0:
        pass
    elif initializer == 'zeros':
        inits.zeros(bias)
    elif initializer is None:
        inits.uniform(in_channels, bias)
    else:
        raise RuntimeError(f"Bias initializer '{initializer}' not supported")

    return bias


class Linear(torch.nn.Module):
    r"""Applies a linear tranformation to the incoming data

    .. math::
        \mathbf{x}^{\prime} = \mathbf{x} \mathbf{W}^{\top} + \mathbf{b}

    similar to :class:`torch.nn.Linear`.
    It supports lazy initialization and customizable weight and bias
    initialization.

    Args:
        in_channels (int): Size of each input sample. Will be initialized
            lazily in case it is given as :obj:`-1`.
        out_channels (int): Size of each output sample.
        bias (bool, optional): If set to :obj:`False`, the layer will not learn
            an additive bias. (default: :obj:`True`)
        weight_initializer (str, optional): The initializer for the weight
            matrix (:obj:`"glorot"`, :obj:`"uniform"`, :obj:`"kaiming_uniform"`
            or :obj:`None`).
            If set to :obj:`None`, will match default weight initialization of
            :class:`torch.nn.Linear`. (default: :obj:`None`)
        bias_initializer (str, optional): The initializer for the bias vector
            (:obj:`"zeros"` or :obj:`None`).
            If set to :obj:`None`, will match default bias initialization of
            :class:`torch.nn.Linear`. (default: :obj:`None`)

    Shapes:
        - **input:** features :math:`(*, F_{in})`
        - **output:** features :math:`(*, F_{out})`
    """
    def __init__(self, in_channels: int, out_channels: int, bias: bool = True,
                 weight_initializer: Optional[str] = None,
                 bias_initializer: Optional[str] = None):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.weight_initializer = weight_initializer
        self.bias_initializer = bias_initializer

        if in_channels > 0:
            self.weight = Parameter(torch.Tensor(out_channels, in_channels))
        else:
            self.weight = nn.parameter.UninitializedParameter()
            self._hook = self.register_forward_pre_hook(
                self.initialize_parameters)

        if bias:
            self.bias = Parameter(torch.Tensor(out_channels))
        else:
            self.register_parameter('bias', None)

        self._load_hook = self._register_load_state_dict_pre_hook(
            self._lazy_load_hook)

        self.reset_parameters()

    def __deepcopy__(self, memo):
        out = Linear(self.in_channels, self.out_channels, self.bias
                     is not None, self.weight_initializer,
                     self.bias_initializer)
        if self.in_channels > 0:
            out.weight = copy.deepcopy(self.weight, memo)
        if self.bias is not None:
            out.bias = copy.deepcopy(self.bias, memo)
        return out

    def reset_parameters(self):
        r"""Resets all learnable parameters of the module."""
        reset_weight_(self.weight, self.in_channels, self.weight_initializer)
        reset_bias_(self.bias, self.in_channels, self.bias_initializer)

    def forward(self, x: Tensor) -> Tensor:
        r"""
        Args:
            x (torch.Tensor): The input features.
        """
        return F.linear(x, self.weight, self.bias)

    @torch.no_grad()
    def initialize_parameters(self, module, input):
        if is_uninitialized_parameter(self.weight):
            self.in_channels = input[0].size(-1)
            self.weight.materialize((self.out_channels, self.in_channels))
            self.reset_parameters()
        self._hook.remove()
        delattr(self, '_hook')

    def _save_to_state_dict(self, destination, prefix, keep_vars):
        if (is_uninitialized_parameter(self.weight)
                or torch.onnx.is_in_onnx_export()):
            destination[prefix + 'weight'] = self.weight
        else:
            destination[prefix + 'weight'] = self.weight.detach()
        if self.bias is not None:
            if torch.onnx.is_in_onnx_export():
                destination[prefix + 'bias'] = self.bias
            else:
                destination[prefix + 'bias'] = self.bias.detach()

    def _lazy_load_hook(self, state_dict, prefix, local_metadata, strict,
                        missing_keys, unexpected_keys, error_msgs):

        weight = state_dict.get(prefix + 'weight', None)

        if weight is not None and is_uninitialized_parameter(weight):
            self.in_channels = -1
            self.weight = nn.parameter.UninitializedParameter()
            if not hasattr(self, '_hook'):
                self._hook = self.register_forward_pre_hook(
                    self.initialize_parameters)

        elif weight is not None and is_uninitialized_parameter(self.weight):
            self.in_channels = weight.size(-1)
            self.weight.materialize((self.out_channels, self.in_channels))
            if hasattr(self, '_hook'):
                self._hook.remove()
                delattr(self, '_hook')

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.in_channels}, '
                f'{self.out_channels}, bias={self.bias is not None})')


class HeteroLinear(torch.nn.Module):
    r"""Applies separate linear tranformations to the incoming data according
    to types

    .. math::
        \mathbf{x}^{\prime}_{\kappa} = \mathbf{x}_{\kappa}
        \mathbf{W}^{\top}_{\kappa} + \mathbf{b}_{\kappa}

    for type :math:`\kappa`.
    It supports lazy initialization and customizable weight and bias
    initialization.

    Args:
        in_channels (int): Size of each input sample. Will be initialized
            lazily in case it is given as :obj:`-1`.
        out_channels (int): Size of each output sample.
        num_types (int): The number of types.
        is_sorted (bool, optional): If set to :obj:`True`, assumes that
            :obj:`type_vec` is sorted. This avoids internal re-sorting of the
            data and can improve runtime and memory efficiency.
            (default: :obj:`False`)
        **kwargs (optional): Additional arguments of
            :class:`torch_geometric.nn.Linear`.

    Shapes:
        - **input:**
          features :math:`(*, F_{in})`,
          type vector :math:`(*)`
        - **output:** features :math:`(*, F_{out})`
    """
    def __init__(self, in_channels: int, out_channels: int, num_types: int,
                 is_sorted: bool = False, **kwargs):
        super().__init__()

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.num_types = num_types
        self.is_sorted = is_sorted
        self.kwargs = kwargs

        if torch_geometric.typing.WITH_PYG_LIB:
            self.lins = None
            if self.in_channels == -1:
                self.weight = nn.parameter.UninitializedParameter()
                self._hook = self.register_forward_pre_hook(
                    self.initialize_parameters)
            else:
                self.weight = torch.nn.Parameter(
                    torch.Tensor(num_types, in_channels, out_channels))
            if kwargs.get('bias', True):
                self.bias = Parameter(torch.Tensor(num_types, out_channels))
            else:
                self.register_parameter('bias', None)
        else:
            self.lins = torch.nn.ModuleList([
                Linear(in_channels, out_channels, **kwargs)
                for _ in range(num_types)
            ])
            self.register_parameter('weight', None)
            self.register_parameter('bias', None)

        self.reset_parameters()

    def reset_parameters(self):
        r"""Resets all learnable parameters of the module."""
        if torch_geometric.typing.WITH_PYG_LIB:
            reset_weight_(self.weight, self.in_channels,
                          self.kwargs.get('weight_initializer', None))
            reset_weight_(self.bias, self.in_channels,
                          self.kwargs.get('bias_initializer', None))
        else:
            for lin in self.lins:
                lin.reset_parameters()

    def forward(self, x: Tensor, type_vec: Tensor) -> Tensor:
        r"""
        Args:
            x (torch.Tensor): The input features.
            type_vec (torch.Tensor): A vector that maps each entry to a type.
        """
        if torch_geometric.typing.WITH_PYG_LIB:
            assert self.weight is not None

            perm: Optional[Tensor] = None
            if not self.is_sorted:
                if (type_vec[1:] < type_vec[:-1]).any():
                    type_vec, perm = index_sort(type_vec, self.num_types)
                    x = x[perm]

            type_vec_ptr = index2ptr(type_vec, self.num_types)
            out = pyg_lib.ops.segment_matmul(x, type_vec_ptr, self.weight)
            if self.bias is not None:
                out += self.bias[type_vec]

            if perm is not None:  # Restore original order (if necessary).
                out_unsorted = torch.empty_like(out)
                out_unsorted[perm] = out
                out = out_unsorted
        else:
            assert self.lins is not None
            out = x.new_empty(x.size(0), self.out_channels)
            for i, lin in enumerate(self.lins):
                mask = type_vec == i
                out[mask] = lin(x[mask])
        return out

    @torch.no_grad()
    def initialize_parameters(self, module, input):
        if is_uninitialized_parameter(self.weight):
            self.in_channels = input[0].size(-1)
            self.weight.materialize(
                (self.num_types, self.in_channels, self.out_channels))
            self.reset_parameters()
        self._hook.remove()
        delattr(self, '_hook')

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.in_channels}, '
                f'{self.out_channels}, num_types={self.num_types}, '
                f'bias={self.kwargs.get("bias", True)})')


class HeteroDictLinear(torch.nn.Module):
    r"""Applies separate linear tranformations to the incoming data dictionary

    .. math::
        \mathbf{x}^{\prime}_{\kappa} = \mathbf{x}_{\kappa}
        \mathbf{W}^{\top}_{\kappa} + \mathbf{b}_{\kappa}

    for key :math:`\kappa`.
    It supports lazy initialization and customizable weight and bias
    initialization.

    Args:
        in_channels (int or Dict[Any, int]): Size of each input sample. If
            passed an integer, :obj:`types` will be a mandatory argument.
            initialized lazily in case it is given as :obj:`-1`.
        out_channels (int): Size of each output sample.
        types (List[Any], optional): The keys of the input dictionary.
            (default: :obj:`None`)
        **kwargs (optional): Additional arguments of
            :class:`torch_geometric.nn.Linear`.
    """
    def __init__(
        self,
        in_channels: Union[int, Dict[Any, int]],
        out_channels: int,
        types: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__()

        if isinstance(in_channels, dict):
            self.types = list(in_channels.keys())

            if any([i == -1 for i in in_channels.values()]):
                self._hook = self.register_forward_pre_hook(
                    self.initialize_parameters)

            if types is not None and set(self.types) != set(types):
                raise ValueError("The provided 'types' do not match with the "
                                 "keys in the 'in_channels' dictionary")

        else:
            if types is None:
                raise ValueError("Please provide a list of 'types' if passing "
                                 "'in_channels' as an integer")

            if in_channels == -1:
                self._hook = self.register_forward_pre_hook(
                    self.initialize_parameters)

            self.types = types
            in_channels = {node_type: in_channels for node_type in types}

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kwargs = kwargs

        self.lins = torch.nn.ModuleDict({
            key: Linear(channels, self.out_channels, **kwargs)
            for key, channels in self.in_channels.items()
        })

        self.reset_parameters()

    def reset_parameters(self):
        r"""Resets all learnable parameters of the module."""
        for lin in self.lins.values():
            lin.reset_parameters()

    def forward(
        self,
        x_dict: Dict[Any, Tensor],
    ) -> Dict[Any, Tensor]:
        r"""
        Args:
            x_dict (Dict[Any, torch.Tensor]): A dictionary holding input
                features for each individual type.
        """
        if torch_geometric.typing.WITH_GMM:
            xs = [x_dict[key] for key in x_dict.keys()]
            weights = [self.lins[key].weight.t() for key in x_dict.keys()]
            if self.kwargs.get('bias', True):
                biases = [self.lins[key].bias for key in x_dict.keys()]
            else:
                biases = None

            outs = pyg_lib.ops.grouped_matmul(xs, weights, biases)
            return {key: out for key, out in zip(x_dict.keys(), outs)}

        return {key: self.lins[key](x) for key, x in x_dict.items()}

    @torch.no_grad()
    def initialize_parameters(self, module, input):
        for key, x in input[0].items():
            lin = self.lins[key]
            if is_uninitialized_parameter(lin.weight):
                self.lins[key].initialize_parameters(None, x)
        self.reset_parameters()
        self._hook.remove()
        self.in_channels = {key: x.size(-1) for key, x in input[0].items()}
        delattr(self, '_hook')

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.in_channels}, '
                f'{self.out_channels}, bias={self.kwargs.get("bias", True)})')
