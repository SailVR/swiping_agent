from http import client
from dashscope import Generation
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DASHSCOPE_API_KEY")

resp = Generation.call(
    api_key=api_key,
    model="qwen-turbo",
    messages=[{"role": "user", "content": "你好"}],
    result_format="message"
)
print(resp)