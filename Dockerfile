FROM mambaorg/micromamba:1.4.9-bullseye-slim

USER mambauser

SHELL [ "/bin/bash", "-c" ]

# Use C.UTF-8 locale to avoid issues with unicode encoding
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# lock file created by running lock.sh in the top level of the repository
COPY --chown=mambauser conda-lock.yml /conda-lock.yml
COPY --chown=mambauser cmd.sh /cmd.sh
RUN chmod +x /cmd.sh

# The mambaorg/micromamba base image's entrypoint is
# /usr/local/bin/_entrypoint.sh which ensures the shell environment is
# correctly set for micromamba to be accessible by the given user.
# c.f. https://github.com/mamba-org/micromamba-docker/blob/604ebafb09543a3d852e437886f1c782f0367911/_entrypoint.sh
# Instead of replicating this, continue to use it as the ENTRYPOINT
# and then pass the action's script as CMD.
ENTRYPOINT [ "/usr/local/bin/_entrypoint.sh" ]
CMD [ "/cmd.sh" ]
