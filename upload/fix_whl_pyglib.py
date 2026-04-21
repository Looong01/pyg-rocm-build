#!/usr/bin/env python3
"""
修复 pyg-lib-rocm wheel 文件，解决上传 PyPI 时的各种问题：
1. 修复版本号双点问题（0.6.0.. -> 0.6.0）
2. 修复 wheel 文件名格式（pyg_lib-rocm -> pyg_lib_rocm）
3. 修复 dist-info 目录名（带版本号，使用下划线）
4. 修复 METADATA 中的 Name 字段（pyg-lib-rocm）
5. 修复 top_level.txt（保持 pyg_lib）
6. 支持添加 post 版本后缀（如 post1, post2）

使用方法：
    python fix_whl_pyglib.py --post post2
    python fix_whl_pyglib.py --post "${version_tag}"
    或
    python fix_whl_pyglib.py  # 自动修复当前目录下所有 pyg_lib 开头的 .whl 文件
"""
import zipfile
import tempfile
import shutil
import sys
from pathlib import Path
import re
import argparse

# 默认只处理 pyg_lib 开头的 wheel 文件
DEFAULT_GLOB_PATTERN = "pyg_lib*.whl"

# Platform tag 转换（参考 fix_whl.py）
OLD_PLATFORM = "linux_x86_64"
NEW_PLATFORM = "manylinux_2_32_x86_64"


def normalize_post_tag(post_tag: str) -> str:
    """
    规范化 post tag：
      - 去掉前导点号
      - 转小写
      - 支持 post1 / .post1 / POST1
    """
    t = post_tag.strip()
    if t.startswith("."):
        t = t[1:]
    return t.lower()


def force_post_version(version: str, post_tag: str) -> str:
    """
    强制添加 post 版本后缀：
    - 没有 post：追加 .postN
    - 已有 postX：替换为 .postN
    """
    if not post_tag:
        return version
    base = re.sub(r"\.post\d+$", "", version)
    return f"{base}.{post_tag}"


def normalize_version(version: str) -> str:
    """修复版本号中的双点问题: 0.6.0.. -> 0.6.0"""
    while '..' in version:
        version = version.replace('..', '.')
    return version.rstrip('.')


def parse_wheel_name(wheel_path: Path):
    """
    解析 wheel 文件名：
      {dist}-{version}-{py}-{abi}-{plat}.whl
    注意 dist 可能包含 '-'，所以从后往前取。
    """
    parts = wheel_path.stem.split('-')
    if len(parts) < 5:
        raise ValueError(f"Cannot parse wheel name: {wheel_path.name}")
    platform_tag = parts[-1]
    abi_tag = parts[-2]
    python_tag = parts[-3]
    version = parts[-4]
    # dist 名称（原始格式，可能包含 -）
    dist_name = '-'.join(parts[:-4])
    return dist_name, version, python_tag, abi_tag, platform_tag


