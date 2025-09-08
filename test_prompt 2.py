#!/usr/bin/env python3
"""Test the actual prompt size being sent to Ollama"""

import time
import requests
import json

# Simulate maximum prompt scenario
task = "Write a Python function to check if a number is prime"
memory_primer = "From past experience with similar tasks:\n" + "x" * 200  # Max 200 tokens
rag_context = "Related code snippets:\n" + "y" * 200  # Simulated RAG
fewshot_examples = "Example solutions:\n" + "z" * 500  # Some fewshot

# Build a prompt similar to what evolution would create
context = {
    "task": task,
    "memory_primer": memory_primer,
    "rag_context": rag_context,
    "fewshot_examples": fewshot_examples
}

# Build the actual prompt
prompt = f"""
{memory_primer}

Task: {task}

{rag_context}

{fewshot_examples}

Previous solutions:
Solution 1: def is_prime(n): return n > 1
Solution 2: def is_prime(n): return all(n % i != 0 for i in range(2, n))

Now combine these solutions to create a better one.
"""

system = "You are an AI that solves coding problems. Generate complete, working code."

print(f"Prompt length: {len(prompt)} characters")
print(f"Estimated tokens: ~{len(prompt)//4}")
print("-" * 50)

# Test with Ollama
url = "http://localhost:11434/api/generate"
payload = {
    "model": "qwen3:4b",
    "prompt": prompt,
    "system": system,
    "stream": False,
    "options": {
        "temperature": 0.7,
        "num_predict": 1024  # META_MAX_TOKENS
    }
}

print("Sending request to Ollama...")
start = time.time()
try:
    response = requests.post(url, json=payload, timeout=180)
    elapsed = time.time() - start
    print(f"Response received in {elapsed:.1f} seconds")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response length: {len(result.get('response', ''))} chars")
        print("\nFirst 200 chars of response:")
        print(result.get('response', '')[:200])
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
except requests.Timeout:
    elapsed = time.time() - start
    print(f"TIMEOUT after {elapsed:.1f} seconds!")
except Exception as e:
    elapsed = time.time() - start
    print(f"Error after {elapsed:.1f} seconds: {e}")