from dotenv import load_dotenv
from google import genai

load_dotenv()  

client = genai.Client()  # Initialize the Gemini client

print("Available models:")
for m in client.models.list():
    actions = m.supported_actions or []
    if "generateContent" in actions and "flash" in m.name:
        print(f"- {m.name} (version: {m.version})")


response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Best places to eat in Sabah?",
)

print("\nGemini replied:", response.text)