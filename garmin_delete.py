"""
删除 Garmin Connect 中的 API 导入活动
"""

import time
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)


def delete_all_activities(email: str, password: str, is_cn: bool = True, dry_run: bool = True):
    """删除 Garmin 中所有 device=0 的导入活动"""
    print("[INFO] 正在登录 Garmin Connect ...")
    client = Garmin(email, password, is_cn=is_cn)
    client.login()
    print("[OK] 登录成功\n")

    deleted = 0
    errors = 0
    batch_size = 50

    if dry_run:
        print("=== DRY RUN 模式，仅列出不删除 ===\n")

    # 用分页方式获取所有活动
    start = 0
    while True:
        try:
            batch = client.get_activities(start=start, limit=batch_size)
        except GarminConnectTooManyRequestsError:
            print("[WARN] 请求频繁，等待60秒...")
            time.sleep(60)
            try:
                batch = client.get_activities(start=start, limit=batch_size)
            except Exception as e:
                print(f"[ERROR] {e}")
                break
        except Exception as e:
            print(f"[ERROR] 获取活动失败: {e}")
            break

        if not batch:
            break

        for act in batch:
            act_id = act.get("activityId")
            if not act_id:
                continue

            act_name = act.get("activityName", "?")
            stime = act.get("startTimeLocal", "?")[:10]

            if dry_run:
                print(f"  [DRY RUN] {stime} {act_name} (id={act_id})")
                deleted += 1
            else:
                try:
                    client.delete_activity(str(act_id))
                    deleted += 1
                    if deleted % 20 == 0:
                        print(f"  已删除 {deleted} 条...")
                except GarminConnectTooManyRequestsError:
                    print(f"  [WARN] 请求频繁，等待30秒...")
                    time.sleep(30)
                    try:
                        client.delete_activity(str(act_id))
                        deleted += 1
                    except Exception as e:
                        print(f"  [ERROR] {stime} {act_name}: {e}")
                        errors += 1
                except Exception as e:
                    error_str = str(e)
                    if "404" in error_str:
                        # 已经不存在了
                        deleted += 1
                    else:
                        print(f"  [ERROR] {stime} {act_name}: {e}")
                        errors += 1

            time.sleep(0.3)

        if len(batch) < batch_size:
            break
        start += batch_size
        time.sleep(0.5)

    print(f"\n[DONE] {'[DRY RUN] ' if dry_run else ''}删除: {deleted} 条, 错误: {errors} 条")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="删除 Garmin Connect 中导入的活动")
    parser.add_argument("email", help="Garmin Connect 邮箱")
    parser.add_argument("password", help="Garmin Connect 密码")
    parser.add_argument("--global", dest="is_global", action="store_true",
                        help="Garmin 国际区")
    parser.add_argument("--delete", action="store_true",
                        help="确认删除（不加此参数则为 dry-run）")

    args = parser.parse_args()

    if args.delete:
        print("=" * 60)
        print("  警告: 将删除所有 device=0 的导入活动!")
        print("  此操作不可撤销!")
        print("=" * 60)
        confirm = input("\n确认? 输入 YES 继续: ")
        if confirm != "YES":
            print("已取消。")
            exit(0)
        delete_all_activities(args.email, args.password, is_cn=not args.is_global, dry_run=False)
    else:
        print("[DRY RUN] 仅列出，不删除。加 --delete 参数确认删除。\n")
        delete_all_activities(args.email, args.password, is_cn=not args.is_global, dry_run=True)
