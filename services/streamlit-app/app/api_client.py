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
        self.timeout_sec = timeout_sec
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

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

    def execute_step(
        self,
        experiment_id: str,
        trial_id: str,
        *,
        coll_x: float,
        coll_y: float,
        torque_upper: float,
        torque_lower: float,
        return_ray_hits: bool = False,
        return_images: bool = False,
    ) -> dict[str, Any] | None:
        payload = {
            "coll_x": coll_x,
            "coll_y": coll_y,
            "torque_upper": torque_upper,
            "torque_lower": torque_lower,
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
