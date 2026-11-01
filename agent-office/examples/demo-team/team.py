"""
Demo multi-agent "second brain" team — a plain Python repo that knows nothing
about agent-office. It just uses the official OpenAI and Anthropic SDKs.

  Mindy   (orchestrator)  OpenAI chat completions, delegates via a tool
  Hermes  (research)      OpenAI chat completions, streaming
  Atlas   (data)          OpenAI Responses API
  Codex   (coding)        OpenAI chat completions, streaming
  Scribe  (writer)        Anthropic Messages, streaming — fans out to 6 parallel summarizers

Run it through agent-office:   agent-office run -- python team.py
"""
import json
import os
import random
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

from anthropic import Anthropic
from openai import OpenAI

warnings.filterwarnings("ignore", category=DeprecationWarning)

oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-demo"))
ant = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "sk-ant-demo"))
OAI_MODEL = os.environ.get("DEMO_OPENAI_MODEL", "gpt-4o-mini")
ANT_MODEL = os.environ.get("DEMO_ANTHROPIC_MODEL", "claude-sonnet-4-5")


def fn(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required if required is not None else list(props)}}}


def say(who, msg):
    print(f"[{who}] {msg}", flush=True)


def fake_tool(name, args):
    time.sleep(random.uniform(0.6, 1.6))  # pretend to do real work
    return json.dumps({"ok": True, "tool": name, "args": args, "result": f"kết quả giả lập cho {name}"}, ensure_ascii=False)


def parallel(fn_, items):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(fn_, items))


# ---------- three ways of calling an LLM ----------
def run_chat_agent(system, task, tools, executor=fake_tool, stream=False):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    while True:
        kw = {"tools": tools} if tools else {}
        if stream:
            text, calls = "", {}
            for ch in oai.chat.completions.create(model=OAI_MODEL, messages=msgs, stream=True, **kw):
                d = ch.choices[0].delta if ch.choices else None
                if not d:
                    continue
                text += d.content or ""
                for tc in d.tool_calls or []:
                    c = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    c["id"] = tc.id or c["id"]
                    if tc.function and tc.function.name:
                        c["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        c["args"] += tc.function.arguments
            tool_calls = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"]}} for c in calls.values()]
        else:
            m = oai.chat.completions.create(model=OAI_MODEL, messages=msgs, **kw).choices[0].message
            text = m.content or ""
            tool_calls = [{"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}} for t in m.tool_calls or []]
        if not tool_calls:
            return text
        msgs.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})
        results = parallel(lambda tc: executor(tc["function"]["name"], json.loads(tc["function"]["arguments"] or "{}")), tool_calls)
        for tc, res in zip(tool_calls, results):
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": res})


def run_responses_agent(system, task, tools, executor=fake_tool):
    rtools = [{"type": "function", "name": t["function"]["name"], "description": t["function"]["description"], "parameters": t["function"]["parameters"]} for t in tools]
    items = [{"role": "user", "content": task}]
    while True:
        r = oai.responses.create(model=OAI_MODEL, instructions=system, input=items, tools=rtools)
        calls = [o for o in r.output if o.type == "function_call"]
        if not calls:
            return r.output_text
        for c in calls:
            items.append({"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments})
            items.append({"type": "function_call_output", "call_id": c.call_id, "output": executor(c.name, json.loads(c.arguments or "{}"))})


def run_anthropic_agent(system, task, tools, executor=fake_tool):
    msgs = [{"role": "user", "content": task}]
    while True:
        with ant.messages.stream(model=ANT_MODEL, max_tokens=1024, system=system, messages=msgs, tools=tools) as s:
            msg = s.get_final_message()
        uses = [b for b in msg.content if b.type == "tool_use"]
        if not uses:
            return "".join(b.text for b in msg.content if b.type == "text")
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in msg.content]})
        results = parallel(lambda b: executor(b.name, b.input), uses)
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": b.id, "content": r} for b, r in zip(uses, results)]})


# ---------- the team ----------
def hermes(task):
    return run_chat_agent("You are Hermes, a research agent. Find and fetch sources, then report back.", task,
                          [fn("web_search", "Search the web", {"query": {"type": "string"}}), fn("fetch_page", "Read a page", {"url": {"type": "string"}})], stream=True)


def atlas(task):
    return run_responses_agent("You are Atlas, a data analyst for the user's second brain.", task,
                               [fn("query_vault", "Run SQL on vault stats", {"sql": {"type": "string"}}), fn("make_chart", "Render a chart", {"title": {"type": "string"}})])


def codex(task):
    return run_chat_agent("You are Codex, a senior coding agent. Read code, patch it, run tests.", task,
                          [fn("read_file", "Read a file", {"path": {"type": "string"}}), fn("edit_file", "Apply a patch", {"path": {"type": "string"}, "patch": {"type": "string"}}), fn("run_tests", "Run test suite", {}, [])], stream=True)


def summarizer(note):
    return run_chat_agent("You are a note summarizer. Turn one raw note into three crisp bullet points.", note,
                          [fn("extract_keywords", "Extract keywords", {"text": {"type": "string"}})])


def scribe_tools(name, args):
    if name == "summarize_notes":
        n = int(args.get("count", 6))
        notes = [f"Ghi chú #{i + 1}: ý tưởng về {random.choice(['MCP', 'Obsidian', 'agent memory', 'RAG', 'workflow', 'GDG Hà Nội'])}" for i in range(n)]
        return json.dumps(parallel(summarizer, notes), ensure_ascii=False)
    return fake_tool(name, args)


def scribe(task):
    return run_anthropic_agent("You are Scribe, a writer who turns notes into clear weekly reports.", task,
                               [{"name": "summarize_notes", "description": "Summarize N raw notes in parallel", "input_schema": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}},
                                {"name": "save_note", "description": "Save a note to the vault", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title", "content"]}}],
                               executor=scribe_tools)


WORKERS = {"hermes": hermes, "atlas": atlas, "codex": codex, "scribe": scribe}


def mindy_tools(name, args):
    if name == "delegate":
        who, task = args["agent"], args["task"]
        say("Mindy", f"→ {who}: {task}")
        out = WORKERS[who](task)
        say(who, out)
        return out
    return fake_tool(name, args)


def mindy(goal):
    return run_chat_agent(
        "You are Mindy, the orchestrator of a second-brain agent team. Break the goal down and delegate to teammates.",
        goal,
        [fn("delegate", "Give a sub-task to a teammate", {"agent": {"type": "string", "enum": list(WORKERS)}, "task": {"type": "string"}})],
        executor=mindy_tools)


if __name__ == "__main__":
    goals = [
        "Chuẩn bị báo cáo tuần cho second brain: tài liệu mới, số liệu, sửa bug sync, tóm tắt ghi chú",
        "Tìm hiểu MCP server mới và tích hợp vào vault",
    ]
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else len(goals)
    for i in range(rounds):
        goal = goals[i % len(goals)]
        say("Sếp", goal)
        say("Mindy", mindy(goal))
        if i < rounds - 1:
            pause = float(os.environ.get("DEMO_PAUSE", "30"))
            say("demo", f"nghỉ {pause:.0f}s cho cả đội đi uống trà…")
            time.sleep(pause)
    say("demo", "xong!")
