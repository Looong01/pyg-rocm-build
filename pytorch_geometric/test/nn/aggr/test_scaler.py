import pytest
import torch

from torch_geometric.nn import DegreeScalerAggregation


def test_degree_scaler_aggregation():
    x = torch.randn(6, 16)
    index = torch.tensor([0, 0, 1, 1, 1, 2])
    ptr = torch.tensor([0, 2, 5, 6])
    deg = torch.tensor([0, 3, 0, 1, 1, 0])

    aggr = ['mean', 'sum', 'max']
    scaler = [
        'identity', 'amplification', 'attenuation', 'linear', 'inverse_linear'
    ]
    aggr = DegreeScalerAggregation(aggr, scaler, deg)
    assert str(aggr) == 'DegreeScalerAggregation()'

    out = aggr(x, index)
    assert out.size() == (3, 240)
    assert torch.allclose(torch.jit.script(aggr)(x, index), out)

    with pytest.raises(NotImplementedError):
        aggr(x, ptr=ptr)
