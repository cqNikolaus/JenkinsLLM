FROM python:3.9
RUN apt-get update && \
    apt-get install -y locales && \
    locale-gen de_DE.UTF-8 && \
    update-locale LANG=de_DE.UTF-8
    apt-get clean && rm -rf /var/lib/apt/lists/*
ENV LANG=de_DE.UTF-8
ENV LANGUAGE=de_DE:de
ENV LC_ALL=de_DE.UTF-8
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY analyze_log.py ./
CMD ["python", "analyze_log.py"]


