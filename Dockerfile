##********************** MAIN BUILD **********************##
# Playwright's image ships Chromium and its system libraries at the matching version.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble


# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    BHULEKH_DATA=/usr/src/app/private


# Set the working directory
WORKDIR /usr/src/app


# Virtual display + VNC, so the headed browser can be driven (and its captcha solved) from http://localhost:6080
RUN apt-get update && \
    apt-get install -y --no-install-recommends xvfb x11vnc fluxbox novnc websockify && \
    rm -rf /var/lib/apt/lists/*


# Install Python dependencies
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


# Copy the application
COPY . .
RUN chmod +x scripts/entrypoint.sh run_cmd.sh


EXPOSE 6080

ENTRYPOINT ["scripts/entrypoint.sh"]
