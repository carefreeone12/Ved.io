import asyncio
import os
import sys
from pathlib import Path

# Add core path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from dotenv import load_dotenv
load_dotenv()

from core.ai_clients.huggingface_client import HuggingFaceClient

async def run_test():
    api_key = os.environ.get("HF_API_KEY")
    model = os.environ.get("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
    
    print(f"Testing model: {model}")
    print(f"API key: {api_key[:10]}...")
    
    client = HuggingFaceClient(api_key=api_key, model=model)
    
    result = await client.generate_image(
        prompt="A vast alien jungle planet at golden hour, lush vegetation, moons in sky, cinematic",
        job_id="test_job_001",
        model=model
    )
    print(f"SUCCESS: {result}")
    
    local_path = result.get("local_path")
    if local_path and os.path.exists(local_path):
        print(f"Image saved at: {local_path} ({os.path.getsize(local_path)} bytes)")
    else:
        print("ERROR: Image file NOT found!")

if __name__ == "__main__":
    asyncio.run(run_test())
