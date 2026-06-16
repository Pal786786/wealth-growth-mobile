"""Regenerate the investment-brand app icon set (run after logo redesign)."""
import asyncio, base64, os
from pathlib import Path
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")
ASSETS = Path("/app/frontend/assets/images")


async def gen(prompt: str, out_name: str):
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(api_key=api_key, session_id=f"mfb-inv-{out_name}", system_message="You are a premium fintech brand designer.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not images:
        print(f"[{out_name}] no image")
        return
    ASSETS.joinpath(out_name).write_bytes(base64.b64decode(images[0]["data"]))
    print(f"[{out_name}] saved")


async def main():
    base = (
        "A premium investment-platform brand mark — a professional, confident, head-up bull "
        "(not aggressive, not cartoon). The bull's curved horns smoothly transform into an "
        "upward-rising stock-market chart line ending in a metallic GOLD arrowhead. "
        "Bull body in smooth sky-blue (#38BDF8) to deep-blue (#0EA5E9) gradient with "
        "subtle white highlights and clean dark-navy outlines. Horn tips capped with "
        "metallic gold (#FBBF24). A faint upward stock-chart line and a small gold coin "
        "near the bull suggest wealth and portfolio growth. Calm dark eyes — NO red, "
        "NO glowing eyes, NO blood, NO scary expression. "
        "Style: modern luxury fintech, corporate banking, scalable vector, clean and minimal. "
        "Composition is centered with safe margin. No text or letters anywhere in the artwork."
    )
    prompts = {
        "icon.png": base + " 1024x1024 pixels, square canvas with slightly rounded corners, "
                          "diagonal deep-navy (#0F172A) to sky-blue (#38BDF8) gradient background, "
                          "subtle hexagonal financial-grid texture in the background, "
                          "iOS / Android app icon ready.",
        "adaptive-icon.png": base + " 1024x1024 pixels, transparent or solid-color background, the bull "
                                    "subject occupies central 60% with generous transparent safe margin "
                                    "around it (for Android adaptive icon mask). No background scenery.",
        "splash-image.png": base + " 1284x2778 portrait splash image, the bull centered on the canvas "
                                   "with deep-navy (#0F172A) fading to sky-blue (#38BDF8) background, "
                                   "faint chart lines and hexagonal grid texture across the background.",
    }
    for name, p in prompts.items():
        try: await gen(p, name)
        except Exception as e: print(f"[{name}] ERROR: {e}")


asyncio.run(main())
