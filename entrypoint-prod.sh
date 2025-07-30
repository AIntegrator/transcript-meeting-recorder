#!/usr/bin/env bash

# --- PulseAudio Setup ---
echo "Setting up PulseAudio..."
# Clean up old PulseAudio state (optional, but helps avoid conflicts)
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# Start PulseAudio in daemon mode in the background
pulseaudio -D --exit-idle-time=-1 &

# Store the PID of the PulseAudio daemon if you want to manage it later
PULSE_PID=$!

# Give PulseAudio time to initialize
sleep 1 # Adjust as needed based on observed startup time

echo "PulseAudio initialized (PID: $PULSE_PID)"

# --- Optional: Database Migrations (if you remove the initContainer) ---
# If you want to run migrations *before* starting Gunicorn in the same container, uncomment this:
# echo "Running Django migrations..."
# python manage.py migrate --noinput
# echo "Migrations complete."

# --- Start Gunicorn ---
echo "Starting Gunicorn..."
# Replace 'transcript_meeting_recorder' with the actual name of your project's WSGI module
# Example: If your project structure is /app/your_project_name/wsgi.py
exec gunicorn --bind 0.0.0.0:8000 \
              --workers ${GUNICORN_WORKERS:-3} \
              --threads ${GUNICORN_THREADS:-2} \
              --timeout ${GUNICORN_TIMEOUT:-60} \
              --log-level ${GUNICORN_LOG_LEVEL:-info} \
              transcript_meeting_recorder.wsgi:application

# Note: The 'exec' command here will replace the current shell process with Gunicorn.
# This means the shell process that started PulseAudio will no longer exist as PID 1.
# This is fine because PulseAudio is running as a daemon in the background.
# Tini (from your Dockerfile.dev) will be the actual PID 1 and will manage Gunicorn and the background PulseAudio process.