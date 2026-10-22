# 启动后端（开发）
Set-Location "D:\DramaForge\backend"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload