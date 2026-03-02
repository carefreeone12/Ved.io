import requests
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.environ.get("HF_API_KEY")

headers = {"Authorization": f"Bearer {api_key}"}
url = "https://huggingface.co/api/models?pipeline_tag=text-to-image&sort=downloads&direction=-1&limit=10"

response = requests.get(url, headers=headers)
models = response.json()

print("Top 10 Text-to-Image models by downloads:")
for m in models:
    print(f"- {m['id']}")
