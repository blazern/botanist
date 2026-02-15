FROM python:3.12-slim

WORKDIR /app

# copy and install dependencies
COPY python/requirements_server.txt /app/requirements_server.txt
RUN pip install --no-cache-dir -r /app/requirements_server.txt

# copy python code
COPY python/ /app/python/

# copy articles into the image
COPY files/illness_schedule/ /app/files/illness_schedule/

# configure the app to know where articles live
ENV ILLNESS_SCHEDULE_DIR=/app/files/illness_schedule

EXPOSE 8000

WORKDIR /app/python
CMD ["uvicorn", "http_server:app", "--host", "0.0.0.0", "--port", "8000"]