from __future__ import annotations

from typing import Any

from .clients import DownstreamClients
from .errors import DownstreamServiceError, TrialAlreadyCompletedError
from .models import StepExecuteRequest, StepRecord, SweepRequest
from .storage import RecipeStorage, utc_now_iso


class RecipeOrchestrator:
    def __init__(self, storage: RecipeStorage, clients: DownstreamClients) -> None:
        self.storage = storage
        self.clients = clients

    async def execute_step(
        self,
        experiment_id: str,
        trial_id: str,
        command: StepExecuteRequest,
    ) -> dict[str, Any]:
        await self.storage.get_trial_meta(experiment_id, trial_id)
        if await self.storage.summary_exists(experiment_id, trial_id):
            raise TrialAlreadyCompletedError()

        experiment = await self.storage.get_experiment(experiment_id)
        step_index = await self.storage.next_step_index(experiment_id, trial_id)
        
        engine_type = experiment.get("engine_type", "KrakenOS")

        # Get actual position from position-service (x0, y0 before bolt fastening)
        after_position = await self.clients.apply_position(command.coll_x, command.coll_y)
        x0 = after_position["actual_x"]
        y0 = after_position["actual_y"]

        sim_after_position = await self.clients.simulate(
            engine_type,
            self._build_simulation_payload(
                experiment=experiment,
                coll_x_shift=x0,
                coll_y_shift=y0,
                return_ray_hits=command.options.return_ray_hits,
                return_images=False,
            )
        )

        # Apply bolt with initial position (x0, y0)
        bolt_shift = await self.clients.apply_bolt(
            x0=x0,
            y0=y0,
            bolt_model=experiment["bolt_model"],
            random_seed=None,
        )

        # Final position after bolt fastening
        final_x = x0 + bolt_shift["delta_x"]
        final_y = y0 + bolt_shift["delta_y"]
        after_bolt = {
            "final_x": final_x,
            "final_y": final_y,
        }

        sim_after_bolt = await self.clients.simulate(
            engine_type,
            self._build_simulation_payload(
                experiment=experiment,
                coll_x_shift=final_x,
                coll_y_shift=final_y,
                return_ray_hits=command.options.return_ray_hits,
                return_images=False,
            )
        )

        step_record = StepRecord(
            step_index=step_index,
            timestamp=utc_now_iso(),
            command={
                "coll_x": command.coll_x,
                "coll_y": command.coll_y,
            },
            after_position={
                "actual_x": x0,
                "actual_y": y0,
            },
            sim_after_position=self._strip_images(sim_after_position),
            bolt_shift={
                "delta_x": bolt_shift["delta_x"],
                "delta_y": bolt_shift["delta_y"],
                "used_seed": bolt_shift["used_seed"],
                "detail": bolt_shift.get("detail"),
            },
            after_bolt=after_bolt,
            sim_after_bolt=self._strip_images(sim_after_bolt),
        ).model_dump()

        saved_to = await self.storage.save_step(experiment_id, trial_id, step_record)

        response_sim_after_position = dict(sim_after_position)
        response_sim_after_bolt = dict(sim_after_bolt)

        if command.options.return_images:
            images_position = await self.clients.simulate(
                engine_type,
                self._build_simulation_payload(
                    experiment=experiment,
                    coll_x_shift=x0,
                    coll_y_shift=y0,
                    return_ray_hits=False,
                    return_images=True,
                )
            )
            images_bolt = await self.clients.simulate(
                engine_type,
                self._build_simulation_payload(
                    experiment=experiment,
                    coll_x_shift=final_x,
                    coll_y_shift=final_y,
                    return_ray_hits=False,
                    return_images=True,
                )
            )
            self._attach_images(response_sim_after_position, images_position)
            self._attach_images(response_sim_after_bolt, images_bolt)

        return {
            "step_index": step_index,
            "after_position": {
                "actual_x": x0,
                "actual_y": y0,
            },
            "sim_after_position": response_sim_after_position,
            "bolt_shift": {
                "delta_x": bolt_shift["delta_x"],
                "delta_y": bolt_shift["delta_y"],
                "used_seed": bolt_shift["used_seed"],
                "detail": bolt_shift.get("detail"),
            },
            "after_bolt": after_bolt,
            "sim_after_bolt": response_sim_after_bolt,
            "saved_to": saved_to,
        }

    async def get_step_images(
        self,
        experiment_id: str,
        trial_id: str,
        step_index: int,
        phase: str,
    ) -> dict[str, str]:
        step = await self.storage.get_step(experiment_id, trial_id, step_index)
        experiment = await self.storage.get_experiment(experiment_id)
        engine_type = experiment.get("engine_type", "KrakenOS")

        shift_key = "after_position" if phase == "after_position" else "after_bolt"
        shift = step[shift_key]

        sim = await self.clients.simulate(
            engine_type,
            self._build_simulation_payload(
                experiment=experiment,
                coll_x_shift=shift["coll_x_shift"],
                coll_y_shift=shift["coll_y_shift"],
                return_ray_hits=False,
                return_images=True,
            )
        )

        ray_path_image = sim.get("ray_path_image")
        spot_diagram_image = sim.get("spot_diagram_image")
        if not isinstance(ray_path_image, str) or not isinstance(spot_diagram_image, str):
            raise DownstreamServiceError(
                detail="optics-sim returned missing image fields",
                downstream="optics-sim",
            )

        return {
            "ray_path_image": ray_path_image,
            "spot_diagram_image": spot_diagram_image,
        }

    async def complete_trial(self, experiment_id: str, trial_id: str) -> dict[str, Any]:
        if await self.storage.summary_exists(experiment_id, trial_id):
            raise TrialAlreadyCompletedError()
        return await self.storage.create_summary(experiment_id, trial_id)

    async def run_sweep(self, request: SweepRequest) -> dict[str, Any]:
        trial = await self.storage.create_trial(
            request.experiment_id,
            mode="sweep",
            control=None,
        )
        trial_id = trial["trial_id"]

        results: list[dict[str, Any]] = []
        for param_value in request.sweep.values:
            command = request.base_command.model_dump()
            command[request.sweep.param_name] = param_value
            step_result = await self.execute_step(
                request.experiment_id,
                trial_id,
                StepExecuteRequest(**command),
            )
            results.append(
                {
                    "step_index": step_result["step_index"],
                    "param_value": param_value,
                    "sim_after_position": self._sim_summary(
                        step_result["sim_after_position"]
                    ),
                    "sim_after_bolt": self._sim_summary(step_result["sim_after_bolt"]),
                }
            )

        await self.storage.create_summary(
            request.experiment_id,
            trial_id,
            allow_existing=True,
        )

        return {
            "trial_id": trial_id,
            "mode": "sweep",
            "sweep_param": request.sweep.param_name,
            "results": results,
        }

    def _build_simulation_payload(
        self,
        experiment: dict[str, Any],
        coll_x_shift: float,
        coll_y_shift: float,
        return_ray_hits: bool,
        return_images: bool,
    ) -> dict[str, Any]:
        optical_system = experiment["optical_system"]
        payload = dict(optical_system)
        payload["coll_x_shift"] = coll_x_shift
        payload["coll_y_shift"] = coll_y_shift
        payload["return_ray_hits"] = return_ray_hits
        payload["return_ray_path_image"] = return_images
        payload["return_spot_diagram_image"] = return_images
        
        # Transfer camera settings if present
        if experiment.get("camera"):
            payload["camera"] = experiment["camera"]
        
        return payload

    def _strip_images(self, sim: dict[str, Any]) -> dict[str, Any]:
        stripped = dict(sim)
        stripped.pop("ray_path_image", None)
        stripped.pop("spot_diagram_image", None)
        return stripped

    def _attach_images(
        self,
        target: dict[str, Any],
        image_simulation: dict[str, Any],
    ) -> None:
        target["ray_path_image"] = image_simulation.get("ray_path_image")
        target["spot_diagram_image"] = image_simulation.get("spot_diagram_image")

    def _sim_summary(self, sim: dict[str, Any]) -> dict[str, float | None]:
        return {
            "spot_center_x": sim.get("spot_center_x"),
            "spot_center_y": sim.get("spot_center_y"),
            "spot_rms_radius": sim.get("spot_rms_radius"),
        }
