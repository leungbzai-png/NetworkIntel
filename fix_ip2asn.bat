@echo off
chcp 65001 >nul
echo Fixing ip2asn...

:: Delete cached combined file to force re-download
del /f /q "E:\NetworkIntel\cache\ip2asn\ip2asn-combined.tsv.gz" 2>nul
del /f /q "E:\NetworkIntel\cache\ip2asn\ip2asn-v4.tsv.gz" 2>nul

:: Show current file content to verify patch applied
echo.
echo Current download URL in ip2asn.py:
findstr /i "ip2asn" "E:\NetworkIntel\python\datasources\plugins\ip2asn.py" | findstr /i "url"
echo.

:: Run only ip2asn update
cd /d E:\NetworkIntel\python
D:\Python\python.exe -c "
import sys
sys.path.insert(0, '.')
from utils.config_loader import get_config
from utils.schema import init_db
from datasources.plugins.ip2asn import IP2ASNSource

cfg = get_config()
init_db(cfg.db_path)
p = IP2ASNSource()
print('URL will be: https://iptoasn.com/data/ip2asn-v4.tsv.gz')
result = p.update(progress_callback=lambda s,pct: print(f'  {s} ({pct}%)'))
print(f'Result: {result}')
"
pause
