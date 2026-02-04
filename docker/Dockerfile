FROM python:3.12-slim

WORKDIR /app

# copy and install dependencies
COPY python/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy python code
COPY python/ /app/python/

EXPOSE 8000

CMD ["uvicorn", "python.main:app", "--host", "0.0.0.0", "--port", "8000"]
