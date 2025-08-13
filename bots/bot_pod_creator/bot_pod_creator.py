import os
import uuid
from typing import Dict, Optional

from kubernetes import client, config

# fmt: off

class BotPodCreator:
    def __init__(self, namespace: str = os.getenv('CUBER_NAMESPACE', "attendee")):
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        
        self.v1 = client.CoreV1Api()
        self.namespace = namespace
        
        # Get configuration from environment variables
        self.app_name = os.getenv('CUBER_APP_NAME', 'attendee')
        self.app_version = os.getenv('CUBER_RELEASE_VERSION')
        
        if not self.app_version:
            raise ValueError("CUBER_RELEASE_VERSION environment variable is required")
            
        # Parse instance from version (matches your pattern of {hash}-{timestamp})
        self.app_instance = f"{self.app_name}-{self.app_version.split('-')[-1]}"
        default_pod_image = f"nduncan{self.app_name}/{self.app_name}"
        self.image = f"{os.getenv('BOT_POD_IMAGE', default_pod_image)}:{self.app_version}"

    def create_bot_pod(
        self,
        bot_id: int,
        bot_name: Optional[str] = None,
        bot_cpu_request: Optional[int] = None,
    ) -> Dict:
        """
        Create a bot pod with configuration from environment.
        
        Args:
            bot_id: Integer ID of the bot to run
            bot_name: Optional name for the bot (will generate if not provided)
        """
        if bot_name is None:
            bot_name = f"bot-{bot_id}-{uuid.uuid4().hex[:8]}"

        if bot_cpu_request is None:
            bot_cpu_request = os.getenv("BOT_CPU_REQUEST", "4")

        # Set the command based on bot_id
        # Run entrypoint script first, then the bot command
        bot_cmd = f"python manage.py run_bot --botid {bot_id}"
        command = ["/bin/bash", "-c", f"/opt/bin/entrypoint.sh && {bot_cmd}"]
        #command = ["/bin/bash", "-c", "/opt/bin/entrypoint.sh && sleep infinity"] For debugging purposes because with 'sleep infinity' pod doesn't die

        # Metadata labels matching the deployment
        labels = {
            "app.kubernetes.io/name": self.app_name,
            "app.kubernetes.io/instance": self.app_instance,
            "app.kubernetes.io/version": self.app_version,
            "app.kubernetes.io/managed-by": "cuber",
            "app": "bot-proc"
        }

        # ...existing code...

        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=bot_name,
                namespace=self.namespace,
                labels=labels
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=labels),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="bot-proc",
                                image=self.image,
                                image_pull_policy="Always",
                                command=command,
                                resources=client.V1ResourceRequirements(
                                    requests={
                                        "cpu": bot_cpu_request,
                                        "memory": os.getenv("BOT_MEMORY_REQUEST", "4Gi"),
                                        "ephemeral-storage": os.getenv("BOT_EPHEMERAL_STORAGE_REQUEST", "10Gi")
                                    },
                                    limits={
                                        "memory": os.getenv("BOT_MEMORY_LIMIT", "4Gi"),
                                        "ephemeral-storage": os.getenv("BOT_EPHEMERAL_STORAGE_LIMIT", "10Gi")
                                    }
                                ),
                                env_from=[
                                    client.V1EnvFromSource(
                                        config_map_ref=client.V1ConfigMapEnvSource(
                                            name=os.getenv("K8S_CONFIG", "transcript-config")
                                        )
                                    ),
                                    client.V1EnvFromSource(
                                        secret_ref=client.V1SecretEnvSource(
                                            name=os.getenv("K8S_SECRETS", "transcript-secrets")
                                        )
                                    ),
                                    client.V1EnvFromSource(
                                        secret_ref=client.V1SecretEnvSource(
                                            name=os.getenv("K8S_DOCKER_SECRETS", "docker-secrets")
                                        )
                                    )
                                ],
                                env=[]
                            )
                        ],
                        restart_policy="Never",
                        image_pull_secrets=[
                            client.V1LocalObjectReference(
                                name=os.getenv("K8S_DOCKER_SECRETS", "app-secrets")
                            )
                        ],
                        termination_grace_period_seconds=60,
                        tolerations=[
                            client.V1Toleration(
                                key="node.kubernetes.io/not-ready",
                                operator="Exists",
                                effect="NoExecute",
                                toleration_seconds=900
                            ),
                            client.V1Toleration(
                                key="node.kubernetes.io/unreachable",
                                operator="Exists",
                                effect="NoExecute",
                                toleration_seconds=900
                            )
                        ]
                    )
                ),
                backoff_limit=4  # Number of retries before considering the job failed
            )
        )

        try:
            api_response = client.BatchV1Api().create_namespaced_job(
                namespace=self.namespace,
                body=job
            )
            return {
                "name": api_response.metadata.name,
                "status": "JobCreated",
                "created": True,
                "image": self.image,
                "app_instance": self.app_instance,
                "app_version": self.app_version
            }
        except client.ApiException as e:
            return {
                "name": bot_name,
                "status": "Error",
                "created": False,
                "error": str(e)
            }

    def delete_bot_pod(self, pod_name: str) -> Dict:
        try:
            self.v1.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                grace_period_seconds=60
            )
            return {"deleted": True}
        except client.ApiException as e:
            return {
                "deleted": False,
                "error": str(e)
            }

# fmt: on
