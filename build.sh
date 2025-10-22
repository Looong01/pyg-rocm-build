#!/bin/bash

current_path=$(pwd)
conda_path=/mnt/4T/miniconda3/loong

# 获取CPU核心数量
cpu_num=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# 任务列表
packages=("pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv")
versions=("py310" "py311" "py312" "py313" "py314")

# 编译函数
compile_task() {
    local dir=$1
    local version=$2
    (
        cd "${current_path}/$dir" || exit 1
        "${conda_path}/${version}/bin/python" setup.py bdist_wheel
    )
}

# 使用计数器控制并行任务
current_jobs=0
for dir in "${packages[@]}"; do
    for version in "${versions[@]}"; do
        # 如果当前任务数达到CPU核心数，等待一个任务完成
        if (( current_jobs >= cpu_num )); then
            wait -n
            ((current_jobs--))
        fi
        
        # 启动编译任务
        compile_task "$dir" "$version" &
        ((current_jobs++))
    done
done

# 等待所有剩余任务完成
wait

# 后续文件处理（保持不变）
if [ -d ${current_path}/dist ]; then
  rm -rf ${current_path}/dist
fi
mkdir ${current_path}/dist

package_name="torch-2.10.0-rocm-7.0"

for version in "${versions[@]}"; do
    mkdir -p ${current_path}/dist/${package_name}-${version}-linux_x86_64
    py_version="${version#py}"
    for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv"; do
        mv "${current_path}/${module}/dist/"*-cp${py_version}-cp${py_version}-linux_x86_64.whl "${current_path}/dist/${package_name}-${version}-linux_x86_64/"
    done
done

for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv"; do
    rm -rf "${current_path}/${module}/dist"
    rm -rf "${current_path}/${module}/build"
done

wget "https://files.pythonhosted.org/packages/1e/d3/4dffd7300500465e0b4a2ae917dcb2ce771de0b9a772670365799a27c024/torch_geometric-2.7.0-py3-none-any.whl" -O "${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl"

for version in "${versions[@]}"; do
    cp ${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl ${current_path}/dist/${package_name}-${version}-linux_x86_64/
    zip -j ${current_path}/dist/${package_name}-${version}-linux_x86_64.zip ${current_path}/dist/${package_name}-${version}-linux_x86_64/*.whl
done

rm ${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl