import os.path as osp

import torch
from torch.nn import Embedding, Linear, ModuleList, ReLU, Sequential

import torch_geometric.transforms as T
from torch_geometric.datasets import ZINC
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GINEConv, GPSConv, global_add_pool

path = osp.join(osp.dirname(osp.realpath(__file__)), '..', 'data', 'ZINC-PE')
transform = T.AddRandomWalkPE(walk_length=20, attr_name='pe')
train_dataset = ZINC(path, subset=True, split='train', pre_transform=transform)
val_dataset = ZINC(path, subset=True, split='val', pre_transform=transform)
test_dataset = ZINC(path, subset=True, split='test', pre_transform=transform)

train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=64)
test_loader = DataLoader(test_dataset, batch_size=64)


class GPS(torch.nn.Module):
    def __init__(self, channels: int, num_layers: int):
        super().__init__()

        self.node_emb = Embedding(21, channels)
        self.pe_lin = Linear(20, channels)
        self.edge_emb = Embedding(4, channels)

        self.convs = ModuleList()
        for _ in range(num_layers):
            nn = Sequential(
                Linear(channels, channels),
                ReLU(),
                Linear(channels, channels),
            )
            conv = GPSConv(channels, GINEConv(nn), heads=4, attn_dropout=0.5)
            self.convs.append(conv)

        self.lin = Linear(channels, 1)

    def forward(self, x, pe, edge_index, edge_attr, batch):
        x = self.node_emb(x.squeeze(-1)) + self.pe_lin(pe)
        edge_attr = self.edge_emb(edge_attr)

        for conv in self.convs:
            x = conv(x, edge_index, batch, edge_attr=edge_attr)
        x = global_add_pool(x, batch)
        return self.lin(x)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = GPS(channels=64, num_layers=10).to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)


def train(epoch):
    model.train()

    total_loss = 0
    for data in train_loader:
        data = data.to(device)
        optimizer.zero_grad()
        out = model(data.x, data.pe, data.edge_index, data.edge_attr,
                    data.batch)
        loss = (out.squeeze() - data.y).abs().mean()
        loss.backward()
        total_loss += loss.item() * data.num_graphs
        optimizer.step()
    return total_loss / len(train_loader.dataset)


@torch.no_grad()
def test(loader):
    model.eval()

    total_error = 0
    for data in loader:
        data = data.to(device)
        out = model(data.x, data.pe, data.edge_index, data.edge_attr,
                    data.batch)
        total_error += (out.squeeze() - data.y).abs().sum().item()
    return total_error / len(loader.dataset)


for epoch in range(1, 101):
    loss = train(epoch)
    val_mae = test(val_loader)
    test_mae = test(test_loader)
    print(f'Epoch: {epoch:02d}, Loss: {loss:.4f}, Val: {val_mae:.4f}, '
          f'Test: {test_mae:.4f}')
