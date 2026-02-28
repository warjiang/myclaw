import os
from litellm import video_generation
from dotenv import load_dotenv


def main():
    load_dotenv()
    response = video_generation(
        prompt="A cat playing with a ball of yarn in a sunny garden",
        model=f"volcengine/{os.environ.get('VIDEO_GENERATION_ENDPOINT')}",
        seconds="8",
        size="720x1280"
    )
    """
    todo not passed
    """


if __name__ == '__main__':
    main()
