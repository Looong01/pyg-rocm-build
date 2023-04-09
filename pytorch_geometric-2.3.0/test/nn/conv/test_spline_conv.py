import warnings

import torch
from torch_sparse import SparseTensor

from torch_geometric.nn import SplineConv
from torch_geometric.testing import is_full_test, withPackage


@withPackage('torch_spline_conv')
def test_spline_conv():
    warnings.filterwarnings('ignore', '.*non-optimized CPU version.*')

    x1 = torch.randn(4, 8)
    x2 = torch.randn(2, 16)
    edge_index = torch.tensor([[0, 1, 2, 3], [0, 0, 1, 1]])
    row, col = edge_index
    value = torch.rand(row.size(0), 3)
    adj = SparseTensor(row=row, col=col, value=value, sparse_sizes=(4, 4))

    conv = SplineConv(8, 32, dim=3, kernel_size=5)
    assert str(conv) == 'SplineConv(8, 32, dim=3)'
    out = conv(x1, edge_index, value)
    assert out.size() == (4, 32)
    assert torch.allclose(conv(x1, edge_index, value, size=(4, 4)), out)
    assert torch.allclose(conv(x1, adj.t()), out)

    if is_full_test():
        t = '(Tensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, edge_index, value), out)
        assert torch.allclose(jit(x1, edge_index, value, size=(4, 4)), out)

        t = '(Tensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, adj.t()), out)

    adj = adj.sparse_resize((4, 2))
    conv = SplineConv((8, 16), 32, dim=3, kernel_size=5)
    assert str(conv) == 'SplineConv((8, 16), 32, dim=3)'
    out1 = conv((x1, x2), edge_index, value)
    out2 = conv((x1, None), edge_index, value, (4, 2))
    assert out1.size() == (2, 32)
    assert out2.size() == (2, 32)
    assert torch.allclose(conv((x1, x2), edge_index, value, (4, 2)), out1)
    assert torch.allclose(conv((x1, x2), adj.t()), out1)
    assert torch.allclose(conv((x1, None), adj.t()), out2)

    if is_full_test():
        t = '(OptPairTensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), edge_index, value), out1)
        assert torch.allclose(jit((x1, x2), edge_index, value, size=(4, 2)),
                              out1)
        assert torch.allclose(jit((x1, None), edge_index, value, size=(4, 2)),
                              out2)

        t = '(OptPairTensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), adj.t()), out1)
        assert torch.allclose(jit((x1, None), adj.t()), out2)


@withPackage('torch_spline_conv')
def test_lazy_spline_conv():
    warnings.filterwarnings('ignore', '.*non-optimized CPU version.*')

    x1 = torch.randn(4, 8)
    x2 = torch.randn(2, 16)
    edge_index = torch.tensor([[0, 1, 2, 3], [0, 0, 1, 1]])
    value = torch.rand(edge_index.size(1), 3)

    conv = SplineConv(-1, 32, dim=3, kernel_size=5)
    assert str(conv) == 'SplineConv(-1, 32, dim=3)'
    out = conv(x1, edge_index, value)
    assert out.size() == (4, 32)

    conv = SplineConv((-1, -1), 32, dim=3, kernel_size=5)
    assert str(conv) == 'SplineConv((-1, -1), 32, dim=3)'
    out = conv((x1, x2), edge_index, value)
    assert out.size() == (2, 32)
