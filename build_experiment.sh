#!/bin/bash

package_name="torch-2.10.0-rocm-7.1"
version_tag="post3"


current_path=$(pwd)
conda_path=/root/miniconda3/

# 获取CPU核心数量
cpu_num=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# 任务列表
packages=("pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv")
versions=("py310" "py311" "py312" "py313" "py314")
# versions=("py310" "py311" "py312" "py313")

# 在编译之前，修正四个模块 setup.py 中的 __version__ 行
for pkg in "${packages[@]}"; do
    setup_file="${current_path}/${pkg}/setup.py"
    if [ -f "$setup_file" ]; then
        # 将 __version__="xxx.post*" 改为 __version__="xxx.${version_tag}"
        sed -i -E "s/(__version__ *= *[\"'][0-9]+\.[0-9]+\.[0-9]+)\.post[0-9]+/\1.${version_tag}/" "$setup_file"
    else
        echo "Warning: $setup_file not found"
    fi
done

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

# 添加pyg-lib-rocm的编译（放在wait之后）
# ================================
# 编译pyg-lib-rocm
for version in "${versions[@]}"; do
    (
        cd "${current_path}/pyg-lib-rocm" || exit 1
        "${conda_path}/${version}/bin/python" setup.py bdist_wheel
    ) &&
    wait
done

# 等待所有剩余任务完成
wait

# ================================
# 后续文件处理
# ================================

# 清理并创建目标目录
if [ -d ${current_path}/dist ]; then
    rm -rf ${current_path}/dist
fi
mkdir -p ${current_path}/dist

# 移动编译好的 wheel 文件到目标目录
for version in "${versions[@]}"; do
    mkdir -p ${current_path}/dist/${package_name}-${version}-linux_x86_64
    py_version="${version#py}"
    for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv" "pyg-lib-rocm"; do
        wheel_pattern="${current_path}/${module}/dist/"*-cp${py_version}-cp${py_version}-linux_x86_64.whl
        if ls ${wheel_pattern} 1>/dev/null 2>&1; then
            mv ${wheel_pattern} ${current_path}/dist/${package_name}-${version}-linux_x86_64/
            echo "Moved ${module} wheel for ${version}"
        else
            echo "Warning: No wheel found for ${module} ${version}"
        fi
    done
done

# 清理构建目录
for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv" "pyg-lib-rocm"; do
    rm -rf "${current_path}/${module}/dist"
    rm -rf "${current_path}/${module}/build"
done

# 下载 torch_geometric
wget "https://files.pythonhosted.org/packages/1e/d3/4dffd7300500465e0b4a2ae917dcb2ce771de0b9a772670365799a27c024/torch_geometric-2.7.0-py3-none-any.whl" -O "${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl"

# 创建包含所有依赖的 zip 文件
for version in "${versions[@]}"; do
    cp ${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl ${current_path}/dist/${package_name}-${version}-linux_x86_64/
    zip -j ${current_path}/dist/${package_name}-${version}-linux_x86_64.zip ${current_path}/dist/${package_name}-${version}-linux_x86_64/*.whl
    # 从 dist 目录中移除 torch_geometric，不包含在最终上传的包中
    rm ${current_path}/dist/${package_name}-${version}-linux_x86_64/torch_geometric-*.whl
done

rm ${current_path}/dist/torch_geometric-2.7.0-py3-none-any.whl

# 准备 upload 目录
if [ -d ${current_path}/upload ]; then
    rm -rf ${current_path}/upload/*.whl
else
    mkdir -p ${current_path}/upload
fi

# 复制所有编译好的包到./upload/
for version in "${versions[@]}"; do
    cp ${current_path}/dist/${package_name}-${version}-linux_x86_64/*.whl ${current_path}/upload/
done

cd ${current_path}/upload

# ================================
# 修复并上传 wheel 文件
# ================================

echo "Fixing torch packages..."
"${conda_path}/py312/bin/python" fix_whl.py --post "${version_tag}"

echo "Fixing pyg-lib-rocm packages..."
"${conda_path}/py312/bin/python" fix_whl_pyglib.py --post "${version_tag}"

echo "Uploading to PyPI..."
"${conda_path}/py312/bin/python" -m twine upload -u __token__ -p <Pypi_token> *.whl

cd ${current_path}
