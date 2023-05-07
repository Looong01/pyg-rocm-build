import torch
from torch_sparse import SparseTensor

from torch_geometric.nn import GraphConv
from torch_geometric.testing import is_full_test


def test_graph_conv():
    x1 = torch.randn(4, 8)
    x2 = torch.randn(2, 16)
    edge_index = torch.tensor([[0, 1, 2, 3], [0, 0, 1, 1]])
    row, col = edge_index
    value = torch.randn(edge_index.size(1))
    adj1 = SparseTensor(row=row, col=col, sparse_sizes=(4, 4))
    adj2 = SparseTensor(row=row, col=col, value=value, sparse_sizes=(4, 4))
    adj3 = adj1.to_torch_sparse_csc_tensor()
    adj4 = adj2.to_torch_sparse_csc_tensor()

    conv = GraphConv(8, 32)
    assert str(conv) == 'GraphConv(8, 32)'
    out11 = conv(x1, edge_index)
    assert out11.size() == (4, 32)
    assert torch.allclose(conv(x1, edge_index, size=(4, 4)), out11, atol=1e-6)
    assert torch.allclose(conv(x1, adj1.t()), out11, atol=1e-6)
    assert torch.allclose(conv(x1, adj3.t()), out11, atol=1e-6)

    out12 = conv(x1, edge_index, value)
    assert out12.size() == (4, 32)
    assert torch.allclose(conv(x1, edge_index, value, size=(4, 4)), out12,
                          atol=1e-6)
    assert torch.allclose(conv(x1, adj2.t()), out12, atol=1e-6)
    assert torch.allclose(conv(x1, adj4.t()), out12, atol=1e-6)

    if is_full_test():
        t = '(Tensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, edge_index), out11)
        assert torch.allclose(jit(x1, edge_index, size=(4, 4)), out11)
        assert torch.allclose(jit(x1, edge_index, value), out12)
        assert torch.allclose(jit(x1, edge_index, value, size=(4, 4)), out12)

        t = '(Tensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x1, adj1.t()), out11)
        assert torch.allclose(jit(x1, adj2.t()), out12)

    adj1 = adj1.sparse_resize((4, 2))
    adj2 = adj2.sparse_resize((4, 2))
    adj3 = adj1.to_torch_sparse_csc_tensor()
    adj4 = adj2.to_torch_sparse_csc_tensor()
    conv = GraphConv((8, 16), 32)
    assert str(conv) == 'GraphConv((8, 16), 32)'
    out21 = conv((x1, x2), edge_index)
    out22 = conv((x1, x2), edge_index, value)
    out23 = conv((x1, None), edge_index, size=(4, 2))
    out24 = conv((x1, None), edge_index, value, size=(4, 2))
    assert out21.size() == (2, 32)
    assert out22.size() == (2, 32)
    assert out23.size() == (2, 32)
    assert out24.size() == (2, 32)
    assert torch.allclose(conv((x1, x2), edge_index, size=(4, 2)), out21,
                          atol=1e-6)
    assert torch.allclose(conv((x1, x2), edge_index, value, (4, 2)), out22,
                          atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj1.t()), out21, atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj2.t()), out22, atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj3.t()), out21, atol=1e-6)
    assert torch.allclose(conv((x1, x2), adj4.t()), out22, atol=1e-6)

    if is_full_test():
        t = '(OptPairTensor, Tensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), edge_index), out21)
        assert torch.allclose(jit((x1, x2), edge_index, size=(4, 2)), out21)
        assert torch.allclose(jit((x1, x2), edge_index, value), out22)
        assert torch.allclose(jit((x1, x2), edge_index, value, (4, 2)), out22)
        assert torch.allclose(jit((x1, None), edge_index, size=(4, 2)), out23)
        assert torch.allclose(jit((x1, None), edge_index, value, (4, 2)),
                              out24)

        t = '(OptPairTensor, SparseTensor, OptTensor, Size) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit((x1, x2), adj1.t()), out21, atol=1e-6)
        assert torch.allclose(jit((x1, x2), adj2.t()), out22, atol=1e-6)
        assert torch.allclose(jit((x1, None), adj1.t()), out23, atol=1e-6)
        assert torch.allclose(jit((x1, None), adj2.t()), out24, atol=1e-6)
