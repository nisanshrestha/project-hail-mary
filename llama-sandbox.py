import modal

MODEL_ID = "NousResearch/Meta-Llama-3.1-70B-Instruct"
MODEL_REVISION = "d50656ee28e2c2906d317cbbb6fcb55eb4055a84"

# hf_transfer + HF_HUB_ENABLE_HF_TRANSFER speeds up large multi-shard downloads (often stuck at 0%).
image = (
    modal.Image.debian_slim()
    .pip_install("transformers", "torch", "accelerate", "hf_transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
app = modal.App("example-base-Meta-Llama-3-70B-Instruct", image=image)

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

        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

        from huggingface_hub import snapshot_download

        if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGING_FACE_HUB_TOKEN"):
            print(
                "WARNING: HF_TOKEN not set in container — gated models may hang or 401. "
                "Create Modal secret `huggingface` with HF_TOKEN=..."
            )

        # One download pass; parallel shards (70B ≈ 50 files / ~140GB — 0% can last until first shard finishes).
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
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            local_files_only=True,
        )

        self.pipeline = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
        )

    @modal.method()
    def generate(self, user_input: str, system_prompt: str | None = None):
        """Called from the FastAPI app via modal.Cls.from_name(...).generate.remote."""
        sys_content = system_prompt or "You are a helpful assistant."
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_input},
        ]

        outputs = self.pipeline(
            messages,
            max_new_tokens=256,
        )

        return outputs[0]["generated_text"][-1]


# ## Run the model
@app.local_entrypoint()
def main(prompt: str = None):
    if prompt is None:
        prompt = "Please write a Python function to compute the Fibonacci numbers."
    print(Model().generate.remote(prompt))