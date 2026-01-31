# fix_whl.py
import zipfile
import tempfile
import shutil
from pathlib import Path
import re
import argparse

# 配置：平台 tag 仍按你原来的逻辑
OLD_PLATFORM = "linux_x86_64"
NEW_PLATFORM = "manylinux_2_32_x86_64"

def normalize_post_tag(post_tag: str) -> str:
    """
    允许用户传：
      post2 / .post2 / POST2
    统一成 'post2'
    """
    t = post_tag.strip()
    if t.startswith("."):
        t = t[1:]
    t = t.lower()
    if not re.fullmatch(r"post\d+", t):
        raise ValueError(f"Invalid post tag: {post_tag!r}. Expected like 'post2'.")
    return t

def force_post_version(version: str, post_tag: str) -> str:
    """
    强制把版本号统一为 *.postN
    - 没有 post：追加 .postN
    - 已有 postX：替换为 .postN
    """
    base = re.sub(r"\.post\d+$", "", version)
    return f"{base}.{post_tag}"

def parse_wheel_name(wheel_path: Path):
    """
    解析 wheel 文件名：
      {dist}-{version}-{py}-{abi}-{plat}.whl
    注意 dist 里可能包含 '-'，所以从后往前取。
    """
    parts = wheel_path.stem.split('-')
    if len(parts) < 5:
        raise ValueError(f"Cannot parse wheel name: {wheel_path.name}, parts={parts}")
    platform_tag = parts[-1]
    abi_tag = parts[-2]
    python_tag = parts[-3]
    version = parts[-4]
    dist_name = '_'.join(parts[:-4])  # 你原脚本就是这样做的
    return dist_name, version, python_tag, abi_tag, platform_tag

def rename_wheel(wheel_path: Path, post_tag: str) -> Path:
    """重命名 wheel 文件：平台标签 + 版本号强制统一 post_tag"""
    wheel_path = Path(wheel_path)

    try:
        dist_name, version, python_tag, abi_tag, platform_tag = parse_wheel_name(wheel_path)
    except Exception as e:
        print(f"  ✗ Cannot parse for rename: {e}")
        return wheel_path

    new_version = force_post_version(version, post_tag)
    new_platform_tag = platform_tag.replace(OLD_PLATFORM, NEW_PLATFORM)

    new_name = f"{dist_name}-{new_version}-{python_tag}-{abi_tag}-{new_platform_tag}.whl"
    new_path = wheel_path.parent / new_name

    if new_path == wheel_path:
        return wheel_path

    try:
        wheel_path.rename(new_path)
        print(f"  ✓ Renamed:  {wheel_path.name}")
        print(f"         -> {new_name}")
        return new_path
    except Exception as e:
        print(f"  ✗ Failed to rename:  {e}")
        return wheel_path

