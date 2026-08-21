#!/bin/bash

# 可通过 PACKAGE_NAME 覆盖发布目录标签；默认在 conda_path 确定后按 Torch 版本生成。
package_name=""
# 发布目录名中的 torch / rocm 版本号，可在此手动设定；留空则自动从 py312 环境探测。
# 例：torch_version="2.13.0"  rocm_version="7.2"
torch_version="2.13.0"
rocm_version="7.14"
version_tag="post6"
export VERSION_TAG="${version_tag}"
wheel_platform="${WHEEL_PLAT_NAME:-manylinux_2_32_x86_64}"
export WHEEL_PLAT_NAME="${wheel_platform}"

# pyg-lib-rocm 的版本号由这里统一计算并传入 setup.py：post6 -> post1。
# post1~post5 对应无后缀；非法 version_tag 直接中止，避免生成错误版本。
if [[ "${version_tag}" =~ ^post([0-9]+)$ ]]; then
    post_number=${BASH_REMATCH[1]}
    if (( post_number > 5 )); then
        pyg_version_tag="post$((post_number - 5))"
    else
        pyg_version_tag=""
    fi
else
    echo "Error: version_tag 必须符合 postN 格式，当前值为 ${version_tag}"
    exit 1
fi
export PYG_LIB_VERSION_TAG="${pyg_version_tag}"
echo "Version tags: torch packages=.${VERSION_TAG}, pyg-lib-rocm=${PYG_LIB_VERSION_TAG:-none}"


current_path=$(pwd)

# 自动探测 conda 环境根目录（优先级：CONDA_PATH 环境变量 > /root/miniconda3 > /mnt/4T/miniconda3/loong）
if [ -n "${CONDA_PATH}" ]; then
    conda_path="${CONDA_PATH}"
elif [ -d /root/miniconda3/py310 ]; then
    conda_path=/root/miniconda3
elif [ -d /mnt/4T/miniconda3/loong/py310 ]; then
    conda_path=/mnt/4T/miniconda3/loong
else
    echo "Error: 未找到包含 py310~py314 环境的 conda 目录，请设置 CONDA_PATH 环境变量"
    exit 1
fi
echo "Using conda path: ${conda_path}"

# 读取实际构建工具链版本。注意：Torch ROCm 版本和系统 ROCm 版本可以不同，
# 但一个 wheel 仍只针对这一套 Torch ABI 构建；若换另一套 Torch ROCm，必须重新运行。
# 目录名格式：torch-<torch版本>-rocm-<rocm版本>，版本号可在脚本开头手动设定，留空则自动探测。
if [ -z "${torch_version}" ] || [ -z "${rocm_version}" ]; then
    detected=$("${conda_path}/py312/bin/python" -c "import torch; print(torch.__version__.split('+')[0] + ' ' + str(torch.version.hip).split('.')[0] + '.' + str(torch.version.hip).split('.')[1])")
    [ -z "${torch_version}" ] && torch_version=${detected%% *}
    [ -z "${rocm_version}" ] && rocm_version=${detected##* }
fi
torch_label="torch-${torch_version}-rocm-${rocm_version}"
system_rocm_path="${ROCM_PATH:-/opt/rocm}"
export ROCM_PATH="${system_rocm_path}"
system_rocm_version=$(sed -n 's/^#define ROCM_VERSION_DEV_STRING "\([^"]*\)"/\1/p' "${system_rocm_path}/include/rocm-core/rocm_version.h" 2>/dev/null || true)
if [ -z "${PACKAGE_NAME}" ]; then
    package_name="${torch_label}"
else
    package_name="${PACKAGE_NAME}"
fi
echo "Torch build: ${torch_label}"
echo "System ROCm compiler: ${system_rocm_path}${system_rocm_version:+ (${system_rocm_version})}"

# ROCm 的 rocm_smi CMake 配置会通过 pkg-config 查找 libdrm；某些
# 系统没有安装 libdrm-dev，但 ROCm 自己已随 rocm_sysdeps 提供兼容版本。
rocm_sysdeps_pkgconfig=$(find "${system_rocm_path}" -path '*/rocm_sysdeps/lib/pkgconfig' -type d -print -quit 2>/dev/null)
if [ -n "${rocm_sysdeps_pkgconfig}" ] && [ -f "${rocm_sysdeps_pkgconfig}/libdrm.pc" ]; then
    export PKG_CONFIG_PATH="${rocm_sysdeps_pkgconfig}:${PKG_CONFIG_PATH}"
    export CMAKE_PREFIX_PATH="$(dirname "$(dirname "${rocm_sysdeps_pkgconfig}")"):${CMAKE_PREFIX_PATH}"
fi

# 【重要】默认编译【全部】torch ROCm wheel 支持的 GPU 架构（15 个）。
# torch 2.13+ 在未设置 PYTORCH_ROCM_ARCH 时，只为"构建时可见 GPU"的架构编译扩展，
# 这样打出来的 wheel 在其他 GPU（gfx1030 / MI 系列等）上会报 "no kernel image" 错误
# （PyPI 上的 post5 版本就只包含 gfx1100，是回归）。
#
# 架构覆盖说明（已用 hipcc --offload-arch 逐一探测验证）：
#   - ROCm 7.14 编译器支持 19 个 gfx 架构，但其中 gfx90c / gfx1010 / gfx1011 /
#     gfx1012 官方 PyTorch ROCm wheel 并不支持（torch 本身无法在这些 GPU 上运行，
#     为它们编译扩展没有意义），故不包含；
#   - 下面 15 个 = torch ROCm wheel 支持的全部架构 = 本 wheel 的完整覆盖范围，
#     涵盖 CDNA(MI50/MI100/MI200/MI300/MI355)、RDNA2(6800/7900)、RDNA3(7000)、
#     RDNA4(9000) 全系列。
# 如需自定义子集（如本地快速构建），运行前 export PYTORCH_ROCM_ARCH="gfx1100"。
DEFAULT_ROCM_ARCHS="gfx900;gfx906;gfx908;gfx90a;gfx942;gfx950;gfx1030;gfx1100;gfx1101;gfx1102;gfx1103;gfx1150;gfx1151;gfx1200;gfx1201"
if [ -z "${PYTORCH_ROCM_ARCH}" ]; then
    # 不读取可见 GPU，也不依赖 torch.cuda.get_arch_list()；构建机可以无 GPU，
    # 且只读可见设备会导致分发 wheel 缺少其他架构的 device code。
    export PYTORCH_ROCM_ARCH="${DEFAULT_ROCM_ARCHS}"
fi
echo "PYTORCH_ROCM_ARCH=${PYTORCH_ROCM_ARCH}"

# 获取CPU核心数量
cpu_num=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)
export MAX_JOBS="${cpu_num}"
export CMAKE_BUILD_PARALLEL_LEVEL="${cpu_num}"
echo "Build parallelism: ${cpu_num} CPU cores"

