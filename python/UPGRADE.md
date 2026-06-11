# NetworkIntel v1.2 升级步骤

## 一、新增 / 替换文件

把 outputs/ 目录里的文件放到 `E:\NetworkIntel\python\`：

| 操作 | 文件 |
|---|---|
| 覆盖 | `main_gui.py` |
| 覆盖 | `gui_extensions.py` |
| **新增** | `gui_map.py`        ← 地图模块 |
| 覆盖 | `build_gui_exe.bat` |
| **新增** | `backup.bat`        ← 备份脚本 |
| **新增** | `update.bat`        ← 一键更新（备份 + 重打包）|
| **新增** | `CHANGELOG.md` |

## 二、先跑一下确认地图工作

```cmd
cd /d E:\NetworkIntel\python
D:\Python\python.exe main_gui.py
```

操作步骤：
1. F2 切到批量页
2. 粘几个 IP（例如 `1.1.1.1` `8.8.8.8` `114.114.114.114` `203.0.113.1`）
3. 点开始批量查询
4. 完成后右边结果区切换到 **地图** Tab
5. 应该看到地图上有彩色圆点，点击有国旗 + IP 详情

**地图需要联网**（加载 OSM tile 和 flagcdn 国旗）。完全离线时地图会显示但没瓦片。

## 三、重新打包 exe

确认 GUI 正常后，**双击 update.bat**：
- 会先自动备份当前 yaml + db + 代码到 `E:\NetworkIntel\backups\backup_xxxxx\`
- 再调 build_gui_exe.bat 重新打包
- 因为含 QtWebEngine，新 exe 会比之前大很多（150-200MB），首次打包 5-8 分钟

打包成功后 exe 仍在：
```
E:\NetworkIntel\python\dist\NetworkIntel.exe
```
桌面快捷方式不用改，指向同一路径。

## 四、以后日常更新流程

每次你想升级/改代码时：

1. 我给你新的 .py 文件
2. 复制到 `E:\NetworkIntel\python\` 覆盖
3. 双击 `update.bat`（自动备份+打包）
4. 完成

或者直接：双击 `backup.bat` 备份一次 → 测试 → 满意了双击 `build_gui_exe.bat` 重打包。

## 五、回滚

如果新版本有问题：
- `dist_backup\` 里有上一版 exe（带时间戳），改名 `NetworkIntel.exe` 拷回 `dist\` 即可
- `..\backups\backup_xxx\` 里有当时的代码 + yaml + db，全部还原即可
