FROM python:3.8-alpine3.11

# development packages that will be installed before pip is run and purged after
ARG DEV_PKGS='linux-headers python3-dev gcc g++ musl-dev libressl-dev libffi-dev'

COPY . /usr/src/app

RUN cd /usr/src/app && \
    apk add --no-cache --virtual .build-deps $DEV_PKGS && \
    pip install --no-cache-dir -e . && \
    python setup.py install && \
    apk del .build-deps

ENTRYPOINT ["python3", "-m", "mrnag"]
