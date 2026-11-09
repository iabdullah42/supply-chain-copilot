"""The assistant: Claude plus the run_sql tool, in a loop.

Each turn, Claude either answers or asks to run a query. When it asks, we run the
query with db_tool.run_sql and send the rows back, until Claude gives a final answer.
"""
from dataclasses import dataclass, field

from src.db_tool import SCHEMA, run_sql

MODEL = "claude-sonnet-5-5"
MAX_STEPS = 8   # safety limit on tool calls per question

SYSTEM_PROMPT = f"""You are a supply chain analyst assistant for a consumer-goods company.
Answer questions using the company's procurement database through the run_sql tool.

{SCHEMA}

Analyst rules:
- Use run_sql to get the facts; never guess numbers.
- On-time means received_date <= promised_date. When measuring a period, count open POs that are
  already past their promised date as late (they are late, just not received yet), and say so.
- Report both how often deliveries are late (% late) and how bad it is (average days late when late).
- Carriers serve different suppliers and lanes, so a raw carrier ranking mostly reflects supplier mix.
  Before blaming a carrier, compare carriers within the same supplier or country lane, and say what you found.
- State your assumptions and time window. If the data cannot answer the question, say so plainly.
- Keep answers short: lead with the answer, then the key numbers; use a small table for 4 or more items."""

TOOLS = [{
    "name": "run_sql",
    "description": "Run one read-only SQLite SELECT query on the procurement database and get the rows back as CSV.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A single SQLite SELECT statement."}},
        "required": ["query"],
    },
}]


@dataclass
class Answer:
    text: str
    queries: list[str] = field(default_factory=list)   # every SQL query Claude ran, for transparency
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def ask(question: str, client, system: str = SYSTEM_PROMPT, model: str = MODEL) -> Answer:
    messages = [{"role": "user", "content": question}]
    answer = Answer(text="")

    for step in range(1, MAX_STEPS + 1):
        response = client.messages.create(model=model, max_tokens=1500, system=system,
                                          tools=TOOLS, messages=messages)
        answer.steps = step
        answer.input_tokens += response.usage.input_tokens
        answer.output_tokens += response.usage.output_tokens
        if response.stop_reason != "tool_use":
            answer.text = "".join(b.text for b in response.content if b.type == "text")
            return answer

        # Claude asked for one or more queries: run each and send back the results.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                query = block.input.get("query", "")
                answer.queries.append(query)
                output = run_sql(query)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": output, "is_error": output.startswith("ERROR")})
        messages.append({"role": "user", "content": results})

    answer.text = "Stopped: too many steps without a final answer."
    return answer