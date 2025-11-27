import os
import json
import sys
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Load Keys
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ Error: GEMINI_API_KEY not found in .env file!")
    sys.exit()

# 2. Configure Client
try:
    client = genai.Client(api_key=api_key)
    print("✅ Client initialized.")
except Exception as e:
    print(f"❌ Error initializing client: {e}")
    sys.exit()

def extract_json(text):
    """Helper to find JSON block inside narrative text"""
    try:
        # Look for markdown code block
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            return json.loads(match.group(1))
        
        # Fallback: Look for just { ... } or [ ... ]
        match = re.search(r"(\[[\s\S]*\])", text)
        if match:
            return json.loads(match.group(1))
            
        return None
    except Exception:
        return None

def scan_market():
    print("🧠 Gemini 2.5 Lite is hunting for Moonshots (Safety Filters: OFF)...")
    
    # 3. Search Tool
    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    # 4. PROMPT (Now includes 'type' requirement)
    prompt = """
    Act as an Aggressive Venture Capitalist hunting for 'Asymmetrical Upside' (10x-100x potential).
    
    TASK 1: STOCKS
    - Find 5 breaking narratives in disruptive tech (Bio-tech, Quantum, Space, Robotics, etc.).
    - IDENTIFY: A "Pure-Play" stock for each.
    - CONSTRAINT: IGNORE 'Magnificent 7' (No NVDA, TSLA, MSFT, AAPL, GOOG). 
    - TARGET: Look for Small-to-Mid Cap companies ($500M - $20B) that are leading a niche.

    TASK 2: CRYPTO
    - Find 5 breaking narratives for the NEXT cycle (e.g., AI Agents, RWA, DePIN, Sci-Fi).
    - IDENTIFY: A "High-Beta" token for each. Find for next potential or current leaders in the breaking narratives
    - CONSTRAINT: IGNORE Top 10 coins (No BTC, ETH, SOL, XRP, ADA, DOGE).
    - TARGET: Look for tokens outside the top 10 that define a new meta.
    
    Format your final output exactly like this:
    
    Analysis: [Short Summary]
    
    ```json
    [
      {"ticker": "IONQ", "type": "Stock", "narrative": "Pure-play quantum hardware leader"},
      {"ticker": "FET", "type": "Crypto", "narrative": "Leading AI Agent alliance"}
    ]
    ```
    """
    
    try:
        # 5. Generate with Safety Settings OFF
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[grounding_tool],
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE"
                    ),
                ]
            )
        )
        
        # 6. DEBUGGING BLACK BOX
        if not response.text:
            print("\n⚠️ DEBUG: Response text is empty.")
            
            if response.candidates:
                candidate = response.candidates[0]
                print(f"🛑 Finish Reason: {candidate.finish_reason}")
                
                # Check safety ratings to see if one triggered
                if candidate.safety_ratings:
                    print("\n🛡️ Safety Ratings:")
                    for rating in candidate.safety_ratings:
                        print(f"   - {rating.category}: {rating.probability}")
                        
            return "❌ AI returned empty text."

        # Extract the JSON using our helper
        data = extract_json(response.text)
        
        if not data:
            print(f"⚠️ Could not find JSON in response:\n{response.text[:200]}...")
            return []
            
        return data
        
    except Exception as e:
        return f"❌ AI Error: {e}"

# Test Run
if __name__ == "__main__":
    result = scan_market()
    print("\n--- MOONSHOT SCOUT REPORT ---")
    if isinstance(result, list):
        print(json.dumps(result, indent=2))
    else:
        print(result)
    print("-----------------------------")