# https://developers.home-assistant.io/docs/add-ons/configuration#add-on-dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

ARG BUILD_ARCH
ARG GO_VERSION 

COPY rootfs /app

HEALTHCHECK --interval=5m --timeout=3s \
    CMD curl -f http://localhost:8080/healthcheck || exit 1

RUN  if [ "${BUILD_ARCH}" = "armv7" ]; then \
         export GO_ARCH="armv6l"; \
     elif [ "${BUILD_ARCH}" = "armhf" ]; then \
         export GO_ARCH="armv6l"; \
     elif [ "${BUILD_ARCH}" = "aarch64" ]; then \
         export GO_ARCH="arm64"; \
     elif [ "${BUILD_ARCH}" = "i386" ]; then \
         export GO_ARCH="386"; \
     elif [ "${BUILD_ARCH}" = "amd64" ]; then \
         export GO_ARCH="amd64"; \
     else \
         exit 1; \
     fi && \
    curl -L -f "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz" \
    | tar Jxvf - -C /usr/local && \
    go build -ldflags="-w -s" -o /rehau_gw /app

