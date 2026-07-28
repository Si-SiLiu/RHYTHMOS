from pathlib import Path
import streamlit.components.v1 as components

_runner = components.declare_component("rhythmos_cognitive_training", path=str(Path(__file__).with_name("cognitive_component_frontend")))


def render_training(*, run_id, training_plan, session_mode, task_types):
    return _runner(run_id=run_id, training_plan=training_plan, session_mode=session_mode, task_types=task_types, key=f"cognitive_training_{run_id}", default=None)
