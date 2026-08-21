import glob
import os
import os.path as osp
import platform
import re
import sys
import threading
from itertools import product

import torch
os.environ.setdefault('MAX_JOBS', str(os.cpu_count() or 1))
from setuptools import find_packages, setup
from wheel.bdist_wheel import bdist_wheel
from torch.__config__ import parallel_info
from torch.utils.cpp_extension import (CUDA_HOME, BuildExtension, CppExtension,
                                       CUDAExtension)
DEFAULT_PLATFORM = 'manylinux_2_32_x86_64'


class ParallelBuildExtension(BuildExtension):
    """Build all extensions in parallel across CPU cores.

    torch's ``BuildExtension`` runs one ninja build per extension (each with
    only a handful of source files) and distutils builds extensions serially
    by default, so hipcc (which compiles for every ROCm arch) never overlaps
    and only 1-3 cores are used. Setting ``self.parallel`` makes distutils
    build the extensions in a thread pool.

    Every extension would otherwise share ``self.build_temp`` as its ninja
    build directory (build.ninja and object files would clobber each other),
    so ``build_temp`` is exposed as a property backed by thread-local
    storage: each worker thread sees its own per-extension subdirectory while
    the main thread keeps the original value.
    """

    def __init__(self, *args, **kwargs):
        self._build_temp_base = None
        self._build_temp_tls = threading.local()
        super().__init__(*args, **kwargs)

    @property
    def build_temp(self):
        override = getattr(self._build_temp_tls, 'value', None)
        return override if override is not None else self._build_temp_base

    @build_temp.setter
    def build_temp(self, value):
        self._build_temp_base = value

    def finalize_options(self):
        super().finalize_options()
        if self.parallel is None:
            self.parallel = int(os.getenv('MAX_JOBS', str(os.cpu_count() or 1)))

    def build_extensions(self):
        # Cap per-extension ninja parallelism: with N extension threads each
        # running `ninja -j MAX_JOBS`, the machine would be oversubscribed
        # (N x MAX_JOBS concurrent hipcc). One job per extension keeps the
        # total at ~N concurrent hipcc, i.e. one per CPU core.
        original_max_jobs = os.environ.get('MAX_JOBS')
        os.environ['MAX_JOBS'] = os.getenv('PYG_NINJA_JOBS', '1')
        try:
            super().build_extensions()
        finally:
            if original_max_jobs is None:
                os.environ.pop('MAX_JOBS', None)
            else:
                os.environ['MAX_JOBS'] = original_max_jobs

    def build_extension(self, ext):
        # Isolate this extension's ninja build dir (build.ninja + .o files)
        # so parallel extension builds do not clobber each other.
        self._build_temp_tls.value = osp.join(self._build_temp_base, ext.name)
        try:
            super().build_extension(ext)
        finally:
            self._build_temp_tls.value = None


def version_with_tag(base_version):
    tag = os.getenv('VERSION_TAG', os.getenv('version_tag', '')).strip().lstrip('.')
    if tag and not re.fullmatch(r'post\d+', tag, re.IGNORECASE):
        raise ValueError('VERSION_TAG must look like post6')
    base_version = re.sub(r'\.post\d+$', '', base_version)
    return f'{base_version}.{tag}' if tag else base_version


class ROCmBdistWheel(bdist_wheel):
    def finalize_options(self):
        self.plat_name = os.getenv('WHEEL_PLAT_NAME', DEFAULT_PLATFORM)
        super().finalize_options()
        self.plat_name = os.getenv('WHEEL_PLAT_NAME', DEFAULT_PLATFORM)


__version__ = version_with_tag('1.6.3')
URL = 'https://github.com/Looong01/pyg-rocm-build'

WITH_CUDA = False
if torch.version.hip is not None:
    # A ROCm build of PyTorch always targets HIP, and no GPU needs to be
    # visible at build time (e.g. when building wheels on a CI runner):
    WITH_CUDA = True
elif torch.cuda.is_available():
    WITH_CUDA = CUDA_HOME is not None

suffices = ['cpu', 'cuda'] if WITH_CUDA else ['cpu']
if os.getenv('FORCE_CUDA', '0') == '1':
    suffices = ['cuda', 'cpu']
if os.getenv('FORCE_ONLY_CUDA', '0') == '1':
    suffices = ['cuda']
