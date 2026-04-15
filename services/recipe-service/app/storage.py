from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles

from .errors import ResourceNotFoundError, TrialAlreadyCompletedError
from .models import ExperimentCreateRequest

EXPERIMENT_PATTERN = re.compile(r"^exp_(\d+)$")
TRIAL_PATTERN = re.compile(r"^trial_(\d+)$")
STEP_PATTERN = re.compile(r"^step_(\d+)\.json$")


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class RecipeStorage:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.experiments_dir = self.data_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    def _experiment_dir(self, experiment_id: str) -> Path:
        return self.experiments_dir / experiment_id

    def _experiment_file(self, experiment_id: str) -> Path:
        return self._experiment_dir(experiment_id) / "experiment.json"

    def _trial_dir(self, experiment_id: str, trial_id: str) -> Path:
        return self._experiment_dir(experiment_id) / trial_id

    def _trial_meta_file(self, experiment_id: str, trial_id: str) -> Path:
        return self._trial_dir(experiment_id, trial_id) / "trial_meta.json"

    def _step_file(self, experiment_id: str, trial_id: str, step_index: int) -> Path:
        return self._trial_dir(experiment_id, trial_id) / f"step_{step_index:03d}.json"

    def _summary_file(self, experiment_id: str, trial_id: str) -> Path:
        return self._trial_dir(experiment_id, trial_id) / "summary.json"

    async def _read_json(self, file_path: Path) -> dict[str, Any]:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)

    async def _write_json(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            await f.write("\n")

    def _next_id(self, parent_dir: Path, pattern: re.Pattern[str], prefix: str) -> str:
        max_index = 0
        if parent_dir.exists():
            for path in parent_dir.iterdir():
                if not path.is_dir():
                    continue
                matched = pattern.match(path.name)
                if matched is None:
                    continue
                max_index = max(max_index, int(matched.group(1)))
        return f"{prefix}_{max_index + 1:03d}"

    def _sorted_dirs(self, parent_dir: Path, pattern: re.Pattern[str]) -> list[Path]:
        matched_paths: list[tuple[int, Path]] = []
        if not parent_dir.exists():
            return []
        for path in parent_dir.iterdir():
            if not path.is_dir():
                continue
            matched = pattern.match(path.name)
            if matched is None:
                continue
            matched_paths.append((int(matched.group(1)), path))
        matched_paths.sort(key=lambda item: item[0])
        return [path for _, path in matched_paths]

    def _sorted_step_files(self, trial_dir: Path) -> list[Path]:
        matched_paths: list[tuple[int, Path]] = []
        if not trial_dir.exists():
            return []
        for path in trial_dir.iterdir():
            if not path.is_file():
                continue
            matched = STEP_PATTERN.match(path.name)
            if matched is None:
                continue
            matched_paths.append((int(matched.group(1)), path))
        matched_paths.sort(key=lambda item: item[0])
        return [path for _, path in matched_paths]

    async def create_experiment(
        self, payload: ExperimentCreateRequest
    ) -> dict[str, Any]:
        experiment_id = self._next_id(
            self.experiments_dir,
            EXPERIMENT_PATTERN,
            "exp",
        )
        created_at = utc_now_iso()
        experiment = {
            "experiment_id": experiment_id,
            "name": payload.name,
            "engine_type": payload.engine_type,
            "created_at": created_at,
            "optical_system": payload.optical_system.model_dump(),
            "bolt_model": payload.bolt_model.model_dump(),
            "camera": payload.camera.model_dump() if payload.camera else None,
        }
        await self._write_json(self._experiment_file(experiment_id), experiment)
        return {
            "experiment_id": experiment_id,
            "name": payload.name,
            "engine_type": payload.engine_type,
            "created_at": created_at,
        }

    async def list_experiments(self) -> list[dict[str, Any]]:
        experiments: list[dict[str, Any]] = []
        for exp_dir in self._sorted_dirs(self.experiments_dir, EXPERIMENT_PATTERN):
            exp_file = exp_dir / "experiment.json"
            if not exp_file.exists():
                continue
            experiment = await self._read_json(exp_file)
            experiments.append(
                {
                    "experiment_id": experiment["experiment_id"],
                    "name": experiment["name"],
                    "engine_type": experiment.get("engine_type", "KrakenOS"),
                    "created_at": experiment["created_at"],
                }
            )
        return experiments

    async def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        exp_file = self._experiment_file(experiment_id)
        if not exp_file.exists():
            raise ResourceNotFoundError(f"experiment not found: {experiment_id}")
        return await self._read_json(exp_file)

    async def create_trial(
        self,
        experiment_id: str,
        mode: str,
        control: dict[str, Any] | None,
    ) -> dict[str, Any]:
        await self.get_experiment(experiment_id)
        experiment_dir = self._experiment_dir(experiment_id)
        trial_id = self._next_id(experiment_dir, TRIAL_PATTERN, "trial")
        started_at = utc_now_iso()
        trial_meta = {
            "trial_id": trial_id,
            "experiment_id": experiment_id,
            "mode": mode,
            "control": control,
            "started_at": started_at,
        }
        await self._write_json(self._trial_meta_file(experiment_id, trial_id), trial_meta)
        return {
            "trial_id": trial_id,
            "experiment_id": experiment_id,
            "mode": mode,
            "started_at": started_at,
        }

    async def get_trial_meta(self, experiment_id: str, trial_id: str) -> dict[str, Any]:
        await self.get_experiment(experiment_id)
        trial_meta_file = self._trial_meta_file(experiment_id, trial_id)
        if not trial_meta_file.exists():
            raise ResourceNotFoundError(f"trial not found: {trial_id}")
        return await self._read_json(trial_meta_file)

    async def list_trials(self, experiment_id: str) -> list[dict[str, Any]]:
        await self.get_experiment(experiment_id)
        trial_items: list[dict[str, Any]] = []
        for trial_dir in self._sorted_dirs(self._experiment_dir(experiment_id), TRIAL_PATTERN):
            trial_id = trial_dir.name
            trial_meta = await self.get_trial_meta(experiment_id, trial_id)
            total_steps = await self.count_steps(experiment_id, trial_id)
            trial_items.append(
                {
                    "trial_id": trial_meta["trial_id"],
                    "mode": trial_meta["mode"],
                    "started_at": trial_meta["started_at"],
                    "total_steps": total_steps,
                    "completed": self._summary_file(experiment_id, trial_id).exists(),
                }
            )
        return trial_items

    async def get_trial_detail(self, experiment_id: str, trial_id: str) -> dict[str, Any]:
        trial_meta = await self.get_trial_meta(experiment_id, trial_id)
        response = dict(trial_meta)
        response["total_steps"] = await self.count_steps(experiment_id, trial_id)

        summary_file = self._summary_file(experiment_id, trial_id)
        if summary_file.exists():
            response["summary"] = await self._read_json(summary_file)
            response["completed"] = True
        else:
            response["summary"] = None
            response["completed"] = False
        return response

    async def summary_exists(self, experiment_id: str, trial_id: str) -> bool:
        await self.get_trial_meta(experiment_id, trial_id)
        return self._summary_file(experiment_id, trial_id).exists()

    async def next_step_index(self, experiment_id: str, trial_id: str) -> int:
        await self.get_trial_meta(experiment_id, trial_id)
        step_files = self._sorted_step_files(self._trial_dir(experiment_id, trial_id))
        if not step_files:
            return 0
        matched = STEP_PATTERN.match(step_files[-1].name)
        if matched is None:
            return 0
        return int(matched.group(1)) + 1

    async def count_steps(self, experiment_id: str, trial_id: str) -> int:
        await self.get_trial_meta(experiment_id, trial_id)
        return len(self._sorted_step_files(self._trial_dir(experiment_id, trial_id)))

    async def save_step(
        self,
        experiment_id: str,
        trial_id: str,
        step_record: dict[str, Any],
    ) -> str:
        await self.get_trial_meta(experiment_id, trial_id)
        step_index = int(step_record["step_index"])
        step_file = self._step_file(experiment_id, trial_id, step_index)
        await self._write_json(step_file, step_record)
        return step_file.relative_to(self.data_dir).as_posix()

    async def list_step_records(
        self,
        experiment_id: str,
        trial_id: str,
    ) -> list[dict[str, Any]]:
        await self.get_trial_meta(experiment_id, trial_id)
        records: list[dict[str, Any]] = []
        for step_file in self._sorted_step_files(self._trial_dir(experiment_id, trial_id)):
            records.append(await self._read_json(step_file))
        return records

    async def list_steps(self, experiment_id: str, trial_id: str) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for step_record in await self.list_step_records(experiment_id, trial_id):
            summaries.append(
                {
                    "step_index": step_record["step_index"],
                    "command": step_record["command"],
                    "sim_after_position": self._sim_summary(
                        step_record["sim_after_position"]
                    ),
                    "sim_after_bolt": self._sim_summary(step_record["sim_after_bolt"]),
                }
            )
        return summaries

    def _sim_summary(self, sim: dict[str, Any]) -> dict[str, float | None]:
        return {
            "spot_center_x": sim.get("spot_center_x"),
            "spot_center_y": sim.get("spot_center_y"),
            "spot_rms_radius": sim.get("spot_rms_radius"),
        }

    async def get_step(
        self,
        experiment_id: str,
        trial_id: str,
        step_index: int,
    ) -> dict[str, Any]:
        await self.get_trial_meta(experiment_id, trial_id)
        step_file = self._step_file(experiment_id, trial_id, step_index)
        if not step_file.exists():
            raise ResourceNotFoundError(f"step not found: {step_index}")
        return await self._read_json(step_file)

    async def create_summary(
        self,
        experiment_id: str,
        trial_id: str,
        *,
        allow_existing: bool = False,
    ) -> dict[str, Any]:
        if await self.summary_exists(experiment_id, trial_id) and not allow_existing:
            raise TrialAlreadyCompletedError()

        trial_meta = await self.get_trial_meta(experiment_id, trial_id)
        steps = await self.list_step_records(experiment_id, trial_id)
        final_step: dict[str, float | None] | None = None
        if steps:
            final_sim = steps[-1]["sim_after_bolt"]
            final_step = {
                "spot_center_x": final_sim.get("spot_center_x"),
                "spot_center_y": final_sim.get("spot_center_y"),
                "spot_rms_radius": final_sim.get("spot_rms_radius"),
            }

        summary = {
            "trial_id": trial_meta["trial_id"],
            "experiment_id": trial_meta["experiment_id"],
            "mode": trial_meta["mode"],
            "total_steps": len(steps),
            "converged": None,
            "final_step": final_step,
            "finished_at": utc_now_iso(),
        }
        await self._write_json(self._summary_file(experiment_id, trial_id), summary)
        return summary
