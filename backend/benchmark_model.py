"""Quick benchmark: Can qwen2.5:7b do tool calling reliably?"""
import httpx
import json
import time

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for products in the catalog",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_price": {"type": "number", "description": "Maximum price in INR"},
                    "category": {"type": "string", "description": "Product category"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_price",
            "description": "Get the current authoritative price of a product",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product UUID"}
                },
                "required": ["product_id"]
            }
        }
    }
]

TEST_PROMPTS = [
    "Find me wireless earbuds under 3000 rupees",
    "What is the price of product P101?",
    "Search for ANC headphones in the electronics category under 5000",
    "I want to buy something. What do you have?",
    "Compare two products: P101 and P102"
]

def test_tool_calling():
    print(f"Benchmarking {MODEL} tool calling...\n")
    
    results = {"success": 0, "failed": 0, "total": len(TEST_PROMPTS)}
    
    for i, prompt in enumerate(TEST_PROMPTS, 1):
        print(f"Test {i}: '{prompt}'")
        start = time.time()
        
        try:
            response = httpx.post(OLLAMA_URL, json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You are a commerce agent. Use the provided tools to help the user. Always respond with tool calls when appropriate."},
                    {"role": "user", "content": prompt}
                ],
                "tools": TOOLS,
                "stream": False,
                "options": {"temperature": 0.1}
            }, timeout=60)
            
            data = response.json()
            elapsed = time.time() - start
            
            message = data.get("message", {})
            tool_calls = message.get("tool_calls", [])
            
            if tool_calls:
                tc = tool_calls[0]
                fn = tc.get("function", {})
                print(f"  OK Tool: {fn.get('name')} | Args: {json.dumps(fn.get('arguments', {}))} | {elapsed:.1f}s")
                results["success"] += 1
            else:
                content = message.get("content", "")[:100]
                print(f"  FAIL No tool call. Response: {content}... | {elapsed:.1f}s")
                results["failed"] += 1
                
        except Exception as e:
            print(f"  ERROR: {e}")
            results["failed"] += 1
        
        print()
    
    print("=" * 50)
    print(f"Results: {results['success']}/{results['total']} successful tool calls")
    print(f"Success rate: {results['success']/results['total']*100:.0f}%")
    
    if results["success"] >= 3:
        print("\nModel is GOOD ENOUGH. Proceed to Phase 1.")
    else:
        print("\nModel struggles. We will add retry logic in Phase 5.")

if __name__ == "__main__":
    test_tool_calling()