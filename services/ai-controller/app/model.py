from __future__ import annotations

from datetime import datetime, timezone


class ModelManager:
	def __init__(self, *, model_type: str, model_version: str | None) -> None:
		self._model_type = model_type
		self._model_version = model_version
		self._loaded_at = datetime.now(timezone.utc)
		self._device = "cpu"

	def status(self) -> dict[str, str | None]:
		return {
			"loaded_version": self._model_version,
			"model_type": self._model_type,
			"loaded_at": self._loaded_at.isoformat(),
			"device": self._device,
		}

	def reload(self, *, model_type: str | None = None, model_version: str | None = None) -> dict[str, str | None]:
		if model_type is not None:
			self._model_type = model_type
		self._model_version = model_version
		self._loaded_at = datetime.now(timezone.utc)
		return {
			"loaded_version": self._model_version,
			"model_type": self._model_type,
		}
