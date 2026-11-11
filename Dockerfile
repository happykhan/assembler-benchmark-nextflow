FROM ghcr.io/prefix-dev/pixi:0.73.0
WORKDIR /opt/benchmark
COPY environments/pixi.toml environments/pixi.lock ./
ARG BENCH_ENV=default
RUN pixi install --locked --environment ${BENCH_ENV}
ENV PATH="/opt/benchmark/.pixi/envs/${BENCH_ENV}/bin:${PATH}"
ENV BENCH_RUNTIME=native
WORKDIR /work
