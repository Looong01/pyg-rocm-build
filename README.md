# Update
1. Upgrade all the PYG libraries to the newest versions.
2. Delete Python 3.7 support, because PyTorch 2.0 does not support it.
  
# How to use
1. Be sure that you have installed ROCm 5.4.2 or newer versions. You can use ```rocm-smi``` to check it.
2. Go to Releases module, choose the versions of PYG you want and the right version of your Python environment.
3. Download the zip file.
4. ```unzip``` it, and ```cd ``` into the folder.
5. ```pip install ./*```
  
# Build environment
```
Ubuntu 22.04
PyTorch 2.0
ROCm 5.4.3
```
  
# Current version
```
pytorch_geometric-2.3.0
pytorch_scatter-2.1.1
pytorch_sparse-0.6.17
pytorch_cluster-1.6.1
pytorch_spline_conv-1.2.2
```