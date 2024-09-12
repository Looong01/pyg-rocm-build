# Update
1. Upgrade all the PYG libraries to the newest versions.
2. ~~Remove Python 3.7 support, because PyTorch 2.0 does not support it.~~ Old update
3. Add Python 3.11 and 3.12 support.
4. Support ROCm 6.2 & 6.1.
5. The Python 3.8 version of these wheels built by PyTorch 2.4.1 building with ROCm 6.1, because ROCm-6.2-build PyTorch doesn't support Python 3.8 in the future.
  
# How to use
1. Be sure that you have installed ROCm 5.7 or newer versions. You can use ```rocm-smi``` to check it.
2. Go to Releases module, choose the versions of PYG you want and the right version of your Python environment.
3. Download the zip file.
4. ```unzip``` it, and ```cd ``` into the folder.
5. ```pip install ./*```
  
# Build environment
```
Ubuntu 22.04
PyTorch 2.5.0 for Python 3.9~3.12
PyTorch 2.4.1 for Python 3.8
ROCm 6.2.0
```
  
# Current version
```
pytorch_geometric-2.5.3
pytorch_scatter-2.1.2
pytorch_sparse-0.6.18
pytorch_cluster-1.6.3
pytorch_spline_conv-1.2.2
```