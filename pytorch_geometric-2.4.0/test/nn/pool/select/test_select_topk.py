from itertools import product

import pytest
import torch

from torch_geometric.nn.pool.select import SelectOutput, SelectTopK
from torch_geometric.nn.pool.select.topk import topk
from torch_geometric.profile import benchmark
from torch_geometric.testing import is_full_test


def test_topk_ratio():
    x = torch.tensor([2.0, 4.0, 5.0, 6.0, 2.0, 9.0])
    batch = torch.tensor([0, 0, 1, 1, 1, 1])

    perm1 = topk(x, 0.5, batch)
    assert perm1.tolist() == [1, 5, 3]
    assert x[perm1].tolist() == [4.0, 9.0, 6.0]
    assert batch[perm1].tolist() == [0, 1, 1]

    perm2 = topk(x, 2, batch)
    assert perm2.tolist() == [1, 0, 5, 3]
    assert x[perm2].tolist() == [4.0, 2.0, 9.0, 6.0]
    assert batch[perm2].tolist() == [0, 0, 1, 1]

    perm3 = topk(x, 3, batch)
    assert perm3.tolist() == [1, 0, 5, 3, 2]
    assert x[perm3].tolist() == [4.0, 2.0, 9.0, 6.0, 5.0]
    assert batch[perm3].tolist() == [0, 0, 1, 1, 1]

    if is_full_test():
        jit = torch.jit.script(topk)
        assert torch.equal(jit(x, 0.5, batch), perm1)
        assert torch.equal(jit(x, 2, batch), perm2)
        assert torch.equal(jit(x, 3, batch), perm3)


@pytest.mark.parametrize('min_score', [None, 2.0])
def test_select_topk(min_score):
    x = torch.randn(6, 16)
    batch = torch.tensor([0, 0, 1, 1, 1, 1])

    pool = SelectTopK(16, min_score=min_score)

    if min_score is None:
        assert str(pool) == 'SelectTopK(16, ratio=0.5)'
    else:
        assert str(pool) == 'SelectTopK(16, min_score=2.0)'

    out = pool(x, batch)
    assert isinstance(out, SelectOutput)

    assert out.num_nodes == 6
    assert out.num_clusters <= out.num_nodes
    assert out.node_index.min() >= 0
    assert out.node_index.max() < out.num_nodes
    assert out.cluster_index.min() == 0
    assert out.cluster_index.max() == out.num_clusters - 1


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--device', type=str, default='cuda')
    args = parser.parse_args()

    BS = [2**i for i in range(6, 8)]
    NS = [2**i for i in range(8, 16)]

    funcs = []
    func_names = []
    args_list = []
    for B, N in product(BS, NS):
        x = torch.randn(N, device=args.device)
        batch = torch.randint(0, B, (N, ), device=args.device).sort()[0]

        funcs.append(topk)
        func_names.append(f'B={B}, N={N}')
        args_list.append((x, 0.5, batch))

    benchmark(
        funcs=funcs,
        func_names=func_names,
        args=args_list,
        num_steps=50 if args.device == 'cpu' else 500,
        num_warmups=10 if args.device == 'cpu' else 100,
        progress_bar=True,
    )
