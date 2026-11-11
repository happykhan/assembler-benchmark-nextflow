FROM ghcr.io/prefix-dev/pixi:0.73.0
WORKDIR /opt/benchmark
COPY environments/pixi.toml environments/pixi.lock ./
RUN pixi install --locked
ENV PATH="/opt/benchmark/.pixi/envs/default/bin:${PATH}"
ENV BENCH_RUNTIME=native
WORKDIR /work
