current_path=$(pwd)
conda_path=$HOME/miniconda3/envs

for dir in pytorch_cluster pytorch_scatter pytorch_sparse pytorch_spline_conv
do
  (
    cd "${current_path}/$dir"
    ${conda_path}/py39/bin/python setup.py bdist_wheel &
    ${conda_path}/py310/bin/python setup.py bdist_wheel
  ) &
done

wait

for dir in pytorch_cluster pytorch_scatter pytorch_sparse pytorch_spline_conv
do
  (
    cd "${current_path}/$dir"
    ${conda_path}/py311/bin/python setup.py bdist_wheel &
    ${conda_path}/py312/bin/python setup.py bdist_wheel
  ) &
done

wait

for dir in pytorch_cluster pytorch_scatter pytorch_sparse pytorch_spline_conv
do
  (
    cd "${current_path}/$dir"
    ${conda_path}/py313/bin/python setup.py bdist_wheel
  ) &
done

wait

if [ -d ${current_path}/dist ]; then
  rm -rf ${current_path}/dist
fi
mkdir ${current_path}/dist

package_name="torch-2.6-rocm-6.2.4"

versions=("py39" "py310" "py311" "py312" "py313")

for version in "${versions[@]}"; do
    mkdir -p ${current_path}/dist/${package_name}-${version}-linux_x86_64
    py_version="${version#py}"
    for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv"; do
        mv "${current_path}/${module}/dist/"*-cp${py_version}-cp${py_version}-linux_x86_64.whl "${current_path}/dist/${package_name}-${version}-linux_x86_64/"
    done
done

for module in "pytorch_cluster" "pytorch_scatter" "pytorch_sparse" "pytorch_spline_conv"; do
    rm -rf ${current_path}/${module}/dist
    rm -rf ${current_path}/${module}/build
done


wget "https://files.pythonhosted.org/packages/03/9f/157e913626c1acfb3b19ce000b1a6e4e4fb177c0bc0ea0c67ca5bd714b5a/torch_geometric-2.6.1-py3-none-any.whl" -O "${current_path}/dist/torch_geometric-2.6.1-py3-none-any.whl"

for version in "${versions[@]}"; do
    cp ${current_path}/dist/torch_geometric-2.6.1-py3-none-any.whl ${current_path}/dist/${package_name}-${version}-linux_x86_64/
    zip -j ${current_path}/dist/${package_name}-${version}-linux_x86_64.zip ${current_path}/dist/${package_name}-${version}-linux_x86_64/*.whl
done

rm ${current_path}/dist/torch_geometric-2.6.1-py3-none-any.whl