def fix_wheel(wheel_path: Path, post_tag: str) -> bool:
    """修复/补齐 wheel 元数据，并强制统一版本号为 *.postN（含替换已有 post）"""
    wheel_path = Path(wheel_path)
    print(f"\nFixing: {wheel_path.name}")

    try:
        dist_name, version, python_tag, abi_tag, platform_tag = parse_wheel_name(wheel_path)
    except Exception as e:
        print(f"  ✗ Cannot parse wheel name: {e}")
        return False

    version_post = force_post_version(version, post_tag)
    print(f"  Parsed: {dist_name} v{version_post} ({python_tag}-{abi_tag}-{platform_tag})")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        extract_dir = tmpdir / "extracted"

        # 解压
        try:
            with zipfile.ZipFile(wheel_path, 'r') as zf:
                zf.extractall(extract_dir)
                all_files = zf.namelist()
                print(f"  Extracted {len(all_files)} files")
        except Exception as e:
            print(f"  ✗ Failed to extract: {e}")
            return False

        # dist-info：强制改成带 post 后的版本号
        dist_info_dirs = list(extract_dir.glob("*.dist-info"))
        desired_dist_info_name = f"{dist_name}-{version_post}.dist-info"
        desired_dist_info_path = extract_dir / desired_dist_info_name

        if not dist_info_dirs:
            desired_dist_info_path.mkdir(exist_ok=True)
            dist_info = desired_dist_info_path
            print(f"  Created dist-info: {desired_dist_info_name}")
        else:
            dist_info = dist_info_dirs[0]
            print(f"  Found dist-info:  {dist_info.name}")

            if dist_info.name != desired_dist_info_name:
                try:
                    dist_info.rename(desired_dist_info_path)
                    dist_info = desired_dist_info_path
                    print(f"  ✓ Renamed dist-info -> {desired_dist_info_name}")
                except Exception as e:
                    print(f"  ✗ Failed to rename dist-info: {e}")
                    return False

        # 描述映射（保留你原来的）
        descriptions = {
            'torch_cluster_rocm': 'PyTorch Extension Library of Optimized Graph Cluster Algorithms (ROCm Build)',
            'torch_scatter_rocm': 'PyTorch Extension Library of Optimized Scatter Operations (ROCm Build)',
            'torch_sparse_rocm': 'PyTorch Extension Library of Optimized Autograd Sparse Matrix Operations (ROCm Build)',
            'torch_spline_conv_rocm': 'PyTorch Implementation of the Spline-Based Convolution Operator of SplineCNN (ROCm Build)',
        }

        description = descriptions.get(dist_name, 'PyTorch ROCm Extension')
        pypi_name = dist_name.replace('_', '-')

        # 写 METADATA（版本号用 post 后的）
        metadata_path = dist_info / "METADATA"
        metadata_content = f"""Metadata-Version: 2.1
Name: {pypi_name}
Version: {version_post}
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
        print(f"  ✓ Created METADATA (Version={version_post})")

        # 写 WHEEL（保持原逻辑）
        wheel_file_path = dist_info / "WHEEL"
        wheel_content = f"""Wheel-Version: 1.0
Generator: bdist_wheel (0.41.2)
Root-Is-Purelib: false
Tag: {python_tag}-{abi_tag}-{platform_tag}
"""
        wheel_file_path.write_text(wheel_content, encoding='utf-8')
        print(f"  ✓ Created WHEEL")

        # 写 top_level.txt（保持原逻辑）
        top_level_path = dist_info / "top_level.txt"
        package_name = dist_name.replace('_rocm', '')
        top_level_path.write_text(package_name, encoding='utf-8')
        print(f"  ✓ Created top_level.txt ({package_name})")

        # 更新 RECORD（保持原逻辑）
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

        # 重新打包覆盖原 wheel
        fixed_wheel = tmpdir / wheel_path.name
        with zipfile.ZipFile(fixed_wheel, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in extract_dir.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(extract_dir)
                    zf.write(file, arcname)

        shutil.copy2(fixed_wheel, wheel_path)
        print(f"  ✓ Fixed successfully")

    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", default="post2", help="e.g. post2 / .post2")
    args = ap.parse_args()

    post_tag = normalize_post_tag(args.post)

    print("=" * 70)
    print("Wheel Renaming and Fixing Tool")
    print("=" * 70)
    print(f"Platform tag: {OLD_PLATFORM} -> {NEW_PLATFORM}")
    print(f"Version tag:  force .{post_tag}\n")

    wheels = sorted(Path(".").glob("*.whl"))
    if not wheels:
        print("No wheel files found in current directory")
        return

    print(f"Found {len(wheels)} wheel file(s)\n")

    # Step 1: 重命名（平台 + 强制 post 版本）
    print("=" * 70)
    print("Step 1: Renaming wheel files (platform + version)")
    print("=" * 70)

    renamed_wheels = []
    for wheel in wheels:
        print(f"\nRenaming: {wheel.name}")
        renamed_wheels.append(rename_wheel(wheel, post_tag))

    # Step 2: 修复元数据（同步 post 版本）
    print("\n" + "=" * 70)
    print("Step 2: Fixing wheel metadata")
    print("=" * 70)

    success = 0
    failed = []
    for wheel in renamed_wheels:
        try:
            if fix_wheel(wheel, post_tag):
                success += 1
            else:
                failed.append(wheel.name)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(wheel.name)

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Successfully fixed: {success}/{len(renamed_wheels)} wheel file(s)")
    if failed:
        print("\nFailed files:")
        for f in failed:
            print(f"  - {f}")
    else:
        print("\n✓ All wheels renamed and fixed successfully!")
        print("\nNext steps:")
        print("  1. Verify:  twine check *.whl")
        print("  2. Upload:  twine upload *.whl")

if __name__ == "__main__":
    main()
