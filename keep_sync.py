"""
Keep 数据导出模块
实现 Keep API 登录、运动记录拉取、GPS 轨迹解码、GPX 文件生成

基于 running_page (yihong0618) 的 Keep API 逆向成果
API 参考: https://github.com/yihong0618/running_page
"""

import base64
import gzip
import json
import math
import os
import time
import zlib
from datetime import datetime, timezone

import requests
from Crypto.Cipher import AES
from gpxpy import gpx as gpx_lib
from lxml import etree


def get_base_dir() -> str:
    """返回应用所在目录（EXE 或脚本同级目录）"""
    import sys as _sys
    if getattr(_sys, "frozen", False):
        # PyInstaller 打包后: 使用 EXE 所在目录
        return os.path.dirname(os.path.abspath(_sys.executable))
    # 普通 Python: 使用本脚本所在目录
    return os.path.dirname(os.path.abspath(__file__))


def get_output_dir() -> str:
    """默认输出目录 = 应用同级目录下的 gpx_output"""
    return os.path.join(get_base_dir(), "gpx_output")


# ── Keep API 地址 ────────────────────────────────────────────
KEEP_LOGIN_URL = "https://api.gotokeep.com/v1.1/users/login"
KEEP_STATS_URL = "https://api.gotokeep.com/pd/v3/stats/detail"
KEEP_RUNNING_LOG_URL = "https://api.gotokeep.com/pd/v3/runninglog/{run_id}"
KEEP_CYCLING_LOG_URL = "https://api.gotokeep.com/pd/v3/cyclinglog/{run_id}"

# 运动类型与 API 参数、日志 URL 的映射
SPORT_CONFIG = {
    "running": {
        "type_param": "running",
        "log_url": KEEP_RUNNING_LOG_URL,
        "gpx_type": "running",
    },
    "cycling": {
        "type_param": "cycling",
        "log_url": KEEP_CYCLING_LOG_URL,
        "gpx_type": "cycling",
    },
    "hiking": {
        "type_param": "hiking",
        "log_url": "https://api.gotokeep.com/pd/v3/hikinglog/{run_id}",
        "gpx_type": "hiking",
    },
}

# UA 模拟（Keep 会校验）
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)


# ═══════════════════════════════════════════════════════════════
# 全局开关
# ═══════════════════════════════════════════════════════════════
GCJ02_TO_WGS84 = True   # 是否启用 GCJ-02 → WGS-84 坐标转换
DEBUG = False           # 调试模式：打印原始 API 响应


def _debug_print(msg: str):
    """仅在 DEBUG 模式下打印"""
    if DEBUG:
        print(f"  [DEBUG] {msg}")


def _dump_json(obj, label: str = "", max_len: int = 800):
    """美的打印 JSON 摘要"""
    if not DEBUG:
        return
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(s) > max_len:
        s = s[:max_len] + f"\n  ... (截断，总长 {len(s)} 字符)"
    print(f"  [DEBUG] {label}:\n{s}")


# ═══════════════════════════════════════════════════════════════
# GCJ-02 ↔ WGS-84 坐标转换
# 中国地图标准 GCJ-02 (火星坐标系) → 全球标准 WGS-84
# ═══════════════════════════════════════════════════════════════

