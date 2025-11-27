# Meeting Recorder Service

This is a customized fork of the open-source repository `attendee` by Noah Duncan, optimized to work with our specific architecture.

## Overview

The Meeting Recorder is a Django application designed to run as a single Docker image, supported by **Postgres** and **Redis**.

**Core Architecture:**
1.  **Main API:** Handles authentication, account management, and bot orchestration.
2.  **Bots:** The API spins up recorder pods (workers) called "Bots". These bots:
    * Join a meeting (Zoom, Teams, etc.).
    * Record the audio/video.
    * Upload the raw data to Object Storage (OpenStack Swift).
    * Leave the meeting and destroy themselves.
    * Trigger a callback to the `transcript-gateway`.

## Key Customizations (vs Upstream)

This fork deviates from the original `attendee` repository in several key ways:

* **Custom Storage:** We utilize OpenStack Swift (via Infomaniak) instead of AWS S3. 
    * *Location:* `/bots/storage/infomaniak_storage.py`
* **Callbacks:** Post-recording, the bot triggers a callback to our `transcript-gateway`.
    * *Location:* `/transcript_services/v1/api_service.py`
* **Kubernetes Native:** We have removed non-essential bloat and added more logs to support running inside a K8s cluster.

## Development Setup

### 1. Running Locally (Docker Compose)
*Best for quick logic changes and database testing.*

1.  **Build the image:**
    `docker compose -f dev.docker-compose.yml build`
2.  **Generate Environment Variables:**
    `docker compose -f dev.docker-compose.yml run --rm recorder-api python init_env.py > .env`
    *(Edit the generated `.env` file to add your AWS/Storage credentials)*
3.  **Start Services:**
    `docker compose -f dev.docker-compose.yml up`
4.  **Run Migrations:**
    `docker compose -f dev.docker-compose.yml exec recorder-api python manage.py migrate`
5.  **Create Account:**
    * Go to `localhost:8001` to sign up.
    * Find the confirmation link in your terminal logs (e.g., `http://localhost:8001/accounts/confirm-email/<key>/`).
    * Login to obtain your API Key.

### 2. Running with Skaffold (Kubernetes)
*Best for testing integration with the wider cluster architecture.*

**Prerequisites:**
* `skaffold` (`brew install skaffold`)
* Docker Desktop (Kubernetes enabled)
* Clone of the `transcript-gitops` repository (for manifests).

**Configuration:**
1.  Update `skaffold.yaml` to point to your local path for the manifests:
    ```yaml
    manifests:
        rawYaml:
        - /Users/USERNAME/PATH_TO/transcript-k8s/deployment-meeting-recorder-api-dev.yaml
    ```
2.  **Secrets Management:**
    * Copy examples: `cp ./secret-examples/secret-docker.yaml secret-docker.yaml`
    * Apply: `kubectl apply -f secret-docker.yaml` (and repeat for `secret-transcript.yaml`)
3.  **Apply Configs & Deps:**
    * `kubectl apply -f configmap-transcript.yaml`
    * `kubectl apply -f deployment-redis.yaml`
    * `kubectl apply -f deployment-postgres.yaml`
    * `kubectl apply -f role-meeting-recorder-bot.yaml`
4.  **Run:**
    `skaffold dev`

### 3. Database Migrations

* **Create Migrations:**
    `docker compose -f dev.docker-compose.yml exec recorder-api python manage.py makemigrations bots`
* **Apply Migrations:**
    `docker compose -f dev.docker-compose.yml exec recorder-api python manage.py migrate`

## Deployment

- Build the Docker image: `docker build --platform=linux/amd64 -t vanyabrucker/transcript-meeting-recorder:1.0.32 -f Dockerfile.dev .` (Takes about 5 minutes)
- Push the image to Docker Hub: `docker push vanyabrucker/transcript-meeting-recorder:1.0.32`

## Calling the API

Join a meeting with a POST request to `/bots`:
```
curl -X POST http://localhost:8000/api/v1/bots \
-H 'Authorization: Token <YOUR_API_KEY>' \
-H 'Content-Type: application/json' \
-d '{"meeting_url": "https://us05web.zoom.us/j/84315220467?pwd=9M1SQg2Pu2l0cB078uz6AHeWelSK19.1", "bot_name": "My Bot"}'
```
Response:
```{"id":"bot_3hfP0PXEsNinIZmh","meeting_url":"https://us05web.zoom.us/j/4849920355?pwd=aTBpNz760UTEBwUT2mQFtdXbl3SS3i.1","state":"joining","transcription_state":"not_started"}```

The API will respond with an object that represents your bot's state in the meeting. 



Make a GET request to `/bots/<id>` to poll the bot:
```
curl -X GET http://localhost:8000/api/v1/bots/bot_3hfP0PXEsNinIZmh \
-H 'Authorization: Token <YOUR_API_KEY>' \
-H 'Content-Type: application/json'
```
Response: 
```{"id":"bot_3hfP0PXEsNinIZmh","meeting_url":"https://us05web.zoom.us/j/88669088234?pwd=AheaMumvS4qxh6UuDtSOYTpnQ1ZbAS.1","state":"ended","transcription_state":"complete"}```

When the endpoint returns a state of `ended`, it means the meeting has ended. When the `transcription_state` is `complete` it means the meeting recording has been transcribed.


Once the meeting has ended and the transcript is ready make a GET request to `/bots/<id>/transcript` to retrieve the meeting transcripts:
```
curl -X GET http://localhost:8000/api/v1/bots/bot_3hfP0PXEsNinIZmh/transcript \
-H 'Authorization: Token mpc67dedUlzEDXfNGZKyC30t6cA11TYh' \
-H 'Content-Type: application/json'
```
Response:
```
[{
"speaker_name":"Alan Turing",
"speaker_uuid":"16778240","speaker_user_uuid":"AAB6E21A-6B36-EA95-58EC-5AF42CD48AF8",
"timestamp_ms":1079,"duration_ms":7710,
"transcription":"You can totally record this, buddy. You can totally record this. Go for it, man."
},...]
```
You can also query this endpoint while the meeting is happening to retrieve partial transcripts.
