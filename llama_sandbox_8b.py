import modal

# Inference uses model.generate (not transformers pipeline) for base checkpoints without chat_template.
MODEL_ID = "NousResearch/Meta-Llama-3-8B"
MODEL_REVISION = "315b20096dc791d381d514deb5f8bd9c8d6d3061"

image = (
    modal.Image.debian_slim()
    .pip_install("transformers==4.49.0", "torch==2.6.0", "accelerate==1.4.0", "hf_transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
app = modal.App("example-base-Meta-Llama-3-8B", image=image)

GPU_CONFIG = "H100:1"

CACHE_DIR = "/cache"
cache_vol = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

@app.cls(
    gpu=GPU_CONFIG,
    volumes={CACHE_DIR: cache_vol},
    secrets=[modal.Secret.from_name("huggingface")],
    scaledown_window=60 * 10,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=15)
class Model:
    @modal.enter()
    def setup(self):
        import os

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from huggingface_hub import snapshot_download

        if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGING_FACE_HUB_TOKEN"):
            print(
                "WARNING: HF_TOKEN not set — gated models may hang or fail. "
                "Use Modal secret `huggingface` with HF_TOKEN."
            )

        model_path = snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=CACHE_DIR,
            max_workers=16,
        )

        print(f"Model snapshot at: {model_path}")

        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        self.tokenizer = tokenizer
        self.model = model

    @staticmethod
    def _llama3_prompt(system: str, user: str) -> str:
        """Llama 3 turn format (base tokenizer may not set chat_template)."""
        return (
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
            f"{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        )

    @modal.method()
    def generate(self, user_input: str, system_prompt: str | None = None):
        """Must match backend: llm_service._modal_generate(user_message, system_prompt)."""
        sys_content = system_prompt or "You are a helpful assistant."
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_input},
        ]
        tok = self.tokenizer
        if getattr(tok, "chat_template", None):
            prompt = tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = self._llama3_prompt(sys_content, user_input)

        import torch

        inputs = tok(prompt, return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            out_ids = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=tok.eos_token_id,
            )
        new_tokens = out_ids[0, inputs["input_ids"].shape[1] :]
        return tok.decode(new_tokens, skip_special_tokens=True).strip()


# ## Run the model
@app.local_entrypoint()
def main(prompt: str = None):
    if prompt is None:
        prompt = "Please write a Python function to compute the Fibonacci numbers."
    print(Model().generate.remote(prompt))
