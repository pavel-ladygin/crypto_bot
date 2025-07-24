import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")  # ключ из env

def call_gpt(prompt_text):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt_text}],
        max_tokens=150,
        temperature=0.7,
    )
    answer = response['choices'][0]['message']['content']
    return answer.strip()
