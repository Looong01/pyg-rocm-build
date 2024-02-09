import torch

import torch_geometric.graphgym.register as register
from torch_geometric.graphgym.config import cfg
from torch_geometric.graphgym.models.layer import MLP, new_layer_config
from torch_geometric.graphgym.register import register_head


@register_head('node')
class GNNNodeHead(torch.nn.Module):
    r"""A GNN prediction head for node-level prediction tasks.

    Args:
        dim_in (int): The input feature dimension.
        dim_out (int): The output feature dimension.
    """
    def __init__(self, dim_in: int, dim_out: int):
        super().__init__()
        self.layer_post_mp = MLP(
            new_layer_config(
                dim_in,
                dim_out,
                cfg.gnn.layers_post_mp,
                has_act=False,
                has_bias=True,
                cfg=cfg,
            ))

    def _apply_index(self, batch):
        x = batch.x
        y = batch.y if 'y' in batch else None

        if 'split' not in batch:
            return x, y

        mask = batch[f'{batch.split}_mask']
        return x[mask], y[mask] if y is not None else None

    def forward(self, batch):
        batch = self.layer_post_mp(batch)
        pred, label = self._apply_index(batch)
        return pred, label


@register_head('edge')
@register_head('link_pred')
class GNNEdgeHead(torch.nn.Module):
    r"""A GNN prediction head for edge-level/link-level prediction tasks.

    Args:
        dim_in (int): The input feature dimension.
        dim_out (int): The output feature dimension.
    """
    def __init__(self, dim_in: int, dim_out: int):
        super().__init__()
        # Module to decode edges from node embeddings:
        if cfg.model.edge_decoding == 'concat':
            self.layer_post_mp = MLP(
                new_layer_config(
                    dim_in * 2,
                    dim_out,
                    cfg.gnn.layers_post_mp,
                    has_act=False,
                    has_bias=True,
                    cfg=cfg,
                ))
            self.decode_module = lambda v1, v2: \
                self.layer_post_mp(torch.cat((v1, v2), dim=-1))
        else:
            if dim_out > 1:
                raise ValueError(f"Binary edge decoding "
                                 f"'{cfg.model.edge_decoding}' is used for "
                                 f"multi-class classification")
            self.layer_post_mp = MLP(
                new_layer_config(
                    dim_in,
                    dim_in,
                    cfg.gnn.layers_post_mp,
                    has_act=False,
                    has_bias=True,
                    cfg=cfg,
                ))
            if cfg.model.edge_decoding == 'dot':
                self.decode_module = lambda v1, v2: torch.sum(v1 * v2, dim=-1)
            elif cfg.model.edge_decoding == 'cosine_similarity':
                self.decode_module = torch.nn.CosineSimilarity(dim=-1)
            else:
                raise ValueError(f"Unknown edge decoding "
                                 f"'{cfg.model.edge_decoding}'")

    def _apply_index(self, batch):
        index = f'{batch.split}_edge_index'
        label = f'{batch.split}_edge_label'
        return batch.x[batch[index]], batch[label]

    def forward(self, batch):
        if cfg.model.edge_decoding != 'concat':
            batch = self.layer_post_mp(batch)
        pred, label = self._apply_index(batch)
        nodes_first = pred[0]
        nodes_second = pred[1]
        pred = self.decode_module(nodes_first, nodes_second)
        return pred, label


@register_head('graph')
class GNNGraphHead(torch.nn.Module):
    r"""A GNN prediction head for graph-level prediction tasks.
    A post message passing layer (as specified by :obj:`cfg.gnn.post_mp`) is
    used to transform the pooled graph-level embeddings using an MLP.

    Args:
        dim_in (int): The input feature dimension.
        dim_out (int): The output feature dimension.
    """
    def __init__(self, dim_in: int, dim_out: int):
        super().__init__()
        self.layer_post_mp = MLP(
            new_layer_config(dim_in, dim_out, cfg.gnn.layers_post_mp,
                             has_act=False, has_bias=True, cfg=cfg))
        self.pooling_fun = register.pooling_dict[cfg.model.graph_pooling]

    def _apply_index(self, batch):
        return batch.graph_feature, batch.y

    def forward(self, batch):
        graph_emb = self.pooling_fun(batch.x, batch.batch)
        graph_emb = self.layer_post_mp(graph_emb)
        batch.graph_feature = graph_emb
        pred, label = self._apply_index(batch)
        return pred, label
