import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# TODO 1
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

SYSTEM = "你是一个简洁的中文助手，回答不超过三句话。"

print("开始对话（输入 exit 退出）")

messages = [{"role": "system", "content": SYSTEM}] 

while True:
    question = input("\n你：")          

    if question.strip() == "exit":
        break                           

    # TODO 2
    messages.append({"role": "user", "content": question}) #存用户说的信息
    print(f"[调试] 本次发送 {len(messages)} 条消息")
    stream = client.chat.completions.create(
        model="deepseek-flash",
        messages = messages,
        stream = True,
    )

    answer = ""
    print("AI：", end="", flush=True)
    for chunk in stream:
        piece = chunk.choices[0].delta.content if chunk.choices else None
        if piece:
            print(piece, end="", flush=True)
            answer += piece
    print()
    
    messages.append({"role": "assistant", "content": answer}) #存模型说的信息

