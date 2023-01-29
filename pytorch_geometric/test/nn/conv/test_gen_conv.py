import pytest
import torch
from torch_sparse import SparseTensor

from torch_geometric.nn import GENConv
from torch_geometric.testing import is_full_test


@pytest.mark.parametrize('aggr', ['softmax', 'powermean'])
def test_gen_conv(aggr):
    x1 = torch.randn(4, 16)
    x2 = torch.randn(2, 16)
    edge_index = torch.tensor([[0, 1, 2, 3], [0, 0, 1, 1]])
    row, col = edge_index
    value = torch.randn(row.size(0), 16)
    adj1 = SparseTensor(row=row, col=col, sparse_sizes=(4, 4))
    adj2 = SparseTensor(row=row, col=col, value=value, sparse_sizes=(4, 4))

    conv = GENConv(16, 32, aggr, edge_dim=16)
    assert conv.__repr__() == f'GENConv(16, 32, aggr={aggr})'
    out11 = conv(x1, edge_index)
    assert out11.size() == (4, 32)
    assert torch.allclose(conv(x1, edge_index, size=(4, 4)), out11, atol=1e-6)
    assert torch.allclose(conv(x1, adj1.t()), out11, atol=1e-6)

    out12 = conv(x1, edge_index, value)
    assert out12.size() == (4, 32)
    assert torch.allclose(conv(x1, edge_index, value, (4, 4)), out12,
                          atol=1e-6)
    assert torch.allclose(conv(x1, adj2.t()), out12, atol=1e-6)

    if is_full_test():
        t = '(Tensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, edge_index), out11, atol=1e-6)
        assert torch.allclose(jit(x1, edge_index, size=(4, 4)), out11,
                              atol=1e-6)
        assert torch.allclose(jit(x1, edge_index, value), out12, atol=1e-6)
        assert torch.allclose(jit(x1, edge_index, value, size=(4, 4)), out12,
                              atol=1e-6)

        t = '(Tensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, adj1.t()), out11, atol=1e-6)
        assert torch.allclose(jit(x1, adj2.t()), out12, atol=1e-6)

    adj1 = adj1.sparse_resize((4, 2))
    adj2 = adj2.sparse_resize((4, 2))

    out21 = conv((x1, x2), edge_index)
    assert out21.size() == (2, 32)
    assert torch.allclose(conv((x1, x2), edge_index, size=(4, 2)), out21,
                          atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj1.t()), out21, atol=1e-6)

    out22 = conv((x1, x2), edge_index, value)
    assert out22.size() == (2, 32)
    assert torch.allclose(conv((x1, x2), edge_index, value, (4, 2)), out22,
                          atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj2.t()), out22, atol=1e-6)

    if is_full_test():
        t = '(OptPairTensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), edge_index), out21, atol=1e-6)
        assert torch.allclose(jit((x1, x2), edge_index, size=(4, 2)), out21,
                              atol=1e-6)
        assert torch.allclose(jit((x1, x2), edge_index, value), out22,
                              atol=1e-6)
        assert torch.allclose(jit((x1, x2), edge_index, value, (4, 2)), out22,
                              atol=1e-6)

        t = '(OptPairTensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), adj1.t()), out21, atol=1e-6)
        assert torch.allclose(jit((x1, x2), adj2.t()), out22, atol=1e-6)

    x1 = torch.randn(4, 8)
    x2 = torch.randn(2, 16)
    adj = adj1.sparse_resize((4, 2))
    conv = GENConv((8, 16), 32, aggr)
    assert str(conv) == f'GENConv((8, 16), 32, aggr={aggr})'
    out1 = conv((x1, x2), edge_index)
    out2 = conv((x1, None), edge_index, size=(4, 2))
    assert out1.size() == (2, 32)
    assert out2.size() == (2, 32)
    assert conv((x1, x2), edge_index, size=(4, 2)).tolist() == out1.tolist()
    assert conv((x1, x2), adj.t()).tolist() == out1.tolist()
    assert conv((x1, None), adj.t()).tolist() == out2.tolist()

    value = torch.randn(row.size(0), 4)
    adj = SparseTensor(row=row, col=col, value=value, sparse_sizes=(4, 2))
    conv = GENConv((-1, -1), 32, aggr, edge_dim=-1)
    assert str(conv) == f'GENConv((-1, -1), 32, aggr={aggr})'
    out1 = conv((x1, x2), edge_index, value)
    out2 = conv((x1, None), edge_index, value, size=(4, 2))
    assert out1.size() == (2, 32)
    assert out2.size() == (2, 32)
    assert conv((x1, x2), edge_index, value,
                size=(4, 2)).tolist() == out1.tolist()
    assert conv((x1, x2), adj.t()).tolist() == out1.tolist()
    assert conv((x1, None), adj.t()).tolist() == out2.tolist()

    if is_full_test():
        t = '(OptPairTensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), edge_index, value), out1,
                              atol=1e-6)
        assert torch.allclose(jit((x1, x2), edge_index, value, size=(4, 2)),
                              out1, atol=1e-6)
        assert torch.allclose(jit((x1, None), edge_index, value, size=(4, 2)),
                              out2, atol=1e-6)

        t = '(OptPairTensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), adj.t()), out1, atol=1e-6)
        assert torch.allclose(jit((x1, None), adj.t()), out2, atol=1e-6)
