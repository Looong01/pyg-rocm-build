import copy

import pytest
import torch
from torch_sparse import SparseTensor

from torch_geometric.data import Data, HeteroData, InMemoryDataset


class MyTestDataset(InMemoryDataset):
    def __init__(self, data_list, transform=None):
        super().__init__('/tmp/MyTestDataset', transform=transform)
        self.data, self.slices = self.collate(data_list)


def test_in_memory_dataset():
    x1 = torch.Tensor([[1], [1], [1]])
    x2 = torch.Tensor([[2], [2], [2]])
    edge_index = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]])
    face = torch.tensor([[0], [1], [2]])

    data1 = Data(x1, edge_index, face=face, test_int=1, test_str='1')
    data1.num_nodes = 10

    data2 = Data(x2, edge_index, face=face, test_int=2, test_str='2')
    data2.num_nodes = 5

    dataset = MyTestDataset([data1, data2])
    assert str(dataset) == 'MyTestDataset(2)'
    assert len(dataset) == 2

    assert len(dataset[0]) == 6
    assert dataset[0].num_nodes == 10
    assert dataset[0].x.tolist() == x1.tolist()
    assert dataset[0].edge_index.tolist() == edge_index.tolist()
    assert dataset[0].face.tolist() == face.tolist()
    assert dataset[0].test_int == 1
    assert dataset[0].test_str == '1'

    assert len(dataset[1]) == 6
    assert dataset[1].num_nodes == 5
    assert dataset[1].x.tolist() == x2.tolist()
    assert dataset[1].edge_index.tolist() == edge_index.tolist()
    assert dataset[1].face.tolist() == face.tolist()
    assert dataset[1].test_int == 2
    assert dataset[1].test_str == '2'

    with pytest.warns(UserWarning, match="internal storage format"):
        dataset.data

    assert torch.equal(dataset.x, torch.cat([x1, x2], dim=0))
    assert dataset.edge_index.tolist() == [
        [0, 1, 1, 2, 10, 11, 11, 12],
        [1, 0, 2, 1, 11, 10, 12, 11],
    ]
    assert torch.equal(dataset[1:].x, x2)


def test_in_memory_num_classes():
    dataset = MyTestDataset([Data(), Data()])
    assert dataset.num_classes == 0

    dataset = MyTestDataset([Data(y=0), Data(y=1)])
    assert dataset.num_classes == 2

    dataset = MyTestDataset([Data(y=1.5), Data(y=2.5), Data(y=3.5)])
    assert dataset.num_classes == 3

    dataset = MyTestDataset([
        Data(y=torch.tensor([[0, 1, 0, 1]])),
        Data(y=torch.tensor([[1, 0, 0, 0]])),
        Data(y=torch.tensor([[0, 0, 1, 0]])),
    ])
    assert dataset.num_classes == 4

    # Test when `__getitem__` returns a tuple of data objects.
    def transform(data):
        copied_data = copy.copy(data)
        copied_data.y += 1
        return data, copied_data, 'foo'

    dataset = MyTestDataset([Data(y=0), Data(y=1)], transform=transform)
    assert dataset.num_classes == 3


def test_in_memory_dataset_copy():
    data_list = [Data(x=torch.randn(5, 16)) for _ in range(4)]
    dataset = MyTestDataset(data_list)

    copied_dataset = dataset.copy()
    assert id(copied_dataset) != id(dataset)

    assert len(copied_dataset) == len(dataset) == 4
    for copied_data, data in zip(copied_dataset, dataset):
        assert torch.equal(copied_data.x, data.x)

    copied_dataset = dataset.copy([1, 2])
    assert len(copied_dataset) == 2
    assert torch.equal(copied_dataset[0].x, data_list[1].x)
    assert torch.equal(copied_dataset[1].x, data_list[2].x)


def test_to_datapipe():
    x = torch.randn(3, 8)
    edge_index = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]])
    data = Data(x=x, edge_index=edge_index)
    dataset = MyTestDataset([data, data])

    dp = dataset.to_datapipe()

    assert isinstance(dp, torch.utils.data.IterDataPipe)
    assert len(dp) == 2

    assert torch.equal(dataset[0].x, list(dp)[0].x)
    assert torch.equal(dataset[0].edge_index, list(dp)[0].edge_index)
    assert torch.equal(dataset[1].x, list(dp)[1].x)
    assert torch.equal(dataset[1].edge_index, list(dp)[1].edge_index)


def test_in_memory_sparse_tensor_dataset():
    x = torch.randn(11, 16)
    adj = SparseTensor(
        row=torch.tensor([4, 1, 3, 2, 2, 3]),
        col=torch.tensor([1, 3, 2, 3, 3, 2]),
        sparse_sizes=(11, 11),
    )
    data = Data(x=x, adj=adj)

    dataset = MyTestDataset([data, data])
    assert len(dataset) == 2
    assert torch.allclose(dataset[0].x, x)
    assert dataset[0].adj.sparse_sizes() == (11, 11)
    assert torch.allclose(dataset[1].x, x)
    assert dataset[1].adj.sparse_sizes() == (11, 11)


def test_collate_with_new_dimension():
    class MyData(Data):
        def __cat_dim__(self, key, value, *args, **kwargs):
            if key == 'foo':
                return None
            else:
                return super().__cat_dim__(key, value, *args, **kwargs)

    x = torch.tensor([1, 2, 3], dtype=torch.float)
    foo = torch.randn(4)
    y = torch.tensor(1)

    data = MyData(x=x, foo=foo, y=y)

    dataset = MyTestDataset([data, data])
    assert str(dataset) == 'MyTestDataset(2)'
    assert len(dataset) == 2

    data1 = dataset[0]
    assert len(data1) == 3
    assert data1.x.tolist() == x.tolist()
    assert data1.foo.tolist() == foo.tolist()
    assert data1.y.tolist() == [1]

    data2 = dataset[0]
    assert len(data2) == 3
    assert data2.x.tolist() == x.tolist()
    assert data2.foo.tolist() == foo.tolist()
    assert data2.y.tolist() == [1]


