import os

import requests
import logging
import sentry_sdk

# Setup logging
logger = logging.getLogger(__name__)


def start_transcription(transcript_uuid):
    """
    Send a request to start transcribing an MP3 file from AWS S3.

    Args:
        transcript_uuid (str): The UUID of the transcript

    Returns:
        requests.Response: The response from the API
    """
    # API credentials
    api_key = os.getenv("TRANSCRIPT_API_KEY")

    if not api_key:
        raise ValueError("API key is not set in environment variables.")

    # API host
    base_url = os.getenv("TRANSCRIPT_API_URL")

    if not base_url:
        raise ValueError("API URL is not set in environment variables.")

    url = os.getenv("TRANSCRIPT_API_URL") + "/api/v1/record/done"
    logger.debug(f"Transcript URL: {url}")

    # Request headers
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Request body
    data = {"transcript_id": transcript_uuid}

    # Send POST request
    response = requests.post(url, headers=headers, json=data, timeout=30)

    # Check if request was successful
    if response.status_code == 200:
        logger.info(f"Successfully started transcription for UUID: {transcript_uuid}")
    else:
        logger.error(f"Error starting transcription: {response.status_code}")
        logger.error(f"Response: {response.text}")

    return response

def started_recording(transcript_id):
    """
    Notify gateway that recording has started for a given transcript ID.

    Args:
        transcript_id (str): The ID of the transcript
        
    Returns:
        requests.Response: The response from the API
    """
    # API credentials
    api_key = os.getenv("TRANSCRIPT_API_KEY")

    if not api_key:
        raise ValueError("API key is not set in environment variables.")

    # API endpoint
    url = os.getenv("TRANSCRIPT_API_URL") + "/api/v1/record/started"

    if not url:
        raise ValueError("API URL is not set in environment variables.")

    # Request headers
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Request body
    data = {"transcript_id": transcript_id}

    # Send POST request
    response = requests.post(url, headers=headers, json=data, timeout=30)

    # Check if request was successful
    if response.status_code == 200:
        logger.info(f"Successfully notified gateway that recording started for UUID: {transcript_id}")
    else:
        logger.error(f"Error notifying gateway of recording start: {response.status_code}")
        logger.error(f"Response: {response.text}")

    return response


def could_not_record(transcript_id):
    """Report recording failure to gateway. Triggers Sentry alert."""
    logger.error(f"Could not record for transcript ID: {transcript_id}")
    
    # Trigger Sentry alert
    sentry_sdk.capture_message(
        f"Recording failed for transcript {transcript_id}",
        level="error"
    )

    # API credentials
    api_key = os.getenv("TRANSCRIPT_API_KEY")

    if not api_key:
        raise ValueError("API key is not set in environment variables.")

    # API endpoint
    url = os.getenv("TRANSCRIPT_API_URL") + "/api/v1/record/failed"

    if not url:
        raise ValueError("API URL is not set in environment variables.")

    # Request headers
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Request body
    data = {"transcript_id": transcript_id}

    # Send POST request
    response = requests.post(url, headers=headers, json=data, timeout=30)

    # Check if request was successful
    if response.status_code == 200:
        logger.info(f"Successfully informed of recording failure for UUID: {transcript_id}")
    else:
        logger.error(f"Error informing of recording failure: {response.status_code}")
        logger.error(f"Response: {response.text}")

    return response


def permission_denied(transcript_id: str) -> requests.Response:
    """Report recording permission denied to gateway. Triggers Sentry alert."""
    logger.error(f"Recording permission denied for transcript ID: {transcript_id}")
    
    # Trigger Sentry alert for dev team
    sentry_sdk.capture_message(
        f"Recording permission denied for transcript {transcript_id}",
        level="error"
    )
    
    api_key = os.getenv("TRANSCRIPT_API_KEY")
    if not api_key:
        raise ValueError("API key is not set in environment variables.")

    base_url = os.getenv("TRANSCRIPT_API_URL")
    if not base_url:
        raise ValueError("API URL is not set in environment variables.")

    url = f"{base_url}/api/v1/record/permission_denied"
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json={"transcript_id": transcript_id},
        timeout=30
    )

    if response.status_code == 200:
        logger.info(f"Reported permission denied to gateway for transcript: {transcript_id}")
    else:
        logger.error(f"Failed to report permission denied to gateway: {response.status_code}")

    return response
