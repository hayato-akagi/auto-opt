from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from .clients import RecipeClient
from .logic import compute_ai_step
from .models import ControlRunRequest, ControlRunResponse, InitialObservation

if TYPE_CHECKING:
    from .model import ModelManager


@dataclass
class LoopState:
    commanded_x: float
    commanded_y: float
    perturb_x: float = 0.0
    perturb_y: float = 0.0


def _extract_spot(sim_data: dict[str, Any]) -> tuple[float, float, float | None]:
    return (
        float(sim_data["spot_center_x"]),
        float(sim_data["spot_center_y"]),
        float(sim_data["spot_rms_radius"]) if sim_data.get("spot_rms_radius") is not None else None,
    )


async def run_control_loop(
    request: ControlRunRequest,
    client: RecipeClient,
    model_manager: ModelManager | None = None,
) -> ControlRunResponse:
    rng = random.Random(request.random_seed)

    model_version = request.config.model_version
    model_type = request.config.model_type

    control_payload: dict[str, Any] = {
        "algorithm": request.algorithm,
        "config": request.config.model_dump(),
        "target": request.target.model_dump(),
        "initial_coll": request.initial_coll.model_dump(),
        "max_steps": request.max_steps,
        "tolerance": request.tolerance,
        "random_seed": request.random_seed,
    }
    trial = await client.create_trial(
        request.experiment_id,
        control_payload,
        bolt_model=request.bolt_model_override,
    )
    trial_id = str(trial["trial_id"])

    step0 = await client.execute_step(
        request.experiment_id,
        trial_id,
        request.initial_coll.coll_x,
        request.initial_coll.coll_y,
    )

    pre_x0, pre_y0, _ = _extract_spot(step0["sim_after_position"])
    post_x0, post_y0, post_rms0 = _extract_spot(step0["sim_after_bolt"])

    boot_correction_x = (request.target.spot_center_x - pre_x0) / request.config.spot_to_coll_scale_x
    boot_correction_y = (request.target.spot_center_y - pre_y0) / request.config.spot_to_coll_scale_y

    state = LoopState(
        commanded_x=request.initial_coll.coll_x + boot_correction_x,
        commanded_y=request.initial_coll.coll_y + boot_correction_y,
    )

    initial_observation = InitialObservation(
        step_index=int(step0["step_index"]),
        initial_coll_x=request.initial_coll.coll_x,
        initial_coll_y=request.initial_coll.coll_y,
        spot_pre_x=pre_x0,
        spot_pre_y=pre_y0,
        spot_post_x=post_x0,
        spot_post_y=post_y0,
        boot_correction_x=boot_correction_x,
        boot_correction_y=boot_correction_y,
    )

    final_post_x = post_x0
    final_post_y = post_y0
    final_post_rms = post_rms0
    final_distance = math.hypot(
        request.target.spot_center_x - final_post_x,
        request.target.spot_center_y - final_post_y,
    )
    converged = final_distance < request.tolerance

    last_step = step0
    steps_executed = 0
    prev_steps_for_inference: list[dict] = []  # Accumulated history for N>1

    for _ in range(request.max_steps):
        pre_x, pre_y, _ = _extract_spot(last_step["sim_after_position"])

        # Record the most recently completed step as history *before* using it
        # for inference, so the model sees the same history it was trained on
        # (the trainer's target step i always has access to steps[0:i]).
        prev_steps_for_inference.append(last_step)

        observed_spot_x = pre_x + state.perturb_x
        observed_spot_y = pre_y + state.perturb_y

        action = compute_ai_step(
            config=request.config,
            target_x=request.target.spot_center_x,
            target_y=request.target.spot_center_y,
            current_coll_x=state.commanded_x,
            current_coll_y=state.commanded_y,
            spot_pre_x=observed_spot_x,
            spot_pre_y=observed_spot_y,
            model_manager=model_manager,
            prev_steps=prev_steps_for_inference,
        )

        state.commanded_x = action.next_coll_x
        state.commanded_y = action.next_coll_y

        ai_step_log = {
            "baseline_delta_x": action.baseline_delta_x,
            "baseline_delta_y": action.baseline_delta_y,
            "dnn_residual_x": action.dnn_residual_x,
            "dnn_residual_y": action.dnn_residual_y,
            "safety_triggered": action.safety_triggered,
            "model_version": model_version,
        }

        step_result = await client.execute_step(
            request.experiment_id,
            trial_id,
            state.commanded_x,
            state.commanded_y,
            ai_step_log=ai_step_log,
            observed_spot_x=observed_spot_x,
            observed_spot_y=observed_spot_y,
        )
        steps_executed += 1
        last_step = step_result

        final_post_x, final_post_y, final_post_rms = _extract_spot(step_result["sim_after_bolt"])
        final_distance = math.hypot(
            request.target.spot_center_x - final_post_x,
            request.target.spot_center_y - final_post_y,
        )
        converged = final_distance < request.tolerance
        if converged:
            break

        state.perturb_x = rng.gauss(0.0, request.config.release_perturbation.std_x)
        state.perturb_y = rng.gauss(0.0, request.config.release_perturbation.std_y)

    await client.complete_trial(request.experiment_id, trial_id)

    return ControlRunResponse(
        trial_id=trial_id,
        algorithm=request.algorithm,
        model_version=model_version,
        model_type=model_type,
        converged=converged,
        steps=steps_executed,
        initial_observation=initial_observation,
        final_spot_center_x=final_post_x,
        final_spot_center_y=final_post_y,
        final_spot_rms_radius=final_post_rms,
        final_distance=final_distance,
    )