# 任务列表
packages=("pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv")
versions=("py310" "py311" "py312" "py313" "py314")
# versions=("py310" "py311" "py312" "py313")

# 检查源码文件可写性：hipify 需要写 csrc/hip/ 下的生成文件，若源码目录
# 属于其他用户（如曾用 root 构建过），hipify 会静默跳过（日志显示
# "[skipped, no permissions]"），导致直接编译原始 .cu 文件而报
# cuda_runtime_api.h not found 之类的错误
for pkg in "${packages[@]}" "pyg-lib-rocm"; do
    noperm=$(find "${current_path}/${pkg}/csrc" "${current_path}/${pkg}/pyg_lib" -type f ! -writable 2>/dev/null | wc -l)
    if (( noperm > 0 )); then
        echo "ERROR: ${pkg} 下有 ${noperm} 个不可写文件（可能属于 root），hipify 将失败。"
        echo "       修复：sudo chown -R \$(id -u):\$(id -g) ${current_path}/${pkg}"
        exit 1
    fi
done

# 编译函数：包间串行 + 包内各 Python 版本串行，单次构建内 ninja 用满全部核心
# 【关键修复】setup.py bdist_wheel 的打包暂存目录 build/bdist.linux-x86_64/wheel/
# 不区分 Python 版本（wheel 包源码：bdist_dir = bdist_base/wheel，bdist_base =
# build/bdist.<plat>），同一包内并行构建会互相覆盖/污染暂存目录，导致 wheel
# 缺文件或混入其他 Python 版本的 .so（Issue #22 根因）。共享的还有 *.egg-info
# 与 hipify 生成的 csrc/hip/。因此：
#   - 同一包内的 Python 版本 → 必须串行，且每个版本构建前清理共享状态
#   - 包与包之间 → 串行执行，每次构建通过 MAX_JOBS 让 ninja 用满全部 CPU 核心
#     （比包间并行更稳：内存压力小、日志清晰、无任何共享状态干扰）
compile_task() {
    local dir=$1
    (
        cd "${current_path}/$dir" || exit 1
        rm -rf all_wheels
        mkdir -p all_wheels
        for version in "${versions[@]}"; do
            echo "[${dir}] === building ${version} ==="
            # 清理上一版本/上次中断留下的共享构建状态，避免脏数据进入 wheel
            rm -rf build dist *.egg-info
            if ! MAX_JOBS="${cpu_num}" "${conda_path}/${version}/bin/python" setup.py bdist_wheel; then
                echo "[${dir}] ERROR: ${version} build failed"
                exit 1
            fi
            # 立即把 wheel 移到独立暂存目录，避免被下一版本的清理误删
            mv dist/*.whl all_wheels/ || exit 1
        done
        rm -rf build dist *.egg-info
    )
}

# 串行构建四个包（每个包内部 ninja 已用满全部核心）
for dir in "${packages[@]}"; do
    compile_task "$dir" || exit 1
done

# 添加pyg-lib-rocm的编译
# ================================
# 编译pyg-lib-rocm（串行 + 每版本清理：CMake 构建目录虽按 Python 版本隔离，
# 但 bdist 暂存目录共享，同样必须串行；CMAKE_BUILD_PARALLEL_LEVEL 让 CMake
# 用满全部核心，做法与 build_pyg_lib_rocm.sh 一致）
(
    cd "${current_path}/pyg-lib-rocm" || exit 1
    rm -rf all_wheels
    mkdir -p all_wheels
    for version in "${versions[@]}"; do
        echo "[pyg-lib-rocm] === building ${version} ==="
        rm -rf build dist *.egg-info
        if ! MAX_JOBS="${cpu_num}" CMAKE_BUILD_PARALLEL_LEVEL="${cpu_num}" "${conda_path}/${version}/bin/python" setup.py bdist_wheel; then
            echo "[pyg-lib-rocm] ERROR: ${version} build failed"
            exit 1
        fi
        mv dist/*.whl all_wheels/ || exit 1
    done
    rm -rf build dist *.egg-info
) || exit 1

# 检查编译结果：每个包必须凑齐全部 Python 版本的 wheel
build_failed=0
for dir in "${packages[@]}" "pyg-lib-rocm"; do
    count=$(ls "${current_path}/${dir}/all_wheels/"*-cp*-cp*-${wheel_platform}.whl 2>/dev/null | wc -l)
    if (( count != ${#versions[@]} )); then
        echo "ERROR: ${dir} 只编译出 ${count}/${#versions[@]} 个 wheel，中止（请检查上方编译日志）"
        build_failed=1
    fi
done
if (( build_failed )); then
    exit 1
fi

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
    mkdir -p ${current_path}/dist/${package_name}-${version}-${wheel_platform}
    py_version="${version#py}"
    for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv" "pyg-lib-rocm"; do
        wheel_pattern="${current_path}/${module}/all_wheels/"*-cp${py_version}-cp${py_version}-${wheel_platform}.whl
        if ls ${wheel_pattern} 1>/dev/null 2>&1; then
            mv ${wheel_pattern} ${current_path}/dist/${package_name}-${version}-${wheel_platform}/
            echo "Moved ${module} wheel for ${version}"
        else
            echo "Warning: No wheel found for ${module} ${version}"
        fi
    done
done

# 清理构建目录与 wheel 暂存目录
for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv" "pyg-lib-rocm"; do
    rm -rf "${current_path}/${module}/dist"
    rm -rf "${current_path}/${module}/build"
    rm -rf "${current_path}/${module}/all_wheels"
done

# 下载 torch_geometric（直接下载到 dist 目录，避免路径不一致）
wget -P ${current_path}/dist "https://files.pythonhosted.org/packages/14/5c/edf74a71249ad19aa0390fb97ff021e2a5b04ce23252730014e1feac957e/torch_geometric-2.8.0.post1-py3-none-any.whl"

# 创建包含所有依赖的 zip 文件
for version in "${versions[@]}"; do
    cp ${current_path}/dist/torch_geometric-2.8.0.post1-py3-none-any.whl ${current_path}/dist/${package_name}-${version}-${wheel_platform}/
    zip -j ${current_path}/dist/${package_name}-${version}-${wheel_platform}.zip ${current_path}/dist/${package_name}-${version}-${wheel_platform}/*.whl
    # 从 dist 目录中移除 torch_geometric，不包含在最终上传的包中
    rm ${current_path}/dist/${package_name}-${version}-${wheel_platform}/torch_geometric-*.whl
done

rm ${current_path}/dist/torch_geometric-2.8.0.post1-py3-none-any.whl

# 准备 upload 目录
if [ -d ${current_path}/upload ]; then
    rm -rf ${current_path}/upload/*.whl
else
    mkdir -p ${current_path}/upload
fi

# 复制所有编译好的包到./upload/
for version in "${versions[@]}"; do
    cp ${current_path}/dist/${package_name}-${version}-${wheel_platform}/*.whl ${current_path}/upload/
done

cd ${current_path}/upload

# wheel 已由各包的 setup.py 原生生成最终版本、平台标签和 RECORD，
# 不再需要 build/upload/fix_whl.py 或 fix_whl_pyglib.py。

# 上传到 PyPI（设置 SKIP_UPLOAD=1 可只生成本地 wheel 而不上传，用于测试）
if [ -n "${SKIP_UPLOAD}" ]; then
    echo "SKIP_UPLOAD 已设置，跳过 twine 上传。wheel 已就绪：${current_path}/upload/"
else
    "${conda_path}/py312/bin/python" -m twine upload -u __token__ -p <pypi_token> *.whl
fi

cd ${current_path}
