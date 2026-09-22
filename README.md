# llm-chat

用 Python 调用 DeepSeek 大模型 API 的命令行多轮对话脚本。

目标不是"做产品"，而是**把 Python 侧调用大模型的整条链路走通并能讲清原理**：venv 隔离依赖、`.env` 管理密钥、
流式（`stream=True`）逐字输出，并靠**客户端自己维护 `messages` 历史**实现多轮对话。

整份有效代码只有 **31 行**，但每一环都刻意没有省略机制——**这个项目要证明的不是"能跑"，而是"每一行为什么这么写"。**

## 数据流

```text
用户输入
  └→ messages.append({"role": "user", ...})            ← 客户端攒历史
       └→ client.chat.completions.create(model, messages, stream=True)
            └→ for chunk in stream:                    ← 逐片到达
                 └→ chunk.choices[0].delta.content      ← 增量，不是完整消息
                      └→ print(piece) + answer += piece ← 自己拼回完整回答
                           └→ messages.append({"role": "assistant", ...})  ← 供下一轮使用
```

## 技术栈

| 技术             | 版本     | 用途                                        |
| -------------- | ------ | ----------------------------------------- |
| Python         | 3.12.1 | 运行环境                                      |
| venv           | 标准库    | 项目级依赖隔离（`include-system-site-packages = false`） |
| openai         | 3.13.0 | 官方 SDK，兼容 DeepSeek 的 OpenAI 格式接口           |
| python-dotenv  | 1.2.3  | 从 `.env` 读取密钥，避免硬编码                       |
| DeepSeek API   | —      | 大模型服务，模型 `deepseek-flash`                 |

> 依赖清单见 `requirements.txt`（15 行，全部用 `==` 锁定版本）。除上面 2 个直接依赖外，其余 13 个是它们递归拖进来的传递依赖。

## 核心功能

1. **多轮对话（带上下文）**
   每轮把 user 输入和 assistant 回复都 append 进 `messages`，请求时**全量发送**。
   调试计数可从 `2 → 4 → 6` 观察到历史在累积。

2. **流式输出**
   `stream=True` 让回答逐字到达；脚本把每个 `delta` 碎片拼回完整字符串（`answer += piece`），
   拼回的完整回答同时被写回 `messages`——**流式不会破坏历史**。

3. **密钥与依赖隔离**
   Key 只存在于环境变量 / `.env`（`.env` 已被 `.gitignore` 忽略）；依赖装在项目自己的 venv 里。

## 技术选型理由

### 为什么用 venv，而不是全局装包？

Python 的 `pip install` 默认把包装进**全局共享**的一份 `site-packages`：项目 A 需要的 1.0 版会被项目 B 需要的 3.0 版**挤掉**。
`python -m venv .venv` 复制一份解释器和 pip，但**不复制任何已安装的包**——新建的货架是空的，从而做到**物理隔离**。

对照 Java：Maven 的本地仓库是全机共享的，靠 `pom.xml` 算出的 classpath 做**逻辑隔离**；Python 默认没有"清单"这一层，
所以只能物理上再复制一份环境。**一句话：Maven 靠逻辑隔离，venv 靠物理隔离。**

### 为什么用 openai SDK，而不是裸 `requests`？

同一个 DeepSeek 接口我在 Java 项目（`iot-data-platform` 的 NL2SQL 模块）里用 `RestTemplate` **裸调**过，所以两边可以直接对比：

| 环节        | Java 裸调                                            | Python + SDK                          |
| --------- | -------------------------------------------------- | ------------------------------------- |
| 请求体       | 手拼 JSON 字符串                                        | 直接传字典，**序列化由 SDK 负责**                 |
| 认证头       | 手设 `Authorization: Bearer xxx`                     | 构造函数传一次 `api_key`，**认证头自动加**          |
| 发送        | `restTemplate.postForObject(...)`                  | `client.chat.completions.create(...)` |
| 取结果       | 四层嵌套 `path()` + `asText()`                         | `resp.choices[0].message.content`     |
| 超时 / 限流重试 | **自己写**                                            | **SDK 内置**（默认 `max_retries = 2`）       |

取舍标准：**长期高频调用用 SDK**（省样板、少犯错）；**偶发调用或需要精细控制**（自定义重试、代理、超时）时裸调更透明。
但要注意——SDK 只替你干"通用 HTTP 那一层"，**业务逻辑（清理模型输出、校验、拼 SQL）永远得自己写**。

### 为什么开流式（`stream=True`）？

它**不改变链路**，只是把第 ④ 步"取结果"的方式从"等一整句话"换成"逐片取"。
代价是返回值从 `ChatCompletion` 变成 `Stream[ChatCompletionChunk]`，字段名从 `message` 变成 **`delta`（增量）**，
所以必须自己把碎片攒起来。收益是**用户体验**：首字上屏时间从"等整句"降到"第一个 token"。

### 为什么把历史全量发过去？

因为**大模型 API 是无状态的**——服务端不保存对话，每次请求都是一次独立调用，模型只能看到这次 `messages` 里给了什么。
所以"多轮"不是模型记住了，而是**客户端每轮把整份历史重新递过去**。（措辞要准：不是"AI 去读上下文"，而是"你把上下文递给它"，主动方是调用方。）
类比 HTTP 也是无状态的，Java Web 得靠 Session / Cookie 把状态带回来——这里"带状态"的方式就是塞进 `messages`。