if os.getenv('FORCE_ONLY_CPU', '0') == '1':
    suffices = ['cpu']

BUILD_DOCS = os.getenv('BUILD_DOCS', '0') == '1'


def get_extensions():
    extensions = []

    extensions_dir = osp.join('csrc')
    main_files = glob.glob(osp.join(extensions_dir, '*.cpp'))
    # remove generated 'hip' files, in case of rebuilds
    main_files = [path for path in main_files if 'hip' not in path]

    for main, suffix in product(main_files, suffices):
        define_macros = [('WITH_PYTHON', None)]
        undef_macros = []

        if sys.platform == 'win32':
            define_macros += [('torchcluster_EXPORTS', None)]

        extra_compile_args = {'cxx': ['-O2']}
        if not os.name == 'nt':  # Not on Windows:
            extra_compile_args['cxx'] += ['-Wno-sign-compare']
        extra_link_args = ['-s']

        info = parallel_info()
        if ('backend: OpenMP' in info and 'OpenMP not found' not in info
                and sys.platform != 'darwin'):
            extra_compile_args['cxx'] += ['-DAT_PARALLEL_OPENMP']
            if sys.platform == 'win32':
                extra_compile_args['cxx'] += ['/openmp']
            else:
                extra_compile_args['cxx'] += ['-fopenmp']
        else:
            print('Compiling without OpenMP...')

        # Compile for mac arm64
        if sys.platform == 'darwin':
            extra_compile_args['cxx'] += ['-D_LIBCPP_DISABLE_AVAILABILITY']
            if platform.machine == 'arm64':
                extra_compile_args['cxx'] += ['-arch', 'arm64']
                extra_link_args += ['-arch', 'arm64']

        if suffix == 'cuda':
            define_macros += [('WITH_CUDA', None)]
            nvcc_flags = os.getenv('NVCC_FLAGS', '')
            nvcc_flags = [] if nvcc_flags == '' else nvcc_flags.split(' ')
            nvcc_flags += ['-O2']
            extra_compile_args['nvcc'] = nvcc_flags

            if torch.version.hip:
                # USE_ROCM was added to later versions of PyTorch
                # Define here to support older PyTorch versions as well:
                define_macros += [('USE_ROCM', None)]
                undef_macros += ['__HIP_NO_HALF_CONVERSIONS__']
            else:
                nvcc_flags += ['--expt-relaxed-constexpr']

        name = main.split(os.sep)[-1][:-4]
        sources = [main]

        path = osp.join(extensions_dir, 'cpu', f'{name}_cpu.cpp')
        if osp.exists(path):
            sources += [path]

        path = osp.join(extensions_dir, 'cuda', f'{name}_cuda.cu')
        if suffix == 'cuda' and osp.exists(path):
            sources += [path]

        Extension = CppExtension if suffix == 'cpu' else CUDAExtension
        extension = Extension(
            f'torch_cluster._{name}_{suffix}',
            sources,
            include_dirs=[extensions_dir],
            define_macros=define_macros,
            undef_macros=undef_macros,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
        )
        extensions += [extension]

    return extensions


install_requires = [
    'scipy',
]

test_requires = [
    'pytest',
    'pytest-cov',
]

# work-around hipify abs paths
include_package_data = True
if torch.version.hip is not None:
    include_package_data = False

setup(
    name='torch-cluster-rocm',
    version=__version__,
    description=('PyTorch Extension Library of Optimized Graph Cluster '
                 'Algorithms (ROCm Build)'),
    author='Looong',
    author_email='lizelongdd@hotmail.com, matthias.fey@tu-dortmund.de',
    url=URL,
    download_url=f'{URL}/releases',
    keywords=[
        'pytorch',
        'geometric-deep-learning',
        'graph-neural-networks',
        'cluster-algorithms',
        'rocm',
        'amd',
    ],
    python_requires='>=3.8',
    install_requires=install_requires,
    extras_require={
        'test': test_requires,
    },
    ext_modules=get_extensions() if not BUILD_DOCS else [],
    cmdclass={
        'build_ext':
        ParallelBuildExtension.with_options(no_python_abi_suffix=True, use_ninja=True),
        'bdist_wheel': ROCmBdistWheel,
    },
    packages=find_packages(),
    include_package_data=include_package_data,
)
