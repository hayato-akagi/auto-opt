from __future__ import annotations

from copy import deepcopy


class InMemoryJobStore:
	def __init__(self) -> None:
		self._jobs: dict[str, dict] = {}

	def create(self, job_id: str, job: dict) -> None:
		if job_id in self._jobs:
			raise ValueError(f"job already exists: {job_id}")
		self._jobs[job_id] = deepcopy(job)

	def get(self, job_id: str) -> dict | None:
		job = self._jobs.get(job_id)
		return deepcopy(job) if job is not None else None

	def list(self, *, status: str | None = None) -> list[dict]:
		jobs = [deepcopy(job) for job in self._jobs.values()]
		if status is not None:
			jobs = [job for job in jobs if job.get("status") == status]
		jobs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
		return jobs

	def update(self, job_id: str, patch: dict) -> None:
		if job_id not in self._jobs:
			raise KeyError(job_id)
		self._jobs[job_id].update(deepcopy(patch))

	def append_task_result(self, job_id: str, task_result: dict) -> None:
		if job_id not in self._jobs:
			raise KeyError(job_id)
		self._jobs[job_id].setdefault("task_results", []).append(deepcopy(task_result))
