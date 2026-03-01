import os
from litellm import image_generation
from dotenv import load_dotenv

def main():
    load_dotenv()
    response = image_generation(prompt="A cute baby sea otter", model=f"volcengine/{os.environ.get('IMAGE_GENERATION_ENDPOINT')}")
    print(response)
    """
    ImageResponse(created=1772296910, background=None, data=[ImageObject(b64_json=None, revised_prompt=None, url='xx_image_url', provider_specific_fields=None)], output_format=None, quality=None, size=None, usage=Usage(completion_tokens=16384, prompt_tokens=0, total_tokens=16384, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetailsWrapper(audio_tokens=None, cached_tokens=None, text_tokens=0, image_tokens=0), input_tokens=0, input_tokens_details={'image_tokens': 0, 'text_tokens': 0}, output_tokens=16384, output_tokens_details=None, generated_images=1))
    """


if __name__ == '__main__':
    main()