PI = math.pi
A = 6378245.0
EE = 0.00669342162296594323


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """将 GCJ-02 (火星坐标) 转换为 WGS-84"""
    if not GCJ02_TO_WGS84:
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lon(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lng - dlng, lat - dlat


# ═══════════════════════════════════════════════════════════════
# Keep API 客户端
# ═══════════════════════════════════════════════════════════════

class KeepClient:
    """Keep API 客户端"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        self.token: str | None = None

    # ── 登录 ──────────────────────────────────────────────────

    def login(self, mobile: str, password: str) -> bool:
        """手机号 + 密码登录 Keep"""
        payload = {"mobile": mobile, "password": password}
        headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}

        try:
            resp = self.session.post(KEEP_LOGIN_URL, data=payload, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(f"[ERROR] 登录请求失败: {e}")
            return False

        data = resp.json()
        _debug_print(f"登录 HTTP {resp.status_code}")
        _dump_json(data, "登录响应")

        if resp.status_code != 200 or data.get("ok") is not True:
            error_msg = data.get("error") or data.get("message") or str(data)
            print(f"[ERROR] Keep 登录失败: {error_msg}")
            return False

        # 尝试多种 token 位置
        self.token = (
            data.get("data", {}).get("token")
            or data.get("token")
            or data.get("access_token")
        )
        if not self.token:
            print(f"[ERROR] 登录响应中未找到 token，响应结构: {json.dumps(data, ensure_ascii=False)[:500]}")
            return False

        self.session.headers["Authorization"] = f"Bearer {self.token}"
        print("[OK] Keep 登录成功")
        return True

    # ── 获取运动统计数据列表 ─────────────────────────────────

    def fetch_activity_list(self, sport_type: str = "running") -> list[dict]:
        """获取某类运动的全部统计数据列表（自动翻页），展开 date-group → logs → stats 嵌套结构"""
        if sport_type not in SPORT_CONFIG:
            print(f"[ERROR] 不支持的运动类型: {sport_type}")
            return []

        all_activities = []
        last_date = ""  # 第一页传空字符串
        page = 0

        while True:
            page += 1
            params = {
                "dateUnit": "all",
                "type": SPORT_CONFIG[sport_type]["type_param"],
                "lastDate": last_date,
            }

            try:
                resp = self.session.get(KEEP_STATS_URL, params=params, timeout=20)
            except requests.RequestException as e:
                print(f"[ERROR] 获取 {sport_type} 列表(第{page}页)失败: {e}")
                break

            if resp.status_code != 200:
                print(f"[ERROR] Keep API 返回 {resp.status_code}: {resp.text[:300]}")
                break

            data = resp.json()
            resp_data = data.get("data", {})
            records = resp_data.get("records") or []

            _debug_print(f"{sport_type} 第{page}页: {len(records)} 个日期组, lastTimestamp={resp_data.get('lastTimestamp')}")

            if not records:
                break

            # 展开 records → logs → stats
            for record in records:
                logs = record.get("logs", [])
                for log_entry in logs:
                    if log_entry.get("type") != "stats":
                        continue
                    stats = log_entry.get("stats", {})
                    if not stats:
                        continue
                    stats["_sport_type"] = sport_type
                    if not stats.get("name"):
                        stats["name"] = record.get("date", "")
                    # 从 nameSuffix 提取距离
                    suffix = stats.get("nameSuffix", "")
                    if suffix and not stats.get("distance"):
                        try:
                            num_str = suffix.replace("公里", "").replace("km", "").strip()
                            stats["distance"] = float(num_str) * 1000
                        except ValueError:
                            pass
                    all_activities.append(stats)

            # 检查是否需要翻页
            last_timestamp = resp_data.get("lastTimestamp", 0)
            if last_timestamp and last_timestamp > 0:
                last_date = str(last_timestamp)
                _debug_print(f"  继续翻页: lastDate={last_date}")
                time.sleep(0.3)  # 避免请求太快
            else:
                break

        _debug_print(f"{sport_type} 展开后共 {len(all_activities)} 条活动 (共{page}页)")
        return all_activities

    def fetch_all_activities(self, sport_types: list[str] | None = None) -> list[dict]:
        """拉取所有运动类型的活动列表"""
        if sport_types is None:
            sport_types = ["running", "cycling", "hiking"]

        all_activities = []
        for st in sport_types:
            print(f"\n[INFO] 正在获取 {st} 数据...")
            records = self.fetch_activity_list(st)
            print(f"[INFO] {st}: 找到 {len(records)} 条记录")
            all_activities.extend(records)

        # 按时间排序（最新在前）
        all_activities.sort(
            key=lambda x: x.get("startTime") or 0,
            reverse=True,
        )
        return all_activities

    # ── 获取单条运动的 GPS 详情 ─────────────────────────────

    def fetch_activity_detail(self, activity_id: str, sport_type: str) -> dict | None:
        """获取某条运动的详细 GPS 数据"""
        config = SPORT_CONFIG.get(sport_type)
        if not config:
            return None

        url = config["log_url"].format(run_id=activity_id)

        try:
            resp = self.session.get(url, timeout=20)
        except requests.RequestException as e:
            print(f"  [WARN] 获取活动 {activity_id} 详情失败: {e}")
            return None

        if resp.status_code != 200:
            print(f"  [WARN] 活动 {activity_id} 详情 HTTP {resp.status_code}")
            _debug_print(f"  响应体: {resp.text[:300]}")
            return None

        data = resp.json()
        _debug_print(f"活动 {activity_id} 详情 HTTP 200")
        _dump_json(data, f"活动 {activity_id} 详情")

        return data

    # ── 解析 GPS 轨迹数据 ────────────────────────────────────

    @staticmethod
    def decode_runmap(runmap_data: str) -> list[dict] | None:
        """
        解码 Keep 的 runmap 数据 (gzip + base64)
        返回 track point 列表
        """
        if not runmap_data:
            return None

        _debug_print(f"runmap 原始数据前 80 字符: {runmap_data[:80]}")

        try:
            compressed = base64.b64decode(runmap_data)
            decompressed = gzip.decompress(compressed)
            raw = json.loads(decompressed.decode("utf-8"))
        except Exception as e:
            print(f"    [WARN] 解码 runmap 失败: {e}")
            _debug_print(f"    尝试直接解析 JSON ...")
            try:
                raw = json.loads(runmap_data)
            except Exception:
                return None

        if not isinstance(raw, list):
            _debug_print(f"runmap 解码后不是 list，而是 {type(raw)}")
            # 可能是 dict，尝试找到 points 数组
            if isinstance(raw, dict):
                for key in ["points", "track", "data", "list", "tracks"]:
                    if key in raw and isinstance(raw[key], list):
                        raw = raw[key]
                        break
                else:
                    return None
            else:
                return None

        _debug_print(f"runmap 解码后共 {len(raw)} 个元素")
        if raw:
            _dump_json(raw[0], "第一个点的结构")

        points = []
        for pt in raw:
            try:
                lng = float(pt.get("longitude", pt.get("lng", 0)))
                lat = float(pt.get("latitude", pt.get("lat", 0)))

                if lng == 0 and lat == 0:
                    continue

                wgs_lng, wgs_lat = gcj02_to_wgs84(lng, lat)

                ele = pt.get("elevation", pt.get("ele", pt.get("altitude", 0)))
                ts = pt.get("timestamp", pt.get("time", 0))
                hr = pt.get("heartRate", pt.get("heart_rate", pt.get("hr"), None))

                if ts and isinstance(ts, (int, float)) and ts > 1e12:
                    ts = ts / 1000.0

                points.append({
                    "latitude": wgs_lat,
                    "longitude": wgs_lng,
                    "elevation": float(ele) if ele else 0,
                    "time": ts,
                    "heart_rate": int(hr) if hr else None,
                })
            except (ValueError, TypeError):
                continue

        return points if points else None

    # ── 提取活动详情中的轨迹数据 ────────────────────────────

    @staticmethod
    def extract_track_points(detail: dict) -> list[dict] | None:
        """从活动详情 JSON 中提取轨迹点，优先使用 geoPoints (完整GPS)"""
        data = detail.get("data", detail)

        if isinstance(data, dict):
            available = [k for k in data.keys()
                         if k in ("geoPoints", "crossKmPoints", "stepPoints", "heartRate")]
            _debug_print(f"可用字段: {available}")

        # ── 方案1: geoPoints (AES+zlib, 完整高精度GPS) ──
        gp = data.get("geoPoints")
        if gp and isinstance(gp, str) and len(gp) > 100:
            result = KeepClient._decode_geo_points(gp, data)
            if result:
                _debug_print(f"geoPoints 成功: {len(result)} 个轨迹点")
                return result

        # ── 方案2: crossKmPoints (每公里分点，降级方案) ──
        cross_km = data.get("crossKmPoints")
        if cross_km and isinstance(cross_km, list) and len(cross_km) > 0:
            first = cross_km[0]
            if isinstance(first, dict) and ("latitude" in first or "lat" in first):
                _debug_print(f"降级使用 crossKmPoints: {len(cross_km)} 个点")
                return KeepClient._parse_cross_km_points(cross_km, data)

        # ── 方案3: stepPoints (gzip+base64，老格式) ──
        sp = data.get("stepPoints")
        if sp and isinstance(sp, str) and sp.startswith("H4sI"):
            result = KeepClient._decode_gzip_base64(sp)
            if result and isinstance(result, list) and len(result) > 1:
                if any(isinstance(p, dict) and ("latitude" in p or "lat" in p)
                       for p in result[:3]):
                    return KeepClient._parse_geo_points(result, data)

        _debug_print("未找到可解码的 GPS 轨迹数据")
        return None

    @staticmethod
    def _parse_cross_km_points(points: list[dict], activity_data: dict) -> list[dict] | None:
        """将 crossKmPoints 转为标准 track point 格式"""
        result = []
        start_time_ms = activity_data.get("startTime") or 0

        for pt in points:
            lat = pt.get("latitude") or pt.get("lat", 0)
            lon = pt.get("longitude") or pt.get("lng", 0)
            if lat == 0 and lon == 0:
                continue

            wgs_lng, wgs_lat = gcj02_to_wgs84(lon, lat)

            # timestamp 是距离开始时间的累计十分之一秒 (deciseconds)
            # 例如 kmPace=341 秒，则 timestamp=3410 (341*10)
            ts_offset_decis = pt.get("timestamp", 0)
            if ts_offset_decis and start_time_ms:
                ts_offset_ms = ts_offset_decis * 100  # 十分之一秒 → 毫秒
                abs_time = (start_time_ms + ts_offset_ms) / 1000.0
            else:
                abs_time = start_time_ms / 1000.0 if start_time_ms else 0

            hr = pt.get("averageHeartRate") or pt.get("heartRate") or None

            result.append({
                "latitude": wgs_lat,
                "longitude": wgs_lng,
                "elevation": float(pt.get("altitude", 0) or 0),
                "time": abs_time,
                "heart_rate": int(hr) if hr else None,
            })

        return result if result else None

    @staticmethod
    def _decode_gzip_base64(data_str: str):
        """解码 gzip + base64 数据"""
        try:
            import base64 as _b64
            import gzip as _gz
            import json as _json
            compressed = _b64.b64decode(data_str)
            decompressed = _gz.decompress(compressed)
            return _json.loads(decompressed.decode("utf-8"))
        except Exception:
            return None

    # Keep geoPoints AES 密钥（来自 running_page）
    _AES_KEY = base64.b64decode("NTZmZTU5OzgyZzpkODczYw==")
    _AES_IV = base64.b64decode("MjM0Njg5MjQzMjkyMDMwMA==")

    @staticmethod
    def _decode_geo_points(gp_str: str, activity_data: dict) -> list[dict] | None:
        """
        解码 geoPoints (AES-CBC 加密 + zlib 压缩 + JSON)
        参考 running_page decode_runmap_data()
        """
        try:
            raw = base64.b64decode(gp_str)
        except Exception:
            return None

        # 策略1: 新版格式 - AES-CBC 解密 + zlib 解压
        try:
            cipher = AES.new(KeepClient._AES_KEY, AES.MODE_CBC, KeepClient._AES_IV)
            decrypted = cipher.decrypt(raw)
            decompressed = zlib.decompress(decrypted, 16 + zlib.MAX_WBITS)
            parsed = json.loads(decompressed)
            if isinstance(parsed, list) and len(parsed) > 0:
                _debug_print(f"geoPoints AES+zlib: {len(parsed)} 个点")
                return KeepClient._parse_geo_points(parsed, activity_data)
        except Exception as e:
            _debug_print(f"geoPoints AES+zlib 失败: {e}")

        # 策略2: 旧版格式 - 仅 zlib 解压 (无 AES)
        try:
            decompressed = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
            parsed = json.loads(decompressed)
            if isinstance(parsed, list) and len(parsed) > 0:
                _debug_print(f"geoPoints zlib only: {len(parsed)} 个点")
                return KeepClient._parse_geo_points(parsed, activity_data)
        except Exception:
            pass

        # 策略3: gzip
        if gp_str.startswith("H4sI"):
            result = KeepClient._decode_gzip_base64(gp_str)
            if result and isinstance(result, list):
                return KeepClient._parse_geo_points(result, activity_data)

        _debug_print("geoPoints 所有解码策略均失败")
        return None

    @staticmethod
    def _parse_geo_points(points: list[dict], activity_data: dict) -> list[dict] | None:
        """将 geoPoints 解码后的点列表转为标准格式（带坐标转换和心率绑定）"""
        start_time_ms = activity_data.get("startTime") or 0
        heart_rate_data = activity_data.get("heartRate", {})
        hr_list_raw = heart_rate_data.get("heartRates") if heart_rate_data else None
        decoded_hr = None
        if hr_list_raw and isinstance(hr_list_raw, str):
            decoded_hr = KeepClient._decode_gzip_base64(hr_list_raw)

        result = []
        for pt in points:
            lat = pt.get("latitude") or pt.get("lat", 0)
            lon = pt.get("longitude") or pt.get("lng", 0)
            if lat == 0 and lon == 0:
                continue

            # GCJ-02 → WGS-84
            wgs_lng, wgs_lat = gcj02_to_wgs84(lon, lat)

            # timestamp 是十分之一秒 (decisecond)，需转为秒
            ts_decis = pt.get("timestamp", 0)
            if ts_decis and start_time_ms:
                # 如果 timestamp 值很大（> 3_600_000），说明是绝对时间而非偏移
                if ts_decis > 3600000:
                    abs_time = ts_decis / 10.0  # 绝对值，十分之一秒 → 秒
                else:
                    abs_time = (start_time_ms / 1000.0) + (ts_decis / 10.0)
            else:
                abs_time = start_time_ms / 1000.0 if start_time_ms else 0

            # 心率匹配
            hr = pt.get("hr") or pt.get("heartRate")
            if not hr and decoded_hr:
                hr = KeepClient._find_nearest_hr(decoded_hr, ts_decis, start_time_ms)

            result.append({
                "latitude": wgs_lat,
                "longitude": wgs_lng,
                "elevation": float(pt.get("altitude", 0) or 0),
                "time": abs_time,
                "heart_rate": int(hr) if hr else None,
            })

        return result if result else None

    @staticmethod
    def _find_nearest_hr(hr_data: list, target_time: int, start_time_ms: int,
                         threshold: int = 100) -> int | None:
        """在心率数据中找最接近的时间点（十分之一秒为单位）"""
        if not hr_data:
            return None
        if target_time > 3600000:
            target_time = target_time - start_time_ms // 100

        closest, min_diff = None, float("inf")
        for item in hr_data:
            ts = item.get("timestamp")
            if not ts:
                continue
            diff = abs(ts - target_time)
            if diff <= threshold and diff < min_diff:
                closest, min_diff = item, diff

        if closest:
            hr = closest.get("beatsPerMinute")
            if hr and hr > 0:
                return hr
        return None

    @staticmethod
    def _parse_generic_points(points: list[dict]) -> list[dict] | None:
        """将通用点列表转为标准格式"""
        result = []
        for pt in points:
            lat = pt.get("latitude") or pt.get("lat", 0)
            lon = pt.get("longitude") or pt.get("lng", 0)
            if lat == 0 and lon == 0:
                continue
            wgs_lng, wgs_lat = gcj02_to_wgs84(lon, lat)
            ts = pt.get("timestamp") or pt.get("time") or pt.get("unixTimestamp") or 0
            if ts and isinstance(ts, (int, float)) and ts > 1e12:
                ts = ts / 1000.0
            hr = pt.get("heartRate") or pt.get("heart_rate") or pt.get("hr")
            result.append({
                "latitude": wgs_lat, "longitude": wgs_lng,
                "elevation": float(pt.get("elevation", pt.get("ele", pt.get("altitude", 0)) or 0)),
                "time": ts, "heart_rate": int(hr) if hr else None,
            })
        return result if result else None


# ═══════════════════════════════════════════════════════════════
# GPX 生成
# ═══════════════════════════════════════════════════════════════

GPXTPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"


# 活动类型映射（Keep dataType → Garmin 标签）
KEEP_TYPE_TO_GARMIN = {
    "outdoorRunning": "Running",
    "outdoorCycling": "Biking",
    "outdoorWalking": "Walking",
    "indoorRunning": "Running",
    "mountaineering": "Hiking",
}

# TCX Sport 标签（Garmin 原生识别）
KEEP_TYPE_TO_TCX = {
    "outdoorRunning": "Running",
    "outdoorCycling": "Biking",
    "outdoorWalking": "Walking",
    "indoorRunning": "Running",
    "mountaineering": "Hiking",
}


def build_gpx(
    track_points: list[dict],
    activity_info: dict | None = None,
) -> gpx_lib.GPX:
    """用 track points 构建 GPX 对象，包含活动类型标记"""
    gpx_obj = gpx_lib.GPX()
    gpx_obj.nsmap["gpxtpx"] = GPXTPX_NS

    track = gpx_lib.GPXTrack()
    gpx_obj.tracks.append(track)
    segment = gpx_lib.GPXTrackSegment()
    track.segments.append(segment)

    # 设置活动类型（Running/Biking/Walking），Garmin 据此分类
    if activity_info:
        data_type = activity_info.get("dataType", "")
        track.type = KEEP_TYPE_TO_GARMIN.get(data_type, "Other")

    for pt in track_points:
        gp = gpx_lib.GPXTrackPoint(
            latitude=pt["latitude"],
            longitude=pt["longitude"],
            elevation=pt.get("elevation"),
        )

        if pt.get("time"):
            if isinstance(pt["time"], (int, float)):
                gp.time = datetime.fromtimestamp(pt["time"], tz=timezone.utc)
            elif isinstance(pt["time"], str):
                try:
                    gp.time = datetime.fromisoformat(pt["time"].replace("Z", "+00:00"))
                except ValueError:
                    pass

        if pt.get("heart_rate"):
            tpe = etree.Element("{" + GPXTPX_NS + "}TrackPointExtension")
            hr_el = etree.SubElement(tpe, "{" + GPXTPX_NS + "}hr")
            hr_el.text = str(pt["heart_rate"])
            gp.extensions.append(tpe)

        segment.points.append(gp)

    if activity_info:
        name = activity_info.get("name") or activity_info.get("title", "")
        gpx_obj.name = name
        gpx_obj.description = (
            f"distance: {activity_info.get('distance', 0)}m, "
            f"duration: {activity_info.get('duration', 0)}s"
        )

    return gpx_obj


def save_gpx(gpx_obj: gpx_lib.GPX, output_dir: str, filename: str) -> str:
    """保存 GPX 到文件"""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(gpx_obj.to_xml())
    return filepath


def build_tcx(
    track_points: list[dict],
    activity_info: dict | None = None,
) -> str:
    """
    构建 TCX 文件（Garmin 原生格式，自动识别活动类型）

    TCX 的 <Activity Sport="Running"> 标签会被 Garmin 直接识别，
    不像 GPX 的 <type> 标签会被忽略。
    """
    import xml.etree.ElementTree as _ET
    from xml.dom import minidom as _minidom

    data_type = (activity_info or {}).get("dataType", "")
    sport = KEEP_TYPE_TO_TCX.get(data_type, "Other")
    start_time_ms = (activity_info or {}).get("startTime") or 0
    duration_s = (activity_info or {}).get("duration", 0)
    distance_m = (activity_info or {}).get("distance", 0)
    calorie = (activity_info or {}).get("calorie", 0)

    # TCX 时间格式
    fit_start = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
    fit_start_str = fit_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 根节点
    ns = {
        "xmlns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": (
            "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 "
            "http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
        ),
    }
    root = _ET.Element("TrainingCenterDatabase", ns)
    activities_el = _ET.SubElement(root, "Activities")
    activity_el = _ET.SubElement(activities_el, "Activity", {"Sport": sport})
    _ET.SubElement(activity_el, "Id").text = fit_start_str
    lap_el = _ET.SubElement(activity_el, "Lap", {"StartTime": fit_start_str})
    _ET.SubElement(lap_el, "TotalTimeSeconds").text = str(duration_s)
    _ET.SubElement(lap_el, "DistanceMeters").text = str(round(distance_m, 1))
    _ET.SubElement(lap_el, "Calories").text = str(calorie or 0)

    # Track points
    track_el = _ET.SubElement(lap_el, "Track")
    for pt in track_points:
        tp = _ET.SubElement(track_el, "Trackpoint")

        # 时间
        if pt.get("time"):
            if isinstance(pt["time"], (int, float)):
                t = datetime.fromtimestamp(pt["time"], tz=timezone.utc)
            else:
                t = datetime.fromisoformat(str(pt["time"]).replace("Z", "+00:00"))
            _ET.SubElement(tp, "Time").text = t.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 位置
        pos = _ET.SubElement(tp, "Position")
        _ET.SubElement(pos, "LatitudeDegrees").text = str(pt["latitude"])
        _ET.SubElement(pos, "LongitudeDegrees").text = str(pt["longitude"])

        # 海拔
        if pt.get("elevation"):
            _ET.SubElement(tp, "AltitudeMeters").text = str(pt["elevation"])

        # 心率
        if pt.get("heart_rate"):
            hr_el = _ET.SubElement(tp, "HeartRateBpm")
            _ET.SubElement(hr_el, "Value").text = str(pt["heart_rate"])

    return _minidom.parseString(_ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")


def save_tcx(tcx_xml: str, output_dir: str, filename: str) -> str:
    """保存 TCX 到文件"""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(tcx_xml)
    return filepath


def make_filename(activity: dict, idx: int) -> str:
    """根据活动信息生成文件名"""
    sport = activity.get("_sport_type", "sport")

    # startTime 是 Unix 毫秒时间戳
    ts = activity.get("startTime") or 0
    if ts > 1e12:
        ts = ts / 1000.0
    if ts > 100000:
        date_part = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    else:
        date_part = datetime.now().strftime("%Y-%m-%d")

    dist_km = round((activity.get("distance") or 0) / 1000, 1)
    name = activity.get("name") or activity.get("title") or f"activity_{idx}"
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:30]
    ext = activity.get("_format", "gpx")
    return f"{date_part}_{sport}_{safe_name}_{dist_km}km.{ext}"


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def sync_keep(
    mobile: str,
    password: str,
    output_dir: str | None = None,
    sport_types: list[str] | None = None,
    max_count: int = 0,
    verbose: bool = True,
    export_format: str = "gpx",
    start_date: str = "",
    end_date: str = "",
) -> list[str]:
    """
    从 Keep 同步数据，生成 GPX 或 TCX 文件

    参数:
        export_format: "gpx" (通用) 或 "tcx" (Garmin 原生, 自动识别活动类型)
        start_date: 开始日期 YYYY-MM-DD (含), 空=不限制
        end_date:   结束日期 YYYY-MM-DD (含), 空=不限制
    """
    if sport_types is None:
        sport_types = ["running", "cycling", "hiking"]

    if output_dir is None:
        output_dir = get_output_dir()

    client = KeepClient()

    # 1. 登录
    if not client.login(mobile, password):
        return []

    # 2. 拉取活动列表
    activities = client.fetch_all_activities(sport_types)
    if not activities:
        print("[WARN] 没有找到任何运动记录。可能的原因：")
        print("  1. Keep API 响应结构变了 → 加 --debug 查看原始响应")
        print("  2. 账号下没有记录或运动类型不匹配")
        print("  3. Token 过期或权限不足")
        return []

    # 日期过滤
    if start_date or end_date:
        filtered = []
        for act in activities:
            ts = act.get("startTime") or 0
            if ts > 1e12:
                ts = ts / 1000.0
            if ts > 100000:
                act_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            else:
                act_date = ""
            if start_date and act_date < start_date:
                continue
            if end_date and act_date > end_date:
                continue
            filtered.append(act)
        activities = filtered
        print(f"[INFO] 日期过滤 ({start_date or '不限'} ~ {end_date or '不限'}): 剩余 {len(activities)} 条")

    if max_count > 0:
        activities = activities[:max_count]

    print(f"\n[INFO] 共 {len(activities)} 条运动记录待处理\n")

    # 3. 逐条获取详情、生成 GPX
    gpx_files = []
    for idx, act in enumerate(activities):
        act_id = str(act.get("id") or "")
        sport_type = act.get("_sport_type", "running")
        act["_format"] = export_format  # 用于 make_filename 确定扩展名

        dist = (act.get("distance") or 0) / 1000
        # 从 startTime/endTime (毫秒) 计算 duration
        duration_ms = 0
        start_time = act.get("startTime") or 0
        end_time = act.get("endTime") or 0
        if start_time and end_time:
            duration_ms = (end_time - start_time) / 1000  # 转为秒
        elif act.get("duration"):
            duration_ms = act.get("duration")
        elif act.get("elapsedTime"):
            duration_ms = act.get("elapsedTime")
        duration_min = duration_ms / 60 if duration_ms else 0
        name = act.get("name") or act.get("title") or ""

        if not act_id:
            _debug_print(f"活动 #{idx} 缺少 id，字段: {list(act.keys())}")
            continue

        filename = make_filename(act, idx + 1)
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath):
            if verbose:
                print(f"  [{idx + 1}/{len(activities)}] {name} — 已存在，跳过")
            gpx_files.append(filepath)
            continue

        if verbose:
            print(f"  [{idx + 1}/{len(activities)}] {sport_type}: {name} "
                  f"({dist:.1f}km, {duration_min:.0f}min) ...", end=" ")

        detail = client.fetch_activity_detail(act_id, sport_type)
        if not detail:
            if verbose:
                print("无详情数据，跳过")
            continue

        track_points = client.extract_track_points(detail)
        if not track_points:
            if verbose:
                print("无 GPS 轨迹")
            continue

        if export_format == "tcx":
            tcx_xml = build_tcx(track_points, act)
            save_path = save_tcx(tcx_xml, output_dir, filename)
        else:
            gpx_obj = build_gpx(track_points, act)
            save_path = save_gpx(gpx_obj, output_dir, filename)
        gpx_files.append(save_path)

        if verbose:
            hr_info = ""
            if any(p.get("heart_rate") for p in track_points):
                hr_info = " +心率"
            print(f"-> {len(track_points)} 轨迹点{hr_info}")

        time.sleep(0.5)

    print(f"\n[DONE] 共导出 {len(gpx_files)} 个 GPX 文件 -> {output_dir}/")
    return gpx_files


# ═══════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从 Keep 导出运动数据为 GPX 文件")
    parser.add_argument("mobile", help="Keep 手机号")
    parser.add_argument("password", help="Keep 密码")
    parser.add_argument("-o", "--output", default="./gpx_output", help="GPX 输出目录")
    parser.add_argument("-t", "--type", nargs="+", default=["running", "cycling", "hiking"],
                        help="运动类型 (默认: running cycling hiking)")
    parser.add_argument("-n", "--max", type=int, default=0, help="最多导出条数 (0=全部)")
    parser.add_argument("--no-gcj02-fix", action="store_true",
                        help="不转换 GCJ-02 → WGS-84 坐标")
    parser.add_argument("--debug", action="store_true",
                        help="调试模式：打印原始 API 响应，用于排查问题")

    args = parser.parse_args()

    if args.no_gcj02_fix:
        import keep_sync as _ks
        _ks.GCJ02_TO_WGS84 = False
        print("[WARN] 已关闭 GCJ-02 → WGS-84 坐标转换")

    if args.debug:
        import keep_sync as _ks
        _ks.DEBUG = True
        print("[DEBUG] 调试模式已开启，将打印 API 原始响应\n")

    files = sync_keep(
        mobile=args.mobile,
        password=args.password,
        output_dir=args.output,
        sport_types=args.type,
        max_count=args.max,
    )

    if not files:
        print("未生成任何 GPX 文件。加 --debug 参数可查看详细 API 响应来排查。")
