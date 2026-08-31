FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir scikit-learn
COPY train.py .
ENV N_ESTIMATORS=100
CMD ["python", "train.py"]
