from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from .clients import ControllerClient
from .models import CollectionJobCreateRequest
from .storage import InMemoryJobStore


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


async def _run_single_task(
	*,
	algorithm: str,
	request: CollectionJobCreateRequest,
	task: dict[str, Any],
	seed: int,
	client: ControllerClient,
	semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
	payload = {
		"experiment_id": task["experiment_id"],
		"algorithm": algorithm,
		"config": request.controller_config.model_dump(),
		"target": request.target.model_dump(),
		"initial_coll": request.initial_coll.model_dump(),
		"max_steps": request.max_steps,
		"tolerance": request.tolerance,
		"random_seed": seed,
	}

	async with semaphore:
		try:
			result = await client.run_control(algorithm, payload)
			return {
				"experiment_id": task["experiment_id"],
				"seed": seed,
				"trial_id": result.get("trial_id"),
				"converged": result.get("converged"),
				"steps": result.get("steps"),
				"error": None,
			}
		except Exception as exc:
			return {
				"experiment_id": task["experiment_id"],
				"seed": seed,
				"trial_id": None,
				"converged": None,
				"steps": None,
				"error": str(exc),
			}


async def run_collection_job(
	*,
	job_id: str,
	request: CollectionJobCreateRequest,
	store: InMemoryJobStore,
	client: ControllerClient,
) -> None:
	flat_tasks: list[tuple[dict[str, Any], int]] = []
	for t in request.tasks:
		task_dict = t.model_dump()
		for seed in t.seeds:
			flat_tasks.append((task_dict, seed))

	semaphore = asyncio.Semaphore(request.max_workers)
	coros = [
		_run_single_task(
			algorithm=request.algorithm,
			request=request,
			task=task,
			seed=seed,
			client=client,
			semaphore=semaphore,
		)
		for task, seed in flat_tasks
	]

	results = await asyncio.gather(*coros)
	completed = len(results)
	failed = sum(1 for r in results if r.get("error"))

	if completed == 0:
		status = "failed"
	elif failed == 0:
		status = "completed"
	elif failed == completed:
		status = "failed"
	else:
		status = "partial"

	store.update(
		job_id,
		{
			"status": status,
			"completed_tasks": completed,
			"failed_tasks": failed,
			"finished_at": _now_iso(),
			"task_results": results,
		},
	)
