FROM python:3.8-slim-buster

COPY . /usr/src/app

RUN cd /usr/src/app && \
    pip install --no-cache-dir -e . && \
    python setup.py install

ENTRYPOINT ["python3", "-m", "mrnag"]
