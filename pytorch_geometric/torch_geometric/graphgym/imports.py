import warnings

import torch

try:
    import pytorch_lightning as pl
    LightningModule = pl.LightningModule
    Callback = pl.Callback
except ImportError:
    pl = object
    LightningModule = torch.nn.Module
    Callback = object

    warnings.warn("Please install 'pytorch_lightning' for using the GraphGym "
                  "experiment manager via 'pip install pytorch_lightning'")
