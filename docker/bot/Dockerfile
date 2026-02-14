FROM python:3.12-slim

WORKDIR /app

# copy and install dependencies
COPY python/requirements_bot.txt /app/requirements_bot.txt
RUN pip install --no-cache-dir -r /app/requirements_bot.txt

# copy python code
COPY python/ /app/python/

# copy articles into the image
COPY files/illness_schedule/ /app/files/illness_schedule/

# configure the app to know where articles live
ENV ILLNESS_SCHEDULE_DIR=/app/files/illness_schedule

EXPOSE 8000

CMD ["python", "python/bot.py"]
