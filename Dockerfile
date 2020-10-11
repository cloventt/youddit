FROM python:3.9-slim

COPY requirements.txt /app/
RUN pip install --upgrade -r /app/requirements.txt

COPY youddit.py /app/

ENTRYPOINT ["python", "/app/youddit.py"]