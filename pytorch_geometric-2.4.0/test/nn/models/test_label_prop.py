import torch

import torch_geometric.typing
from torch_geometric.nn.models import LabelPropagation
from torch_geometric.typing import SparseTensor


def test_label_prop():
    y = torch.tensor([1, 0, 0, 2, 1, 1])
    edge_index = torch.tensor([[0, 1, 1, 2, 4, 5], [1, 0, 2, 1, 5, 4]])
    mask = torch.randint(0, 2, (6, ), dtype=torch.bool)

    model = LabelPropagation(num_layers=2, alpha=0.5)
    assert str(model) == 'LabelPropagation(num_layers=2, alpha=0.5)'

    # Test without mask:
    out = model(y, edge_index)
    assert out.size() == (6, 3)
    if torch_geometric.typing.WITH_TORCH_SPARSE:
        adj = SparseTensor.from_edge_index(edge_index, sparse_sizes=(6, 6))
        assert torch.allclose(model(y, adj.t()), out)

    # Test with mask:
    out = model(y, edge_index, mask)
    assert out.size() == (6, 3)
    if torch_geometric.typing.WITH_TORCH_SPARSE:
        assert torch.allclose(model(y, adj.t(), mask), out)

    # Test post step:
    out = model(y, edge_index, mask, post_step=lambda y: torch.zeros_like(y))
    assert torch.sum(out) == 0.
