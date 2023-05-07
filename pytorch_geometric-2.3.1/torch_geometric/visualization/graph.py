from math import sqrt
from typing import Any, Optional

import torch
from torch import Tensor

BACKENDS = {'graphviz', 'networkx'}


def has_graphviz() -> bool:
    try:
        import graphviz
    except ImportError:
        return False

    try:
        graphviz.Digraph().pipe()
    except graphviz.backend.ExecutableNotFound:
        return False

    return True


def visualize_graph(
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
    path: Optional[str] = None,
    backend: Optional[str] = None,
) -> Any:
    r"""Visualizes the graph given via :obj:`edge_index` and (optional)
    :obj:`edge_weight`.

    Args:
        edge_index (torch.Tensor): The edge indices.
        edge_weight (torch.Tensor, optional): The edge weights.
        path (str, optional): The path to where the plot is saved.
            If set to :obj:`None`, will visualize the plot on-the-fly.
            (default: :obj:`None`)
        backend (str, optional): The graph drawing backend to use for
            visualization (:obj:`"graphviz"`, :obj:`"networkx"`).
            If set to :obj:`None`, will use the most appropriate
            visualization backend based on available system packages.
            (default: :obj:`None`)
    """
    if edge_weight is not None:  # Normalize edge weights.
        edge_weight = edge_weight - edge_weight.min()
        edge_weight = edge_weight / edge_weight.max()

    if edge_weight is not None:  # Discard any edges with zero edge weight:
        mask = edge_weight > 1e-7
        edge_index = edge_index[:, mask]
        edge_weight = edge_weight[mask]

    if edge_weight is None:
        edge_weight = torch.ones(edge_index.size(1))

    if backend is None:
        backend = 'graphviz' if has_graphviz() else 'networkx'

    if backend.lower() == 'networkx':
        return _visualize_graph_via_networkx(edge_index, edge_weight, path)
    elif backend.lower() == 'graphviz':
        return _visualize_graph_via_graphviz(edge_index, edge_weight, path)

    raise ValueError(f"Expected graph drawing backend to be in "
                     f"{BACKENDS} (got '{backend}')")


def _visualize_graph_via_graphviz(
    edge_index: Tensor,
    edge_weight: Tensor,
    path: Optional[str] = None,
) -> Any:
    import graphviz

    suffix = path.split('.')[-1] if path is not None else None
    g = graphviz.Digraph('graph', format=suffix)
    g.attr('node', shape='circle', fontsize='11pt')

    for node in edge_index.view(-1).unique().tolist():
        g.node(str(node))

    for (src, dst), w in zip(edge_index.t().tolist(), edge_weight.tolist()):
        hex_color = hex(255 - round(255 * w))[2:]
        hex_color = f'{hex_color}0' if len(hex_color) == 1 else hex_color
        g.edge(str(src), str(dst), color=f'#{hex_color}{hex_color}{hex_color}')

    if path is not None:
        path = '.'.join(path.split('.')[:-1])
        g.render(path, cleanup=True)
    else:
        g.view()

    return g


def _visualize_graph_via_networkx(
    edge_index: Tensor,
    edge_weight: Tensor,
    path: Optional[str] = None,
) -> Any:
    import matplotlib.pyplot as plt
    import networkx as nx

    g = nx.DiGraph()
    node_size = 800

    for node in edge_index.view(-1).unique().tolist():
        g.add_node(node)

    for (src, dst), w in zip(edge_index.t().tolist(), edge_weight.tolist()):
        g.add_edge(src, dst, alpha=w)

    ax = plt.gca()
    pos = nx.spring_layout(g)
    for src, dst, data in g.edges(data=True):
        ax.annotate(
            '',
            xy=pos[src],
            xytext=pos[dst],
            arrowprops=dict(
                arrowstyle="->",
                alpha=data['alpha'],
                shrinkA=sqrt(node_size) / 2.0,
                shrinkB=sqrt(node_size) / 2.0,
                connectionstyle="arc3,rad=0.1",
            ),
        )

    nodes = nx.draw_networkx_nodes(g, pos, node_size=node_size,
                                   node_color='white', margins=0.1)
    nodes.set_edgecolor('black')
    nx.draw_networkx_labels(g, pos, font_size=10)

    if path is not None:
        plt.savefig(path)
    else:
        plt.show()

    plt.close()
