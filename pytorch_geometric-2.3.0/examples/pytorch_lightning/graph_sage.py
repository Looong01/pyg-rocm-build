import os.path as osp

import pytorch_lightning as pl
import torch
import torch.nn.functional as F
from torch.nn import BatchNorm1d
from torchmetrics import Accuracy

from torch_geometric.data.lightning import LightningNodeData
from torch_geometric.datasets import Reddit
from torch_geometric.nn import GraphSAGE


class Model(pl.LightningModule):
    def __init__(self, in_channels: int, out_channels: int,
                 hidden_channels: int = 256, num_layers: int = 2,
                 dropout: float = 0.5):
        super().__init__()
        self.gnn = GraphSAGE(in_channels, hidden_channels, num_layers,
                             out_channels, dropout=dropout,
                             norm=BatchNorm1d(hidden_channels))

        self.train_acc = Accuracy(task='multiclass', num_classes=out_channels)
        self.val_acc = Accuracy(task='multiclass', num_classes=out_channels)
        self.test_acc = Accuracy(task='multiclass', num_classes=out_channels)

    def forward(self, x, edge_index):
        return self.gnn(x, edge_index)

    def training_step(self, data, batch_idx):
        y_hat = self(data.x, data.edge_index)[:data.batch_size]
        y = data.y[:data.batch_size]
        loss = F.cross_entropy(y_hat, y)
        self.train_acc(y_hat.softmax(dim=-1), y)
        self.log('train_acc', self.train_acc, prog_bar=True, on_step=False,
                 on_epoch=True)
        return loss

    def validation_step(self, data, batch_idx):
        y_hat = self(data.x, data.edge_index)[:data.batch_size]
        y = data.y[:data.batch_size]
        self.val_acc(y_hat.softmax(dim=-1), y)
        self.log('val_acc', self.val_acc, prog_bar=True, on_step=False,
                 on_epoch=True)

    def test_step(self, data, batch_idx):
        y_hat = self(data.x, data.edge_index)[:data.batch_size]
        y = data.y[:data.batch_size]
        self.test_acc(y_hat.softmax(dim=-1), y)
        self.log('test_acc', self.test_acc, prog_bar=True, on_step=False,
                 on_epoch=True)

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.01)


if __name__ == '__main__':
    dataset = Reddit(osp.join('data', 'Reddit'))
    data = dataset[0]

    datamodule = LightningNodeData(
        data,
        input_train_nodes=data.train_mask,
        input_val_nodes=data.val_mask,
        input_test_nodes=data.test_mask,
        loader='neighbor',
        num_neighbors=[25, 10],
        batch_size=1024,
        num_workers=8,
    )

    model = Model(dataset.num_node_features, dataset.num_classes)

    strategy = pl.strategies.SingleDeviceStrategy('cuda:0')
    checkpoint = pl.callbacks.ModelCheckpoint(monitor='val_acc', save_top_k=1,
                                              mode='max')
    trainer = pl.Trainer(strategy=strategy, devices=1, max_epochs=20,
                         callbacks=[checkpoint])

    trainer.fit(model, datamodule)
    trainer.test(ckpt_path='best', datamodule=datamodule)
