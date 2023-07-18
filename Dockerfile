FROM mambaorg/micromamba:1.4.9-bullseye-slim

SHELL [ "/bin/bash", "-c" ]

# Use C.UTF-8 locale to avoid issues with unicode encoding
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
