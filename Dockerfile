# FROM ubuntu:latest

# RUN apt-get update && \
#     apt-get install -y python3.10 python3-pip

# RUN python3.10 -m pip install --upgrade pip && \
#     pip install anaconda-client

FROM mambaorg/micromamba:latest

COPY entrypoint.sh /entrypoint.sh
# RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
