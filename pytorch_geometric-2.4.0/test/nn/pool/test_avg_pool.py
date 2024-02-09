import torch

from torch_geometric.data import Batch
from torch_geometric.nn import avg_pool, avg_pool_neighbor_x, avg_pool_x
from torch_geometric.testing import is_full_test


def test_avg_pool_x():
    cluster = torch.tensor([0, 1, 0, 1, 2, 2])
    x = torch.tensor([
        [1.0, 2.0],
        [3.0, 4.0],
        [5.0, 6.0],
        [7.0, 8.0],
        [9.0, 10.0],
        [11.0, 12.0],
    ])
    batch = torch.tensor([0, 0, 0, 0, 1, 1])

    out = avg_pool_x(cluster, x, batch)
    assert out[0].tolist() == [[3, 4], [5, 6], [10, 11]]
    assert out[1].tolist() == [0, 0, 1]

    if is_full_test():
        jit = torch.jit.script(avg_pool_x)
        out = jit(cluster, x, batch)
        assert out[0].tolist() == [[3, 4], [5, 6], [10, 11]]
        assert out[1].tolist() == [0, 0, 1]

    out, _ = avg_pool_x(cluster, x, batch, size=2)
    assert out.tolist() == [[3, 4], [5, 6], [10, 11], [0, 0]]

    batch_size = int(batch.max().item()) + 1
    out2, _ = avg_pool_x(cluster, x, batch, batch_size=batch_size, size=2)
    assert torch.equal(out, out2)

    if is_full_test():
        jit = torch.jit.script(avg_pool_x)
        out, _ = jit(cluster, x, batch, size=2)
        assert out.tolist() == [[3, 4], [5, 6], [10, 11], [0, 0]]

        out2, _ = jit(cluster, x, batch, batch_size=batch_size, size=2)
        assert torch.equal(out, out2)


def test_avg_pool():
    cluster = torch.tensor([0, 1, 0, 1, 2, 2])
    x = torch.tensor([
        [1.0, 2.0],
        [3.0, 4.0],
        [5.0, 6.0],
        [7.0, 8.0],
        [9.0, 10.0],
        [11.0, 12.0],
    ])
    pos = torch.tensor([
        [0.0, 0.0],
        [1.0, 1.0],
        [2.0, 2.0],
        [3.0, 3.0],
        [4.0, 4.0],
        [5.0, 5.0],
    ])
    edge_index = torch.tensor([[0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5],
                               [1, 2, 3, 0, 2, 3, 0, 1, 3, 0, 1, 2, 5, 4]])
    edge_attr = torch.ones(edge_index.size(1))
    batch = torch.tensor([0, 0, 0, 0, 1, 1])

    data = Batch(x=x, pos=pos, edge_index=edge_index, edge_attr=edge_attr,
                 batch=batch)

    data = avg_pool(cluster, data, transform=lambda x: x)

    assert data.x.tolist() == [[3, 4], [5, 6], [10, 11]]
    assert data.pos.tolist() == [[1, 1], [2, 2], [4.5, 4.5]]
    assert data.edge_index.tolist() == [[0, 1], [1, 0]]
    assert data.edge_attr.tolist() == [4, 4]
    assert data.batch.tolist() == [0, 0, 1]


def test_avg_pool_neighbor_x():
    x = torch.tensor([
        [1.0, 2.0],
        [3.0, 4.0],
        [5.0, 6.0],
        [7.0, 8.0],
        [9.0, 10.0],
        [11.0, 12.0],
    ])
    edge_index = torch.tensor([[0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5],
                               [1, 2, 3, 0, 2, 3, 0, 1, 3, 0, 1, 2, 5, 4]])
    batch = torch.tensor([0, 0, 0, 0, 1, 1])

    data = Batch(x=x, edge_index=edge_index, batch=batch)
    data = avg_pool_neighbor_x(data)

    assert data.x.tolist() == [
        [4, 5],
        [4, 5],
        [4, 5],
        [4, 5],
        [10, 11],
        [10, 11],
    ]
    assert torch.equal(data.edge_index, edge_index)
