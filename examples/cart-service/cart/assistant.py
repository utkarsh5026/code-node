"""
A sentence about the order for its receipt, written by a language model.
"""

from openai import OpenAI

client = OpenAI()


def summary(items, total):
    """Ask the model for one friendly sentence about the order."""
    names = ", ".join(item["name"] for item in items)
    answer = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"One friendly sentence about an order of {names} for ${total}."}],
    )
    return answer.choices[0].message.content
