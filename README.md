# Keep2Garmin · Keep → Garmin 数据迁移工具

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

把 **Keep** 的运动数据（跑步/骑行/徒步）完整导出到 **Garmin Connect**，保留高精度 GPS 轨迹、海拔、配速、心率。

换佳明手表不丢数据——几年运动记录一键迁移。

> 本工具基于开源项目 [running_page](https://github.com/yihong0618/running_page) 的 Keep API 逆向成果开发，感谢原作者的贡献。

---

## 功能特性

- ✅ Keep 登录 + 自动翻页拉取全部历史数据
- ✅ AES-CBC 解密完整高精度 GPS 轨迹（geoPoints）
- ✅ GCJ-02 → WGS-84 坐标自动转换
- ✅ 心率数据匹配绑定
- ✅ 导出标准 GPX / TCX 文件（TCX 可被 Garmin 自动识别活动类型）
- ✅ 上传到 Garmin Connect（中国区 / 国际区）
- ✅ 图形界面 + 命令行双模式，零编程基础可用
- ✅ 纯本地运行，账号密码不上传任何第三方服务器

## 能迁移的数据

| 数据 | 说明 |
|------|------|
| GPS 轨迹 | 秒级采样，与 Keep 原始记录一致 |
| 海拔 | 完整海拔曲线 |
| 时间 / 距离 / 配速 | 完整保留 |
| 心率 | Keep 记录时连接了心率设备即有 |
| 活动类型 | 跑步/骑行自动识别，徒步需在 Garmin 手动改类型 |

> ⚠️ 注意：手动导入的活动不参与 Garmin 的 VO2max、训练负荷、训练状态等算法计算（佳明官方规则）。

---

## 快速开始

### 方式一：直接使用 EXE（推荐，免装环境）

1. 前往 [Releases](../../releases) 下载 `Keep2Garmin.exe`
2. 双击运行，无需安装 Python

### 方式二：使用 Python 源码

```bash
# 1. 安装 Python 3.10+（https://www.python.org/downloads/，勾选 Add Python to PATH）
# 2. 安装依赖
pip install -r requirements.txt
# 3. 启动图形界面
python gui.py
```

### 首次使用前的重要设置

Garmin 账号需先开启两个隐私开关（否则上传会报 412 错误）：

1. 登录 [connect.garmin.cn](https://connect.garmin.cn)（或 Garmin Connect App）
2. 进入「账户设置 → 隐私设置」
3. 把 **「存储和处理」** 设为「同意」
4. 把 **「设备上传」** 设为「已启用」

### 导出格式建议

| 场景 | 推荐格式 |
|------|---------|
| 导入 Garmin | TCX（自动识别跑步/骑行） |
| 本地备份 / 导入 Strava 等其它平台 | GPX |

---

## 命令行用法（高级用户）

```bash
# 导出 TCX（推荐 Garmin 用户）
python run.py keep 手机号 密码 -f tcx

# 只导出 2025 年跑步
python run.py keep 手机号 密码 -t running --from 2025-01-01 --to 2025-12-31

# 全流程一键（导出 + 上传，中国区）
python run.py all 手机号 Keep密码 Garmin邮箱 Garmin密码

# Garmin 国际区
python run.py all 手机号 Keep密码 Garmin邮箱 Garmin密码 --garmin-global

# 只上传已有文件
python run.py upload Garmin邮箱 密码

# 删除 Garmin 中导入的活动
python garmin_delete.py Garmin邮箱 密码 --delete
```

---

## 常见问题

**Q：上传报 412 Privacy Consent 错误？**
Garmin 隐私设置未开启，见上方「首次使用前的重要设置」。

**Q：导出 0 个文件？**
检查时间范围内是否有 GPS 记录；手机计步器模式的徒步无 GPS 轨迹，无法导出路线。

**Q：GPX 里没有心率？**
Keep 记录时未连接心率设备。用带心率的设备记录后重新导出即可。

**Q：活动类型显示 Other？**
GPX 格式在 Garmin 中不自动识别类型，改用 TCX；徒步类需手动改。

完整说明见仓库附带的操作手册。

---

## 文件结构

```
keep2garmin/
├── gui.py                # 图形界面
├── run.py                # 命令行入口
├── keep_sync.py          # Keep 数据导出核心（AES 解密 + GPX/TCX 生成）
├── garmin_upload.py      # Garmin Connect 上传
├── garmin_delete.py      # 清理 Garmin 中导入的活动
├── requirements.txt      # Python 依赖列表
└── gpx_output/           # 输出目录（运行后生成）
```

## 注意事项

1. **频率限制**：Keep 和 Garmin 均有 API 频率限制，批量操作已内置延时，请勿频繁重复导出
2. **账号安全**：工具只在本地运行，账号密码仅用于登录各自官方 API
3. **仅供个人数据迁移使用**，请遵守 Keep 与 Garmin 的服务条款

## License

[MIT](LICENSE)

## 致谢

- [running_page](https://github.com/yihong0618/running_page) — Keep API 逆向与数据同步的开创性工作
- 所有为本项目提出 issue 和建议的用户
