import torch
import numpy as np
import fal_client
from PIL import Image
import comfy.utils
import io

t2i_model_ids = [
    "fal-ai/hidream-i1-full",
    "fal-ai/hidream-i1-dev",
    "fal-ai/hidream-i1-fast",
    # Flux
    "fal-ai/flux/dev",
]


class FalStreamingTextToImage:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "a cat holding a skateboard which has 'fal' and 'comfydeploy' written on it in red spray paint",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": "The random seed used for creating the noise.",
                    },
                ),
                "model_id": (t2i_model_ids,),
                "steps": ("INT", {"default": 50, "min": 1, "max": 100}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "stream_generation"
    CATEGORY = "fal.ai"

    def __init__(self):
        self.loop = None
        self.stream = None
        self.current_step = 0
        self.total_steps = 0
        self.final_image = None

    def stream_generation(self, prompt, seed, model_id, steps):
        self.total_steps = steps
        try:
            print("Starting streaming task")
            self.stream = fal_client.stream(
                model_id,
                arguments={
                    "prompt": prompt,
                    "num_inference_steps": steps,
                    "seed": seed,
                },
            )

            self.current_step = 0
            for event in self.stream:
                self.current_step += 1
                # print(event)

                # Process the event data
                if "images" in event:
                    # Get the raw image data
                    image_data = event["images"][0]
                    # Process the image data
                    url = image_data["url"]

                    # print(isinstance(url, str))
                    # print(isinstance(image_data, dict))
                    # print("data:image" in url)
                    if isinstance(url, str) and "data:image" in url:
                        # Handle base64 data URL
                        import base64

                        # Extract the base64 part from the data URL
                        base64_data = url.split(",")[1]
                        # Decode base64 to bytes
                        image_bytes = base64.b64decode(base64_data)
                        # Convert bytes to PIL Image
                        image = Image.open(io.BytesIO(image_bytes))
                    else:
                        # Handle direct URL
                        import requests

                        # Get the URL from the image_data dictionary
                        image_url = url
                        # Ensure URL has a protocol
                        # print(f"Fetching image from URL: {image_url}")
                        response = requests.get(image_url)
                        image = Image.open(io.BytesIO(response.content))

                    # Convert PIL Image to tensor in ComfyUI format [batch, height, width, channels]
                    image_np = np.array(image)
                    image_tensor = torch.from_numpy(image_np).float() / 255.0
                    # Add batch dimension
                    image_tensor = image_tensor.unsqueeze(0)

                    # Store the final image
                    self.final_image = image_tensor

                    # Update the progress bar with the current image
                    pbar = comfy.utils.ProgressBar(self.total_steps)
                    pbar.update_absolute(
                        self.current_step, self.total_steps, ("JPEG", image, None)
                    )

                # If we've reached the end of the stream, break
                if self.current_step >= steps:
                    break

            return (self.final_image,)

        except Exception as e:
            print(f"Error in fal.ai streaming")
            # Return a blank image if there's an error
            return torch.zeros((1, 512, 512, 3), dtype=torch.float32)
