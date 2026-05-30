# 用于 Hugging Face Spaces（Docker SDK）部署 Streamlit Web 体验端。
# HF Spaces 默认对外端口为 7860，因此让 Streamlit 监听 7860。

FROM python:3.11-slim

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码与复用的核心模块。
COPY app.py .
COPY src/ ./src/

# HF Spaces 期望应用监听 7860 端口。
EXPOSE 7860

# 启动 Streamlit：监听所有地址的 7860 端口，无头模式，关闭使用统计上报。
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