def fix_wheel(wheel_path: Path, post_tag: str = "") -> Path:
    """修复单个 wheel 文件"""
    wheel_path = Path(wheel_path)
    print(f"\n[处理] {wheel_path.name}")

    # 解析 wheel 文件名
    try:
        raw_dist, raw_version, pyver, abi, platform = parse_wheel_name(wheel_path)
    except Exception as e:
        raise ValueError(f"无法解析 wheel 文件名: {e}")

    print(f"  解析: dist={raw_dist}, version={raw_version}")

    # 步骤 1: 修复版本号（先修复双点问题）
    normalized_version = normalize_version(raw_version)
    print(f"  修复版本号: {raw_version} -> {normalized_version}")

    # 步骤 2: 添加 post 后缀
    final_version = force_post_version(normalized_version, post_tag)
    if final_version != normalized_version:
        print(f"  添加 post: {normalized_version} -> {final_version}")

    # 步骤 3: 修复 dist 名称（wheel 文件名中使用下划线）
    dist_for_filename = raw_dist.replace('-', '_')
    print(f"  包名(文件名): {raw_dist} -> {dist_for_filename}")

    # 步骤 4: 计算各种名称格式
    # PyPI 显示名称（使用连字符）: pyg-lib-rocm
    pypi_name = dist_for_filename.replace('_', '-')
    # dist-info 目录名（带版本号）: pyg_lib_rocm-0.6.0.post1.dist-info
    dist_info_name = f"{dist_for_filename}-{final_version}.dist-info"
    print(f"  dist-info: {dist_info_name}")

    # 步骤 4.5: 平台标签转换
    new_platform = platform.replace(OLD_PLATFORM, NEW_PLATFORM)
    if new_platform != platform:
        print(f"  平台标签: {platform} -> {new_platform}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        extract_dir = tmpdir / "extracted"

        # 解压 wheel
        with zipfile.ZipFile(wheel_path, 'r') as zf:
            zf.extractall(extract_dir)

        # 找到并处理 dist-info 目录
        dist_info_dirs = list(extract_dir.glob("*.dist-info"))
        if not dist_info_dirs:
            raise ValueError(f"未找到 dist-info 目录")

        old_dist_info = dist_info_dirs[0]
        new_dist_info = extract_dir / dist_info_name

        # 重命名 dist-info 目录
        if old_dist_info.name != dist_info_name:
            old_dist_info.rename(new_dist_info)
            print(f"  ✓ 重命名 dist-info: {old_dist_info.name} -> {dist_info_name}")

        # 修复 METADATA
        metadata_path = new_dist_info / "METADATA"
        if metadata_path.exists():
            content = metadata_path.read_text(encoding='utf-8')
            # 修复 Name 字段
            content = re.sub(r'^Name: .+$', f'Name: {pypi_name}', content, flags=re.MULTILINE)
            # 修复 Version 字段
            content = re.sub(r'^Version: .+$', f'Version: {final_version}', content, flags=re.MULTILINE)
            metadata_path.write_text(content, encoding='utf-8')
            print(f"  ✓ 修复 METADATA: Name={pypi_name}, Version={final_version}")

        # 修复 WHEEL 文件
        wheel_file_path = new_dist_info / "WHEEL"
        wheel_content_changed = False
        if wheel_file_path.exists():
            content = wheel_file_path.read_text(encoding='utf-8')
            if not content.startswith('Wheel-Version:'):
                content = 'Wheel-Version: 1.0\n' + content
            # 更新 platform tag
            new_content = re.sub(
                rf'^Tag: (\S+-\S+-){re.escape(OLD_PLATFORM)}$',
                rf'Tag: \1{NEW_PLATFORM}',
                content,
                flags=re.MULTILINE
            )
            if new_content != content:
                wheel_content_changed = True
                content = new_content
            wheel_file_path.write_text(content, encoding='utf-8')
            print(f"  ✓ 修复 WHEEL")

        # 修复 top_level.txt（保持 pyg_lib，不要带 _rocm 后缀）
        top_level_path = new_dist_info / "top_level.txt"
        if top_level_path.exists():
            # 从 dist 名称中提取基础包名（去掉 _rocm 后缀）
            base_pkg = dist_for_filename.replace('_rocm', '')
            top_level_path.write_text(base_pkg, encoding='utf-8')
            print(f"  ✓ 修复 top_level.txt: {base_pkg}")

        # 修复 RECORD（更新 dist-info 路径引用）
        record_path = new_dist_info / "RECORD"
        if record_path.exists():
            content = record_path.read_text(encoding='utf-8')
            old_name = old_dist_info.name
            content = content.replace(f"{old_name}/", f"{dist_info_name}/")
            record_path.write_text(content, encoding='utf-8')
            print(f"  ✓ 修复 RECORD")

        # 如果 WHEEL 文件内容有变化，需要更新 RECORD 中的 hash
        if wheel_content_changed and record_path.exists():
            import hashlib, base64
            record_lines = record_path.read_text(encoding='utf-8').splitlines()
            new_lines = []
            for line in record_lines:
                cols = line.split(',')
                if len(cols) >= 3 and cols[0].endswith('/WHEEL'):
                    wheel_data = wheel_file_path.read_bytes()
                    digest = hashlib.sha256(wheel_data).digest()
                    b64 = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
                    cols[1] = f"sha256={b64}"
                    cols[2] = str(len(wheel_data))
                    new_lines.append(','.join(cols))
                else:
                    new_lines.append(line)
            record_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
            print(f"  ✓ 更新 RECORD (WHEEL hash)")

        # 重新打包 wheel
        fixed_wheel = tmpdir / wheel_path.name
        with zipfile.ZipFile(fixed_wheel, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in extract_dir.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(extract_dir)
                    zf.write(file, arcname)

        # 步骤 5: 生成新的 wheel 文件名
        new_wheel_name = f"{dist_for_filename}-{final_version}-{pyver}-{abi}-{new_platform}.whl"
        new_wheel_path = wheel_path.parent / new_wheel_name

        # 如果文件名有变化，备份原文件
        if new_wheel_name != wheel_path.name:
            backup_path = wheel_path.with_suffix('.whl.bak')
            shutil.move(wheel_path, backup_path)
            shutil.copy2(fixed_wheel, new_wheel_path)
            print(f"  ✓ 重命名 wheel: {wheel_path.name} -> {new_wheel_name}")
            print(f"  备份: {backup_path.name}")
            return new_wheel_path
        else:
            shutil.copy2(fixed_wheel, wheel_path)
            print(f"  ✓ 完成（文件名无需修改）")
            return wheel_path


def main():
    ap = argparse.ArgumentParser(
        description="修复 pyg-lib-rocm wheel 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 修复当前目录下所有 pyg_lib 开头的 wheel 文件
  python fix_whl_pyglib.py

  # 修复指定 wheel 文件
  python fix_whl_pyglib.py /path/to/pyg_lib_rocm-0.6.0-*.whl

  # 添加 post 版本后缀
  python fix_whl_pyglib.py --post post2
  python fix_whl_pyglib.py --post "${version_tag}"
"""
    )
    ap.add_argument(
        "--post",
        default="",
        help="post 版本后缀，如 post1, post2（默认空）"
    )
    ap.add_argument(
        "wheels",
        nargs="*",
        help=f"wheel 文件路径，默认为当前目录下所有 {DEFAULT_GLOB_PATTERN} 文件"
    )
    args = ap.parse_args()

    # 处理 post tag
    post_tag = normalize_post_tag(args.post) if args.post else ""
    if post_tag:
        print(f"将添加 post 后缀: .{post_tag}")

    # 获取 wheel 文件列表
    if args.wheels:
        wheels = [Path(p) for p in args.wheels]
    else:
        # 默认只处理 pyg_lib 开头的 wheel 文件
        wheels = sorted(Path(".").glob(DEFAULT_GLOB_PATTERN))

    if not wheels:
        print(f"未找到 wheel 文件 (模式: {DEFAULT_GLOB_PATTERN})")
        print("提示: 可以手动指定文件路径，或使用 --post 参数")
        sys.exit(1)

    print(f"找到 {len(wheels)} 个 wheel 文件")
    print("=" * 60)

    success = 0
    failed = []

    for wheel in wheels:
        try:
            fix_wheel(wheel, post_tag=post_tag)
            success += 1
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            failed.append((wheel.name, str(e)))

    print("\n" + "=" * 60)
    print(f"成功: {success}/{len(wheels)}")

    if failed:
        print("\n失败的文件:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        sys.exit(1)
    else:
        print("\n✓ 所有 wheel 文件已修复!")
        print("\n下一步:")
        print("  1. 检查: twine check *.whl")
        print("  2. 上传: twine upload *.whl")


if __name__ == "__main__":
    main()
