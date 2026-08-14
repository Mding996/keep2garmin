#!/usr/bin/env python3
"""
Keep → Garmin 数据迁移工具
一键从 Keep 导出运动数据并上传到 Garmin Connect

用法:
    # 仅导出 Keep 数据到 GPX
    python run.py keep 13800138000 你的密码

    # 导出并上传到 Garmin
    python run.py all 13800138000 你的密码 garmin@email.com garmin密码

    # 仅上传已有 GPX 到 Garmin
    python run.py upload garmin@email.com garmin密码
"""

import argparse
import sys

from keep_sync import sync_keep, get_output_dir
from garmin_upload import upload_gpx_files


def cmd_keep(args):
    """仅导出 Keep → GPX"""
    print("=" * 60)
    print("  Keep → GPX 导出")
    print("=" * 60)
    files = sync_keep(
        mobile=args.mobile,
        password=args.keep_password,
        output_dir=args.output,
        sport_types=args.sport_type,
        max_count=args.max,
        export_format=args.format,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"\n导出完成: {len(files)} 个文件 → {args.output}/")


def cmd_upload(args):
    """仅上传 GPX → Garmin"""
    print("=" * 60)
    print("  GPX → Garmin Connect 上传")
    print("=" * 60)
    upload_gpx_files(
        email=args.email,
        password=args.garmin_password,
        gpx_dir=args.gpx_dir,
        is_cn=not args.is_global,
    )


def cmd_all(args):
    """Keep → GPX → Garmin 全流程"""
    # Step 1: Keep 导出
    print("=" * 60)
    print("  Step 1/2: Keep → GPX 导出")
    print("=" * 60)
    files = sync_keep(
        mobile=args.mobile,
        password=args.keep_password,
        output_dir=args.output,
        sport_types=args.sport_type,
        max_count=args.max,
        export_format=args.format,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if not files:
        print("\n没有导出任何 GPX 文件，流程终止。")
        return

    # Step 2: Garmin 上传
    print("\n" + "=" * 60)
    print("  Step 2/2: GPX → Garmin Connect 上传")
    print("=" * 60)
    upload_gpx_files(
        email=args.email,
        password=args.garmin_password,
        gpx_dir=args.output,
        is_cn=not args.is_global,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Keep → Garmin 数据迁移工具 (基于 running_page 的 Keep API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 1. 仅导出 Keep 数据到 GPX 文件
  python run.py keep 13800138000 mypassword

  # 2. 导出并限制数量和类型
  python run.py keep 13800138000 mypassword -t running -n 10

  # 3. 仅上传已有 GPX 到 Garmin (中国区)
  python run.py upload garmin@email.com garminpass

  # 4. 全流程: Keep导出 + Garmin上传 (中国区账号)
  python run.py all 13800138000 keepass garmin@email.com garminpass

  # 5. Garmin 国际区账号
  python run.py all 13800138000 keepass garmin@email.com garminpass --garmin-global
        """,
    )

    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── keep 子命令 ──
    p_keep = sub.add_parser("keep", help="从 Keep 导出 GPX")
    p_keep.add_argument("mobile", help="Keep 手机号")
    p_keep.add_argument("keep_password", help="Keep 密码")
    p_keep.add_argument("-o", "--output", default=get_output_dir(), help="GPX 输出目录")
    p_keep.add_argument("-t", "--sport-type", nargs="+",
                         default=["running", "cycling", "hiking"],
                         help="运动类型 (默认: running cycling hiking)")
    p_keep.add_argument("-n", "--max", type=int, default=0, help="最多导出数 (0=全部)")
    p_keep.add_argument("-f", "--format", default="gpx", choices=["gpx", "tcx"],
                         help="导出格式: gpx (默认) 或 tcx (Garmin原生,自动识别活动类型)")
    p_keep.add_argument("--from", dest="start_date", default="", help="开始日期 YYYY-MM-DD")
    p_keep.add_argument("--to", dest="end_date", default="", help="结束日期 YYYY-MM-DD")
    p_keep.set_defaults(func=cmd_keep)

    # ── upload 子命令 ──
    p_up = sub.add_parser("upload", help="上传 GPX 到 Garmin")
    p_up.add_argument("email", help="Garmin Connect 邮箱")
    p_up.add_argument("garmin_password", help="Garmin Connect 密码")
    p_up.add_argument("-d", "--gpx-dir", default=get_output_dir(), help="GPX 目录")
    p_up.add_argument("--garmin-global", dest="is_global", action="store_true",
                      help="Garmin 国际区 (默认中国区)")
    p_up.set_defaults(func=cmd_upload)

    # ── all 子命令 ──
    p_all = sub.add_parser("all", help="全流程: Keep导出 → Garmin上传")
    p_all.add_argument("mobile", help="Keep 手机号")
    p_all.add_argument("keep_password", help="Keep 密码")
    p_all.add_argument("email", help="Garmin Connect 邮箱")
    p_all.add_argument("garmin_password", help="Garmin Connect 密码")
    p_all.add_argument("-o", "--output", default=get_output_dir(), help="GPX 输出目录")
    p_all.add_argument("-t", "--sport-type", nargs="+",
                       default=["running", "cycling", "hiking"],
                       help="运动类型")
    p_all.add_argument("-n", "--max", type=int, default=0, help="最多导出数 (0=全部)")
    p_all.add_argument("-f", "--format", default="tcx", choices=["gpx", "tcx"],
                        help="导出格式: gpx 或 tcx (默认tcx, Garmin原生识别活动类型)")
    p_all.add_argument("--from", dest="start_date", default="", help="开始日期 YYYY-MM-DD")
    p_all.add_argument("--to", dest="end_date", default="", help="结束日期 YYYY-MM-DD")
    p_all.add_argument("--garmin-global", dest="is_global", action="store_true",
                       help="Garmin 国际区 (默认中国区)")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
