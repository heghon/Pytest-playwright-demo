# syntax=docker/dockerfile:1
#
# The environment the suite runs in, not the suite itself: the pinned Python,
# every package in requirements.txt, and a browser with the system libraries it
# needs. The code is mounted in at run time by compose.yaml, so editing a test
# never needs a rebuild; changing requirements.txt or the Python version does.
#
#     docker compose build
#     docker compose run --rm tests
#
# Not Playwright's own image (mcr.microsoft.com/playwright/python): it ships
# Ubuntu's Python, not the one .python-version pins, and the venv check would
# rightly refuse to run on it.

# Must match .python-version, which framework_tests/test_docker.py checks.
ARG PYTHON_VERSION=3.14.9

FROM python:${PYTHON_VERSION}-slim-trixie

# Which engines to bake in: all three by default, so --browser firefox or webkit
# works in the container as it does locally. Each one adds a few hundred MB; for
# a lighter image with Chromium only, the engine a run uses unless told otherwise:
#     docker compose build --build-arg BROWSERS="chromium"
ARG BROWSERS="chromium firefox webkit"

# No .pyc files written into the mounted project, and output straight to the
# terminal rather than buffered. The browsers go to a fixed path rather than the
# home of whichever user built the image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# The lock alone first, so the slow layers below are only rebuilt when it
# change, not on every edit to the code, which never enters the image.
COPY requirements.txt /tmp/requirements.txt

# Straight into the image's Python rather than a venv: the container is the
# isolation, and the venv check reads whatever environment pytest runs in.
# --with-deps installs the system libraries the browser needs through apt.
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && playwright install --with-deps ${BROWSERS} \
    && rm /tmp/requirements.txt

CMD ["pytest"]
