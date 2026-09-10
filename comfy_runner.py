from __future__ import annotations

import asyncio
import inspect
import uuid
from pathlib import Path
from typing import Any


class ComfyExecutionError(RuntimeError):
    pass


class ComfyRunner:
    """Submit API-format workflows directly to ComfyUI's in-process queue."""

    def __init__(self):
        import execution
        from server import PromptServer

        self.execution = execution
        self.server = PromptServer.instance

    async def queue(self, prompt: dict[str, Any], *, client_id: str = "bird-cage") -> str:
        payload = {"prompt": prompt, "client_id": client_id}
        payload = self.server.trigger_on_prompt(payload)
        prompt = payload["prompt"]
        prompt_id = str(uuid.uuid4())

        valid = await self._validate(prompt_id, prompt)
        if not valid[0]:
            raise ComfyExecutionError(f"Invalid ComfyUI workflow: {valid[1]} | node errors: {valid[3]}")

        number = self.server.number
        self.server.number += 1
        outputs_to_execute = valid[2]
        extra_data = {"client_id": client_id}

        sensitive_keys = getattr(self.execution, "SENSITIVE_EXTRA_DATA_KEYS", None)
        if sensitive_keys:
            sensitive = {}
            for key in sensitive_keys:
                if key in extra_data:
                    sensitive[key] = extra_data.pop(key)
            item = (number, prompt_id, prompt, extra_data, outputs_to_execute, sensitive)
        else:
            item = (number, prompt_id, prompt, extra_data, outputs_to_execute)
        self.server.prompt_queue.put(item)
        return prompt_id

    async def _validate(self, prompt_id: str, prompt: dict[str, Any]):
        fn = self.execution.validate_prompt
        attempts = [
            (prompt_id, prompt, None),
            (prompt_id, prompt),
            (prompt,),
        ]
        last_error = None
        for args in attempts:
            try:
                result = fn(*args)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except TypeError as exc:
                last_error = exc
        raise last_error or RuntimeError("Unable to validate workflow")

    async def wait(self, prompt_id: str, *, timeout: float = 600.0, poll: float = 0.25) -> dict[str, Any]:
        elapsed = 0.0
        while elapsed < timeout:
            history = self.server.prompt_queue.get_history(prompt_id=prompt_id)
            if prompt_id in history:
                item = history[prompt_id]
                status = item.get("status") or {}
                if status.get("status_str") == "error" or status.get("completed") is False:
                    messages = status.get("messages", [])
                    raise ComfyExecutionError(f"ComfyUI execution failed: {messages}")
                return item
            await asyncio.sleep(poll)
            elapsed += poll
        raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")

    async def run(self, prompt: dict[str, Any], *, output_node: str | None = None, timeout: float = 600.0) -> dict[str, Any]:
        prompt_id = await self.queue(prompt)
        history = await self.wait(prompt_id, timeout=timeout)
        image = self.resolve_output_image(history, output_node)
        return {"prompt_id": prompt_id, "history": history, "image": image}

    @staticmethod
    def resolve_output_image(history: dict[str, Any], output_node: str | None = None) -> dict[str, Any] | None:
        outputs = history.get("outputs", {})
        ordered = []
        if output_node and str(output_node) in outputs:
            ordered.append(outputs[str(output_node)])
        ordered.extend(v for k, v in outputs.items() if not output_node or str(k) != str(output_node))
        for output in ordered:
            images = output.get("images") if isinstance(output, dict) else None
            if images:
                return images[0]
        return None

    @staticmethod
    def image_ref_path(ref: dict[str, Any]) -> Path:
        import folder_paths

        typ = ref.get("type", "output")
        subfolder = ref.get("subfolder", "")
        filename = ref["filename"]
        if typ == "input":
            root = Path(folder_paths.get_input_directory())
        elif typ == "temp":
            root = Path(folder_paths.get_temp_directory())
        else:
            root = Path(folder_paths.get_output_directory())
        p = (root / subfolder / filename).resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        return p
