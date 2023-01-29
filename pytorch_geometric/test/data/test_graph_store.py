import pytest
import torch
from torch_sparse import SparseTensor

from torch_geometric.testing import MyGraphStore


def get_edge_index(num_src_nodes, num_dst_nodes, num_edges):
    row = torch.randint(num_src_nodes, (num_edges, ), dtype=torch.long)
    col = torch.randint(num_dst_nodes, (num_edges, ), dtype=torch.long)
    return row, col


def test_graph_store():
    graph_store = MyGraphStore()

    coo = torch.tensor([0, 1]), torch.tensor([1, 2])
    csr = torch.tensor([0, 1, 2]), torch.tensor([1, 2])
    csc = torch.tensor([0, 1]), torch.tensor([0, 0, 1, 2])

    graph_store['edge_type', 'coo'] = coo
    graph_store['edge_type', 'csr'] = csr
    graph_store['edge_type', 'csc'] = csc

    assert torch.equal(graph_store['edge_type', 'coo'][0], coo[0])
    assert torch.equal(graph_store['edge_type', 'coo'][1], coo[1])
    assert torch.equal(graph_store['edge_type', 'csr'][0], csr[0])
    assert torch.equal(graph_store['edge_type', 'csr'][1], csr[1])
    assert torch.equal(graph_store['edge_type', 'csc'][0], csc[0])
    assert torch.equal(graph_store['edge_type', 'csc'][1], csc[1])

    assert len(graph_store.get_all_edge_attrs()) == 3

    with pytest.raises(KeyError):
        graph_store['edge_type_2', 'coo']


def test_graph_store_conversion():
    graph_store = MyGraphStore()

    coo = (row, col) = get_edge_index(100, 100, 300)
    adj = SparseTensor(row=row, col=col, sparse_sizes=(100, 100))
    csr, csc = adj.csr()[:2], adj.csc()[:2][::-1]

    graph_store.put_edge_index(coo, ('v', '1', 'v'), 'coo', size=(100, 100))
    graph_store.put_edge_index(csr, ('v', '2', 'v'), 'csr', size=(100, 100))
    graph_store.put_edge_index(csc, ('v', '3', 'v'), 'csc', size=(100, 100))

    # Convert to COO:
    row_dict, col_dict, perm_dict = graph_store.coo()
    assert len(row_dict) == len(col_dict) == len(perm_dict) == 3
    for row, col, perm in zip(row_dict.values(), col_dict.values(),
                              perm_dict.values()):
        assert torch.equal(row.sort()[0], coo[0].sort()[0])
        assert torch.equal(col.sort()[0], coo[1].sort()[0])
        assert perm is None

    # Convert to CSR:
    row_dict, col_dict, perm_dict = graph_store.csr()
    assert len(row_dict) == len(col_dict) == len(perm_dict) == 3
    for row, col in zip(row_dict.values(), col_dict.values()):
        assert torch.equal(row, csr[0])
        assert torch.equal(col.sort()[0], csr[1].sort()[0])

    # Convert to CSC:
    row_dict, col_dict, perm_dict = graph_store.csc()
    assert len(row_dict) == len(col_dict) == len(perm_dict) == 3
    for row, col in zip(row_dict.values(), col_dict.values()):
        assert torch.equal(row.sort()[0], csc[0].sort()[0])
        assert torch.equal(col, csc[1])

    # Ensure that 'edge_types' parameters work as intended:
    out = graph_store.coo([('v', '1', 'v')])
    assert torch.equal(list(out[0].values())[0], coo[0])
    assert torch.equal(list(out[1].values())[0], coo[1])
