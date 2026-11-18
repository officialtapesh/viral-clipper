# Hugging Face Space for Viral Clipper. Pulls the app straight from GitHub,
# so every push to the repo reaches the website on the next restart.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git fontconfig libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 \
    CLIPPER_JOBS=/tmp/viral-clipper-jobs
WORKDIR /home/user
RUN git clone --depth 1 https://github.com/officialtapesh/viral-clipper app
RUN pip install --no-cache-dir --user -r app/requirements.txt "gradio>=4.44,<6"
EXPOSE 7860
CMD ["sh", "-c", "git -C app pull --ff-only || true; pip install -q --user -r app/requirements.txt || true; python app/webapp/app.py"]
