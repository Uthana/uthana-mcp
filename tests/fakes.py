import io

from PIL import Image


def native(motion_id="motion1", count=120, fps=30):
    return {
        "motion_id": motion_id,
        "bundle_id": "bundle_" + motion_id,
        "bundle_sha256": "a" * 64,
        "duration_seconds": count / fps,
        "last_sample_seconds": (count - 1) / fps,
        "fps": fps,
        "frame_count": count,
        "name": motion_id,
    }


def apng():
    output = io.BytesIO()
    frames = [Image.new("RGBA", (16, 16), color) for color in ("red", "blue", "green")]
    frames[0].save(output, format="PNG", save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)
    return output.getvalue()


class FakeAPI:
    scope = "offline_test_identity"

    def __init__(self):
        self.calls = []
        self.motions = {"motion1": native(), "motion2": native("motion2")}
        self.fail_verification = False

    async def close(self):
        pass

    async def generate(self, **args):
        self.calls.append(("generate", args))
        return {"job_id": "job1", "character_id": args["character_id"]}

    async def job(self, job_id):
        return {"job_id": job_id, "motion_id": "motion1", "provider_status": "FINISHED", "state": "complete"}

    async def motion(self, motion_id):
        if self.fail_verification and motion_id != "motion1":
            raise RuntimeError("Unavailable")
        return dict(self.motions[motion_id])

    async def trim(self, motion_id, start, end, name):
        self.calls.append(("trim", {"motion_id": motion_id, "start": start, "end": end, "name": name}))
        source = self.motions[motion_id]
        count = min(int(end * source["frame_count"]) + 1, source["frame_count"]) - int(start * source["frame_count"])
        self.motions["trimmed1"] = native("trimmed1", count, source["fps"])
        return {"motion_id": "trimmed1"}

    async def preview(self, motion_id, character_id, format):
        self.calls.append(("preview", (motion_id, character_id, format)))
        return apng()

    async def download(self, **args):
        self.calls.append(("download", args))
        return b"offline-export-fixture"

    async def character_metadata(self, character_id):
        return {"engine": "roblox" if character_id == "roblox1" else "generic"}

    async def characters(self):
        return [{"id": "mixamo1", "name": "First"}, {"id": "mixamo2", "name": "Second"}]

    async def upload_character(
        self, filename, content, name, auto_rig, front_facing=True, include_fingers=True, rerig_target=None
    ):
        self.calls.append(
            (
                "upload_character",
                {
                    "filename": filename,
                    "content": content,
                    "auto_rig": auto_rig,
                    "front_facing": front_facing,
                    "include_fingers": include_fingers,
                    "rerig_target": rerig_target,
                },
            )
        )
        count = sum(call[0] == "upload_character" for call in self.calls)
        return {"character_id": f"mixamo{count}"}

    async def prepare_character_image(self, filename, content):
        self.calls.append(("prepare_image", {"filename": filename, "content": content}))
        return {"stage": "image_prepared", "character_id": "imagechar1", "image_key": "imagechar1-front.png"}

    async def finalize_character_image(self, prepared, name, include_fingers=True):
        self.calls.append(("finalize_image", {"prepared": prepared, "name": name, "include_fingers": include_fingers}))
        return {"character_id": prepared["character_id"], "auto_rig_confidence": 0.9}

    async def preview_character_prompt(self, prompt):
        self.calls.append(("preview_prompt", {"prompt": prompt}))
        return {
            "character_id": "promptchar1",
            "previews": [
                {"image_key": "promptchar1-0.png", "url": "https://storage.example/0.png"},
                {"image_key": "promptchar1-1.png", "url": "https://storage.example/1.png"},
            ],
        }

    async def fetch_preview_image(self, url, max_bytes=16 * 1024 * 1024):
        self.calls.append(("fetch_preview", {"url": url}))
        output = io.BytesIO()
        Image.new("RGB", (64, 96), "orange").save(output, format="PNG")
        return output.getvalue()

    async def finalize_character_prompt(self, character_id, prompt, image_key, name):
        self.calls.append(
            ("finalize_prompt", {"character_id": character_id, "prompt": prompt, "image_key": image_key, "name": name})
        )
        return {"character_id": character_id, "auto_rig_confidence": 1.0}

    async def stitch(self, character_id, prefix, suffix):
        self.calls.append(("stitch", {"character_id": character_id, "prefix": prefix, "suffix": suffix}))
        self.motions["stitched1"] = native("stitched1", count=300)
        return {"motion_id": "stitched1", "character_id": character_id}

    async def loop(self, **args):
        self.calls.append(("loop", args))
        self.motions["looped1"] = native("looped1")
        return {"motion_id": "looped1", "character_id": args["character_id"]}

    async def video(self, filename, content, name, model):
        self.calls.append(("video", {"filename": filename, "content": content, "name": name, "model": model}))
        return {"job_id": "videojob1"}

    async def save(self, gltf, name, source_motion_id, character_id):
        self.calls.append(("save", {"gltf": gltf, "source": source_motion_id, "character": character_id}))
        self.motions["saved1"] = native("saved1")
        return {"motion_id": "saved1"}

    async def motion_catalog(self):
        self.calls.append(("motion_catalog", {}))
        return {
            "org": {"id": "org1"},
            "motions": [
                {"id": "motion1", "org_id": "org1", "name": "Walking slowly", "tags": {"Method": "TextToMotion"}},
                {"id": "example1", "org_id": "shared", "name": "Walking example", "tags": {"Method": "Mocap"}},
            ],
        }

    async def usage(self):
        self.calls.append(("usage", {}))
        return {
            "org": {
                "payg_enabled": False,
                "payg_total_usd": None,
                "payg_auto_recharge_enabled": False,
                "motion_download_secs_per_month": 60,
                "motion_download_secs_per_month_remaining": 15,
                "characters_allowed": 2,
                "characters_allowed_remaining": 1,
            },
            "subscription": None,
            "payg_prices": [],
        }

    async def download_allowed(self, motion_id, character_id):
        self.calls.append(("download_allowed", {"motion_id": motion_id, "character_id": character_id}))
        return {"allowed": motion_id != "denied", "reason": "Offline fixture eligibility"}

    async def generate_v2(self, **args):
        self.calls.append(("generate_v2", args))
        return {"motion_id": "motion1", "character_id": args["character_id"]}

    async def locomotion_styles(self):
        return ["neutral_male_a", "neutral_female_a"]

    async def locomotion(self, **args):
        self.calls.append(("locomotion", args))
        return {"motion_id": "motion1", "character_id": args["character_id"]}

    async def prices(self):
        return [
            {"model_key": "text-to-motion-bucmd", "billing_unit": "second", "unit_price": "0.03"},
            {"model_key": "text-to-motion-3.0", "billing_unit": "second", "unit_price": "0.10"},
            {"model_key": "locomotion", "billing_unit": "second", "unit_price": "0.02"},
            {"model_key": "autorig", "billing_unit": "rig", "unit_price": "0.15"},
        ]
