# NuOrb – selbst gehosteter Sprachassistent als ein Container.
# Basis: offizielles Hermes-Agent-Image (s6-überwacht, Benutzer hermes, Daten unter /opt/data).
# Darauf: NuOrb-Oberfläche (:8443), Admin-Panel (:8444), STT-Router mit Parakeet (CPU) und Piper-TTS.
# Modelle und Stimmen werden beim ersten Start ins Volume /opt/models geladen, nicht ins Image gebacken.
ARG HERMES_IMAGE=nousresearch/hermes-agent:v0.23.4

FROM busybox:1.37 AS files
COPY src/ui/ /f/opt/nuorb/ui/
COPY src/admin/ /f/opt/nuorb/admin/
COPY src/stt/ /f/opt/nuorb/stt/
COPY app/ /f/opt/nuorb/app/
COPY rootfs/ /f/
RUN mkdir -p /f/opt/nuorb/home/.config /f/opt/models

FROM ${HERMES_IMAGE}

USER root
COPY requirements.txt /opt/nuorb/requirements.txt
# Eigenes venv mit Debians Python 3.13 (Hermes nutzt sein eigenes 3.14-venv, das bleibt unberührt)
RUN /usr/bin/python3 -m venv /opt/nuorb/venv \
 && /opt/nuorb/venv/bin/pip install --no-cache-dir --disable-pip-version-check -r /opt/nuorb/requirements.txt \
 && find /opt/nuorb/venv -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf /root/.cache

# Bereinigte Quellen (docker/tools/prepare-src.py) + Docker-Hülle + s6-Dienste: in einer Zwischenstufe
# zusammenstellen und mit EINEM COPY übernehmen (wenige Schichten, wichtig bei Storage-Treibern wie vfs)
COPY --from=files /f/ /
RUN ln -sfn /opt/data /opt/nuorb/home/.hermes \
 && ln -sfn /opt/data/nuorb/config /opt/nuorb/home/.config/nuorb \
 && chown hermes:hermes /opt/models \
 && /opt/nuorb/venv/bin/python -m compileall -q /opt/nuorb/app /opt/nuorb/ui /opt/nuorb/admin /opt/nuorb/stt

EXPOSE 8443 8444
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD ["/opt/nuorb/bin/healthcheck"]

# Hermes-Gateway (Agent + API auf 127.0.0.1:8642) als Hauptprozess; NuOrb-Dienste laufen daneben unter s6.
CMD ["gateway", "run"]