def test_hetero_in_memory_dataset():
    data1 = HeteroData()
    data1.y = torch.randn(5)
    data1['paper'].x = torch.randn(10, 16)
    data1['paper', 'paper'].edge_index = torch.randint(0, 10, (2, 30)).long()

    data2 = HeteroData()
    data2.y = torch.randn(5)
    data2['paper'].x = torch.randn(10, 16)
    data2['paper', 'paper'].edge_index = torch.randint(0, 10, (2, 30)).long()

    dataset = MyTestDataset([data1, data2])
    assert str(dataset) == 'MyTestDataset(2)'
    assert len(dataset) == 2

    assert len(dataset[0]) == 3
    assert dataset[0].y.tolist() == data1.y.tolist()
    assert dataset[0]['paper'].x.tolist() == data1['paper'].x.tolist()
    assert (dataset[0]['paper', 'paper'].edge_index.tolist() == data1[
        'paper', 'paper'].edge_index.tolist())

    assert len(dataset[1]) == 3
    assert dataset[1].y.tolist() == data2.y.tolist()
    assert dataset[1]['paper'].x.tolist() == data2['paper'].x.tolist()
    assert (dataset[1]['paper', 'paper'].edge_index.tolist() == data2[
        'paper', 'paper'].edge_index.tolist())


def test_override_behavior():
    class DS1(InMemoryDataset):
        def __init__(self):
            self.enter_download = False
            self.enter_process = False
            super().__init__()

        def _download(self):
            self.enter_download = True

        def _process(self):
            self.enter_process = True

        def download(self):
            pass

        def process(self):
            pass

    class DS2(InMemoryDataset):
        def __init__(self):
            self.enter_download = False
            self.enter_process = False
            super().__init__()

        def _download(self):
            self.enter_download = True

        def _process(self):
            self.enter_process = True

        def process(self):
            pass

    class DS3(InMemoryDataset):
        def __init__(self):
            self.enter_download = False
            self.enter_process = False
            super().__init__()

        def _download(self):
            self.enter_download = True

        def _process(self):
            self.enter_process = True

    class DS4(DS1):
        pass

    ds = DS1()
    assert ds.enter_download
    assert ds.enter_process

    ds = DS2()
    assert not ds.enter_download
    assert ds.enter_process

    ds = DS3()
    assert not ds.enter_download
    assert not ds.enter_process

    ds = DS4()
    assert ds.enter_download
    assert ds.enter_process


def test_lists_of_tensors_in_memory_dataset():
    def tr(n, m):
        return torch.rand((n, m))

    d1 = Data(xs=[tr(4, 3), tr(11, 4), tr(1, 2)])
    d2 = Data(xs=[tr(5, 3), tr(14, 4), tr(3, 2)])
    d3 = Data(xs=[tr(6, 3), tr(15, 4), tr(2, 2)])
    d4 = Data(xs=[tr(4, 3), tr(16, 4), tr(1, 2)])

    data_list = [d1, d2, d3, d4]

    dataset = MyTestDataset(data_list)
    assert len(dataset) == 4
    assert dataset[0].xs[1].size() == (11, 4)
    assert dataset[0].xs[2].size() == (1, 2)
    assert dataset[1].xs[0].size() == (5, 3)
    assert dataset[2].xs[1].size() == (15, 4)
    assert dataset[3].xs[1].size() == (16, 4)


def test_lists_of_SparseTensors():
    e1 = torch.tensor([[4, 1, 3, 2, 2, 3], [1, 3, 2, 3, 3, 2]])
    e2 = torch.tensor([[0, 1, 4, 7, 2, 9], [7, 2, 2, 1, 4, 7]])
    e3 = torch.tensor([[3, 5, 1, 2, 3, 3], [5, 0, 2, 1, 3, 7]])
    e4 = torch.tensor([[0, 1, 9, 2, 0, 3], [1, 1, 2, 1, 3, 2]])
    adj1 = SparseTensor.from_edge_index(e1, sparse_sizes=(11, 11))
    adj2 = SparseTensor.from_edge_index(e2, sparse_sizes=(22, 22))
    adj3 = SparseTensor.from_edge_index(e3, sparse_sizes=(12, 12))
    adj4 = SparseTensor.from_edge_index(e4, sparse_sizes=(15, 15))

    d1 = Data(adj_test=[adj1, adj2])
    d2 = Data(adj_test=[adj3, adj4])

    data_list = [d1, d2]
    dataset = MyTestDataset(data_list)
    assert len(dataset) == 2
    assert dataset[0].adj_test[0].sparse_sizes() == (11, 11)
    assert dataset[0].adj_test[1].sparse_sizes() == (22, 22)
    assert dataset[1].adj_test[0].sparse_sizes() == (12, 12)
    assert dataset[1].adj_test[1].sparse_sizes() == (15, 15)


def test_file_names_as_property_and_method():
    class MyTestDataset(InMemoryDataset):
        def __init__(self):
            super().__init__('/tmp/MyTestDataset')

        @property
        def raw_file_names(self):
            return ['test_file']

        def download(self):
            pass

    MyTestDataset()

    class MyTestDataset(InMemoryDataset):
        def __init__(self):
            super().__init__('/tmp/MyTestDataset')

        def raw_file_names(self):
            return ['test_file']

        def download(self):
            pass

    MyTestDataset()
