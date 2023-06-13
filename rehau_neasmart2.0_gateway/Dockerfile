# https://developers.home-assistant.io/docs/add-ons/configuration#add-on-dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1

COPY rootfs /

HEALTHCHECK --interval=2m --timeout=3s \
    CMD curl -f http://localhost:5000/health || exit 1

WORKDIR /src

RUN pip3 install -r requirements.txt

WORKDIR /
