# fix_and_rename_whl.py
import zipfile
import tempfile
import shutil
from pathlib import Path
import re

# 配置
OLD_PLATFORM = "linux_x86_64"
NEW_PLATFORM = "manylinux_2_39_x86_64"

def rename_wheel(wheel_path):
    """重命名 wheel 文件，将平台标签从 linux_x86_64 改为 manylinux_2_39_x86_64"""
    wheel_path = Path(wheel_path)
    
    if OLD_PLATFORM not in wheel_path.name:
        return wheel_path  # 不需要重命名
    
    new_name = wheel_path.name.replace(OLD_PLATFORM, NEW_PLATFORM)
    new_path = wheel_path.parent / new_name
    
    try:
        wheel_path.rename(new_path)
        print(f"  ✓ Renamed:  {wheel_path.name}")
        print(f"         -> {new_name}")
        return new_path
    except Exception as e:
        print(f"  ✗ Failed to rename:  {e}")
        return wheel_path

def fix_wheel(wheel_path):
    """修复缺少元数据的 wheel 文件"""
    wheel_path = Path(wheel_path)
    print(f"\nFixing: {wheel_path.name}")
    
    # 解析文件名
    parts = wheel_path.stem.split('-')
    
    if len(parts) < 5:
        print(f"  ✗ Cannot parse wheel name:  expected at least 5 parts, got {len(parts)}")
        print(f"     Parts:  {parts}")
        return False
    
    # 从后往前解析
    platform_tag = parts[-1]  # 最后一部分是平台
    abi_tag = parts[-2]
    python_tag = parts[-3]
    version = parts[-4]
    dist_name = '_'. join(parts[:-4])  # 前面所有部分是包名
    
    print(f"  Parsed: {dist_name} v{version} ({python_tag}-{abi_tag}-{platform_tag})")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        extract_dir = tmpdir / "extracted"
        
        # 解压
        try:
            with zipfile.ZipFile(wheel_path, 'r') as zf:
                zf. extractall(extract_dir)
                all_files = zf.namelist()
                print(f"  Extracted {len(all_files)} files")
        except Exception as e:
            print(f"  ✗ Failed to extract: {e}")
            return False
        
        # 查找或创建 dist-info 目录
        dist_info_dirs = list(extract_dir.glob("*.dist-info"))
        
        if not dist_info_dirs:
            # 创建 dist-info 目录
            dist_info_name = f"{dist_name}-{version}.dist-info"
            dist_info = extract_dir / dist_info_name
            dist_info.mkdir(exist_ok=True)
            print(f"  Created dist-info: {dist_info_name}")
        else:
            dist_info = dist_info_dirs[0]
            print(f"  Found dist-info:  {dist_info. name}")
        
        # 包描述映射
        descriptions = {
            'torch_cluster_rocm': 'PyTorch Extension Library of Optimized Graph Cluster Algorithms (ROCm Build)',
            'torch_scatter_rocm': 'PyTorch Extension Library of Optimized Scatter Operations (ROCm Build)',
            'torch_sparse_rocm': 'PyTorch Extension Library of Optimized Autograd Sparse Matrix Operations (ROCm Build)',
            'torch_spline_conv_rocm': 'PyTorch Implementation of the Spline-Based Convolution Operator of SplineCNN (ROCm Build)',
        }
        
        description = descriptions.get(dist_name, 'PyTorch ROCm Extension')
        pypi_name = dist_name.replace('_', '-')
        
        # 创建 METADATA
        metadata_path = dist_info / "METADATA"
        metadata_content = f"""Metadata-Version:  2.1
Name: {pypi_name}
Version:  {version}
Summary: {description}
Home-page: https://github.com/Looong01/pyg-rocm-build
Download-URL: https://github.com/Looong01/pyg-rocm-build/releases
Author: Looong
Author-email: lizelongdd@hotmail.com, matthias.fey@tu-dortmund.de
License: MIT
Platform: {platform_tag}
Requires-Python: >=3.8
"""
        metadata_path.write_text(metadata_content, encoding='utf-8')
        print(f"  ✓ Created METADATA")
        
        # 创建 WHEEL
        wheel_file_path = dist_info / "WHEEL"
        wheel_content = f"""Wheel-Version: 1.0
Generator: bdist_wheel (0.41.2)
Root-Is-Purelib: false
Tag: {python_tag}-{abi_tag}-{platform_tag}
"""
        wheel_file_path.write_text(wheel_content, encoding='utf-8')
        print(f"  ✓ Created WHEEL")
        
        # 创建 top_level.txt
        top_level_path = dist_info / "top_level.txt"
        package_name = dist_name.replace('_rocm', '')
        top_level_path. write_text(package_name, encoding='utf-8')
        print(f"  ✓ Created top_level.txt ({package_name})")
        
        # 更新 RECORD
        record_path = dist_info / "RECORD"
        record_lines = []
        
        for file in extract_dir.rglob('*'):
            if file.is_file() and file != record_path:
                rel_path = file.relative_to(extract_dir)
                size = file.stat().st_size
                record_lines.append(f"{rel_path.as_posix()},,{size}")
        
        record_lines.append(f"{dist_info.name}/RECORD,,")
        record_path.write_text('\n'.join(sorted(record_lines)), encoding='utf-8')
        print(f"  ✓ Updated RECORD ({len(record_lines)} entries)")
        
        # 重新打包
        fixed_wheel = tmpdir / wheel_path.name
        with zipfile. ZipFile(fixed_wheel, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in extract_dir.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(extract_dir)
                    zf.write(file, arcname)
        
        # 替换原文件
        shutil.copy2(fixed_wheel, wheel_path)
        print(f"  ✓ Fixed successfully")
    
    return True

def main():
    from pathlib import Path
    
    print("=" * 70)
    print("Wheel Renaming and Fixing Tool")
    print("=" * 70)
    print(f"Platform tag: {OLD_PLATFORM} -> {NEW_PLATFORM}\n")
    
    # 获取所有 wheel 文件
    wheels = sorted(list(Path('.').glob('*.whl')))
    
    if not wheels:
        print("No wheel files found in current directory")
        return
    
    print(f"Found {len(wheels)} wheel file(s)\n")
    
    # 第一步：重命名
    print("=" * 70)
    print("Step 1: Renaming wheel files")
    print("=" * 70)
    
    renamed_wheels = []
    for wheel in wheels:
        if OLD_PLATFORM in wheel.name:
            print(f"\nRenaming: {wheel. name}")
            new_wheel = rename_wheel(wheel)
            renamed_wheels.append(new_wheel)
        else:
            print(f"\nSkipping: {wheel.name} (already correct)")
            renamed_wheels.append(wheel)
    
    # 第二步：修复元数据
    print("\n" + "=" * 70)
    print("Step 2: Fixing wheel metadata")
    print("=" * 70)
    
    success = 0
    failed = []
    
    for wheel in renamed_wheels:
        try: 
            if fix_wheel(wheel):
                success += 1
            else:
                failed.append(wheel.name)
        except Exception as e:
            print(f"  ✗ Error:  {e}")
            import traceback
            traceback.print_exc()
            failed.append(wheel.name)
    
    # 总结
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Successfully fixed:  {success}/{len(renamed_wheels)} wheel file(s)")
    
    if failed:
        print(f"\nFailed files:")
        for f in failed:
            print(f"  - {f}")
    else:
        print("\n✓ All wheels renamed and fixed successfully!")
        print("\nNext steps:")
        print("  1. Verify:  twine check *. whl")
        print("  2. Upload:  twine upload *.whl")

if __name__ == '__main__':
    main()