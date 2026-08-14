"""
Garmin Connect 上传模块
将 GPX/FIT/TCX 文件上传到 Garmin Connect 并自动设置活动类型
"""

import json
import time
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectInvalidFileFormatError,
    GarminConnectTooManyRequestsError,
)

# 活动类型映射（文件名中的类型 → Garmin typeId/typeKey/parentTypeId）
ACTIVITY_TYPE_MAP = {
    "running":  {"typeId": 1,  "typeKey": "running", "parentTypeId": 17},
    "cycling":  {"typeId": 2,  "typeKey": "cycling", "parentTypeId": 17},
    "hiking":   {"typeId": 9,  "typeKey": "walking", "parentTypeId": 17},
}


def _detect_sport_type(filename: str) -> str | None:
    """从文件名检测运动类型"""
    for key in ACTIVITY_TYPE_MAP:
        if f"_{key}_" in filename or filename.startswith(key):
            return key
    return None


def _extract_activity_id(upload_result) -> str | None:
    """从上传响应中提取 activity ID"""
    try:
        if isinstance(upload_result, dict):
            return str(upload_result.get("detailedImportResult", {}).get("activityId")
                       or upload_result.get("activityId")
                       or upload_result.get("activity_id"))
        if isinstance(upload_result, str):
            data = json.loads(upload_result)
            return str(data.get("detailedImportResult", {}).get("activityId")
                       or data.get("activityId"))
    except Exception:
        pass
    return None


def upload_gpx_files(
    email: str,
    password: str,
    gpx_dir: str | None = None,
    is_cn: bool = True,
    verbose: bool = True,
) -> dict:
    """将目录中的 GPX/TCX 文件逐个上传到 Garmin Connect，并设置正确的活动类型"""
    result = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    if gpx_dir is None:
        from keep_sync import get_output_dir
        gpx_dir = get_output_dir()

    gpx_files = sorted(list(Path(gpx_dir).glob("*.gpx")) + list(Path(gpx_dir).glob("*.tcx")))
    if not gpx_files:
        print(f"[WARN] {gpx_dir}/ 下没有找到 GPX/TCX 文件")
        return result

    print(f"[INFO] 找到 {len(gpx_files)} 个 GPX 文件")

    print("[INFO] 正在登录 Garmin Connect ...")
    try:
        client = Garmin(email, password, is_cn=is_cn)
        client.login()
    except GarminConnectAuthenticationError:
        print("[ERROR] Garmin 登录失败：账号或密码错误")
        result["errors"].append("Garmin 登录认证失败")
        return result
    except GarminConnectConnectionError as e:
        print(f"[ERROR] Garmin 连接失败: {e}")
        result["errors"].append(f"Garmin 连接失败: {e}")
        return result
    except Exception as e:
        print(f"[ERROR] Garmin 登录异常: {e}")
        result["errors"].append(f"Garmin 登录异常: {e}")
        return result

    print(f"[OK] Garmin Connect 登录成功 (区域: {'中国' if is_cn else '国际'})\n")

    for i, gpx_path in enumerate(gpx_files):
        filename = gpx_path.name
        filepath = str(gpx_path.resolve())
        sport = _detect_sport_type(filename)
        if verbose:
            print(f"  [{i + 1}/{len(gpx_files)}] {filename} ...", end=" ")

        act_id = None
        try:
            resp = client.upload_activity(filepath)
            act_id = _extract_activity_id(resp)
            result["success"] += 1
            if verbose:
                print("[OK] 上传成功", end="")
        except GarminConnectTooManyRequestsError:
            print("[WARN] 请求太频繁，等待 30 秒...")
            time.sleep(30)
            try:
                resp = client.upload_activity(filepath)
                act_id = _extract_activity_id(resp)
                result["success"] += 1
                print("  [OK] 重试成功", end="")
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"{filename}: {e}")
                print(f"[FAIL] {e}")
                continue
        except GarminConnectInvalidFileFormatError as e:
            result["failed"] += 1
            result["errors"].append(f"{filename}: 格式不支持")
            print(f"[FAIL] 格式不支持")
            continue
        except Exception as e:
            error_str = str(e)
            if "409" in error_str or "duplicate" in error_str.lower():
                result["skipped"] += 1
                print("-> 已存在，跳过")
            else:
                result["failed"] += 1
                result["errors"].append(f"{filename}: {error_str}")
                print(f"[FAIL] {error_str}")
            continue

        # 设置活动类型
        if act_id and sport and sport in ACTIVITY_TYPE_MAP:
            try:
                ti = ACTIVITY_TYPE_MAP[sport]
                client.set_activity_type(act_id, ti["typeId"], ti["typeKey"], ti["parentTypeId"])
                if verbose:
                    print(f" [{ti['typeKey']}]")
            except Exception as e:
                if verbose:
                    print(f" (类型设置失败: {e})")
        else:
            if verbose:
                print()

        time.sleep(1.0)

    print(f"\n[DONE] 上传结果: {result['success']} 成功, "
          f"{result['skipped']} 已跳过, {result['failed']} 失败")
    if result["errors"]:
        print("错误详情:")
        for err in result["errors"][:10]:
            print(f"  - {err}")
        if len(result["errors"]) > 10:
            print(f"  ... 还有 {len(result['errors']) - 10} 条错误")

    return result


def upload_single_gpx(
    email: str,
    password: str,
    gpx_file: str,
    is_cn: bool = True,
) -> bool:
    """上传单个 GPX 文件到 Garmin Connect（含类型设置）"""
    p = Path(gpx_file)
    if not p.exists():
        print(f"[ERROR] 文件不存在: {gpx_file}")
        return False

    sport = _detect_sport_type(p.name)

    try:
        client = Garmin(email, password, is_cn=is_cn)
        client.login()
    except Exception as e:
        print(f"[ERROR] Garmin 登录失败: {e}")
        return False

    try:
        resp = client.upload_activity(str(p.resolve()))
        act_id = _extract_activity_id(resp)
        print(f"[OK] {p.name} 上传成功", end="")

        if act_id and sport and sport in ACTIVITY_TYPE_MAP:
            ti = ACTIVITY_TYPE_MAP[sport]
            client.set_activity_type(act_id, ti["typeId"], ti["typeKey"], ti["parentTypeId"])
            print(f" [{ti['typeKey']}]")
        else:
            print()

        return True
    except Exception as e:
        print(f"[ERROR] 上传失败: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="上传 GPX 文件到 Garmin Connect")
    parser.add_argument("email", help="Garmin Connect 邮箱")
    parser.add_argument("password", help="Garmin Connect 密码")
    parser.add_argument("-d", "--dir", default=None, help="GPX 文件目录 (默认: 应用同级 gpx_output)")
    parser.add_argument("-f", "--file", help="上传单个 GPX 文件")
    parser.add_argument("--global", dest="is_global", action="store_true",
                        help="使用 Garmin 国际区 (默认中国区)")

    args = parser.parse_args()

    if args.file:
        upload_single_gpx(args.email, args.password, args.file, is_cn=not args.is_global)
    else:
        upload_gpx_files(args.email, args.password, args.dir, is_cn=not args.is_global)