## 踩坑记录

### ① PowerShell 的 `>` 把 `requirements.txt` 写成了 UTF-16

- **现象**：`pip freeze > requirements.txt` 之后，该文件被工具判定为"二进制"，`pip install -r` 报 `Invalid requirement`。
- **原因**：Windows PowerShell 5.1 的 `Out-File`（`>` 等价于它）**默认编码是 `unicode`，即 UTF-16LE**；PowerShell 7.x 起才改为 `utf8NoBOM`。所以网上教程说法不一，**差别在版本**。
- **解法**：用 `cmd /c "pip freeze > requirements.txt"`（cmd 的 `>` 直接写原始字节），或 `... | Out-File -Encoding ascii`。**能绕开的坑就直接绕开。**
- 出处：[Out-File（5.1）](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/out-file?view=powershell-5.1)

### ② 401：系统环境变量里的旧 Key 覆盖了 `.env` 里的新 Key

- **现象**：在官网换了新 Key 并写进 `.env` 后运行，仍报 `401 Authentication Fails, Your api key: ****3aa5`（结尾正是**已作废的旧 Key**）。
- **原因**：`load_dotenv()` 默认 **`override=False`**——Python 进程先继承操作系统的环境变量，`.env` 的值**不覆盖**已存在的，所以旧 Key 胜出。
- **解法**：**换 Key 要换两处**（`setx` 系统变量 + `.env`），并重开终端。排查方式是比较两处是否一致（只比指纹、不打印 Key）：

  ```python
  from dotenv import dotenv_values
  import os
  e = dotenv_values('.env')['DEEPSEEK_API_KEY']
  s = os.getenv('DEEPSEEK_API_KEY', '')
  print('相同?', e == s)
  ```
- 出处：[python-dotenv 官方文档](https://saurabh-kumar.com/python-dotenv/)

### ③ 模型名会过期：`deepseek-chat` 已不在官方模型表

- **现象**：按早期资料写的 `model="deepseek-chat"` 实测**仍能跑通**，但查官方文档发现该名已不在模型表中。
- **原因**：兼容层会接受 legacy 名，但**不保证长期有效**。
- **解法**：改用官方当前名 `deepseek-flash`。同类参数（模型名、API 路径、SDK 签名）**必须查官方文档，不能沿用旧资料、更不能凭记忆**。
  顺带核实：`base_url` 只写到域名 `https://api.deepseek.com`，具体路径由 SDK 自己拼。
- 出处：[模型与定价](https://api-docs.deepseek.com/quick_start/pricing)

### ④ `os.getenv()` 的参数是"变量名"，不是"值"

- **现象**：一开始把 Key 的**值**填进了 `os.getenv("sk-...")`，等于让 Python 去找一个"名字叫 sk-xxx 的环境变量"，必然取不到。
- **原因**：`os.getenv(变量名)` 是**间接层**——代码里只该出现变量名，值永远留在环境里。
- **解法**：`os.getenv("DEEPSEEK_API_KEY")`。**这一层间接不是仪式，是防火墙**：代码要进 git，密钥不能进 git。
  （代价是那次 Key 已被带进聊天记录，只能作废重建。）

### ⑤ 流式收尾时 `chunk.choices` 是空列表

- **现象**：流式迭代到最后一片时报 `IndexError: list index out of range`。
- **原因**：最后一片（尤其开启用量统计时）`choices` 可能是**空列表**，此时 `chunk.choices[0]` 越界。
- **解法**：取值前判空——`chunk.choices[0].delta.content if chunk.choices else None`。

## 快速开始

### 环境要求

- Python 3.12+

### 1. 创建并激活虚拟环境

```powershell
cd "D:\Code practice\llm-chat"
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # 成功标志：提示符出现 (.venv)
```

> 激活**只对当前终端窗口有效**，关窗即失效。报 `No module named 'xxx'` 的第一嫌疑就是"没激活"。
> Git Bash 下是 `source .venv/Scripts/activate`。

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置 API Key

在项目根目录新建 `.env`：

```
DEEPSEEK_API_KEY=你的Key
```

> `.env` 已被 `.gitignore` 忽略，不会进版本库。若同时设置了系统环境变量，**系统变量优先**（见踩坑 ②）。

### 4. 运行

```powershell
python chat.py
```

输入 `exit` 退出。终端会打印 `[调试] 本次发送 N 条消息`，可直观看到 `messages` 历史在逐轮累积（`2 → 4 → 6`）。

## 项目结构

```text
llm-chat/
├── chat.py            # 主脚本，44 行（有效代码 31 行）
├── requirements.txt   # 依赖清单，版本已用 == 锁定
├── .env               # 密钥（已被 .gitignore 忽略，不进版本库）
└── .venv/             # 虚拟环境（已被 .gitignore 忽略）
```

## 已知边界与下一步

- **上下文会线性增长**：历史只增不减、每轮全量重发，token 消耗随轮数增长，最终撞上模型上下文上限。下一步可做截断 / 摘要式上下文管理。
- **无自定义异常处理**：目前依赖 SDK 的默认重试（2 次）与异常类型；未按 `AuthenticationError` / `RateLimitError` 等分类兜底。
- **无单元测试**：目前靠人工跑通验证。
