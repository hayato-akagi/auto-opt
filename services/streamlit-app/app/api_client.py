from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


class RecipeApiClient:
    def __init__(self, base_url: str | None = None, timeout_sec: float = 20.0) -> None:
        self.base_url = (
            base_url
            or os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002")
        ).rstrip("/")
        self.simple_controller_url = os.getenv(
            "SIMPLE_CONTROLLER_URL", "http://simple-controller:8003"
        ).rstrip("/")
        self.trainer_url = os.getenv(
            "TRAINER_SERVICE_URL", "http://trainer:9008"
        ).rstrip("/")
        self.model_store_url = os.getenv(
            "MODEL_STORE_SERVICE_URL", "http://model-store:9009"
        ).rstrip("/")
        self.ai_controller_url = os.getenv(
            "AI_CONTROLLER_SERVICE_URL", "http://ai-controller:9006"
        ).rstrip("/")
        self.collection_orchestrator_url = os.getenv(
            "COLLECTION_ORCHESTRATOR_SERVICE_URL", "http://collection-orchestrator:8007"
        ).rstrip("/")
        self.timeout_sec = timeout_sec
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _controller_url(self, path: str) -> str:
        return f"{self.simple_controller_url}{path}"

    def _trainer_url(self, path: str) -> str:
        return f"{self.trainer_url}{path}"

    def _model_store_url(self, path: str) -> str:
        return f"{self.model_store_url}{path}"

    def _ai_controller_url(self, path: str) -> str:
        return f"{self.ai_controller_url}{path}"

    def _collection_orchestrator_url(self, path: str) -> str:
        return f"{self.collection_orchestrator_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            response = self.session.request(
                method=method,
                url=self._url(path),
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()
        except requests.exceptions.ConnectionError:
            st.error("Recipe Service に接続できません")
        except requests.exceptions.Timeout:
            st.error("Recipe Service への通信がタイムアウトしました")
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            detail = ""
            if exc.response is not None:
                try:
                    body = exc.response.json()
                    if isinstance(body, dict):
                        detail = str(body.get("detail", ""))
                except ValueError:
                    detail = exc.response.text
            message = f"Recipe Service エラー ({status})"
            if detail:
                message = f"{message}: {detail}"
            st.error(message)
        except requests.exceptions.RequestException as exc:
            st.error(f"Recipe Service 通信エラー: {exc}")
        except ValueError:
            st.error("Recipe Service から不正な JSON レスポンスを受信しました")
        return None

    def list_experiments(self) -> list[dict[str, Any]] | None:
        data = self._request("GET", "/experiments")
        if data is None:
            return None
        experiments = data.get("experiments")
        if isinstance(experiments, list):
            return experiments
        st.error("Recipe Service の実験一覧レスポンス形式が不正です")
        return None

    def create_experiment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request("POST", "/experiments", payload)

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        return self._request("GET", f"/experiments/{experiment_id}")

    def create_trial(
        self,
        experiment_id: str,
        mode: str = "manual",
        control: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"mode": mode, "control": control}
        return self._request("POST", f"/experiments/{experiment_id}/trials", payload)

    def list_trials(self, experiment_id: str) -> list[dict[str, Any]] | None:
        data = self._request("GET", f"/experiments/{experiment_id}/trials")
        if data is None:
            return None
        trials = data.get("trials")
        if isinstance(trials, list):
            return trials
        st.error("Recipe Service の試行一覧レスポンス形式が不正です")
        return None

    def get_trial(self, experiment_id: str, trial_id: str) -> dict[str, Any] | None:
        return self._request("GET", f"/experiments/{experiment_id}/trials/{trial_id}")

    def execute_step(
        self,
        experiment_id: str,
        trial_id: str,
        *,
        coll_x: float,
        coll_y: float,
        return_ray_hits: bool = False,
        return_images: bool = False,
    ) -> dict[str, Any] | None:
        payload = {
            "coll_x": coll_x,
            "coll_y": coll_y,
            "options": {
                "return_ray_hits": return_ray_hits,
                "return_images": return_images,
            },
        }
        return self._request(
            "POST",
            f"/experiments/{experiment_id}/trials/{trial_id}/steps",
            payload,
        )

    def complete_trial(
        self,
        experiment_id: str,
        trial_id: str,
    ) -> dict[str, Any] | None:
        return self._request(
            "POST",
            f"/experiments/{experiment_id}/trials/{trial_id}/complete",
        )

    def list_steps(
        self,
        experiment_id: str,
        trial_id: str,
    ) -> list[dict[str, Any]] | None:
        data = self._request(
            "GET",
            f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        )
        if data is None:
            return None
        steps = data.get("steps")
        if isinstance(steps, list):
            return steps
        st.error("Recipe Service のステップ一覧レスポンス形式が不正です")
        return None

    def get_step(
        self,
        experiment_id: str,
        trial_id: str,
        step_index: int,
    ) -> dict[str, Any] | None:
        return self._request(
            "GET",
            f"/experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}",
        )

    def get_step_images(
        self,
        experiment_id: str,
        trial_id: str,
        step_index: int,
        phase: str,
    ) -> dict[str, Any] | None:
        return self._request(
            "POST",
            f"/experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}/images",
            {"phase": phase},
        )

    def run_sweep(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request("POST", "/recipes/sweep", payload)

    def _request_controller(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            response = self.session.request(
                method=method,
                url=self._controller_url(path),
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()
        except requests.exceptions.ConnectionError:
            st.error("simple-controller に接続できません")
        except requests.exceptions.Timeout:
            st.error("simple-controller への通信がタイムアウトしました")
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            detail = ""
            if exc.response is not None:
                try:
                    body = exc.response.json()
                    if isinstance(body, dict):
                        detail = str(body.get("detail", ""))
                except ValueError:
                    detail = exc.response.text
            message = f"simple-controller エラー ({status})"
            if detail:
                message = f"{message}: {detail}"
            st.error(message)
        except requests.exceptions.RequestException as exc:
            st.error(f"simple-controller 通信エラー: {exc}")
        except ValueError:
            st.error("simple-controller から不正な JSON レスポンスを受信しました")
        return None

    def _request_external_service(
        self,
        method: str,
        url: str,
        service_name: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Generic error-handling for external services (trainer, model-store, ai-controller, collection-orchestrator)."""
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()
        except requests.exceptions.ConnectionError:
            st.error(f"{service_name} に接続できません")
        except requests.exceptions.Timeout:
            st.error(f"{service_name} への通信がタイムアウトしました")
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            detail = ""
            if exc.response is not None:
                try:
                    body = exc.response.json()
                    if isinstance(body, dict):
                        detail = str(body.get("detail", ""))
                except ValueError:
                    detail = exc.response.text
            message = f"{service_name} エラー ({status})"
            if detail:
                message = f"{message}: {detail}"
            st.error(message)
        except requests.exceptions.RequestException as exc:
            st.error(f"{service_name} 通信エラー: {exc}")
        except ValueError:
            st.error(f"{service_name} から不正な JSON レスポンスを受信しました")
        return None

    def _request_external_service_silent(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Silent request helper for capability checks.

        Returns tuple[ok, data, error_message].
        """
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            if not response.text:
                return True, {}, None
            return True, response.json(), None
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            detail = ""
            if exc.response is not None:
                try:
                    body = exc.response.json()
                    if isinstance(body, dict):
                        detail = str(body.get("detail", ""))
                except ValueError:
                    detail = exc.response.text
            message = f"HTTP {status}"
            if detail:
                message = f"{message}: {detail}"
            return False, None, message
        except requests.exceptions.ConnectionError:
            return False, None, "connection error"
        except requests.exceptions.Timeout:
            return False, None, "timeout"
        except requests.exceptions.RequestException as exc:
            return False, None, str(exc)
        except ValueError:
            return False, None, "invalid JSON"

    def control_run(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request_controller("POST", "/control/run", payload)

    def control_step(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request_controller("POST", "/control/step", payload)

    def control_algorithms(self) -> list[dict[str, Any]] | None:
        data = self._request_controller("GET", "/control/algorithms")
        if data is None:
            return None
        algorithms = data.get("algorithms")
        if isinstance(algorithms, list):
            return algorithms
        st.error("simple-controller のアルゴリズム一覧レスポンス形式が不正です")
        return None

    # Trainer service methods
    def start_training(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Start a training job with TrainRequest payload."""
        return self._request_external_service(
            "POST",
            self._trainer_url("/train"),
            "Trainer Service",
            payload,
        )

    def get_training_jobs(self) -> list[dict[str, Any]] | None:
        """Get all training jobs."""
        data = self._request_external_service(
            "GET",
            self._trainer_url("/train"),
            "Trainer Service",
        )
        if data is None:
            return None
        jobs = data.get("jobs")
        if isinstance(jobs, list):
            return jobs
        st.error("Trainer Service のジョブ一覧レスポンス形式が不正です")
        return None

    def get_training_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get status of a specific training job."""
        return self._request_external_service(
            "GET",
            self._trainer_url(f"/train/{job_id}"),
            "Trainer Service",
        )

    # Model store service methods
    def get_models(self) -> list[dict[str, Any]] | None:
        """Get list of all models."""
        data = self._request_external_service(
            "GET",
            self._model_store_url("/models"),
            "Model Store Service",
        )
        if data is None:
            return None
        models = data.get("models")
        if isinstance(models, list):
            return models
        st.error("Model Store Service のモデル一覧レスポンス形式が不正です")
        return None

    def get_model(self, version: str) -> dict[str, Any] | None:
        """Get a specific model by version."""
        return self._request_external_service(
            "GET",
            self._model_store_url(f"/models/{version}"),
            "Model Store Service",
        )

    def register_model(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Register a new model metadata entry."""
        return self._request_external_service(
            "POST",
            self._model_store_url("/models"),
            "Model Store Service",
            payload,
        )

    def promote_model(self, version: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Promote a model to production."""
        return self._request_external_service(
            "POST",
            self._model_store_url(f"/models/{version}/promote"),
            "Model Store Service",
            payload,
        )

    # AI controller service methods
    def run_ai_control(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Run AI-based control loop."""
        return self._request_external_service(
            "POST",
            self._ai_controller_url("/control/run"),
            "AI Controller Service",
            payload,
        )

    # Collection orchestrator service methods
    def start_collection_job(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Start a data collection job."""
        return self._request_external_service(
            "POST",
            self._collection_orchestrator_url("/jobs"),
            "Collection Orchestrator Service",
            payload,
        )

    def get_collection_jobs(self) -> list[dict[str, Any]] | None:
        """Get list of collection jobs."""
        data = self._request_external_service(
            "GET",
            self._collection_orchestrator_url("/jobs"),
            "Collection Orchestrator Service",
        )
        if data is None:
            return None
        jobs = data.get("jobs")
        if isinstance(jobs, list):
            return jobs
        st.error("Collection Orchestrator Service のジョブ一覧レスポンス形式が不正です")
        return None

    def get_collection_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get status of a specific collection job."""
        return self._request_external_service(
            "GET",
            self._collection_orchestrator_url(f"/jobs/{job_id}"),
            "Collection Orchestrator Service",
        )

    # Generic service health/capability methods
    def get_service_health(self, service: str) -> tuple[bool, dict[str, Any] | None, str | None]:
        targets = {
            "trainer": self._trainer_url("/health"),
            "model_store": self._model_store_url("/health"),
            "ai_controller": self._ai_controller_url("/health"),
            "collection_orchestrator": self._collection_orchestrator_url("/health"),
            "simple_controller": self._controller_url("/health"),
        }
        url = targets.get(service)
        if url is None:
            return False, None, f"unknown service: {service}"
        return self._request_external_service_silent("GET", url)

    def check_endpoint(
        self,
        service: str,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        builders = {
            "trainer": self._trainer_url,
            "model_store": self._model_store_url,
            "ai_controller": self._ai_controller_url,
            "collection_orchestrator": self._collection_orchestrator_url,
            "simple_controller": self._controller_url,
        }
        builder = builders.get(service)
        if builder is None:
            return False, None, f"unknown service: {service}"
        try:
            response = self.session.request(
                method=method,
                url=builder(path),
                json=payload,
                timeout=self.timeout_sec,
            )
            # Endpoint existence check: treat anything except not found / server-not-implemented as "available".
            if response.status_code in (404, 501):
                return False, None, f"HTTP {response.status_code}"
            if not response.text:
                return True, {}, None
            try:
                return True, response.json(), None
            except ValueError:
                return True, None, None
        except requests.exceptions.RequestException as exc:
            return False, None, str(exc)
