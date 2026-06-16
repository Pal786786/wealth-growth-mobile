"""Generate app icon + adaptive icon + splash image using Gemini Nano Banana."""
import asyncio
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")

ASSETS = Path("/app/frontend/assets/images")


async def gen(prompt: str, out_name: str):
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(api_key=api_key, session_id=f"mfb-icon-{out_name}", system_message="You are a premium fintech brand designer.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])

    msg = UserMessage(text=prompt)
    text, images = await chat.send_message_multimodal_response(msg)
    print(f"[{out_name}] response text: {text[:120] if text else '(no text)'}")
    if not images:
        print(f"[{out_name}] no images returned")
        return False
    img = images[0]
    out = ASSETS / out_name
    image_bytes = base64.b64decode(img["data"])
    out.write_bytes(image_bytes)
    print(f"[{out_name}] saved {out} ({len(image_bytes)} bytes)")
    return True


async def main():
    prompts = {
        "icon.png": (
            "A premium fintech app icon, 1024x1024 pixels, square, no text, no watermark. "
            "Centered subject: an aggressive forward-charging stock-market bull head, "
            "muscular face, sharp swept-back silver-metallic horns, intense expression, "
            "GLOWING NEON RED EYES (#FF2D2D) with subtle red halo glow, "
            "black snout with a silver nose ring. "
            "Below the bull, a rising green stock-market chart line with an upward arrow. "
            "Background: smooth deep navy blue (#0F172A) to sky blue (#38BDF8) diagonal gradient with "
            "very subtle hexagonal fintech grid texture. "
            "Modern 3D vector style, sharp geometric edges, clean professional, "
            "iOS / Android app icon ready, slightly rounded square canvas, "
            "centered composition with safe margins, no text or letters anywhere."
        ),
        "adaptive-icon.png": (
            "App adaptive icon foreground, 1024x1024 pixels, transparent or solid color background acceptable. "
            "Subject only: an aggressive stock-market bull head, muscular face, sharp swept-back silver-metallic horns, "
            "GLOWING NEON RED EYES (#FF2D2D), black snout with silver nose ring, "
            "below the bull a rising green stock arrow. "
            "Subject occupies central 60% of canvas with generous transparent margin around it. "
            "Modern 3D vector style, premium fintech branding, no text."
        ),
        "splash-image.png": (
            "A premium fintech mobile splash screen image, 1284x2778 portrait, no text. "
            "Centered: an aggressive stock-market bull head with glowing neon red eyes (#FF2D2D), "
            "muscular face, sharp swept-back silver-metallic horns, intense expression, "
            "with a rising green stock-market chart line and upward arrow below. "
            "Background: rich deep navy (#0F172A) at top fading to sky blue (#38BDF8) at bottom, "
            "subtle hexagonal fintech grid texture and faint financial chart lines in the background. "
            "Centered composition with safe margins around the bull, premium 3D vector style."
        ),
        "favicon.png": (
            "A premium fintech app favicon, 256x256 pixels square, no text. "
            "Subject: an aggressive stock-market bull head with glowing neon red eyes (#FF2D2D), "
            "sharp swept-back silver-metallic horns, on deep navy to sky blue diagonal gradient background. "
            "Bold, clean, recognizable at small sizes, no text."
        ),
    }
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, p in prompts.items():
        if only and only != name:
            continue
        try:
            await gen(p, name)
        except Exception as e:
            print(f"[{name}] ERROR: {e}")


asyncio.run(main())
