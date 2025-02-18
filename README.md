# Update
1. Upgrade all the PYG libraries to the newest versions.
2. Remove Python 3.8 support, because PyTorch 2.6 does not support it.
3. Add Python 3.13 support.
4. Support ROCm 6.2.4.
5. ~~The Python 3.8 version of these wheels built by PyTorch 2.5 building with ROCm 6.1, because ROCm-6.2-build PyTorch doesn't support Python 3.8 in the future.~~ Old update
  
# How to use
1. You can find all the pre-build packages [here](https://github.com/Looong01/pyg-rocm-build/releases). Please follow the tags and find which version of ROCm and PyTorch you do need!
2. Be sure that you have installed ROCm 5.7 or newer versions. You can use ```rocm-smi``` to check it.
3. Go to Releases module, choose the versions of PYG you want and the right version of your Python environment.
4. Download the zip file.
5. ```unzip``` it, and ```cd ``` into the folder.
6. ```pip install ./*```
  
# Build environment
```
Ubuntu 22.04
PyTorch 2.6.0 for Python 3.9~3.13
ROCm 6.2.4
```
  
# Current version
```
pytorch_geometric-2.6.1
pytorch_scatter-2.1.2
pytorch_sparse-0.6.18
pytorch_cluster-1.6.3
pytorch_spline_conv-1.2.2
```